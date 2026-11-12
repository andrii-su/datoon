"""Excel reader (requires openpyxl extra: pip install 'datoon[excel]')."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from datoon.readers._tabular import header_rows_to_dicts


def read_excel(path: Path, *, sheet: int = 0) -> list[dict[str, Any]]:
    """Read one sheet of an Excel file (the first by default) into a list of row dicts."""
    try:
        import openpyxl  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "Excel support requires the 'excel' extra: pip install 'datoon[excel]'"
        ) from exc

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        if not 0 <= sheet < len(wb.worksheets):
            raise ValueError(
                f"Sheet index {sheet} is out of range: the workbook has "
                f"{len(wb.worksheets)} sheet(s)."
            )
        rows = list(wb.worksheets[sheet].iter_rows(values_only=True))
    finally:
        wb.close()

    return header_rows_to_dicts(rows)
