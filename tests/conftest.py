"""Shared pytest fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _no_tokenizer_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep a developer's DATOON_TOKENIZER from steering tests (or the network)."""
    monkeypatch.delenv("DATOON_TOKENIZER", raising=False)
