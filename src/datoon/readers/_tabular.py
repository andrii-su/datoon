"""Shared header/data-row normalization for spreadsheet readers (Excel, Numbers)."""

from __future__ import annotations

from typing import Any


def header_rows_to_dicts(rows: list[Any]) -> list[dict[str, Any]]:
    """Turn ``[header, *data]`` cell tuples into row dicts with stable keys.

    * A ``None`` header cell becomes ``col{index}``.
    * Data rows wider than the header keep their overflow cells under synthetic
      ``col{index}`` keys instead of being silently dropped.
    * Data rows narrower than the header get ``None`` for missing trailing cells,
      so every emitted row shares an identical key set.
    * Rows whose cells are all ``None`` are skipped.
    """
    if not rows:
        return []

    data_rows = rows[1:]
    if not data_rows:
        return []

    widest = max((len(row) for row in data_rows), default=0)
    header_row = rows[0]
    column_count = max(len(header_row), widest)

    headers: list[str] = []
    for i in range(column_count):
        raw = header_row[i] if i < len(header_row) else None
        headers.append(str(raw) if raw is not None else f"col{i}")

    result: list[dict[str, Any]] = []
    for row in data_rows:
        if not any(cell is not None for cell in row):
            continue
        result.append(dict(zip(headers, _pad(row, column_count))))
    return result


def _pad(row: Any, width: int) -> list[Any]:
    cells = list(row)
    if len(cells) < width:
        cells.extend([None] * (width - len(cells)))
    return cells
