import logging
from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel

from app.dependencies import DatabaseSessionDependency, SettingsDependency
from app.services.google_sheets_sync_service import GoogleSheetsSyncService
from app.services.google_sheets_memory_sync_service import GoogleSheetsMemorySyncService
from app.services.memory_store import get_memory_store


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["operation"])


class RefreshResponse(BaseModel):
    ok: bool
    refreshed_at: datetime
    message: str
    processed_count: int | None = None
    success_count: int | None = None
    error_count: int | None = None


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
