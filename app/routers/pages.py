import logging
import time
from collections import OrderedDict
from datetime import datetime
from threading import Lock
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import PROJECT_ROOT, Settings
from app.dependencies import DatabaseSessionDependency, SettingsDependency
from app.pwa import (
    PWA_NAME,
    PWA_THEME_COLOR,
    STATIC_ASSETS_VERSION,
    STATIC_ICONS_VERSION,
)
from app.schemas.dashboard import MachineCard
from app.services.document_search import DocumentCandidateResult
from app.services.memory_store import get_memory_store
from app.services.production_service import ProductionService
from app.services.scheduled_job_state_store import (
    ScheduledJobStateError,
    ScheduledJobStateStore,
)
from app.services.scheduled_operations_service import ScheduledOperationsService
from app.services.sharepoint_service import (
    SharePointError,
    SharePointNumericInspectionService,
    SharePointService,
)
from app.utils.time_zone import format_jst

router = APIRouter(include_in_schema=False)
logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory=PROJECT_ROOT / "app" / "templates")
templates.env.filters["format_jst"] = format_jst
templates.env.globals["static_icons_version"] = STATIC_ICONS_VERSION
templates.env.globals["static_assets_version"] = STATIC_ASSETS_VERSION
templates.env.globals["pwa_theme_color"] = PWA_THEME_COLOR
templates.env.globals["pwa_name"] = PWA_NAME
_external_file_cache: dict[tuple[str, str, str, str], tuple[float, tuple[DocumentCandidateResult, ...]]] = {}
_external_file_cache_lock = Lock()
_EXTERNAL_FILE_PAGE_SIZE = 50


def _external_excel_files(
    settings: Settings, category: str, *, refresh: bool = False
) -> tuple[DocumentCandidateResult, ...]:
    if category == "process":
        service = SharePointService(settings)
    elif category == "shipping":
        service = SharePointNumericInspectionService(settings)
    else:
        raise HTTPException(status_code=404, detail="Unknown document category")
    key = (
        category,
        service.location.drive_id or "",
        service.location.folder_id or "",
        service.location.folder_url or "",
    )
    now = time.monotonic()
    with _external_file_cache_lock:
        if refresh:
            _external_file_cache.pop(key, None)
        cached = _external_file_cache.get(key)
        if cached and cached[0] > now:
            return cached[1]
    files = service.list_excel_files(refresh=refresh)
    with _external_file_cache_lock:
        _external_file_cache[key] = (time.monotonic() + 300, files)
    return files


STATUS_LABELS = {
    "found": "利用できます",
    "not_found": "見つかりません",
    "multiple": "候補が複数あります",
    "auth_error": "最新情報を取得できません",
    "permission_error": "アクセス権を確認してください",
    "api_error": "最新情報を取得できません",
    "not_checked": "未確認",
}


def group_machines(machines: list[MachineCard]) -> list[tuple[str, list[MachineCard]]]:
    groups: OrderedDict[str, list[MachineCard]] = OrderedDict()
    for machine in machines:
        groups.setdefault(machine.group_name, []).append(machine)
    return list(groups.items())


def build_overview_lanes(
    machine_groups: list[tuple[str, list[MachineCard]]], max_lanes: int = 5
) -> list[list[tuple[str, list[MachineCard]]]]:
    """Pack the smallest adjacent groups together without changing display order."""

    lanes = [[group] for group in machine_groups]
    while len(lanes) > max_lanes:
        pair_index = min(
            range(len(lanes) - 1),
            key=lambda index: sum(len(group[1]) for group in lanes[index])
            + sum(len(group[1]) for group in lanes[index + 1]),
        )
        lanes[pair_index : pair_index + 2] = [
            lanes[pair_index] + lanes[pair_index + 1]
        ]
    return lanes


def _print_state_store(settings) -> ScheduledJobStateStore:
    return ScheduledJobStateStore(
        settings.scheduled_job_state_path,
        spreadsheet_id=settings.google_spreadsheet_id,
    )


def _shared_page_context(settings, *, active_page: str) -> dict[str, object]:
    try:
        print_attention = _print_state_store(settings).latest_print_state(
            attention_only=True
        )
    except ScheduledJobStateError:
        logger.error(
            "Print attention is hidden because scheduled state is unavailable"
        )
        print_attention = None
    dashboard_updated_at = get_memory_store().get_last_updated_at()
    return {
        "active_page": active_page,
        "app_env": settings.app_env,
        "print_attention": print_attention,
        "dashboard_revision": (
            dashboard_updated_at.isoformat() if dashboard_updated_at else ""
        ),
        "dashboard_revision_poll_seconds": settings.dashboard_revision_poll_seconds,
        "sharepoint_process_inspection_url": settings.sharepoint_process_inspection_url,
        "sharepoint_shipping_inspection_url": settings.sharepoint_shipping_inspection_url,
        "notion_measurement_equipment_inspection_url": settings.notion_measurement_equipment_inspection_url,
        "current_year": datetime.now().year,
    }


