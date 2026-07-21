from app.schemas.dashboard import DocumentState
from app.utils.part_number import normalize_part_number


class DocumentService:
    @staticmethod
    def part_changed(previous_part_number: str | None, current_part_number: str | None) -> bool:
        return normalize_part_number(previous_part_number) != normalize_part_number(current_part_number)

    def should_refresh_links(
        self,
        previous_part_number: str | None,
        current_part_number: str | None,
        force: bool = False,
    ) -> bool:
        return force or self.part_changed(previous_part_number, current_part_number)

    @staticmethod
    def preserve_previous_on_error(
        previous: DocumentState | None, failed_status: str = "api_error"
    ) -> tuple[DocumentState, bool]:
        """Disable a document link when the latest external lookup fails."""

        return DocumentState(status=failed_status), False
