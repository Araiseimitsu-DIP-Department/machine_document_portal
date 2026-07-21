from collections.abc import Iterable

from app.config import Settings
from app.services.google_drive_service import DocumentSearchResult
from app.services.google_sheets_memory_sync_service import GoogleSheetsMemorySyncService
from app.services.memory_store import MemoryDashboardStore
from app.services.spreadsheet_service import (
    ProductionRecord,
    SpreadsheetFetchError,
    SpreadsheetGateway,
)


class FakeGateway(SpreadsheetGateway):
    def fetch_current_productions(self) -> list[ProductionRecord]:
        return [
            ProductionRecord("A-1", "ab-100", "製品A", "生産中"),
            ProductionRecord("G-2", "ab-200", "製品B", "生産中"),
        ]


class LiteralInspectionService:
    def __init__(self) -> None:
        self.requested_part_numbers: tuple[str, ...] = ()

    def search_many(
        self, part_numbers: Iterable[str]
    ) -> dict[str, DocumentSearchResult]:
        self.requested_part_numbers = tuple(part_numbers)
        return {
            "ab-100": DocumentSearchResult(
                status="found", url="https://example.com/ab-100"
            ),
            "ab-200": DocumentSearchResult(status="not_found"),
        }


def test_memory_sync_displays_only_machine_ids_in_the_spreadsheet(tmp_path) -> None:
    (tmp_path / "ab-100.pdf").write_bytes(b"%PDF-1.4\n")
    settings = Settings(
        persistence_mode="memory",
        use_sample_data=False,
        nas_drawing_directory=tmp_path,
        dashboard_snapshot_path=tmp_path / "dashboard.json",
    )
    store = MemoryDashboardStore(settings)
    inspection_service = LiteralInspectionService()

    result = GoogleSheetsMemorySyncService(
        settings,
        store,
        gateway=FakeGateway(),
        inspection_service=inspection_service,
    ).sync()
    dashboard = store.get_dashboard()
    a1 = next(machine for machine in dashboard.machines if machine.machine_id == "A-1")
    g2 = next(machine for machine in dashboard.machines if machine.machine_id == "G-2")

    assert result.ok is True
    assert result.processed_count == 2
    assert result.success_count == 2
    assert result.error_count == 0
    assert len(dashboard.machines) == 2
    assert a1.part_number == "ab-100"
    assert a1.normalized_part_number == "AB-100"
    assert a1.inspection.status == "found"
    assert a1.inspection.url == "https://example.com/ab-100"
    assert a1.drawing.status == "found"
    assert a1.drawing.url == "/drawings/A-1"
    assert g2.part_number == "ab-200"
    assert g2.group_name == "G"
    assert g2.drawing.status == "not_found"
    assert dashboard.notice is None
    assert inspection_service.requested_part_numbers == ("ab-100", "ab-200")


class FailingGateway(SpreadsheetGateway):
    def fetch_current_productions(self) -> list[ProductionRecord]:
        raise SpreadsheetFetchError("request failed")


def test_memory_sync_shows_a_notice_only_when_the_sheet_cannot_be_read(tmp_path) -> None:
    settings = Settings(
        persistence_mode="memory",
        use_sample_data=False,
        dashboard_snapshot_path=tmp_path / "dashboard.json",
    )
    store = MemoryDashboardStore(settings)

    result = GoogleSheetsMemorySyncService(
        settings, store, gateway=FailingGateway()
    ).sync()
    dashboard = store.get_dashboard()

    assert result.ok is False
    assert dashboard.degraded is True
    assert dashboard.notice == "Google Sheets を読み込めませんでした。設定と共有権限を確認してください。"
