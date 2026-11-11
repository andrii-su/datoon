"""Deterministic synthetic query-result tables for the format reading benchmark.

Every table starts with a unique string key ``row_id`` (``r-0001``, ...), then
cycles through analytics-like column kinds. The cycle starts with the kinds the
questions need (category, unique integer, nullable integer), so even a 4-column
table can carry every question. Values come from a ``random.Random`` seeded by
the shape and seed, so the same arguments always build the same table.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

KEY_COLUMN = "row_id"

KIND_CATEGORY = "category"
KIND_INTEGER = "integer"
KIND_NULLABLE_INTEGER = "nullable_integer"
KIND_FLOAT = "float"
KIND_DATE = "date"
KIND_TEXT = "text"
KIND_BOOLEAN = "boolean"
KIND_TIMESTAMP = "timestamp"

# Question-critical kinds first, so narrow tables still hold every question.
KIND_CYCLE: tuple[str, ...] = (
    KIND_CATEGORY,
    KIND_INTEGER,
    KIND_NULLABLE_INTEGER,
    KIND_FLOAT,
    KIND_DATE,
    KIND_TEXT,
    KIND_BOOLEAN,
    KIND_TIMESTAMP,
)

DEFAULT_SHAPES: tuple[tuple[int, int], ...] = (
    (20, 4),
    (20, 11),
    (100, 4),
    (100, 11),
    (100, 30),
    (300, 4),
    (300, 10),
)
DEFAULT_SEEDS = 2
MIN_ROWS = 4
MIN_COLUMNS = 1 + 3  # row_id + category + integer + nullable integer

_COLUMN_NAMES: dict[str, tuple[str, ...]] = {
    KIND_CATEGORY: ("country", "plan_name", "platform", "channel"),
    KIND_INTEGER: ("sessions", "installs", "active_users", "orders"),
    KIND_NULLABLE_INTEGER: ("refunds", "support_tickets", "churned_users"),
    KIND_FLOAT: ("revenue_usd", "conversion_rate", "arpu_usd"),
    KIND_DATE: ("activity_date", "signup_date", "cohort_date"),
    KIND_TEXT: ("campaign_name", "landing_page", "note"),
    KIND_BOOLEAN: ("is_trial", "is_paid", "has_coupon"),
    KIND_TIMESTAMP: ("first_paid_at", "last_seen_at", "created_at"),
}
_NAME_SUFFIXES: tuple[str, ...] = ("", "_7d", "_30d", "_90d", "_365d", "_ytd")

_CATEGORY_POOLS: dict[str, tuple[str, ...]] = {
    "country": (
        "United States",
        "Germany",
        "United Kingdom",
        "Japan",
        "Brazil",
        "Ukraine",
        "South Korea",
        "France",
    ),
    "plan_name": (
        "Free",
        "Pro Monthly",
        "Pro Annual",
        "Business",
        "Education",
        "Family Plan",
    ),
    "platform": ("macOS", "iOS", "Windows", "Android", "Web App", "Setapp Bundle"),
    "channel": (
        "organic",
        "paid search",
        "paid social",
        "email",
        "referral",
        "affiliate",
        "app store",
    ),
}
_TEXT_ADJECTIVES: tuple[str, ...] = (
    "spring",
    "winter",
    "summer",
    "autumn",
    "flash",
    "loyalty",
    "launch",
    "retention",
)
_TEXT_NOUNS: tuple[str, ...] = (
    "sale",
    "promo",
    "bundle",
    "upgrade push",
    "win-back",
    "webinar",
    "newsletter",
    "trial offer",
)
_TEXT_COMMA_SHARE = 0.2
_NULL_SHARE = 0.15
_BOOLEAN_TRUE_SHARE = 0.3
_DATE_BASE = date(2026, 1, 1)
_TIMESTAMP_BASE = datetime(2026, 1, 1)
_DATE_SPAN_DAYS = 300
_TIMESTAMP_SPAN_SECONDS = 300 * 24 * 3600
_INTEGER_SPAN = 100_000
_NULLABLE_MAX = 60
_FLOAT_MAX = 5000.0
_FLOAT_DECIMALS = (2, 3, 4)


@dataclass(slots=True)
class Table:
    """A synthetic query result: ordered columns and rows keyed by column name.

    ``kinds`` maps each non-key column to its value kind (one of ``KIND_*``);
    questions use it to pick the right column for each question.
    """

    name: str
    columns: list[str]
    rows: list[dict[str, Any]]
    kinds: dict[str, str] = field(default_factory=dict)

    @property
    def shape(self) -> str:
        """Return ``<rows>x<columns>``, e.g. ``20x4``."""
        return f"{len(self.rows)}x{len(self.columns)}"


def parse_shape(text: str) -> tuple[int, int]:
    """Parse ``<rows>x<columns>`` into a tuple, validating the minimum size."""
    parts = text.strip().lower().split("x")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        raise ValueError(f"Shape '{text}' must look like 20x4.")
    rows, columns = int(parts[0]), int(parts[1])
    if rows < MIN_ROWS or columns < MIN_COLUMNS:
        raise ValueError(
            f"Shape '{text}' is too small: need at least {MIN_ROWS} rows and "
            f"{MIN_COLUMNS} columns."
        )
    return rows, columns


def _column_plan(column_count: int) -> list[tuple[str, str, str]]:
    """Return ``(name, kind, base name)`` for the non-key columns, in order."""
    plan: list[tuple[str, str, str]] = []
    seen_per_kind: dict[str, int] = {}
    for index in range(column_count - 1):
        kind = KIND_CYCLE[index % len(KIND_CYCLE)]
        occurrence = seen_per_kind.get(kind, 0)
        seen_per_kind[kind] = occurrence + 1
        names = _COLUMN_NAMES[kind]
        base = names[occurrence % len(names)]
        suffix = _NAME_SUFFIXES[(occurrence // len(names)) % len(_NAME_SUFFIXES)]
        plan.append((f"{base}{suffix}", kind, base))
    return plan


def _text_value(rng: random.Random) -> str:
    """Return a short campaign-like phrase, sometimes containing a comma."""
    phrase = f"{rng.choice(_TEXT_ADJECTIVES)} {rng.choice(_TEXT_NOUNS)}"
    if rng.random() < _TEXT_COMMA_SHARE:
        phrase = f"{phrase}, wave {rng.randint(1, 4)}"
    return phrase


def _column_values(
    kind: str, base_name: str, row_count: int, rng: random.Random
) -> list[Any]:
    """Generate one column of ``row_count`` values of the given kind."""
    if kind == KIND_CATEGORY:
        pool = _CATEGORY_POOLS[base_name]
        distinct = rng.sample(pool, rng.randint(5, min(8, len(pool))))
        return [rng.choice(distinct) for _ in range(row_count)]
    if kind == KIND_INTEGER:
        # Unique, so an argmax over this column has one answer.
        return rng.sample(range(1, _INTEGER_SPAN), row_count)
    if kind == KIND_NULLABLE_INTEGER:
        return [
            None if rng.random() < _NULL_SHARE else rng.randint(0, _NULLABLE_MAX)
            for _ in range(row_count)
        ]
    if kind == KIND_FLOAT:
        return [
            round(rng.uniform(0, _FLOAT_MAX), rng.choice(_FLOAT_DECIMALS))
            for _ in range(row_count)
        ]
    if kind == KIND_DATE:
        return [
            (_DATE_BASE + timedelta(days=rng.randint(0, _DATE_SPAN_DAYS))).isoformat()
            for _ in range(row_count)
        ]
    if kind == KIND_TEXT:
        return [_text_value(rng) for _ in range(row_count)]
    if kind == KIND_BOOLEAN:
        return [rng.random() < _BOOLEAN_TRUE_SHARE for _ in range(row_count)]
    if kind == KIND_TIMESTAMP:
        return [
            (
                _TIMESTAMP_BASE
                + timedelta(seconds=rng.randint(0, _TIMESTAMP_SPAN_SECONDS))
            ).strftime("%Y-%m-%dT%H:%M:%SZ")
            for _ in range(row_count)
        ]
    raise ValueError(f"Unknown column kind '{kind}'.")


def build_table(row_count: int, column_count: int, seed: int) -> Table:
    """Build one deterministic table of the given shape for ``seed``."""
    parse_shape(f"{row_count}x{column_count}")
    rng = random.Random(f"format-eval:{row_count}x{column_count}:{seed}")
    plan = _column_plan(column_count)
    columns = [KEY_COLUMN] + [name for name, _, _ in plan]
    values = {
        name: _column_values(kind, base, row_count, rng) for name, kind, base in plan
    }
    rows = []
    for index in range(row_count):
        row: dict[str, Any] = {KEY_COLUMN: f"r-{index + 1:04d}"}
        for name, _, _ in plan:
            row[name] = values[name][index]
        rows.append(row)
    return Table(
        name=f"t{row_count}x{column_count}_s{seed}",
        columns=columns,
        rows=rows,
        kinds={name: kind for name, kind, _ in plan},
    )


def build_tables(
    shapes: tuple[tuple[int, int], ...] | list[tuple[int, int]] = DEFAULT_SHAPES,
    seeds: int = DEFAULT_SEEDS,
) -> list[Table]:
    """Build ``seeds`` tables per shape, ordered by shape then seed."""
    if seeds < 1:
        raise ValueError("seeds must be at least 1.")
    return [
        build_table(rows, columns, seed)
        for rows, columns in shapes
        for seed in range(seeds)
    ]
