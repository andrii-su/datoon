"""Questions with Python-computed gold answers, and lenient answer scoring.

Each table gets six questions, one per kind. Column and row choices come from a
``random.Random`` seeded by the table name, so the same table always gets the
same questions, whatever format it is rendered in.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any

from .datasets import (
    KEY_COLUMN,
    KIND_CATEGORY,
    KIND_INTEGER,
    KIND_NULLABLE_INTEGER,
    Table,
)

KIND_ROW_COUNT = "row_count"
KIND_LOOKUP = "lookup"
KIND_FILTER_COUNT = "filter_count"
KIND_ARGMAX = "argmax"
KIND_DIFF = "diff"
KIND_NULL_COUNT = "null_count"
QUESTION_KINDS: tuple[str, ...] = (
    KIND_ROW_COUNT,
    KIND_LOOKUP,
    KIND_FILTER_COUNT,
    KIND_ARGMAX,
    KIND_DIFF,
    KIND_NULL_COUNT,
)

FLOAT_TOLERANCE = 1e-6
_NULL_STRINGS = frozenset({"null"})
_BOOLEAN_STRINGS = {"true": True, "false": False}


@dataclass(slots=True, frozen=True)
class Question:
    """One question about a table with its deterministic gold answer."""

    id: str
    kind: str
    text: str
    gold: Any


def _columns_of_kind(table: Table, kind: str) -> list[str]:
    """Return the table's columns of one kind, in table order."""
    columns = [column for column in table.columns if table.kinds.get(column) == kind]
    if not columns:
        raise ValueError(f"Table '{table.name}' has no {kind} column.")
    return columns


def build_questions(table: Table) -> list[Question]:
    """Build the six questions for ``table`` with gold answers."""
    rng = random.Random(f"format-eval-questions:{table.name}")
    rows = table.rows
    row_count = len(rows)
    value_columns = [column for column in table.columns if column != KEY_COLUMN]

    lookup_row = rows[rng.randint(row_count // 2, row_count - 1)]
    lookup_column = rng.choice(value_columns)

    filter_column = rng.choice(_columns_of_kind(table, KIND_CATEGORY))
    filter_value = rng.choice(sorted({row[filter_column] for row in rows}))

    argmax_column = rng.choice(_columns_of_kind(table, KIND_INTEGER))
    argmax_row = max(rows, key=lambda row: row[argmax_column])

    diff_column = rng.choice(_columns_of_kind(table, KIND_INTEGER))
    first_index, second_index = rng.sample(range(row_count), 2)
    first_row, second_row = rows[first_index], rows[second_index]

    null_column = rng.choice(_columns_of_kind(table, KIND_NULLABLE_INTEGER))

    specs: list[tuple[str, str, Any]] = [
        (
            KIND_ROW_COUNT,
            "How many data rows does the table have (not counting the header)?",
            row_count,
        ),
        (
            KIND_LOOKUP,
            (
                f"What is the value of `{lookup_column}` in the row where "
                f'`{KEY_COLUMN}` is "{lookup_row[KEY_COLUMN]}"?'
            ),
            lookup_row[lookup_column],
        ),
        (
            KIND_FILTER_COUNT,
            f'How many rows have `{filter_column}` equal to "{filter_value}"?',
            sum(1 for row in rows if row[filter_column] == filter_value),
        ),
        (
            KIND_ARGMAX,
            (
                f"What is the `{KEY_COLUMN}` of the row with the largest "
                f"`{argmax_column}`?"
            ),
            argmax_row[KEY_COLUMN],
        ),
        (
            KIND_DIFF,
            (
                f"What is `{diff_column}` in the row where `{KEY_COLUMN}` is "
                f'"{first_row[KEY_COLUMN]}" minus `{diff_column}` in the row where '
                f'`{KEY_COLUMN}` is "{second_row[KEY_COLUMN]}"?'
            ),
            first_row[diff_column] - second_row[diff_column],
        ),
        (
            KIND_NULL_COUNT,
            f"How many rows have a NULL (missing) value in `{null_column}`?",
            sum(1 for row in rows if row[null_column] is None),
        ),
    ]
    return [
        Question(id=f"q{index}", kind=kind, text=text, gold=gold)
        for index, (kind, text, gold) in enumerate(specs, start=1)
    ]


def _as_number(answer: Any) -> float | None:
    """Coerce a JSON number or numeric string to float; ``None`` if not numeric."""
    if isinstance(answer, bool):
        return None
    if isinstance(answer, int | float):
        return float(answer)
    if isinstance(answer, str):
        try:
            return float(answer.strip())
        except ValueError:
            return None
    return None


def _score(gold: Any, answer: Any) -> bool:
    """Compare by the gold value's type; see ``score``."""
    if gold is None:
        return answer is None or (
            isinstance(answer, str) and answer.strip().lower() in _NULL_STRINGS
        )
    if isinstance(gold, bool):
        if isinstance(answer, bool):
            return answer is gold
        if isinstance(answer, str):
            return _BOOLEAN_STRINGS.get(answer.strip().lower()) is gold
        return False
    if isinstance(gold, int):
        number = _as_number(answer)
        return number is not None and number.is_integer() and int(number) == gold
    if isinstance(gold, float):
        number = _as_number(answer)
        return (
            number is not None
            and math.isfinite(number)
            and abs(number - gold) <= FLOAT_TOLERANCE
        )
    if isinstance(gold, str):
        return isinstance(answer, str) and answer.strip() == gold.strip()
    return False


def score(kind: str, gold: Any, answer: Any) -> bool:
    """Return whether ``answer`` matches ``gold``; never raises.

    The comparison follows the gold value's type (``kind`` is accepted for the
    record and does not change the rule):

    * ``None``: ``null`` / ``"NULL"`` (any case) / ``None``;
    * bool: a bool or ``"true"``/``"false"`` in any case;
    * int: a number or numeric string equal after int coercion;
    * float: a number or numeric string within ``FLOAT_TOLERANCE``;
    * str: a string equal after ``strip()``.

    Anything else, including unparseable input, is wrong.
    """
    try:
        return _score(gold, answer)
    except (TypeError, ValueError, OverflowError):
        return False
