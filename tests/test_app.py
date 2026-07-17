import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
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
    assert "メモリ（サンプル）" in response.text
    assert "再起動すると状態はリセット" in response.text
    assert response.text.count('class="group-column"') == 6
    assert response.text.count('class="overview-lane"') == 5
    assert response.text.count('class="machine-row ') == 61
    assert 'data-auto-refresh-seconds="120"' in response.text
    assert 'class="badge badge-running">稼働中</span>' in response.text
    assert 'class="badge badge-stopped">停止中</span>' in response.text
    assert 'class="badge badge-finished">生産終了</span>' in response.text
    assert 'class="badge badge-setup">セット中</span>' in response.text
    assert "machine-updated-at" not in response.text
    assert 'aria-label="A-1_AX-1200-01_加工図面"' in response.text
    assert "data-drawing-preview" in response.text
    assert 'aria-label="全号機一覧"' in response.text
    assert response.text.count(">検査シート</span>") == 6
    assert response.text.count(">加工図面</span>") == 6


def test_manual_refresh_endpoint() -> None:
    with TestClient(app) as client:
        response = client.post("/api/refresh")
    assert response.status_code == 200
    assert response.json()["ok"] is True
