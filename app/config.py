from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Environment-backed application settings."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "Machine Document Portal"
    app_env: str = "development"
    debug: bool = False
    use_sample_data: bool = True
    persistence_mode: Literal["memory", "postgresql"] = "memory"

    database_url: str | None = None
    db_pool_size: int = Field(default=5, ge=1)
    db_max_overflow: int = Field(default=10, ge=0)
    db_connect_timeout: int = Field(default=10, ge=1)

    google_credentials_path: str | None = None
    google_spreadsheet_id: str | None = None
    google_spreadsheet_sheet_name: str | None = None
    google_spreadsheet_start_row: int = Field(default=2, ge=1)
    google_spreadsheet_machine_column: str = "D"
    google_spreadsheet_part_number_column: str = "H"
    google_spreadsheet_product_name_column: str = "I"
    google_spreadsheet_status_column: str = "A"
    google_spreadsheet_active_status: str = "稼働中"
    nas_drawing_directory: Path | None = None

    sharepoint_drive_id: str | None = None
    sharepoint_folder_id: str | None = None
    sharepoint_process_inspection_url: str | None = None
    sharepoint_shipping_inspection_url: str | None = None
    notion_measurement_equipment_inspection_url: str | None = None
    microsoft_tenant_id: str | None = None
    microsoft_client_id: str | None = None
    microsoft_client_secret: str | None = None

    auto_refresh_seconds: int = Field(default=300, ge=0)
    memory_cache_ttl_seconds: int = Field(default=300, ge=0)
    log_level: str = "INFO"
    log_dir: Path = PROJECT_ROOT / "logs"
    log_max_bytes: int = Field(default=5_242_880, ge=1024)
    log_backup_count: int = Field(default=5, ge=1)
    sample_data_path: Path = PROJECT_ROOT / "sample_data" / "machines.json"

    @field_validator("debug", mode="before")
    @classmethod
    def parse_debug_flag(cls, value: object) -> object:
        """Tolerate common build-environment values such as DEBUG=release."""

        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"release", "production", "prod", "off", "no"}:
                return False
            if normalized in {"debug", "development", "dev", "on", "yes"}:
                return True
        return value

    @property
    def database_configured(self) -> bool:
        return self.persistence_mode == "postgresql" and bool(self.database_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()
