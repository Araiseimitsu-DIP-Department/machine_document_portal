from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class DocumentLink(Base):
    __tablename__ = "document_links"
    __table_args__ = (Index("ix_document_links_normalized_part_number", "normalized_part_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    part_number: Mapped[str] = mapped_column(String(128), nullable=False)
    normalized_part_number: Mapped[str] = mapped_column(String(128), nullable=False)
    inspection_url: Mapped[str | None] = mapped_column(Text)
    drawing_url: Mapped[str | None] = mapped_column(Text)
    inspection_status: Mapped[str] = mapped_column(String(32), nullable=False, default="not_checked")
    drawing_status: Mapped[str] = mapped_column(String(32), nullable=False, default="not_checked")
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    candidates = relationship(
        "DocumentCandidate", back_populates="document_link", cascade="all, delete-orphan"
    )
