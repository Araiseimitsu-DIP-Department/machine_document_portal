import logging
from datetime import datetime, timezone
from functools import lru_cache
from threading import RLock

from app.config import Settings, get_settings
from app.schemas.dashboard import DashboardData, DocumentState, MachineCard
from app.services.sample_data_service import SampleDataService
from app.utils.machine_sort import sort_machines


logger = logging.getLogger(__name__)


class MemoryDashboardStore:
    """Process-local state store used when persistent database writes are disabled."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._lock = RLock()
        self._dashboard: DashboardData | None = None

    def get_dashboard(self) -> DashboardData:
        with self._lock:
            if self._dashboard is None:
                self._dashboard = self._load_initial_dashboard()
            return self._dashboard.model_copy(deep=True)

    def replace_dashboard(
        self,
        machines: list[MachineCard],
        *,
        updated_at: datetime | None = None,
        notice: str | None = None,
    ) -> DashboardData:
        """Replace current state after a future external-service refresh."""

        with self._lock:
            self._dashboard = DashboardData(
                machines=sort_machines(
                    [machine.model_copy(deep=True) for machine in machines]
                ),
                last_updated_at=updated_at or datetime.now(timezone.utc),
                source_label="メモリ",
                notice=notice,
            )
            if not self.settings.use_sample_data:
                self._save_snapshot(self._dashboard)
            return self._dashboard.model_copy(deep=True)

    def reload_sample(self) -> DashboardData:
        with self._lock:
            self._dashboard = self._load_sample_dashboard()
            return self._dashboard.model_copy(deep=True)

    def set_notice(self, notice: str, *, degraded: bool = True) -> DashboardData:
        """Show an operational warning without discarding the last dashboard."""

        with self._lock:
            if self._dashboard is None:
                self._dashboard = self._load_initial_dashboard()
            self._dashboard.notice = notice
            self._dashboard.degraded = degraded
            if not self.settings.use_sample_data:
                self._save_snapshot(self._dashboard)
            return self._dashboard.model_copy(deep=True)

    def mark_external_documents_unavailable(self, notice: str) -> DashboardData:
        """Keep reference production data but disable links after a failed full sync."""

        with self._lock:
            if self._dashboard is None:
                self._dashboard = self._load_initial_dashboard()
            for machine in self._dashboard.machines:
                if not machine.has_production:
                    continue
                machine.inspection = DocumentState(status="api_error")
                machine.drawing = DocumentState(status="api_error")
            self._dashboard.notice = notice
            self._dashboard.degraded = True
            self._save_snapshot(self._dashboard)
            return self._dashboard.model_copy(deep=True)

    def clear(self) -> None:
        """Clear all process-local state, equivalent to an application restart."""

        with self._lock:
            self._dashboard = None

    def _load_initial_dashboard(self) -> DashboardData:
        if self.settings.use_sample_data:
            return self._load_sample_dashboard()
        snapshot = self._load_snapshot()
        if snapshot is not None:
            snapshot.source_label = "メモリ（前回保存）"
            return snapshot
        return DashboardData(
            machines=[],
            source_label="メモリ",
        )

    def _load_sample_dashboard(self) -> DashboardData:
        dashboard = SampleDataService(self.settings.sample_data_path).load_dashboard()
        dashboard.source_label = "メモリ（サンプル）"
        dashboard.notice = (
            "メモリ運用中です。外部サービスには接続せず、画面確認用データを表示しています。"
            "アプリを再起動すると状態はリセットされます。"
        )
        return dashboard

    def _load_snapshot(self) -> DashboardData | None:
        path = self.settings.dashboard_snapshot_path
        try:
            return DashboardData.model_validate_json(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError):
            logger.exception("Dashboard snapshot could not be read")
            return None

    def _save_snapshot(self, dashboard: DashboardData) -> None:
        path = self.settings.dashboard_snapshot_path
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(path.suffix + ".tmp")
            temporary.write_text(
                dashboard.model_dump_json(indent=2),
                encoding="utf-8",
            )
            temporary.replace(path)
        except OSError:
            logger.exception("Dashboard snapshot could not be saved")


@lru_cache
def get_memory_store() -> MemoryDashboardStore:
    return MemoryDashboardStore(get_settings())
