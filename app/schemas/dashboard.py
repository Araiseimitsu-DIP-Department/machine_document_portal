from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, model_validator


DocumentStatus = Literal[
    "found",
    "not_found",
    "multiple",
    "auth_error",
    "permission_error",
    "api_error",
    "not_checked",
]


class DocumentState(BaseModel):
    status: DocumentStatus = "not_checked"
    url: str | None = None

    @model_validator(mode="after")
    def validate_external_url(self) -> "DocumentState":
        if not self.url:
            return self
        parsed_url = urlsplit(self.url)
        is_safe_local_url = (
            not parsed_url.scheme and not parsed_url.netloc and self.url.startswith("/")
        )
        if parsed_url.scheme.lower() not in {"http", "https"} and not is_safe_local_url:
            self.url = None
            if self.status == "found":
                self.status = "not_checked"
        return self

    @property
    def available(self) -> bool:
        return self.status == "found" and bool(self.url)


class MachineCard(BaseModel):
    machine_id: str
    group_name: str
    machine_number: int
    display_order: int = 0
    group_color: str = Field(default="#1e88e5", pattern=r"^#[0-9A-Fa-f]{6}$")
    part_number: str | None = None
    normalized_part_number: str | None = None
    product_name: str | None = None
    production_status: str | None = None
    inspection: DocumentState = Field(default_factory=DocumentState)
    drawing: DocumentState = Field(default_factory=DocumentState)
    updated_at: datetime | None = None
    stale: bool = False

    @property
    def has_production(self) -> bool:
        return bool(self.part_number)


class DashboardData(BaseModel):
    machines: list[MachineCard]
    last_updated_at: datetime | None = None
    source_label: str
    notice: str | None = None
    degraded: bool = False
