from datetime import date

from app.config import Settings
from app.services.next_day_sheet_service import (
    GoogleSheetsNextDayGateway,
    NextBusinessDaySheetService,
    SheetInfo,
)


def test_finds_next_existing_date_sheet_regardless_of_tab_order() -> None:
    gateway = GoogleSheetsNextDayGateway(
        Settings(),
        metadata_fetcher=lambda: [
            SheetInfo(sheet_id=27, title="27S"),
            SheetInfo(sheet_id=24, title="24S"),
        ],
    )

    target = NextBusinessDaySheetService(gateway).find_target(date(2026, 7, 24))

    assert target is not None
    assert target.target_date == date(2026, 7, 27)
    assert target.sheet_name == "27S"
    assert target.sheet_id == 27


def test_finds_first_day_sheet_after_month_end() -> None:
    gateway = GoogleSheetsNextDayGateway(
        Settings(),
        metadata_fetcher=lambda: [SheetInfo(sheet_id=801, title="1S")],
    )

    target = NextBusinessDaySheetService(gateway).find_target(date(2026, 7, 31))

    assert target is not None
    assert target.target_date == date(2026, 8, 1)
    assert target.sheet_name == "1S"


def test_reads_non_blank_unique_part_numbers_from_b40_to_k40() -> None:
    captured: list[str] = []
    gateway = GoogleSheetsNextDayGateway(
        Settings(),
        values_fetcher=lambda range_name: captured.append(range_name)
        or [[" AB-100 ", "", "CD-200", "AB-100", "CD-200"]],
    )

    values = gateway.fetch_part_numbers("27S")

    assert captured == ["'27S'!B40:K40"]
    assert values == [" AB-100 ", "CD-200", "AB-100"]
