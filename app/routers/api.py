import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from app.dependencies import DatabaseSessionDependency, SettingsDependency
from app.services.google_sheets_sync_service import GoogleSheetsSyncService
from app.services.google_sheets_memory_sync_service import GoogleSheetsMemorySyncService
from app.services.memory_store import get_memory_store
from app.services.nas_drawing_service import (
    NasDrawingAccessError,
    NasDrawingPreviewError,
    NasDrawingPreviewService,
    NasDrawingService,
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


@router.get("/drawings/{machine_id}/preview", response_class=Response)
def preview_drawing(machine_id: str, settings: SettingsDependency) -> Response:
    """Render the current machine's NAS drawing as an in-app image preview."""

    dashboard = get_memory_store().get_dashboard()
    machine = next((item for item in dashboard.machines if item.machine_id == machine_id), None)
    if machine is None or not machine.part_number:
        raise HTTPException(status_code=404, detail="Drawing not found")
    try:
        drawing_path = NasDrawingService(settings.nas_drawing_directory).find_pdf(
            machine.part_number
        )
    except NasDrawingAccessError as exc:
        raise HTTPException(status_code=503, detail="Drawing storage is unavailable") from exc
    if drawing_path is None:
        raise HTTPException(status_code=404, detail="Drawing not found")
    try:
        content = preview_service.render_first_page(drawing_path)
    except NasDrawingAccessError as exc:
        raise HTTPException(status_code=503, detail="Drawing storage is unavailable") from exc
    except NasDrawingPreviewError as exc:
        raise HTTPException(status_code=422, detail="Drawing preview could not be rendered") from exc
    return Response(
        content=content,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=300"},
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
