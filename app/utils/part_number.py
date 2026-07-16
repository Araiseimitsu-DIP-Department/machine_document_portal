import re
import unicodedata


_DASHES = str.maketrans({
    "‐": "-",
    "‑": "-",
    "‒": "-",
    "–": "-",
    "—": "-",
    "―": "-",
    "−": "-",
    "ー": "-",
})


def normalize_part_number(value: str | None) -> str | None:
    """Normalize a part number for lookup without removing revisions or suffixes."""

    if value is None:
        return None
    normalized = unicodedata.normalize("NFKC", value).translate(_DASHES)
    normalized = re.sub(r"\s+", "", normalized).upper()
    return normalized or None
