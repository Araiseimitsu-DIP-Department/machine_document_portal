import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from app.config import Settings
from app.schemas.dashboard import MachineCard
from app.services.memory_store import MemoryDashboardStore
from app.services.spreadsheet_service import (
    GoogleSheetsService,
    SpreadsheetError,
    SpreadsheetGateway,
)
from app.utils.part_number import normalize_part_number
from app.utils.machine_sort import parse_machine_id, sort_machines


logger = logging.getLogger(__name__)


_GROUP_COLORS = {
    "A": "#1e88e5",
    "B": "#008c9e",
    "C": "#6473d9",
    "D": "#8b63c7",
    "E": "#d17b25",
    "F": "#3b8d69",
}
_FALLBACK_GROUP_COLOR = "#607d8b"


@dataclass(frozen=True, slots=True)
class MemorySpreadsheetSyncResult:
    ok: bool
    processed_count: int
    success_count: int
    error_count: int
    message: str


class GoogleSheetsMemorySyncService:
    """Refresh the in-process dashboard from Google Sheets without a database."""

    def __init__(
        self,
        settings: Settings,
        memory_store: MemoryDashboardStore,
        *,
        gateway: SpreadsheetGateway | None = None,
    ) -> None:
        self.memory_store = memory_store
        self.gateway = gateway or GoogleSheetsService(settings)

    def sync(self) -> MemorySpreadsheetSyncResult:
        try:
            records = self.gateway.fetch_current_productions()
        except SpreadsheetError:
            logger.exception("Google Sheets synchronization could not read the spreadsheet")
            message = "Google Sheets を読み込めませんでした。設定と共有権限を確認してください。"
            self.memory_store.set_notice(message)
            return MemorySpreadsheetSyncResult(
                ok=False,
                processed_count=0,
                success_count=0,
                error_count=1,
                message=message,
            )

        synced_at = datetime.now(timezone.utc)
        cards: list[MachineCard] = []
        for display_order, record in enumerate(records, start=1):
            group_name, machine_number = parse_machine_id(record.machine_id)
            cards.append(
                MachineCard(
                    machine_id=record.machine_id,
                    group_name=group_name,
                    machine_number=machine_number,
                    display_order=display_order,
                    group_color=_GROUP_COLORS.get(group_name, _FALLBACK_GROUP_COLOR),
                    part_number=record.part_number,
                    normalized_part_number=normalize_part_number(record.part_number),
                    product_name=record.product_name,
                    production_status=record.production_status,
                    updated_at=synced_at,
                )
            )
        self.memory_store.replace_dashboard(
            sort_machines(cards), updated_at=synced_at
        )

        success_count = len(records)
        message = f"Google Sheets から {success_count} 件を同期しました。"
        return MemorySpreadsheetSyncResult(
            ok=True,
            processed_count=len(records),
            success_count=success_count,
            error_count=0,
            message=message,
        )
