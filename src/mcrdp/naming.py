from __future__ import annotations

import re


NAME_ORDERS = (
    "var-num-name",
    "var-name-num",
    "num-var-name",
    "num-name-var",
    "name-var-num",
    "name-num-var",
)


def make_column_name(
    variable_key: str,
    number: int,
    sample_name: str,
    name_order: str,
    separator: str = "_",
    number_digits: int = 3,
) -> str:
    if name_order not in NAME_ORDERS:
        raise ValueError(f"Unsupported column-name order: {name_order}")

    parts = {
        "var": variable_key,
        "num": f"{number:0{number_digits}d}",
        "name": sample_name,
    }
    return separator.join(parts[token] for token in name_order.split("-"))


def sanitize_sample_name(
    name: str,
    replacements: tuple[tuple[str, str], ...] = (
        (".", "r"),
        ("/", "per"),
        ("%", "percent"),
    ),
    strip_trailing_number: bool = True,
) -> str:
    for source, replacement in replacements:
        name = name.replace(source, replacement)
    if strip_trailing_number:
        name = re.sub(r"_\d+$", "", name)
    return name
