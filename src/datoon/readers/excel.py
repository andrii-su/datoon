"""Excel reader (requires openpyxl extra: pip install 'datoon[excel]')."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def read_excel(path: Path, *, sheet: int = 0) -> list[dict[str, Any]]:
    """Read the first sheet of an Excel file into a list of row dicts."""
    try:
        import openpyxl  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "Excel support requires the 'excel' extra: pip install 'datoon[excel]'"
        ) from exc

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.worksheets[sheet]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()

    if not rows:
        return []

    headers = [str(h) if h is not None else f"col{i}" for i, h in enumerate(rows[0])]
    return [
        {h: v for h, v in zip(headers, row)}
        for row in rows[1:]
        if any(v is not None for v in row)
    ]
