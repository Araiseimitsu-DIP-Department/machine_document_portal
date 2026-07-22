from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from app.config import Settings
from app.services.google_drive_service import (
    DocumentCandidateResult,
    DocumentSearchResult,
)
from app.services.nas_drawing_service import NasDrawingService
from app.services.next_day_sheet_service import SheetInfo
from app.services.pdf_print_service import PdfPrintError
from app.services.scheduled_job_state_store import ScheduledJobStateStore
from app.services.scheduled_operations_service import ScheduledOperationsService


class FakeGateway:
    def __init__(self, part_numbers: list[str]) -> None:
        self.part_numbers = part_numbers

    def list_sheets(self) -> list[SheetInfo]:
        return [SheetInfo(sheet_id=27, title="27S")]

    def fetch_part_numbers(self, sheet_name: str) -> list[str]:
        assert sheet_name == "27S"
        return list(self.part_numbers)


class FakeInspectionService:
    configured = True

    def search_many(self, part_numbers) -> dict[str, DocumentSearchResult]:
        results: dict[str, DocumentSearchResult] = {}
        for part_number in part_numbers:
            if part_number == "AB-100":
                results[part_number] = DocumentSearchResult(
                    status="found",
                    url="https://example.com/inspection",
                )
            else:
                results[part_number] = DocumentSearchResult(
                    status="multiple",
                    candidates=(
                        DocumentCandidateResult(
                            name=f"{part_number}-1.xlsx",
                            url="https://example.com/inspection-1",
                        ),
                        DocumentCandidateResult(
                            name=f"{part_number}-2.xlsx",
                            url="https://example.com/inspection-2",
                        ),
                    ),
                )
        return results


class FakeAraichatService:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def send_text(self, message: str, *, idempotency_key: str) -> None:
        self.messages.append((message, idempotency_key))


class FakePrinter:
    def __init__(self, *, fail_once_for: str | None = None) -> None:
        self.printed: list[str] = []
        self.fail_once_for = fail_once_for

    def print_pdf(self, pdf_path: Path) -> None:
        if self.fail_once_for == pdf_path.stem:
            self.fail_once_for = None
            raise PdfPrintError("temporary printer failure")
        self.printed.append(pdf_path.stem)


def make_service(tmp_path, *, part_numbers, printer=None):
    settings = Settings(
        google_spreadsheet_id="spreadsheet-id",
        nas_drawing_directory=tmp_path,
        scheduled_job_state_path=tmp_path / "job-state.json",
        araichat_base_url="https://example.com",
        araichat_api_key="api-key",
        araichat_room_id="24",
    )
    chat = FakeAraichatService()
    selected_printer = printer or FakePrinter()
    state_store = ScheduledJobStateStore(
        settings.scheduled_job_state_path,
        spreadsheet_id=settings.google_spreadsheet_id,
    )
    service = ScheduledOperationsService(
        settings,
        gateway=FakeGateway(part_numbers),
        inspection_service=FakeInspectionService(),
        drawing_service=NasDrawingService(tmp_path),
        araichat_service=chat,
        printer=selected_printer,
        state_store=state_store,
    )
    return service, chat, selected_printer


def test_notification_and_printing_are_not_repeated_on_the_weekend(tmp_path) -> None:
    (tmp_path / "AB-100.pdf").write_bytes(b"pdf")
    service, chat, printer = make_service(
        tmp_path,
        part_numbers=["AB-100", "CD-200"],
    )

    friday_check = service.check_and_notify(date(2026, 7, 24))
    friday_print = service.print_drawings(date(2026, 7, 24))
    saturday_check = service.check_and_notify(date(2026, 7, 25))
    saturday_print = service.print_drawings(date(2026, 7, 25))

    assert friday_check.status == "completed"
    assert friday_print.status == "completed"
    assert saturday_check.status == "already_processed"
    assert saturday_print.status == "already_processed"
    assert len(chat.messages) == 1
    assert chat.messages[0][0].count("CD-200") == 1
    assert "・CD-200" in chat.messages[0][0]
    assert "加工図面未アップロードリスト:\n・CD-200" in chat.messages[0][0]
    assert printer.printed == ["AB-100"]


def test_print_retry_submits_only_parts_not_already_recorded(tmp_path) -> None:
    (tmp_path / "AB-100.pdf").write_bytes(b"pdf")
    (tmp_path / "CD-200.pdf").write_bytes(b"pdf")
    printer = FakePrinter(fail_once_for="CD-200")
    service, _, _ = make_service(
        tmp_path,
        part_numbers=["AB-100", "CD-200"],
        printer=printer,
    )
    service.check_and_notify(date(2026, 7, 24))

    with pytest.raises(PdfPrintError):
        service.print_drawings(date(2026, 7, 24))

    result = service.print_drawings(date(2026, 7, 24))

    assert result.status == "completed"
    assert printer.printed == ["AB-100", "CD-200"]
