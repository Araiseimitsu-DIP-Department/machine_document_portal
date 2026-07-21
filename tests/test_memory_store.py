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


def test_dashboard_snapshot_is_loaded_after_process_store_recreation(tmp_path) -> None:
    settings = Settings(
        use_sample_data=False,
        persistence_mode="memory",
        dashboard_snapshot_path=tmp_path / "dashboard.json",
    )
    first_store = MemoryDashboardStore(settings)
    first_store.replace_dashboard(
        [
            MachineCard(
                machine_id="A-1",
                group_name="A",
                machine_number=1,
                part_number="AB-100",
                inspection=DocumentState(
                    status="found", url="https://example.com/inspection"
                ),
            )
        ]
    )

    restored = MemoryDashboardStore(settings).get_dashboard()

    assert restored.machines[0].part_number == "AB-100"
    assert restored.machines[0].inspection.available is True
    assert restored.source_label == "メモリ（前回保存）"


def test_failed_full_sync_disables_links_in_snapshot(tmp_path) -> None:
    settings = Settings(
        use_sample_data=False,
        persistence_mode="memory",
        dashboard_snapshot_path=tmp_path / "dashboard.json",
    )
    store = MemoryDashboardStore(settings)
    store.replace_dashboard(
        [
            MachineCard(
                machine_id="A-1",
                group_name="A",
                machine_number=1,
                part_number="AB-100",
                inspection=DocumentState(
                    status="found", url="https://example.com/inspection"
                ),
                drawing=DocumentState(
                    status="found", url="https://example.com/drawing"
                ),
            )
        ]
    )

    store.mark_external_documents_unavailable("同期失敗")
    restored = MemoryDashboardStore(settings).get_dashboard()

    assert restored.machines[0].inspection.status == "api_error"
    assert restored.machines[0].drawing.status == "api_error"
    assert restored.machines[0].inspection.url is None
    assert restored.notice == "同期失敗"


def test_memory_mode_never_marks_database_as_configured() -> None:
    settings = Settings(
        persistence_mode="memory",
        database_url="postgresql+psycopg://example.invalid/database",
    )
    assert settings.database_configured is False
