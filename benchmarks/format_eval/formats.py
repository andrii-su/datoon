"""Serializations of one table that the benchmark compares.

All renderers keep the table's column order. ``objects`` mirrors what an MCP
``run_sql`` tool returns today; the others are the compact candidates. Text
renderers (markdown, csv) write ``NULL`` for ``None`` so a missing value stays
distinguishable from an empty string, and ``true``/``false`` for booleans to
match the JSON spelling.
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Callable
from typing import Any

import toon_format

from .datasets import Table

NULL_TEXT = "NULL"


def _ordered_rows(table: Table) -> list[dict[str, Any]]:
    """Return rows as dicts whose key order follows ``table.columns``."""
    return [{column: row[column] for column in table.columns} for row in table.rows]


def _compact_json(value: Any) -> str:
    """Serialize to compact JSON, keeping non-ASCII characters readable."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _cell_text(value: Any) -> str:
    """Render one cell for the text formats (markdown, csv)."""
    if value is None:
        return NULL_TEXT
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def render_objects(table: Table) -> str:
    """Compact JSON with one object per row."""
    return _compact_json({"columns": table.columns, "rows": _ordered_rows(table)})


def render_arrays(table: Table) -> str:
    """Compact JSON with a column list and one array per row."""
    rows = [[row[column] for column in table.columns] for row in table.rows]
    return _compact_json({"columns": table.columns, "rows": rows})


def render_toon(table: Table) -> str:
    """TOON tabular array under a ``rows`` key."""
    return toon_format.encode({"rows": _ordered_rows(table)})


def render_markdown(table: Table) -> str:
    """Markdown pipe table: header, ``---`` row, ``NULL`` for None, ``|`` escaped."""

    def line(cells: list[str]) -> str:
        escaped = [cell.replace("|", "\\|") for cell in cells]
        return "| " + " | ".join(escaped) + " |"

    lines = [line(table.columns), line(["---"] * len(table.columns))]
    lines.extend(
        line([_cell_text(row[column]) for column in table.columns])
        for row in table.rows
    )
    return "\n".join(lines)


def render_csv(table: Table) -> str:
    """CSV with a header row; ``NULL`` for None so it differs from ``""``."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(table.columns)
    for row in table.rows:
        writer.writerow([_cell_text(row[column]) for column in table.columns])
    return buffer.getvalue().rstrip("\n")


FORMATS: dict[str, Callable[[Table], str]] = {
    "objects": render_objects,
    "arrays": render_arrays,
    "toon": render_toon,
    "markdown": render_markdown,
    "csv": render_csv,
}
BASELINE_FORMAT = "objects"
