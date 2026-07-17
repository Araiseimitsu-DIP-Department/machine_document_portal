from datetime import datetime, timezone

from app.utils.time_zone import format_jst


def test_format_jst_converts_utc_to_japan_time() -> None:
    value = datetime(2026, 7, 17, 7, 7, tzinfo=timezone.utc)

    assert format_jst(value) == "2026/07/17 16:07"
