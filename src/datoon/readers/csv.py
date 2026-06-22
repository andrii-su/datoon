"""CSV reader with basic type coercion."""

from __future__ import annotations

import csv
import io
from typing import Any


def _coerce(value: str) -> int | float | bool | str | None:
    stripped = value.strip()
    if stripped == "":
        return None
    low = stripped.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    try:
        return int(stripped)
    except ValueError:
        pass
    try:
        return float(stripped)
    except ValueError:
        pass
    return stripped


def read_csv(text: str, *, coerce_types: bool = True) -> list[dict[str, Any]]:
    """Parse CSV text into a list of row dicts."""
    reader = csv.DictReader(io.StringIO(text))
    if coerce_types:
        return [{k: _coerce(str(v)) for k, v in row.items()} for row in reader]
    return [dict(row) for row in reader]
