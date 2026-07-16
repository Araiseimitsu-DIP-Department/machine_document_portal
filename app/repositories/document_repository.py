from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.document_link import DocumentLink


class DocumentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def find_by_normalized_part_number(self, value: str) -> DocumentLink | None:
        statement = (
            select(DocumentLink)
            .where(DocumentLink.normalized_part_number == value)
            .options(selectinload(DocumentLink.candidates))
            .order_by(DocumentLink.checked_at.desc().nullslast())
        )
        return self.session.scalar(statement)

    def save(self, link: DocumentLink) -> DocumentLink:
        self.session.add(link)
        self.session.flush()
        return link
