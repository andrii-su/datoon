"""Tests for the datoon.errors module and its use across layers."""

from __future__ import annotations

import inspect

import pytest


def test_datoon_error_lives_in_errors_module() -> None:
    from datoon.errors import DatoonError

    assert issubclass(DatoonError, RuntimeError)


def test_converter_reexports_the_same_error_object() -> None:
    # Backward compatibility: `from datoon.converter import DatoonError` must
    # keep working and refer to the single canonical class.
    from datoon.converter import DatoonError as FromConverter
    from datoon.errors import DatoonError as Canonical

    assert FromConverter is Canonical


def test_jsonl_reader_does_not_depend_on_converter() -> None:
    # The low-level reader must not import the high-level conversion service
    # just for an exception type (layering inversion).
    import datoon.readers.jsonl as jsonl

    source = inspect.getsource(jsonl)
    assert "datoon.converter" not in source


def test_jsonl_raises_canonical_error() -> None:
    from datoon.errors import DatoonError
    from datoon.readers.jsonl import read_jsonl

    with pytest.raises(DatoonError, match="line 2"):
        read_jsonl('{"a":1}\nbad json\n')
