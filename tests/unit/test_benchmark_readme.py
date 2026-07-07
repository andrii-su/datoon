"""Tests for the README benchmark-table injector in benchmarks/run.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_RUN_PY = Path(__file__).resolve().parents[2] / "benchmarks" / "run.py"


def _load_run_module() -> object:
    spec = importlib.util.spec_from_file_location("benchmark_run", _RUN_PY)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Register before exec so dataclasses in run.py resolve their own module.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_marker_replacement_surrounds_table_with_blank_lines() -> None:
    # mdformat requires a blank line between the HTML comment markers and the
    # table, so the injected README stays lint-clean after --update-readme.
    run = _load_run_module()
    content = "<!--S-->\nOLD TABLE\n<!--E-->"
    result = run._replace_between_markers(content, "<!--S-->", "<!--E-->", "NEW TABLE")
    assert result == "<!--S-->\n\nNEW TABLE\n\n<!--E-->"
