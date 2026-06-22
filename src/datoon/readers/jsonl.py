"""JSONL (newline-delimited JSON) reader."""

from __future__ import annotations

import json
from typing import Any

from datoon.converter import DatoonError


def read_jsonl(text: str) -> list[dict[str, Any]]:
    """Parse JSONL text into a list of row dicts."""
    rows: list[dict[str, Any]] = []
    for i, line in enumerate(text.strip().splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise DatoonError(
                f"Invalid JSONL at line {i}: {exc.msg} (pos={exc.pos})."
            ) from exc
        if not isinstance(obj, dict):
            raise DatoonError(f"JSONL line {i} is not a JSON object.")
        rows.append(obj)
    return rows