@router.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    settings: SettingsDependency,
    session: DatabaseSessionDependency,
) -> HTMLResponse:
    dashboard_data = ProductionService(settings, get_memory_store()).get_dashboard(session)
    machine_groups = group_machines(dashboard_data.machines)
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "app_name": settings.app_name,
            "dashboard": dashboard_data,
            "machine_groups": machine_groups,
            "overview_lanes": build_overview_lanes(machine_groups),
            "status_labels": STATUS_LABELS,
            "sample_mode": settings.use_sample_data,
            **_shared_page_context(settings, active_page="dashboard"),
        },
    )


@router.get("/external-files/{category}", response_class=HTMLResponse)
def external_excel_files(
    category: str,
    request: Request,
    settings: SettingsDependency,
    search: str = Query(default="", max_length=100),
    folder: str = Query(default="", max_length=1024),
    page: int = Query(default=1, ge=1),
    refresh: bool = False,
) -> HTMLResponse:
    """Show a searchable SharePoint workbook list for tablet users."""

    if category not in {"process", "shipping"}:
        raise HTTPException(status_code=404, detail="Unknown document category")
    title = "工程内検査シート" if category == "process" else "出荷検査表"
    try:
        all_files = _external_excel_files(settings, category, refresh=refresh)
    except SharePointError:
        logger.exception("Could not list %s Excel files", category)
        raise HTTPException(status_code=503, detail="SharePoint files are unavailable")
    folder_paths: set[str] = set()
    for file in all_files:
        parts = (file.location or "").split("/")
        folder_paths.update("/".join(parts[:index]) for index in range(1, len(parts) + 1) if parts[index - 1])
    if folder and folder not in folder_paths:
        raise HTTPException(status_code=404, detail="Unknown document folder")
    prefix = f"{folder}/" if folder else ""
    child_folders = sorted(
        {
            prefix + location[len(prefix) :].split("/", 1)[0]
            for file in all_files
            if (location := file.location or "")
            and location.startswith(prefix)
            and location != folder
        },
        key=str.casefold,
    )
    breadcrumbs = [("", title)]
    if folder:
        accumulated = ""
        for segment in folder.split("/"):
            accumulated = f"{accumulated}/{segment}" if accumulated else segment
            breadcrumbs.append((accumulated, segment))
    needle = search.strip().casefold()
    files = tuple(
        file
        for file in all_files
        if (not folder or (file.location or "") == folder or (file.location or "").startswith(prefix))
        and (
            (needle and (needle in file.name.casefold() or needle in (file.location or "").casefold()))
            or (not needle and (file.location or "") == folder)
        )
    )
    total_pages = max(1, (len(files) + _EXTERNAL_FILE_PAGE_SIZE - 1) // _EXTERNAL_FILE_PAGE_SIZE)
    page = min(page, total_pages)
    start = (page - 1) * _EXTERNAL_FILE_PAGE_SIZE
    return templates.TemplateResponse(
        request=request,
        name="external_files.html",
        context={
            "app_name": settings.app_name,
            "document_title": title,
            "category": category,
            "folder": folder,
            "child_folders": tuple((path.rsplit("/", 1)[-1], path) for path in child_folders),
            "breadcrumbs": breadcrumbs,
            "files": files[start : start + _EXTERNAL_FILE_PAGE_SIZE],
            "all_file_count": len(all_files),
            "total_files": len(files),
            "search": search,
            "page": page,
            "total_pages": total_pages,
            **_shared_page_context(settings, active_page="dashboard"),
        },
    )


@router.get("/inspections/{machine_id}", response_class=HTMLResponse)
def inspection_files(
    machine_id: str,
    request: Request,
    settings: SettingsDependency,
    session: DatabaseSessionDependency,
) -> HTMLResponse:
    """List every related SharePoint inspection sheet for one machine."""

    dashboard_data = ProductionService(settings, get_memory_store()).get_dashboard(session)
    machine = next(
        (item for item in dashboard_data.machines if item.machine_id == machine_id), None
    )
    if (
        machine is None
        or not machine.part_number
        or not machine.inspection.available
        or len(machine.inspection.candidates) < 2
    ):
        raise HTTPException(status_code=404, detail="Inspection sheets not found")
    return templates.TemplateResponse(
        request=request,
        name="inspection_files.html",
        context={
            "app_name": settings.app_name,
            "dashboard": dashboard_data,
            "machine": machine,
            "document_title": "工程内検査シート",
            "document": machine.inspection,
            **_shared_page_context(settings, active_page="dashboard"),
        },
    )


@router.get("/numeric-inspections/{machine_id}", response_class=HTMLResponse)
def numeric_inspection_files(
    machine_id: str,
    request: Request,
    settings: SettingsDependency,
    session: DatabaseSessionDependency,
) -> HTMLResponse:
    """List every numeric-inspection file related to one machine."""

    dashboard_data = ProductionService(settings, get_memory_store()).get_dashboard(session)
    machine = next(
        (item for item in dashboard_data.machines if item.machine_id == machine_id), None
    )
    if (
        machine is None
        or not machine.part_number
        or not machine.numeric_inspection.available
        or len(machine.numeric_inspection.candidates) < 2
    ):
        raise HTTPException(status_code=404, detail="Numeric inspection files not found")
    return templates.TemplateResponse(
        request=request,
        name="inspection_files.html",
        context={
            "app_name": settings.app_name,
            "dashboard": dashboard_data,
            "machine": machine,
            "document_title": "数値検査用",
            "document": machine.numeric_inspection,
            **_shared_page_context(settings, active_page="dashboard"),
        },
    )


@router.get("/drawings/{machine_id}", response_class=HTMLResponse)
def drawing_viewer(
    machine_id: str,
    request: Request,
    settings: SettingsDependency,
    session: DatabaseSessionDependency,
) -> HTMLResponse:
    """Show a NAS drawing in its own browser tab with the in-app PDF.js viewer."""

    dashboard_data = ProductionService(settings, get_memory_store()).get_dashboard(session)
    machine = next(
        (item for item in dashboard_data.machines if item.machine_id == machine_id), None
    )
    if machine is None or not machine.part_number or not machine.drawing.available:
        raise HTTPException(status_code=404, detail="Drawing not found")
    return templates.TemplateResponse(
        request=request,
        name="drawing_viewer.html",
        context={
            "app_name": settings.app_name,
            "machine": machine,
            "pdf_url": f"/api/drawings/{quote(machine.machine_id, safe='')}/pdf",
            "preview_url": f"/api/drawings/{quote(machine.machine_id, safe='')}/preview",
            "debug": settings.debug,
        },
    )


@router.get("/printing", response_class=HTMLResponse)
def printing_recovery(
    request: Request,
    settings: SettingsDependency,
) -> HTMLResponse:
    """Show only the user actions needed to finish the scheduled printing."""

    store = _print_state_store(settings)
    try:
        print_state = (
            store.latest_print_state(attention_only=True)
            or store.latest_print_state()
        )
    except ScheduledJobStateError as exc:
        raise HTTPException(
            status_code=503,
            detail="印刷情報を安全に確認できないため、操作を停止しました。",
        ) from exc
    return templates.TemplateResponse(
        request=request,
        name="printing_recovery.html",
        context={
            "app_name": settings.app_name,
            "print_state": print_state,
            "printer_display_name": settings.drawing_printer_display_name,
            **_shared_page_context(settings, active_page="printing"),
        },
    )


@router.post("/printing/{target_key}/retry", response_class=RedirectResponse)
def retry_scheduled_printing(
    target_key: str,
    request: Request,
    settings: SettingsDependency,
) -> RedirectResponse:
    requested_by = request.client.host if request.client else "unknown"
    try:
        ScheduledOperationsService(settings).retry_printing(
            target_key,
            requested_by=f"user:{requested_by}",
        )
    except ScheduledJobStateError as exc:
        raise HTTPException(
            status_code=503,
            detail="印刷情報を安全に確認できないため、操作を停止しました。",
        ) from exc
    return RedirectResponse(url="/printing?updated=1", status_code=303)


@router.post("/printing/{target_key}/confirm-printed", response_class=RedirectResponse)
def confirm_scheduled_printing(
    target_key: str,
    part_number: str,
    settings: SettingsDependency,
) -> RedirectResponse:
    try:
        _print_state_store(settings).confirm_part_printed(target_key, part_number)
    except ScheduledJobStateError as exc:
        raise HTTPException(
            status_code=503,
            detail="印刷情報を安全に確認できないため、操作を停止しました。",
        ) from exc
    return RedirectResponse(url="/printing?updated=1", status_code=303)


@router.post("/printing/{target_key}/retry-part", response_class=RedirectResponse)
def retry_scheduled_printing_part(
    target_key: str,
    part_number: str,
    request: Request,
    settings: SettingsDependency,
) -> RedirectResponse:
    requested_by = request.client.host if request.client else "unknown"
    try:
        ScheduledOperationsService(settings).retry_printing(
            target_key,
            part_number=part_number,
            requested_by=f"user:{requested_by}",
        )
    except ScheduledJobStateError as exc:
        raise HTTPException(
            status_code=503,
            detail="印刷情報を安全に確認できないため、操作を停止しました。",
        ) from exc
    return RedirectResponse(url="/printing?updated=1", status_code=303)
