"""Shared scalar coercion for text readers (CSV, XML).

Coercion must never change semantic values. Two traps are guarded here:

* Leading-zero integers (ZIP codes, phone numbers, IDs) stay strings — only
  values that round-trip through ``int`` are coerced.
* ``inf``/``nan`` and overflowing exponents would serialize to ``Infinity``/
  ``NaN`` (invalid JSON), so non-finite floats stay strings.
"""

from __future__ import annotations

import math
import re

# Canonical decimal/scientific literal: no leading zeros, no underscores. Guards
# against float("00755") -> 755.0 and float("1_000") -> 1000.0 quietly rewriting
# IDs and formatted numbers.
_FLOAT_RE = re.compile(r"^[+-]?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?$")


def coerce_scalar(value: str) -> int | float | bool | str | None:
    """Coerce a raw string cell to a JSON-safe scalar without losing meaning."""
    stripped = value.strip()
    if stripped == "":
        return None

    low = stripped.lower()
    if low == "true":
        return True
    if low == "false":
        return False

    # Only accept integers that round-trip: rejects "00123", "+5", "1_000".
    try:
        as_int = int(stripped)
    except ValueError:
        pass
    else:
        if str(as_int) == stripped:
            return as_int

    if _FLOAT_RE.match(stripped):
        as_float = float(stripped)
        # Reject overflowing exponents (1e400 -> inf) that break JSON serialization.
        if math.isfinite(as_float):
            return as_float
    return stripped
