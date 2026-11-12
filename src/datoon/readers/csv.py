"""CSV reader with basic type coercion."""

from __future__ import annotations

import csv
import io
from typing import Any

from datoon.readers._coerce import coerce_scalar

# Key that holds the cells of a row longer than the header.
EXTRA_CELLS_KEY = "_extra"


def read_csv(text: str, *, coerce_types: bool = True) -> list[dict[str, Any]]:
    """Parse CSV text into a list of row dicts.

    A row shorter than the header gets ``None`` for its missing cells. The
    cells of a row longer than the header are kept as a list under
    ``EXTRA_CELLS_KEY``.
    """
    reader = csv.DictReader(io.StringIO(text), restkey=EXTRA_CELLS_KEY)
    if not coerce_types:
        return [dict(row) for row in reader]
    return [{key: _coerce_cell(value) for key, value in row.items()} for row in reader]


def _coerce_cell(value: Any) -> Any:
    """Coerce one DictReader value: a cell string, a list of extra cells, or None."""
    if isinstance(value, str):
        return coerce_scalar(value)
    if isinstance(value, list):
        return [coerce_scalar(cell) for cell in value]
    return value
