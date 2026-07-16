from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(slots=True)
class ProductionRecord:
    machine_id: str
    part_number: str | None
    product_name: str | None
    production_status: str | None
    source_updated_at: datetime | None


class SpreadsheetGateway(Protocol):
    def fetch_current_productions(self) -> list[ProductionRecord]: ...


class SpreadsheetService:
    """Stage 2 extension point; no external connection is made in Stage 1."""

    def fetch_current_productions(self) -> list[ProductionRecord]:
        raise NotImplementedError("Googleスプレッドシート連携は第2段階で実装します")
