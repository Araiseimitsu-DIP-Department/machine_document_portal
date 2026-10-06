"""Single-process AACM monitoring; health requests never wait for network I/O."""

import json
import logging
import threading
import time

import psycopg
from sqlalchemy.engine import make_url

from app.config import Settings

logger = logging.getLogger(__name__)


def is_monitoring_or_static(path: str) -> bool:
    path = path.rstrip("/")
    return (
        path.endswith("/health")
        or path in ("/static", "/design-assets", "/favicon.ico", "/robots.txt")
        or path.startswith(("/static/", "/design-assets/"))
    )


class Monitoring:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.path = settings.monitoring_dir / "access_counter.json"
        self.lock = threading.Lock()
        self.total = 0
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            total = data["access_total"]
            if type(total) is not int or total < 0:
                raise ValueError("access_total must be a nonnegative integer")
            self.total = total
        except FileNotFoundError:
            pass
        except (OSError, ValueError, KeyError, TypeError):
            logger.warning("access_counter.json could not be loaded", exc_info=True)
        self.db_lock = threading.Lock()
        self.db_status = "pending"
        self.checked_at = float("-inf")
        self.checking = False

    def increment(self) -> None:
        with self.lock:
            self.total += 1
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                temporary = self.path.with_suffix(".json.tmp")
                temporary.write_text(
                    json.dumps({"access_total": self.total}), encoding="utf-8"
                )
                temporary.replace(self.path)
            except OSError:
                logger.exception("Access counter persistence failed")

    def check_database(self) -> None:
        status = "error"
        try:
            url = make_url(self.settings.database_url or "")
            # Dedicated connection avoids application pool waits and pre-ping delays.
            with psycopg.connect(
                host=url.host,
                port=url.port or 5432,
                user=url.username,
                password=url.password,
                dbname=url.database,
                **{
                    **url.query,
                    "connect_timeout": 1,
                    "options": "-c statement_timeout=1000 -c lock_timeout=1000",
                },
            ) as connection:
                connection.execute("SELECT 1").fetchone()
            status = "ok"
        except Exception:
            # Do not expose connection credentials or driver errors to HTTP clients.
            logger.warning("Health check PostgreSQL connection failed")
        finally:
            with self.db_lock:
                self.db_status = status
                self.checked_at = time.monotonic()
                self.checking = False

    def payload(self) -> dict:
        database = "disabled"
        healthy = True
        if (
            self.settings.persistence_mode == "postgresql"
            and not self.settings.use_sample_data
        ):
            with self.db_lock:
                if time.monotonic() - self.checked_at >= 10:
                    if not self.checking:
                        self.checking = True
                        threading.Thread(
                            target=self.check_database, daemon=True
                        ).start()
                    database = (
                        self.db_status
                        if time.monotonic() - self.checked_at < 15
                        else "pending"
                    )
                else:
                    database = self.db_status
            healthy = database == "ok"
        with self.lock:
            total = self.total
        return {
            "status": "ok" if healthy else "error",
            "version": self.settings.app_version,
            "access_total": total,
            "database": database,
        }
