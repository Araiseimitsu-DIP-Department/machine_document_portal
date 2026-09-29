"""Common result types returned by external document searches."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DocumentCandidateResult:
    name: str
    url: str
    location: str | None = None
    app_url: str | None = None


@dataclass(slots=True)
class DocumentSearchResult:
    status: str
    url: str | None = None
    candidates: tuple[DocumentCandidateResult, ...] = ()
