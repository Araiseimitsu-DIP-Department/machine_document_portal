from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class DocumentCandidateResult:
    name: str
    url: str
    location: str | None = None


@dataclass(slots=True)
class DocumentSearchResult:
    status: str
    url: str | None = None
    candidates: tuple[DocumentCandidateResult, ...] = ()


class DrawingGateway(Protocol):
    def search(self, normalized_part_number: str) -> DocumentSearchResult: ...


class GoogleDriveService:
    """Stage 3 extension point; no external connection is made in Stage 1."""

    def search(self, normalized_part_number: str) -> DocumentSearchResult:
        raise NotImplementedError("Googleドライブ連携は第3段階で実装します")
