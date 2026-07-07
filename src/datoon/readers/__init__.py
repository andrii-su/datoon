"""Format readers that normalize structured data to list-of-dicts for TOON conversion."""

from __future__ import annotations

from pathlib import Path
from typing import Any

BINARY_FORMATS: frozenset[str] = frozenset(
    {"excel", "parquet", "orc", "avro", "numbers"}
)
TEXT_FORMATS: frozenset[str] = frozenset({"csv", "jsonl", "yaml", "xml"})
ALL_FORMATS: frozenset[str] = BINARY_FORMATS | TEXT_FORMATS

_EXTENSION_MAP: dict[str, str] = {
    ".csv": "csv",
    ".jsonl": "jsonl",
    ".ndjson": "jsonl",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".xml": "xml",
    ".xlsx": "excel",
    ".xls": "excel",
    ".parquet": "parquet",
    ".avro": "avro",
    ".orc": "orc",
    ".numbers": "numbers",
}


def detect_format(path: str | Path) -> str | None:
    """Return the format name for a path by extension, or None if unknown."""
    return _EXTENSION_MAP.get(Path(path).suffix.lower())


def read_tabular(
    fmt: str,
    *,
    text: str | None = None,
    path: Path | None = None,
    sheet: int = 0,
    table: int = 0,
) -> list[dict[str, Any]]:
    """Read structured data and return rows as a list of dicts.

    Text formats (csv, jsonl, yaml, xml) require ``text``.
    Binary formats (excel, parquet, orc, avro, numbers) require ``path``.
    ``sheet`` selects the worksheet for excel/numbers; ``table`` selects the
    table within a Numbers sheet. Both are ignored by columnar formats.
    """
    if fmt in BINARY_FORMATS:
        if path is None:
            raise ValueError(f"Format '{fmt}' requires a file path, not text input.")
        return _read_binary(fmt, path, sheet=sheet, table=table)
    if fmt in TEXT_FORMATS:
        if text is None:
            raise ValueError(f"Format '{fmt}' requires text input.")
        return _read_text(fmt, text)
    raise ValueError(f"Unknown format '{fmt}'. Supported: {sorted(ALL_FORMATS)}.")


def _read_text(fmt: str, text: str) -> list[dict[str, Any]]:
    if fmt == "csv":
        from datoon.readers.csv import read_csv

        return read_csv(text)
    if fmt == "jsonl":
        from datoon.readers.jsonl import read_jsonl

        return read_jsonl(text)
    if fmt == "yaml":
        from datoon.readers.yaml import read_yaml

        return read_yaml(text)
    if fmt == "xml":
        from datoon.readers.xml import read_xml

        return read_xml(text)
    raise ValueError(f"Unknown text format: {fmt}")


def _read_binary(
    fmt: str, path: Path, *, sheet: int = 0, table: int = 0
) -> list[dict[str, Any]]:
    if fmt == "excel":
        from datoon.readers.excel import read_excel

        return read_excel(path, sheet=sheet)
    if fmt == "parquet":
        from datoon.readers.columnar import read_parquet

        return read_parquet(path)
    if fmt == "orc":
        from datoon.readers.columnar import read_orc

        return read_orc(path)
    if fmt == "avro":
        from datoon.readers.columnar import read_avro

        return read_avro(path)
    if fmt == "numbers":
        from datoon.readers.numbers import read_numbers

        return read_numbers(path, sheet=sheet, table=table)
    raise ValueError(f"Unknown binary format: {fmt}")
