from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.config import Settings


class SpreadsheetError(RuntimeError):
    """Base error for production spreadsheet access."""


class SpreadsheetConfigurationError(SpreadsheetError):
    """Raised when the Google Sheets settings are incomplete or invalid."""


class SpreadsheetFetchError(SpreadsheetError):
    """Raised when Google Sheets cannot be read."""


@dataclass(slots=True)
class ProductionRecord:
    machine_id: str
    part_number: str | None
    product_name: str | None
    production_status: str | None
    source_updated_at: datetime | None = None


class SpreadsheetGateway:
    def fetch_current_productions(self) -> list[ProductionRecord]:
        raise NotImplementedError


ValuesFetcher = Callable[[str, str], Sequence[Sequence[object]]]


class GoogleSheetsService(SpreadsheetGateway):
    """Read current-production data from the configured Google Sheet."""

    _SCOPE = "https://www.googleapis.com/auth/spreadsheets.readonly"

    def __init__(
        self, settings: Settings, *, values_fetcher: ValuesFetcher | None = None
    ) -> None:
        self.settings = settings
        self._values_fetcher = values_fetcher

    def fetch_current_productions(self) -> list[ProductionRecord]:
        spreadsheet_id, sheet_name = self._validate_settings()
        columns = {
            "machine_id": _column_index(self.settings.google_spreadsheet_machine_column),
            "part_number": _column_index(self.settings.google_spreadsheet_part_number_column),
            "product_name": _column_index(self.settings.google_spreadsheet_product_name_column),
            "production_status": _column_index(self.settings.google_spreadsheet_status_column),
        }
        last_column = max(columns.values())
        escaped_sheet_name = sheet_name.replace("'", "''")
        range_name = (
            f"'{escaped_sheet_name}'!"
            f"A{self.settings.google_spreadsheet_start_row}:{_column_name(last_column)}"
        )
        fetch_values = self._values_fetcher or self._fetch_values_from_google
        try:
            rows = fetch_values(spreadsheet_id, range_name)
        except SpreadsheetError:
            raise
        except Exception as exc:
            raise SpreadsheetFetchError("Google Sheets request failed") from exc

        records: list[ProductionRecord] = []
        seen_machine_ids: set[str] = set()
        for row_number, row in enumerate(rows, start=self.settings.google_spreadsheet_start_row):
            machine_id = _cell(row, columns["machine_id"])
            if not machine_id:
                continue
            if machine_id in seen_machine_ids:
                raise SpreadsheetFetchError(
                    f"Duplicate machine ID in row {row_number}: {machine_id}"
                )
            seen_machine_ids.add(machine_id)
            records.append(
                ProductionRecord(
                    machine_id=machine_id,
                    part_number=_cell(
                        row, columns["part_number"], preserve_whitespace=True
                    ),
                    product_name=_cell(row, columns["product_name"]),
                    production_status=_cell(row, columns["production_status"]),
                )
            )
        return records

    def _validate_settings(self) -> tuple[str, str]:
        spreadsheet_id = (self.settings.google_spreadsheet_id or "").strip()
        sheet_name = (self.settings.google_spreadsheet_sheet_name or "").strip()
        if not spreadsheet_id or not sheet_name:
            raise SpreadsheetConfigurationError(
                "GOOGLE_SPREADSHEET_ID and GOOGLE_SPREADSHEET_SHEET_NAME are required"
            )
        credentials_path = self.settings.google_credentials_path
        if self._values_fetcher is None and (
            not credentials_path or not Path(credentials_path).is_file()
        ):
            raise SpreadsheetConfigurationError(
                "GOOGLE_CREDENTIALS_PATH must point to a readable service-account key file"
            )
        return spreadsheet_id, sheet_name

    def _fetch_values_from_google(
        self, spreadsheet_id: str, range_name: str
    ) -> Sequence[Sequence[object]]:
        try:
            from google.oauth2.service_account import Credentials
            from googleapiclient.discovery import build

            credentials = Credentials.from_service_account_file(
                self.settings.google_credentials_path or "", scopes=[self._SCOPE]
            )
            response = (
                build("sheets", "v4", credentials=credentials, cache_discovery=False)
                .spreadsheets()
                .values()
                .get(spreadsheetId=spreadsheet_id, range=range_name, majorDimension="ROWS")
                .execute()
            )
            return response.get("values", [])
        except ImportError as exc:
            raise SpreadsheetConfigurationError(
                "google-api-python-client is not installed"
            ) from exc
        except Exception as exc:
            raise SpreadsheetFetchError("Google Sheets request failed") from exc


def _cell(
    row: Sequence[object],
    column_index: int,
    *,
    preserve_whitespace: bool = False,
) -> str | None:
    if len(row) < column_index:
        return None
    value = str(row[column_index - 1])
    if not value.strip():
        return None
    return value if preserve_whitespace else value.strip()


def _column_index(value: str) -> int:
    normalized = value.strip().upper()
    if not normalized.isalpha():
        raise SpreadsheetConfigurationError(f"Invalid spreadsheet column: {value!r}")
    result = 0
    for character in normalized:
        result = result * 26 + ord(character) - ord("A") + 1
    return result


def _column_name(column_index: int) -> str:
    name = ""
    while column_index:
        column_index, remainder = divmod(column_index - 1, 26)
        name = chr(ord("A") + remainder) + name
    return name
