from collections.abc import Iterable

from app.config import Settings
from app.services.google_drive_service import DocumentSearchResult
from app.services.google_sheets_memory_sync_service import GoogleSheetsMemorySyncService
from app.services.memory_store import MemoryDashboardStore
from app.services.spreadsheet_service import ProductionRecord, SpreadsheetGateway


class MutableGateway(SpreadsheetGateway):
    def __init__(self, records: list[ProductionRecord]) -> None:
        self.records = records

    def fetch_current_productions(self) -> list[ProductionRecord]:
        return self.records


class RecordingInspectionService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def search_many(
        self, part_numbers: Iterable[str]
    ) -> dict[str, DocumentSearchResult]:
        requested = tuple(part_numbers)
        self.calls.append(requested)
        return {
            part_number: DocumentSearchResult(
                status="found",
                url=f"https://example.com/{part_number}",
            )
            for part_number in requested
        }


class RecordingDrawingService:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def find_pdf(self, part_number: str | None):
        if part_number:
            self.calls.append(part_number)
        return None


def make_service(tmp_path):
    gateway = MutableGateway(
        [
            ProductionRecord("A-1", "AB-100", "Product A", "running"),
            ProductionRecord("A-2", "AB-200", "Product B", "running"),
        ]
    )
    inspection_service = RecordingInspectionService()
    drawing_service = RecordingDrawingService()
    settings = Settings(
        persistence_mode="memory",
        use_sample_data=False,
        dashboard_snapshot_path=tmp_path / "dashboard.json",
    )
    store = MemoryDashboardStore(settings)
    service = GoogleSheetsMemorySyncService(
        settings,
        store,
        gateway=gateway,
        inspection_service=inspection_service,
        drawing_service=drawing_service,
    )
    return service, store, gateway, inspection_service, drawing_service


def test_incremental_sync_rechecks_documents_only_when_part_number_changes(
    tmp_path,
) -> None:
    service, store, gateway, inspection_service, drawing_service = make_service(
        tmp_path
    )
    service.sync()
    gateway.records = [
        ProductionRecord("A-1", "AB-100", "Product A updated", "stopped"),
        ProductionRecord("A-2", "AB-201", "Product B", "running"),
        ProductionRecord("A-3", "AB-300", "Product C", "running"),
    ]

    service.sync_changed()

    dashboard = store.get_dashboard()
    a1 = next(machine for machine in dashboard.machines if machine.machine_id == "A-1")
    assert inspection_service.calls == [
        ("AB-100", "AB-200"),
        ("AB-201", "AB-300"),
    ]
    assert drawing_service.calls == ["AB-100", "AB-200", "AB-201", "AB-300"]
    assert a1.product_name == "Product A updated"
    assert a1.production_status == "stopped"
    assert a1.inspection.url == "https://example.com/AB-100"


def test_document_refresh_rechecks_all_parts_without_reading_google(tmp_path) -> None:
    service, store, gateway, inspection_service, drawing_service = make_service(
        tmp_path
    )
    service.sync()
    gateway.records = []

    result = service.refresh_documents()

    assert result.ok is True
    assert result.processed_count == 2
    assert inspection_service.calls == [
        ("AB-100", "AB-200"),
        ("AB-100", "AB-200"),
    ]
    assert drawing_service.calls == ["AB-100", "AB-200", "AB-100", "AB-200"]
    assert len(store.get_dashboard().machines) == 2
