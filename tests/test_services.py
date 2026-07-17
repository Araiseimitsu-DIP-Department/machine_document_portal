from app.config import Settings
from app.schemas.dashboard import DocumentState
from app.services.document_service import DocumentService
from app.services.memory_store import MemoryDashboardStore
from app.services.production_service import ProductionService


def test_links_are_refreshed_only_when_part_number_changes() -> None:
    service = DocumentService()
    assert service.should_refresh_links("ab-100", "ＡＢ－１００") is False
    assert service.should_refresh_links("AB-100", "AB-101") is True
    assert service.should_refresh_links("AB-100", "AB-100", force=True) is True


def test_previous_good_link_is_kept_after_external_error() -> None:
    previous = DocumentState(status="found", url="https://example.com/document")
    state, stale = DocumentService.preserve_previous_on_error(previous)
    assert state == previous
    assert stale is True


def test_error_is_visible_when_no_previous_link_exists() -> None:
    state, stale = DocumentService.preserve_previous_on_error(None, "auth_error")
    assert state.status == "auth_error"
    assert state.url is None
    assert stale is False


def test_unsafe_document_url_is_not_exposed() -> None:
    state = DocumentState(status="found", url="javascript:alert(1)")
    assert state.status == "not_checked"
    assert state.url is None


def test_missing_database_configuration_is_a_friendly_degraded_result() -> None:
    settings = Settings(
        use_sample_data=False,
        persistence_mode="postgresql",
        database_url=None,
    )
    data = ProductionService(settings).get_dashboard(None)
    assert data.degraded is True
    assert data.machines == []
    assert "データベース" in (data.notice or "")


def test_sample_mode_does_not_need_postgresql() -> None:
    settings = Settings(
        use_sample_data=True,
        persistence_mode="memory",
        database_url=None,
    )
    store = MemoryDashboardStore(settings)
    data = ProductionService(settings, store).get_dashboard(None)
    assert data.degraded is False
    assert len(data.machines) == 61
    assert data.source_label == "メモリ（サンプル）"


def test_memory_mode_without_external_data_does_not_request_database() -> None:
    settings = Settings(
        use_sample_data=False,
        persistence_mode="memory",
        database_url=None,
    )
    data = ProductionService(settings, MemoryDashboardStore(settings)).get_dashboard(None)
    assert data.degraded is False
    assert data.machines == []
    assert data.source_label == "メモリ"
    assert data.notice is None
