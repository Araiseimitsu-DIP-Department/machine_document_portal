import pytest

from app.utils.part_number import normalize_part_number


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("  ab-123-r2  ", "AB-123-R2"),
        ("　ＡＢＣ－１２３　", "ABC-123"),
        ("ab_123-01", "AB_123-01"),
        ("A B　C-12", "ABC-12"),
        ("ZX—900", "ZX-900"),
        (None, None),
        ("　", None),
    ],
)
def test_normalize_part_number(source: str | None, expected: str | None) -> None:
    assert normalize_part_number(source) == expected


def test_revision_and_branch_number_are_preserved() -> None:
    assert normalize_part_number("ab-100-02_r3") == "AB-100-02_R3"
