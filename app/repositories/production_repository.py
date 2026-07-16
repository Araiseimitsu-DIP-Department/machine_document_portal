from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.current_production import CurrentProduction


class ProductionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_for_machine(self, machine_pk: int) -> CurrentProduction | None:
        return self.session.scalar(
            select(CurrentProduction).where(CurrentProduction.machine_id == machine_pk)
        )

    def save(self, production: CurrentProduction) -> CurrentProduction:
        self.session.add(production)
        self.session.flush()
        return production
