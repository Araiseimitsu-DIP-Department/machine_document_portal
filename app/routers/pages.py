from collections import OrderedDict
from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import PROJECT_ROOT
from app.dependencies import DatabaseSessionDependency, SettingsDependency
from app.schemas.dashboard import MachineCard
from app.services.memory_store import get_memory_store
from app.services.production_service import ProductionService
from app.utils.time_zone import format_jst


router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=PROJECT_ROOT / "app" / "templates")
templates.env.filters["format_jst"] = format_jst


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
            "auto_refresh_seconds": settings.auto_refresh_seconds,
            "sharepoint_process_inspection_url": settings.sharepoint_process_inspection_url,
            "sharepoint_shipping_inspection_url": settings.sharepoint_shipping_inspection_url,
            "notion_measurement_equipment_inspection_url": settings.notion_measurement_equipment_inspection_url,
            "current_year": datetime.now().year,
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
            "auto_refresh_seconds": settings.auto_refresh_seconds,
            "sharepoint_process_inspection_url": settings.sharepoint_process_inspection_url,
            "sharepoint_shipping_inspection_url": settings.sharepoint_shipping_inspection_url,
            "notion_measurement_equipment_inspection_url": settings.notion_measurement_equipment_inspection_url,
            "current_year": datetime.now().year,
        },
    )


@router.get("/drawings/{machine_id}", response_class=HTMLResponse)
def drawing_viewer(
    machine_id: str,
    request: Request,
    settings: SettingsDependency,
    session: DatabaseSessionDependency,
) -> HTMLResponse:
    """Show a NAS drawing in its own browser tab without opening the PDF viewer."""

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
            "preview_url": f"/api/drawings/{quote(machine.machine_id, safe='')}/preview",
        },
    )
