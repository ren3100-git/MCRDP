from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata


@dataclass(frozen=True)
class SoftwareProfile:
    datapoints_col: int
    first_point: int
    name_col: int
    space_var: int
    find_col: int
    encodings: tuple[str, ...]
    sep: str


REPLACEMENTS = {
    ".": "r",
    "/": "per",
    "%": "percent",
}


SOFTWARE_PROFILES = {
    "RheoPlus": SoftwareProfile(
        datapoints_col=0,
        first_point=1,
        name_col=3,
        space_var=2,
        find_col=0,
        encodings=("cp932", "shift-jis", "utf-8-sig", "utf-8"),
        sep=",",
    ),
    "RheoCompass": SoftwareProfile(
        datapoints_col=1,
        first_point=1,
        name_col=1,
        space_var=3,
        find_col=0,
        encodings=("utf-16", "utf-16-le", "utf-8-sig", "utf-8"),
        sep="\t",
    ),
}


SAMPLE_NAME_FLAGS = ("名前:", "テスト:", "Name:", "Test:")


def normalize_header(value: object) -> str:
    """Normalize a CSV header for exact alias matching."""
    text = unicodedata.normalize("NFKC", str(value)).strip()
    text = re.sub(r"\s+", " ", text)
    return text.casefold()
