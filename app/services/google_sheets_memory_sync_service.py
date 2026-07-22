import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from urllib.parse import quote

from app.config import Settings
from app.schemas.dashboard import DocumentCandidate, DocumentState, MachineCard
from app.services.google_drive_service import DocumentSearchResult
from app.services.memory_store import MemoryDashboardStore
from app.services.nas_drawing_service import NasDrawingAccessError, NasDrawingService
from app.services.sharepoint_service import SharePointService
from app.services.spreadsheet_service import (
    GoogleSheetsService,
    SpreadsheetError,
    SpreadsheetGateway,
)
from app.utils.part_number import normalize_part_number
from app.utils.machine_sort import parse_machine_id, sort_machines


logger = logging.getLogger(__name__)
_SYNC_LOCK = Lock()


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
        drawing_service: NasDrawingService | None = None,
        inspection_service: SharePointService | None = None,
    ) -> None:
        self.memory_store = memory_store
        self.gateway = gateway or GoogleSheetsService(settings)
        self.drawing_service = drawing_service or NasDrawingService(
            settings.nas_drawing_directory
        )
        self.inspection_service = inspection_service or SharePointService(settings)

    def sync(self) -> MemorySpreadsheetSyncResult:
        """Fully refresh Google Sheets, SharePoint, and NAS."""

        with _SYNC_LOCK:
            return self._sync(refresh_all_documents=True)

    def sync_changed(self) -> MemorySpreadsheetSyncResult:
        """Refresh Google Sheets and recheck documents only for changed part numbers."""

        with _SYNC_LOCK:
            return self._sync(refresh_all_documents=False)

    def refresh_documents(self) -> MemorySpreadsheetSyncResult:
        """Recheck SharePoint and NAS for every machine without reading Google Sheets."""

        with _SYNC_LOCK:
            dashboard = self.memory_store.get_dashboard()
            synced_at = datetime.now(timezone.utc)
            part_numbers = tuple(
                machine.part_number
                for machine in dashboard.machines
                if machine.part_number
            )
            inspection_results = (
                self.inspection_service.search_many(part_numbers)
                if part_numbers
                else {}
            )
            cards: list[MachineCard] = []
            for machine in dashboard.machines:
                cards.append(
                    machine.model_copy(
                        update={
                            "inspection": self._inspection_state(
                                machine.machine_id,
                                machine.part_number,
                                inspection_results,
                            ),
                            "drawing": self._drawing_state(
                                machine.machine_id,
                                machine.part_number,
                            ),
                            "updated_at": synced_at,
                            "stale": False,
                        },
                        deep=True,
                    )
                )
            self.memory_store.replace_dashboard(cards, updated_at=synced_at)
            count = len(cards)
            return MemorySpreadsheetSyncResult(
                ok=True,
                processed_count=count,
                success_count=count,
                error_count=0,
                message=f"SharePoint・NAS資料を {count} 号機分更新しました。",
            )

    def _sync(self, *, refresh_all_documents: bool) -> MemorySpreadsheetSyncResult:
        try:
            records = self.gateway.fetch_current_productions()
        except SpreadsheetError:
            logger.exception("Google Sheets synchronization could not read the spreadsheet")
            message = "Google Sheets を読み込めませんでした。設定と共有権限を確認してください。"
            self.memory_store.mark_external_documents_unavailable(message)
            return MemorySpreadsheetSyncResult(
                ok=False,
                processed_count=0,
                success_count=0,
                error_count=1,
                message=message,
            )

        previous_dashboard = self.memory_store.get_dashboard()
        previous_by_machine_id = {
            machine.machine_id: machine for machine in previous_dashboard.machines
        }
        records_requiring_document_refresh = [
            record
            for record in records
            if refresh_all_documents
            or record.machine_id not in previous_by_machine_id
            or previous_by_machine_id[record.machine_id].part_number
            != record.part_number
        ]

        synced_at = datetime.now(timezone.utc)
        part_numbers_to_refresh = tuple(
            record.part_number
            for record in records_requiring_document_refresh
            if record.part_number
        )
        inspection_results = (
            self.inspection_service.search_many(part_numbers_to_refresh)
            if part_numbers_to_refresh
            else {}
        )
        cards: list[MachineCard] = []
        for display_order, record in enumerate(records, start=1):
            group_name, machine_number = parse_machine_id(record.machine_id)
            previous = previous_by_machine_id.get(record.machine_id)
            documents_changed = (
                refresh_all_documents
                or previous is None
                or previous.part_number != record.part_number
            )
            if documents_changed:
                drawing = self._drawing_state(record.machine_id, record.part_number)
                inspection = self._inspection_state(
                    record.machine_id,
                    record.part_number,
                    inspection_results,
                )
            else:
                drawing = previous.drawing.model_copy(deep=True)
                inspection = previous.inspection.model_copy(deep=True)
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
                    inspection=inspection,
                    drawing=drawing,
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

    @staticmethod
    def _inspection_state(
        machine_id: str,
        part_number: str | None,
        inspection_results: dict[str, DocumentSearchResult],
    ) -> DocumentState:
        if not part_number:
            return DocumentState()
        inspection_result = inspection_results.get(part_number)
        if inspection_result is None:
            return DocumentState()
        candidates = tuple(
            DocumentCandidate(
                name=candidate.name,
                url=candidate.url,
                location=candidate.location,
            )
            for candidate in inspection_result.candidates
        )
        if inspection_result.status == "multiple" and candidates:
            return DocumentState(
                status="found",
                url=f"/inspections/{quote(machine_id, safe='')}",
                candidates=candidates,
            )
        return DocumentState(
            status=inspection_result.status,
            url=inspection_result.url,
            candidates=candidates,
        )

    def _drawing_state(self, machine_id: str, part_number: str | None) -> DocumentState:
        if not part_number:
            return DocumentState()
        try:
            drawing_path = self.drawing_service.find_pdf(part_number)
        except NasDrawingAccessError:
            logger.exception("NAS drawing lookup failed for machine %s", machine_id)
            return DocumentState(status="api_error")
        if drawing_path is None:
            return DocumentState(status="not_found")
        return DocumentState(
            status="found",
            url=f"/drawings/{quote(machine_id, safe='')}",
        )
