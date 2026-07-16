from fastapi.testclient import TestClient

from app.main import app


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
    assert response.text.count('class="machine-row ') == 63
    assert 'aria-label="全号機一覧"' in response.text
    assert response.text.count(">検査シート</span>") == 6
    assert response.text.count(">加工図面</span>") == 6


def test_manual_refresh_endpoint() -> None:
    with TestClient(app) as client:
        response = client.post("/api/refresh")
    assert response.status_code == 200
    assert response.json()["ok"] is True
