"""Tests for token estimation through the tokenizer setting."""

from __future__ import annotations

import sys
from collections.abc import Iterator

import pytest

import datoon
from datoon.converter import estimate_tokens
from datoon.models import ConversionConfig
from datoon.tokenizers import _resolve_spec


@pytest.fixture(autouse=True)
def _fresh_tokenizer_cache() -> Iterator[None]:
    """Keep resolved tokenizers from leaking between tests."""
    _resolve_spec.cache_clear()
    yield
    _resolve_spec.cache_clear()


def test_default_tokenizer_is_auto() -> None:
    assert ConversionConfig().tokenizer == "auto"


@pytest.mark.parametrize("value", ["", "   "])
def test_config_rejects_empty_tokenizer(value: str) -> None:
    with pytest.raises(ValueError, match="tokenizer"):
        ConversionConfig(tokenizer=value)


def test_config_rejects_non_callable_tokenizer() -> None:
    with pytest.raises(TypeError, match="tokenizer"):
        ConversionConfig(tokenizer=42)  # type: ignore[arg-type]


def test_config_accepts_callable_tokenizer() -> None:
    config = ConversionConfig(tokenizer=len)
    assert config.tokenizer is len


def test_estimate_tokens_is_importable_from_package_and_converter() -> None:
    assert datoon.estimate_tokens is estimate_tokens


def test_tiktoken_spec_selects_the_encoding() -> None:
    tiktoken = pytest.importorskip("tiktoken")
    text = '{"rows":[{"id":1,"name":"Ada","role":"admin"}]}'

    for name in ("o200k_base", "cl100k_base"):
        expected = len(tiktoken.get_encoding(name).encode(text))
        assert estimate_tokens(text, f"tiktoken:{name}") == expected


def test_auto_falls_back_to_char_heuristic_without_tiktoken(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "tiktoken", None)  # type: ignore[arg-type]
    # 30 chars -> ceil(30 / 3) == 10 by the char heuristic.
    assert estimate_tokens("x" * 30) == 10


def test_estimate_tokens_accepts_callable() -> None:
    assert estimate_tokens("abcd", lambda text: len(text) * 2) == 8


def test_estimate_tokens_never_below_one() -> None:
    assert estimate_tokens("anything", lambda _text: 0) == 1


def test_estimate_tokens_rejects_non_int_counter() -> None:
    with pytest.raises(datoon.DatoonError, match="expected int"):
        estimate_tokens("abc", lambda _text: 1.5)  # type: ignore[arg-type,return-value]
