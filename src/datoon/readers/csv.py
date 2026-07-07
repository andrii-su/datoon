"""CSV reader with basic type coercion."""

from __future__ import annotations

import csv
import io
from typing import Any

from datoon.readers._coerce import coerce_scalar


def read_csv(text: str, *, coerce_types: bool = True) -> list[dict[str, Any]]:
    """Parse CSV text into a list of row dicts."""
    reader = csv.DictReader(io.StringIO(text))
    if coerce_types:
        return [{k: coerce_scalar(str(v)) for k, v in row.items()} for row in reader]
    return [dict(row) for row in reader]
