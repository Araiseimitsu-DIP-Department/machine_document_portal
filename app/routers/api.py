import logging
from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel

from app.dependencies import SettingsDependency
from app.services.memory_store import get_memory_store


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["operation"])


class RefreshResponse(BaseModel):
    ok: bool
    refreshed_at: datetime
    message: str


@router.post("/refresh", response_model=RefreshResponse)
def refresh_dashboard(settings: SettingsDependency) -> RefreshResponse:
    """Manual refresh endpoint; external synchronization starts in Stage 2."""

    refreshed_at = datetime.now(timezone.utc)
    if settings.persistence_mode == "memory" and settings.use_sample_data:
        get_memory_store().reload_sample()
        message = "サンプルデータを再読み込みしました。"
    elif settings.persistence_mode == "memory":
        message = "現在のメモリデータを再表示します。外部サービス連携は未実装です。"
    elif settings.use_sample_data:
        message = "サンプルデータを再読み込みしました。"
    else:
        message = "現在の保存データを再読み込みします。"
    logger.info(
        "Manual refresh requested: persistence_mode=%s sample_mode=%s",
        settings.persistence_mode,
        settings.use_sample_data,
    )
    return RefreshResponse(ok=True, refreshed_at=refreshed_at, message=message)
