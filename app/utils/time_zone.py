from datetime import datetime, timezone
from zoneinfo import ZoneInfo


JST = ZoneInfo("Asia/Tokyo")


def format_jst(value: datetime, pattern: str = "%Y/%m/%d %H:%M") -> str:
    """Format an application timestamp in Japan Standard Time for the UI."""

    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(JST).strftime(pattern)
