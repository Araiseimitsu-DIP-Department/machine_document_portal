from app.services.google_drive_service import DocumentSearchResult


class SharePointService:
    """Stage 4 extension point; no external connection is made in Stage 1."""

    def search(self, normalized_part_number: str) -> DocumentSearchResult:
        raise NotImplementedError("SharePoint連携は第4段階で実装します")
