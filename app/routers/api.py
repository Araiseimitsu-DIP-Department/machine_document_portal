import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from app.config import Settings
from app.dependencies import DatabaseSessionDependency, SettingsDependency
from app.services.google_sheets_memory_sync_service import GoogleSheetsMemorySyncService
from app.services.google_sheets_sync_service import GoogleSheetsSyncService
from app.services.memory_store import get_memory_store
from app.services.nas_drawing_service import (
    NasDrawingAccessError,
    NasDrawingPreviewError,
    NasDrawingPreviewService,
    NasDrawingService,
)
from app.services.scheduled_job_state_store import (
    ScheduledJobStateError,
    ScheduledJobStateStore,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["operation"])
preview_service = NasDrawingPreviewService()


class RefreshResponse(BaseModel):
    ok: bool
    refreshed_at: datetime
    message: str
    processed_count: int | None = None
    success_count: int | None = None
    error_count: int | None = None


class PrintAttentionResponse(BaseModel):
    required: bool
    count: int = 0


def _current_drawing_path(machine_id: str, settings: Settings) -> Path:
    dashboard = get_memory_store().get_dashboard()
    machine = next(
        (item for item in dashboard.machines if item.machine_id == machine_id), None
    )
    if machine is None or not machine.part_number:
        raise HTTPException(status_code=404, detail="Drawing not found")
    try:
        drawing_path = NasDrawingService(settings.nas_drawing_directory).find_pdf(
            machine.part_number
        )
    except NasDrawingAccessError as exc:
        raise HTTPException(
            status_code=503, detail="Drawing storage is unavailable"
        ) from exc
    if drawing_path is None:
        raise HTTPException(status_code=404, detail="Drawing not found")
    return drawing_path


class DashboardRevisionResponse(BaseModel):
    updated_at: datetime | None = None


@router.get("/dashboard/revision", response_model=DashboardRevisionResponse)
def dashboard_revision() -> DashboardRevisionResponse:
    """Return the completed dashboard revision observed by browser clients."""

    return DashboardRevisionResponse(
        updated_at=get_memory_store().get_last_updated_at(),
    )


@router.get("/printing/attention", response_model=PrintAttentionResponse)
def printing_attention(settings: SettingsDependency) -> PrintAttentionResponse:
    try:
        state = ScheduledJobStateStore(
            settings.scheduled_job_state_path,
            spreadsheet_id=settings.google_spreadsheet_id,
        ).latest_print_state(attention_only=True)
    except ScheduledJobStateError:
        logger.error(
            "Print attention API is disabled because scheduled state is unavailable"
        )
        state = None
    return PrintAttentionResponse(
        required=state is not None,
        count=state.attention_count if state is not None else 0,
    )


@router.get("/drawings/{machine_id}/preview", response_class=Response)
def preview_drawing(machine_id: str, settings: SettingsDependency) -> Response:
    """Render the current machine's drawing as a PDF.js fallback JPEG."""

    drawing_path = _current_drawing_path(machine_id, settings)
    logger.warning("Drawing JPEG fallback requested: machine_id=%s", machine_id)
    try:
        content = preview_service.render_first_page(drawing_path)
    except NasDrawingAccessError as exc:
        raise HTTPException(
            status_code=503, detail="Drawing storage is unavailable"
        ) from exc
    except NasDrawingPreviewError as exc:
        raise HTTPException(
            status_code=422, detail="Drawing preview could not be rendered"
        ) from exc
    return Response(
        content=content,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=300"},
    )


@router.get("/drawings/{machine_id}/pdf", response_class=FileResponse)
def drawing_pdf(machine_id: str, settings: SettingsDependency) -> FileResponse:
    """Stream the current machine's PDF without exposing its NAS path."""

    drawing_path = _current_drawing_path(machine_id, settings)
    try:
        stat_result = drawing_path.stat()
    except OSError as exc:
        raise HTTPException(
            status_code=503, detail="Drawing storage is unavailable"
        ) from exc
    return FileResponse(
        path=drawing_path,
        stat_result=stat_result,
        media_type="application/pdf",
        filename=drawing_path.name,
        content_disposition_type="inline",
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.post("/refresh", response_model=RefreshResponse)
def refresh_dashboard(
    settings: SettingsDependency, session: DatabaseSessionDependency
) -> RefreshResponse:
    """Refresh sample data or synchronize the configured production spreadsheet."""

    refreshed_at = datetime.now(timezone.utc)
    logger.info(
        "Manual refresh requested: persistence_mode=%s sample_mode=%s",
        settings.persistence_mode,
        settings.use_sample_data,
    )
    if settings.persistence_mode == "memory" and settings.use_sample_data:
        get_memory_store().reload_sample()
        return RefreshResponse(
            ok=True,
            refreshed_at=refreshed_at,
            message="サンプルデータを再読み込みしました。",
        )
    if settings.persistence_mode == "memory":
        result = GoogleSheetsMemorySyncService(settings, get_memory_store()).sync()
        return RefreshResponse(
            ok=result.ok,
            refreshed_at=refreshed_at,
            message=result.message,
            processed_count=result.processed_count,
            success_count=result.success_count,
            error_count=result.error_count,
        )
    if settings.use_sample_data:
        get_memory_store().reload_sample()
        return RefreshResponse(
            ok=True,
            refreshed_at=refreshed_at,
            message="サンプルデータを再読み込みしました。",
        )
    if session is None:
        return RefreshResponse(
            ok=False,
            refreshed_at=refreshed_at,
            message="本番データベースに接続できません。DATABASE_URL を確認してください。",
        )

    result = GoogleSheetsSyncService(settings).sync(session)
    return RefreshResponse(
        ok=result.ok,
        refreshed_at=refreshed_at,
        message=result.message,
        processed_count=result.processed_count,
        success_count=result.success_count,
        error_count=result.error_count,
    )
