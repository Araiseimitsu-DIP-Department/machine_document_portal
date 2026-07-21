import pytest

from app.config import Settings
from app.services.spreadsheet_service import (
    GoogleSheetsService,
    SpreadsheetFetchError,
)


def _settings() -> Settings:
    return Settings(
        google_spreadsheet_id="spreadsheet-id",
        google_spreadsheet_sheet_name="生産中",
        google_spreadsheet_start_row=2,
        google_spreadsheet_status_column="A",
        google_spreadsheet_machine_column="D",
        google_spreadsheet_part_number_column="H",
        google_spreadsheet_product_name_column="I",
    )


def test_google_sheets_reads_the_configured_production_columns() -> None:
    captured: dict[str, str] = {}

    def fetch_values(spreadsheet_id: str, range_name: str) -> list[list[str]]:
        captured["spreadsheet_id"] = spreadsheet_id
        captured["range_name"] = range_name
        return [
            ["稼働中", "", "", "A-1", "", "", "", " ab-100 ", " 製品A "],
            ["停止中", "", "", "A-2", "", "", "", "", ""],
            ["生産終了", "", "", "A-3", "", "", "", "ab-300", "製品C"],
            ["セット中", "", "", "A-4", "", "", "", "ab-400", "製品D"],
            ["稼働中", "", "", "", "", "", "", "ignored", "ignored"],
        ]

    records = GoogleSheetsService(_settings(), values_fetcher=fetch_values).fetch_current_productions()

    assert captured == {
        "spreadsheet_id": "spreadsheet-id",
        "range_name": "'生産中'!A2:I",
    }
    assert [(record.machine_id, record.part_number, record.product_name, record.production_status) for record in records] == [
        ("A-1", " ab-100 ", "製品A", "稼働中"),
        ("A-2", None, None, "停止中"),
        ("A-3", "ab-300", "製品C", "生産終了"),
        ("A-4", "ab-400", "製品D", "セット中"),
    ]


def test_google_sheets_preserves_part_number_whitespace_for_literal_matching() -> None:
    service = GoogleSheetsService(
        _settings(),
        values_fetcher=lambda _spreadsheet_id, _range_name: [
            ["稼働中", "", "", "A-1", "", "", "", " AB 100 ", "製品A"],
        ],
    )

    record = service.fetch_current_productions()[0]

    assert record.part_number == " AB 100 "


def test_google_sheets_rejects_duplicate_machine_ids() -> None:
    service = GoogleSheetsService(
        _settings(),
        values_fetcher=lambda _spreadsheet_id, _range_name: [
            ["生産中", "", "", "A-1"],
            ["停止", "", "", "A-1"],
        ],
    )

    with pytest.raises(SpreadsheetFetchError, match="Duplicate machine ID"):
        service.fetch_current_productions()
