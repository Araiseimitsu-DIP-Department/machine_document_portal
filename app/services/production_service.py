import logging
from datetime import datetime, timezone

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import Settings
from app.repositories.document_repository import DocumentRepository
from app.repositories.machine_repository import MachineRepository
from app.schemas.dashboard import DashboardData, DocumentState, MachineCard
from app.services.memory_store import MemoryDashboardStore
from app.services.sample_data_service import SampleDataService
from app.utils.machine_sort import sort_machines


logger = logging.getLogger(__name__)


class ProductionService:
    def __init__(
        self, settings: Settings, memory_store: MemoryDashboardStore | None = None
    ) -> None:
        self.settings = settings
        self.memory_store = memory_store or MemoryDashboardStore(settings)

    def get_dashboard(self, session: Session | None) -> DashboardData:
        if self.settings.persistence_mode == "memory":
            return self.memory_store.get_dashboard()
        if self.settings.use_sample_data:
            return SampleDataService(self.settings.sample_data_path).load_dashboard()
        if session is None:
            return DashboardData(
                machines=[],
                source_label="PostgreSQL",
                notice="データベース設定を確認してください。",
                degraded=True,
            )

        try:
            machine_repo = MachineRepository(session)
            document_repo = DocumentRepository(session)
            cards: list[MachineCard] = []
            timestamps: list[datetime] = []
            for machine in machine_repo.list_enabled_with_productions():
                production = machine.current_production
                link = None
                if production and production.normalized_part_number:
                    link = document_repo.find_by_normalized_part_number(
                        production.normalized_part_number
                    )
                if production:
                    timestamps.append(production.fetched_at)
                cards.append(
                    MachineCard(
                        machine_id=machine.machine_id,
                        group_name=machine.group_name,
                        machine_number=machine.machine_number,
                        display_order=machine.display_order,
                        group_color=machine.group_color,
                        part_number=production.part_number if production else None,
                        normalized_part_number=(
                            production.normalized_part_number if production else None
                        ),
                        product_name=production.product_name if production else None,
                        production_status=production.production_status if production else None,
                        inspection=DocumentState(
                            status=link.inspection_status if link else "not_checked",
                            url=link.inspection_url if link else None,
                        ),
                        drawing=DocumentState(
                            status=link.drawing_status if link else "not_checked",
                            url=link.drawing_url if link else None,
                        ),
                        updated_at=production.fetched_at if production else None,
                    )
                )
            return DashboardData(
                machines=sort_machines(cards),
                last_updated_at=max(timestamps) if timestamps else None,
                source_label="PostgreSQL",
            )
        except SQLAlchemyError:
            logger.exception("Failed to load dashboard from PostgreSQL")
            session.rollback()
            return DashboardData(
                machines=[],
                last_updated_at=datetime.now(timezone.utc),
                source_label="PostgreSQL",
                notice="最新情報を取得できませんでした。データベース接続を確認してください。",
                degraded=True,
            )
