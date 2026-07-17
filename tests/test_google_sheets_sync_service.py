from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.database.base import Base
from app.models.current_production import CurrentProduction
from app.models.machine import Machine
from app.models.sync_history import SyncHistory
from app.services.google_sheets_sync_service import GoogleSheetsSyncService
from app.services.spreadsheet_service import ProductionRecord, SpreadsheetGateway


class FakeGateway(SpreadsheetGateway):
    def fetch_current_productions(self) -> list[ProductionRecord]:
        return [
            ProductionRecord("A-1", "ab-100", "製品A", "生産中"),
            ProductionRecord("UNKNOWN-1", "ab-200", "製品B", "生産中"),
        ]


def test_sync_updates_known_machines_and_records_unknown_ones() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            Machine(
                machine_id="A-1",
                group_name="A",
                machine_number=1,
                display_order=1,
                group_color="#1e88e5",
                enabled=True,
            )
        )
        session.commit()

        result = GoogleSheetsSyncService(Settings(), gateway=FakeGateway()).sync(session)
        session.commit()

        production = session.scalar(select(CurrentProduction))
        history = session.scalar(select(SyncHistory))
        assert result.ok is False
        assert result.processed_count == 2
        assert result.success_count == 1
        assert result.error_count == 1
        assert production is not None
        assert production.part_number == "ab-100"
        assert production.normalized_part_number == "AB-100"
        assert history is not None
        assert history.status == "failed"
