import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.schemas.dashboard import DocumentCandidate, DocumentState, MachineCard
from app.services.memory_store import get_memory_store


@pytest.fixture(autouse=True)
def use_sample_mode(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PERSISTENCE_MODE", "memory")
    monkeypatch.setenv("USE_SAMPLE_DATA", "true")
    monkeypatch.setenv("AUTO_REFRESH_SECONDS", "120")
    get_settings.cache_clear()
    get_memory_store.cache_clear()
    yield
    get_settings.cache_clear()
    get_memory_store.cache_clear()


def test_dashboard_renders_in_sample_mode_without_postgresql() -> None:
    with TestClient(app) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert "稼働中工程内検査シート" in response.text
    assert "A-1" in response.text
    assert "候補が複数あります" in response.text
    assert "生産中品番なし" in response.text
    assert "メモリ（サンプル）" not in response.text
    assert 'class="sidebar-meta"' not in response.text
    assert "再起動すると状態はリセット" in response.text
    assert response.text.count('class="group-column"') == 6
    assert response.text.count('class="overview-lane"') == 5
    assert response.text.count('class="machine-row ') == 61
    assert 'data-auto-refresh-seconds="120"' in response.text
    assert 'class="refresh-controls"' in response.text
    assert "工程内検査シート・加工図面を更新するときに押してください。" in response.text
    assert 'class="badge badge-running">稼働中</span>' in response.text
    assert 'class="badge badge-stopped">停止中</span>' in response.text
    assert 'class="badge badge-finished">生産終了</span>' in response.text
    assert 'class="badge badge-setup">セット中</span>' in response.text
    assert "machine-updated-at" not in response.text
    assert 'aria-label="A-1_AX-1200-01_加工図面"' in response.text
    assert 'target="_blank"' in response.text
    assert 'aria-label="全号機一覧"' in response.text
    assert ">測定機器点検表</span>" in response.text
    assert "27737bffefe881aca5aac2e44de8cb2e" in response.text
    assert ">外部リンク</p>" in response.text
    assert response.text.count('class="nav-item nav-item-external"') == 3
    assert response.text.count('class="external-link-mark"') == 3
    assert response.text.count(">検査シート</span>") == 6
    assert response.text.count(">加工図面</span>") == 6


def test_manual_refresh_endpoint() -> None:
    with TestClient(app) as client:
        response = client.post("/api/refresh")
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_drawing_viewer_opens_as_a_separate_page() -> None:
    with TestClient(app) as client:
        response = client.get("/drawings/A-1")
    assert response.status_code == 200
    assert "A-1_AX-1200-01_加工図面" in response.text
    assert 'data-drawing-viewer-image' in response.text
    assert 'src="/api/drawings/A-1/preview"' in response.text


def test_multiple_inspection_files_are_listed_on_a_separate_page() -> None:
    inspection = DocumentState(
        status="found",
        url="/inspections/E-4",
        candidates=(
            DocumentCandidate(
                name="T798129-1.xlsx",
                url="https://example.com/inspection-1",
                location="Vendor A",
            ),
            DocumentCandidate(
                name="T798129-2.xlsx",
                url="https://example.com/inspection-2",
                location="Vendor B",
            ),
        ),
    )
    with TestClient(app) as client:
        get_memory_store().replace_dashboard(
            [
                MachineCard(
                    machine_id="E-4",
                    group_name="E",
                    machine_number=4,
                    part_number="T798129",
                    inspection=inspection,
                )
            ]
        )
        dashboard_response = client.get("/")
        selection_response = client.get("/inspections/E-4")

    assert dashboard_response.status_code == 200
    assert 'href="/inspections/E-4"' in dashboard_response.text
    assert 'class="machine-doc-count"' in dashboard_response.text
    assert selection_response.status_code == 200
    assert "T798129-1.xlsx" in selection_response.text
    assert "T798129-2.xlsx" in selection_response.text
    assert "Vendor A" in selection_response.text
    assert "Vendor B" in selection_response.text
    assert selection_response.text.count('target="_blank"') >= 2
