"""Unit tests for the shared header-rows-to-dicts helper used by spreadsheet readers."""

from __future__ import annotations

from datoon.readers._tabular import header_rows_to_dicts


def test_uniform_rows() -> None:
    raw = [("id", "name"), (1, "Ada"), (2, "Lin")]
    assert header_rows_to_dicts(raw) == [
        {"id": 1, "name": "Ada"},
        {"id": 2, "name": "Lin"},
    ]


def test_wider_data_row_keeps_overflow_cells() -> None:
    # A data row with more cells than headers must not silently drop data.
    raw = [("a", "b"), (1, 2, 3)]
    assert header_rows_to_dicts(raw) == [{"a": 1, "b": 2, "col2": 3}]


def test_shorter_row_gets_none_for_missing_keys() -> None:
    # Missing trailing cells become None so every row keeps identical keys
    # (uniform-array detection depends on stable key sets).
    raw = [("a", "b", "c"), (1, 2)]
    assert header_rows_to_dicts(raw) == [{"a": 1, "b": 2, "c": None}]


def test_skips_all_none_rows() -> None:
    raw = [("a", "b"), (None, None), (1, 2)]
    assert header_rows_to_dicts(raw) == [{"a": 1, "b": 2}]


def test_empty_input_returns_empty() -> None:
    assert header_rows_to_dicts([]) == []


def test_header_only_returns_empty() -> None:
    assert header_rows_to_dicts([("a", "b")]) == []


def test_none_header_becomes_synthetic_column() -> None:
    raw = [("a", None), (1, 2)]
    assert header_rows_to_dicts(raw) == [{"a": 1, "col1": 2}]
