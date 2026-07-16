from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from threading import RLock

from app.config import Settings, get_settings
from app.schemas.dashboard import DashboardData, DocumentState, MachineCard
from app.services.sample_data_service import SampleDataService
from app.utils.machine_sort import sort_machines


@dataclass(frozen=True, slots=True)
class CachedDocuments:
    inspection: DocumentState
    drawing: DocumentState
    checked_at: datetime


class MemoryDashboardStore:
    """Process-local state store used when persistent database writes are disabled."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._lock = RLock()
        self._dashboard: DashboardData | None = None
        self._document_cache: dict[str, CachedDocuments] = {}

    def get_dashboard(self) -> DashboardData:
        with self._lock:
            if self._dashboard is None:
                self._dashboard = self._load_initial_dashboard()
                self._index_document_cache(self._dashboard.machines, clear=True)
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
            prepared_machines = self._apply_cached_documents(machines)
            self._dashboard = DashboardData(
                machines=sort_machines(prepared_machines),
                last_updated_at=updated_at or datetime.now(timezone.utc),
                source_label="メモリ",
                notice=notice or self._memory_notice(),
            )
            self._index_document_cache(self._dashboard.machines)
            return self._dashboard.model_copy(deep=True)

    def reload_sample(self) -> DashboardData:
        with self._lock:
            self._dashboard = self._load_sample_dashboard()
            self._index_document_cache(self._dashboard.machines, clear=True)
            return self._dashboard.model_copy(deep=True)

    def cache_documents(
        self,
        normalized_part_number: str,
        inspection: DocumentState,
        drawing: DocumentState,
        *,
        checked_at: datetime | None = None,
    ) -> None:
        with self._lock:
            self._document_cache[normalized_part_number] = CachedDocuments(
                inspection=inspection.model_copy(deep=True),
                drawing=drawing.model_copy(deep=True),
                checked_at=checked_at or datetime.now(timezone.utc),
            )

    def get_cached_documents(self, normalized_part_number: str) -> CachedDocuments | None:
        with self._lock:
            cached = self._document_cache.get(normalized_part_number)
            if cached is None:
                return None
            if self._cache_expired(cached):
                del self._document_cache[normalized_part_number]
                return None
            return CachedDocuments(
                inspection=cached.inspection.model_copy(deep=True),
                drawing=cached.drawing.model_copy(deep=True),
                checked_at=cached.checked_at,
            )

    def clear(self) -> None:
        """Clear all process-local state, equivalent to an application restart."""

        with self._lock:
            self._dashboard = None
            self._document_cache.clear()

    def _load_initial_dashboard(self) -> DashboardData:
        if self.settings.use_sample_data:
            return self._load_sample_dashboard()
        return DashboardData(
            machines=[],
            source_label="メモリ",
            notice=(
                "メモリ運用中です。外部サービスから取得したデータは、"
                "アプリを再起動するとリセットされます。"
            ),
        )

    def _load_sample_dashboard(self) -> DashboardData:
        dashboard = SampleDataService(self.settings.sample_data_path).load_dashboard()
        dashboard.source_label = "メモリ（サンプル）"
        dashboard.notice = (
            "メモリ運用中です。外部サービスには接続せず、画面確認用データを表示しています。"
            "アプリを再起動すると状態はリセットされます。"
        )
        return dashboard

    @staticmethod
    def _memory_notice() -> str:
        return "メモリ運用中です。アプリを再起動すると取得状態はリセットされます。"

    def _apply_cached_documents(self, machines: list[MachineCard]) -> list[MachineCard]:
        prepared: list[MachineCard] = []
        for source in machines:
            machine = source.model_copy(deep=True)
            if machine.normalized_part_number:
                cached = self.get_cached_documents(machine.normalized_part_number)
                if cached:
                    if machine.inspection.status == "not_checked":
                        machine.inspection = cached.inspection
                    if machine.drawing.status == "not_checked":
                        machine.drawing = cached.drawing
            prepared.append(machine)
        return prepared

    def _index_document_cache(
        self, machines: list[MachineCard], *, clear: bool = False
    ) -> None:
        if clear:
            self._document_cache.clear()
        for machine in machines:
            if not machine.normalized_part_number:
                continue
            if (
                machine.inspection.status == "not_checked"
                and machine.drawing.status == "not_checked"
            ):
                continue
            self._document_cache[machine.normalized_part_number] = CachedDocuments(
                inspection=machine.inspection.model_copy(deep=True),
                drawing=machine.drawing.model_copy(deep=True),
                checked_at=machine.updated_at or datetime.now(timezone.utc),
            )

    def _cache_expired(self, cached: CachedDocuments) -> bool:
        ttl = self.settings.memory_cache_ttl_seconds
        if ttl == 0:
            return False
        checked_at = cached.checked_at
        if checked_at.tzinfo is None:
            checked_at = checked_at.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - checked_at > timedelta(seconds=ttl)


@lru_cache
def get_memory_store() -> MemoryDashboardStore:
    return MemoryDashboardStore(get_settings())
