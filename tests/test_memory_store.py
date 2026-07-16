from datetime import datetime, timedelta, timezone

from app.config import Settings
from app.schemas.dashboard import DocumentState, MachineCard
from app.services.memory_store import MemoryDashboardStore


def make_store() -> MemoryDashboardStore:
    return MemoryDashboardStore(
        Settings(use_sample_data=True, persistence_mode="memory", database_url=None)
    )


def test_memory_store_returns_defensive_copies() -> None:
    store = make_store()
    first = store.get_dashboard()
    first.machines[0].part_number = "CHANGED-OUTSIDE"

    second = store.get_dashboard()
    assert second.machines[0].part_number == "AX-1200-01"


def test_memory_store_reuses_document_results_by_normalized_part_number() -> None:
    store = make_store()
    inspection = DocumentState(status="found", url="https://example.com/inspection")
    drawing = DocumentState(status="multiple")
    checked_at = datetime.now(timezone.utc)

    store.cache_documents("AB-100", inspection, drawing, checked_at=checked_at)
    cached = store.get_cached_documents("AB-100")

    assert cached is not None
    assert cached.inspection == inspection
    assert cached.drawing == drawing
    assert cached.checked_at == checked_at


def test_replacing_dashboard_keeps_state_until_store_is_cleared() -> None:
    store = make_store()
    replacement = MachineCard(
        machine_id="Z-1",
        group_name="Z",
        machine_number=1,
        part_number="ZZ-001",
        normalized_part_number="ZZ-001",
    )
    store.replace_dashboard([replacement])

    assert [machine.machine_id for machine in store.get_dashboard().machines] == ["Z-1"]

    store.clear()
    assert store.get_dashboard().machines[0].machine_id == "A-1"


def test_replacing_dashboard_reuses_cached_documents_for_same_part() -> None:
    store = make_store()
    store.cache_documents(
        "ZZ-001",
        DocumentState(status="found", url="https://example.com/inspection"),
        DocumentState(status="found", url="https://example.com/drawing"),
    )
    replacement = MachineCard(
        machine_id="Z-1",
        group_name="Z",
        machine_number=1,
        part_number="ZZ-001",
        normalized_part_number="ZZ-001",
    )

    dashboard = store.replace_dashboard([replacement])
    assert dashboard.machines[0].inspection.available is True
    assert dashboard.machines[0].drawing.available is True


def test_expired_document_cache_is_discarded() -> None:
    settings = Settings(
        use_sample_data=False,
        persistence_mode="memory",
        memory_cache_ttl_seconds=1,
    )
    store = MemoryDashboardStore(settings)
    store.cache_documents(
        "OLD-001",
        DocumentState(status="found", url="https://example.com/inspection"),
        DocumentState(status="found", url="https://example.com/drawing"),
        checked_at=datetime.now(timezone.utc) - timedelta(seconds=2),
    )
    assert store.get_cached_documents("OLD-001") is None


def test_memory_mode_never_marks_database_as_configured() -> None:
    settings = Settings(
        persistence_mode="memory",
        database_url="postgresql+psycopg://example.invalid/database",
    )
    assert settings.database_configured is False
