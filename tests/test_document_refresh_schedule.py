from datetime import datetime, time

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.main import JST, next_document_refresh_at


def test_document_refresh_times_accept_multiple_japan_times() -> None:
    settings = Settings(document_refresh_times="09:05, 14:30,09:05")

    assert settings.document_refresh_times == "09:05,14:30"
    assert settings.document_refresh_schedule == (time(9, 5), time(14, 30))


def test_document_refresh_times_reject_invalid_clock_time() -> None:
    with pytest.raises(ValidationError):
        Settings(document_refresh_times="25:00")


def test_next_document_refresh_uses_next_time_today() -> None:
    now = datetime(2026, 7, 21, 10, 0, tzinfo=JST)

    result = next_document_refresh_at(now, (time(9, 0), time(14, 30)))

    assert result == datetime(2026, 7, 21, 14, 30, tzinfo=JST)


def test_next_document_refresh_rolls_to_tomorrow() -> None:
    now = datetime(2026, 7, 21, 18, 0, tzinfo=JST)

    result = next_document_refresh_at(now, (time(9, 0), time(14, 30)))

    assert result == datetime(2026, 7, 22, 9, 0, tzinfo=JST)
