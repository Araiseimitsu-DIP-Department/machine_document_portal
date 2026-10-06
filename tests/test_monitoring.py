import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from logging.handlers import RotatingFileHandler

from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app
from app.services.monitoring import Monitoring
from app.utils.logging_config import configure_logging


def test_health_exclusion_and_restart(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("USE_SAMPLE_DATA", "true")
    monkeypatch.setenv("PERSISTENCE_MODE", "memory")
    get_settings.cache_clear()
    try:
        with TestClient(create_app()) as client:
            before = client.get("/health", follow_redirects=False)
            assert before.status_code == 200
            assert before.json()["status"] == "ok"
            assert before.json()["version"] == "1.0"
            for _ in range(5):
                assert client.get("/health/", follow_redirects=False).status_code == 200
            client.get("/static/manifest.json")
            client.get("/robots.txt")
            assert client.get("/health").json()["access_total"] == 0
            assert client.get("/missing?token=secret").status_code == 404
            assert client.get("/health").json()["access_total"] == 1
        with TestClient(create_app()) as client:
            assert client.get("/health").json()["access_total"] == 1
        log = (tmp_path / "app.log").read_text(encoding="utf-8")
        assert '"GET /missing" 404' in log
        assert "secret" not in log
        assert '"GET /health' not in log
        assert '"GET /static' not in log
    finally:
        get_settings.cache_clear()


def test_counter_concurrency_and_corrupt_file(tmp_path):
    settings = Settings(app_data_dir=tmp_path)
    (tmp_path / "access_counter.json").write_text("broken", encoding="utf-8")
    monitor = Monitoring(settings)
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: monitor.increment(), range(100)))
    assert Monitoring(settings).total == 100


def test_slow_database_never_blocks_health(monkeypatch, tmp_path):
    monitor = Monitoring(
        Settings(
            app_data_dir=tmp_path, persistence_mode="postgresql", use_sample_data=False
        )
    )
    started = threading.Event()
    release = threading.Event()

    def slow_check():
        started.set()
        release.wait(5)

    monkeypatch.setattr(monitor, "check_database", slow_check)
    try:
        before = time.monotonic()
        assert monitor.payload()["status"] == "error"
        assert started.wait(1)
        for _ in range(100):
            assert monitor.payload()["database"] == "pending"
        assert time.monotonic() - before < 1
    finally:
        release.set()


def test_database_cache_and_failure(monkeypatch, tmp_path):
    monitor = Monitoring(
        Settings(
            app_data_dir=tmp_path,
            persistence_mode="postgresql",
            use_sample_data=False,
            database_url=None,
        )
    )
    monitor.check_database()
    assert monitor.payload()["status"] == "error"
    monitor.db_status = "ok"
    assert monitor.payload()["status"] == "ok"
    monitor.checked_at = time.monotonic() - 16
    monkeypatch.setattr(monitor, "check_database", lambda: None)
    assert monitor.payload()["status"] == "error"


def test_log_rotation_and_reconfiguration(tmp_path):
    settings = Settings(app_data_dir=tmp_path, log_max_bytes=1024, log_backup_count=2)
    configure_logging(settings)
    configure_logging(settings)
    handlers = [
        h for h in logging.getLogger().handlers if isinstance(h, RotatingFileHandler)
    ]
    assert len(handlers) == 1
    assert handlers[0].encoding == "utf-8"
    for _ in range(50):
        logging.getLogger("app.test").info("検証ログ %s", "x" * 200)
    assert (tmp_path / "app.log.1").exists()
    assert (tmp_path / "app.log.2").exists()
    assert not (tmp_path / "app.log.3").exists()
