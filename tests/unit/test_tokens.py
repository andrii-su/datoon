"""Tests for configurable token-encoding estimation."""

from __future__ import annotations

import pytest

from datoon.converter import estimate_tokens
from datoon.models import DEFAULT_TOKEN_ENCODING, ConversionConfig


def test_default_encoding_is_o200k() -> None:
    assert DEFAULT_TOKEN_ENCODING == "o200k_base"
    assert ConversionConfig().token_encoding == "o200k_base"


def test_config_rejects_empty_encoding() -> None:
    with pytest.raises(ValueError, match="token_encoding"):
        ConversionConfig(token_encoding="")


def test_estimate_tokens_respects_encoding() -> None:
    tiktoken = pytest.importorskip("tiktoken")
    text = '{"rows":[{"id":1,"name":"Ada","role":"admin"}]}'

    for name in ("o200k_base", "cl100k_base"):
        expected = len(tiktoken.get_encoding(name).encode(text))
        assert estimate_tokens(text, encoding=name) == expected


def test_estimate_tokens_falls_back_to_heuristic_without_tiktoken(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sys

    import datoon.converter as conv

    conv._load_token_encoder.cache_clear()
    monkeypatch.setitem(sys.modules, "tiktoken", None)  # type: ignore[arg-type]
    try:
        # 30 chars -> ceil(30 / 3) == 10 by the char heuristic.
        assert estimate_tokens("x" * 30, encoding="o200k_base") == 10
    finally:
        conv._load_token_encoder.cache_clear()
