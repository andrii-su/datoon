"""Apple Numbers reader (requires numbers-parser extra: pip install 'datoon[numbers]')."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def read_numbers(path: Path, *, sheet: int = 0, table: int = 0) -> list[dict[str, Any]]:
    """Read an Apple Numbers file into a list of row dicts."""
    try:
        from numbers_parser import Document  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "Numbers support requires the 'numbers' extra: pip install 'datoon[numbers]'"
        ) from exc

    doc = Document(str(path))
    tbl = doc.sheets[sheet].tables[table]
    rows = list(tbl.rows(values_only=True))

    if not rows:
        return []

    headers = [str(h) if h is not None else f"col{i}" for i, h in enumerate(rows[0])]
    return [
        {h: v for h, v in zip(headers, row)}
        for row in rows[1:]
        if any(v is not None for v in row)
    ]
