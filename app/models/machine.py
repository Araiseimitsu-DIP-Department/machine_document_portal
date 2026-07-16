from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Machine(Base):
    __tablename__ = "machines"
    __table_args__ = (Index("ix_machines_display_order", "display_order"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    machine_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    group_name: Mapped[str] = mapped_column(String(32), nullable=False)
    machine_number: Mapped[int] = mapped_column(Integer, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    group_color: Mapped[str] = mapped_column(String(16), nullable=False, default="#1e88e5")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    current_production = relationship(
        "CurrentProduction", back_populates="machine", uselist=False, cascade="all, delete-orphan"
    )
