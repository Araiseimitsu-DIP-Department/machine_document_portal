from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.machine import Machine


class MachineRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_enabled_with_productions(self) -> list[Machine]:
        statement = (
            select(Machine)
            .where(Machine.enabled.is_(True))
            .options(selectinload(Machine.current_production))
            .order_by(Machine.group_name, Machine.machine_number, Machine.display_order)
        )
        return list(self.session.scalars(statement).all())
