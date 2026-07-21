from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from app.config import Settings
from app.services.araichat_service import (
    AraichatAmbiguousError,
    AraichatService,
)
from app.services.nas_drawing_service import NasDrawingAccessError, NasDrawingService
from app.services.next_day_sheet_service import (
    GoogleSheetsNextDayGateway,
    NextBusinessDaySheetService,
    NextDaySheetGateway,
    SheetTarget,
)
from app.services.pdf_print_service import PdfPrinter, RawPdfPrinter
from app.services.scheduled_job_state_store import ScheduledJobStateStore
from app.services.sharepoint_service import SharePointService


logger = logging.getLogger(__name__)
_EXTERNAL_ERROR_STATUSES = {
    "auth_error",
    "permission_error",
    "api_error",
    "not_checked",
}


class ScheduledOperationError(RuntimeError):
    """A scheduled check or print operation could not complete safely."""


@dataclass(frozen=True, slots=True)
class ScheduledOperationResult:
    status: str
    message: str
    target: SheetTarget | None = None
    processed_count: int = 0


class ScheduledOperationsService:
    def __init__(
        self,
        settings: Settings,
        *,
        gateway: NextDaySheetGateway | None = None,
        inspection_service: SharePointService | None = None,
        drawing_service: NasDrawingService | None = None,
        araichat_service: AraichatService | None = None,
        printer: PdfPrinter | None = None,
        state_store: ScheduledJobStateStore | None = None,
    ) -> None:
        self.settings = settings
        self.gateway = gateway or GoogleSheetsNextDayGateway(settings)
        self.target_service = NextBusinessDaySheetService(
            self.gateway,
            lookahead_days=settings.next_day_sheet_lookahead_days,
        )
        self.inspection_service = inspection_service or SharePointService(settings)
        self.drawing_service = drawing_service or NasDrawingService(
            settings.nas_drawing_directory
        )
        self.araichat_service = araichat_service or AraichatService(settings)
        self.printer = printer or RawPdfPrinter(settings.drawing_printer_name)
        self.state_store = state_store or ScheduledJobStateStore(
            settings.scheduled_job_state_path,
            spreadsheet_id=settings.google_spreadsheet_id,
        )

    def check_and_notify(self, run_date: date) -> ScheduledOperationResult:
        target = self.target_service.find_target(run_date)
        if target is None:
            return ScheduledOperationResult(
                status="no_target",
                message="翌営業日のセット情報シートがないため通知をスキップしました。",
            )

        target_key = self.state_store.record_daily_target(run_date, target)
        notification_status = self.state_store.notification_status(target_key)
        if notification_status == "ambiguous":
            return ScheduledOperationResult(
                status="ambiguous",
                message=(
                    f"{target.sheet_name} はARAICHAT送信結果が不明なため、"
                    "二重送信防止で停止しています。"
                ),
                target=target,
            )
        if notification_status == "completed":
            return ScheduledOperationResult(
                status="already_processed",
                message=f"{target.sheet_name} は通知済みのためスキップしました。",
                target=target,
            )

        part_numbers = self.gateway.fetch_part_numbers(target.sheet_name)
        if not self.inspection_service.configured:
            raise ScheduledOperationError("SharePoint settings are incomplete")
        inspection_results = self.inspection_service.search_many(part_numbers)
        inspection_errors = {
            result.status
            for result in inspection_results.values()
            if result.status in _EXTERNAL_ERROR_STATUSES
        }
        if inspection_errors:
            raise ScheduledOperationError(
                "SharePoint inspection-sheet lookup failed: "
                + ",".join(sorted(inspection_errors))
            )

        missing_inspections = [
            part_number
            for part_number in part_numbers
            if inspection_results.get(part_number) is None
            or inspection_results[part_number].status in {"not_found", "multiple"}
        ]
        missing_drawings: list[str] = []
        self._ensure_drawing_directory_available()
        try:
            for part_number in part_numbers:
                if self.drawing_service.find_pdf(part_number) is None:
                    missing_drawings.append(part_number)
        except NasDrawingAccessError as exc:
            raise ScheduledOperationError("NAS drawing lookup failed") from exc

        message = self._notification_message(
            target,
            missing_inspections=missing_inspections,
            missing_drawings=missing_drawings,
        )
        idempotency_key = (
            f"next-day-check:{self.settings.araichat_room_id}:"
            f"{target.target_date.isoformat()}:{target.sheet_id}"
        )
        try:
            self.araichat_service.send_text(
                message,
                idempotency_key=idempotency_key,
            )
        except AraichatAmbiguousError:
            self.state_store.mark_notification(target_key, "ambiguous")
            raise
        self.state_store.mark_notification(target_key, "completed")
        return ScheduledOperationResult(
            status="completed",
            message=f"{target.sheet_name} の確認結果をARAICHATへ送信しました。",
            target=target,
            processed_count=len(part_numbers),
        )

    def print_drawings(self, run_date: date) -> ScheduledOperationResult:
        stored_target = self.state_store.target_for_run_date(run_date)
        if stored_target is None:
            return ScheduledOperationResult(
                status="no_target",
                message="13:00に対象シートが決定されていないため印刷をスキップしました。",
            )
        target_key, target = stored_target
        if self.state_store.printing_completed(target_key):
            return ScheduledOperationResult(
                status="already_processed",
                message=f"{target.sheet_name} は印刷処理済みです。",
                target=target,
            )

        part_numbers = self.gateway.fetch_part_numbers(target.sheet_name)
        printed = self.state_store.printed_part_numbers(target_key)
        submitted_count = 0
        self._ensure_drawing_directory_available()
        try:
            for part_number in part_numbers:
                if part_number in printed:
                    continue
                drawing_path = self.drawing_service.find_pdf(part_number)
                if drawing_path is None:
                    continue
                self.printer.print_pdf(drawing_path)
                self.state_store.mark_part_printed(target_key, part_number)
                submitted_count += 1
        except NasDrawingAccessError as exc:
            raise ScheduledOperationError("NAS drawing lookup failed") from exc

        self.state_store.mark_printing_completed(target_key)
        return ScheduledOperationResult(
            status="completed",
            message=(
                f"{target.sheet_name} の加工図 {submitted_count} 件を印刷キューへ送信しました。"
            ),
            target=target,
            processed_count=submitted_count,
        )

    def _ensure_drawing_directory_available(self) -> None:
        directory = self.drawing_service.drawing_directory
        if directory is None:
            raise ScheduledOperationError("NAS_DRAWING_DIRECTORY is not configured")
        try:
            available = directory.is_dir()
        except OSError as exc:
            raise ScheduledOperationError("NAS drawing directory is unavailable") from exc
        if not available:
            raise ScheduledOperationError("NAS drawing directory is unavailable")

    @staticmethod
    def _notification_message(
        target: SheetTarget,
        *,
        missing_inspections: list[str],
        missing_drawings: list[str],
    ) -> str:
        def lines(values: list[str]) -> str:
            if not values:
                return "（該当なし）"
            return "\n".join(f"・{value}" for value in values)

        return (
            "【翌営業日セット内容リンク設定通知】\n\n"
            f"対象シート: {target.sheet_name}\n\n"
            "■ 工程検査シートリンク未設定リスト:\n"
            f"{lines(missing_inspections)}\n\n"
            "■ 加工図面未アップロードリスト:\n"
            f"{lines(missing_drawings)}"
        )
