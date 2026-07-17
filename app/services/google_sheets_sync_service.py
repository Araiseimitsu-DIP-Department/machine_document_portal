import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import Settings
from app.models.current_production import CurrentProduction
from app.models.machine import Machine
from app.models.sync_history import SyncHistory
from app.services.spreadsheet_service import (
    GoogleSheetsService,
    SpreadsheetError,
    SpreadsheetGateway,
)
from app.utils.part_number import normalize_part_number


logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SpreadsheetSyncResult:
    ok: bool
    processed_count: int
    success_count: int
    error_count: int
    message: str


class GoogleSheetsSyncService:
    """Synchronize the configured production sheet into current_productions."""

    def __init__(
        self, settings: Settings, *, gateway: SpreadsheetGateway | None = None
    ) -> None:
        self.gateway = gateway or GoogleSheetsService(settings)

    def sync(self, session: Session) -> SpreadsheetSyncResult:
        started_at = datetime.now(timezone.utc)
        history = SyncHistory(
            sync_type="google_sheets",
            status="running",
            started_at=started_at,
            processed_count=0,
            success_count=0,
            error_count=0,
        )
        session.add(history)

        try:
            records = self.gateway.fetch_current_productions()
        except SpreadsheetError:
            logger.exception("Google Sheets synchronization could not read the spreadsheet")
            return self._finish(
                history,
                ok=False,
                processed_count=0,
                success_count=0,
                error_count=1,
                message="Google Sheets を読み込めませんでした。設定と共有権限を確認してください。",
            )

        machines = session.scalars(
            select(Machine)
            .where(Machine.machine_id.in_([record.machine_id for record in records]))
            .options(selectinload(Machine.current_production))
        ).all()
        machines_by_id = {machine.machine_id: machine for machine in machines}
        unknown_machine_ids: list[str] = []
        now = datetime.now(timezone.utc)

        for record in records:
            machine = machines_by_id.get(record.machine_id)
            if machine is None:
                unknown_machine_ids.append(record.machine_id)
                continue
            production = machine.current_production
            if production is None:
                production = CurrentProduction(machine_id=machine.id, fetched_at=now)
                session.add(production)
            production.part_number = record.part_number
            production.normalized_part_number = normalize_part_number(record.part_number)
            production.product_name = record.product_name
            production.production_status = record.production_status
            production.source_updated_at = None
            production.fetched_at = now

        error_count = len(unknown_machine_ids)
        success_count = len(records) - error_count
        if unknown_machine_ids:
            logger.warning(
                "Google Sheets contains machine IDs not registered in PostgreSQL: %s",
                ", ".join(unknown_machine_ids),
            )
            message = (
                f"{success_count} 件を同期しました。"
                f"未登録の機械ID {error_count} 件は取り込みませんでした。"
            )
        else:
            message = f"Google Sheets から {success_count} 件を同期しました。"
        return self._finish(
            history,
            ok=error_count == 0,
            processed_count=len(records),
            success_count=success_count,
            error_count=error_count,
            message=message,
        )

    @staticmethod
    def _finish(
        history: SyncHistory,
        *,
        ok: bool,
        processed_count: int,
        success_count: int,
        error_count: int,
        message: str,
    ) -> SpreadsheetSyncResult:
        history.status = "success" if ok else "failed"
        history.finished_at = datetime.now(timezone.utc)
        history.processed_count = processed_count
        history.success_count = success_count
        history.error_count = error_count
        history.error_message = None if ok else message
        return SpreadsheetSyncResult(
            ok=ok,
            processed_count=processed_count,
            success_count=success_count,
            error_count=error_count,
            message=message,
        )
