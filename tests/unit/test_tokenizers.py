"""Unit tests for tokenizer spec resolution (no network, no model downloads)."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from datoon import tokenizers
from datoon.errors import DatoonError
from datoon.tokenizers import resolve_tokenizer


@pytest.fixture(autouse=True)
def _fresh_tokenizer_cache() -> Iterator[None]:
    """Keep resolved tokenizers from leaking between tests."""
    tokenizers._resolve_spec.cache_clear()
    yield
    tokenizers._resolve_spec.cache_clear()


class _FakeEncoding:
    """Stand-in for a tiktoken encoding: one token per character."""

    def encode(self, text: str) -> list[int]:
        return [ord(char) for char in text]


def _install_fake_tiktoken(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Replace tiktoken with a fake module; returns the loaded encoding names."""
    loaded: list[str] = []

    def get_encoding(name: str) -> _FakeEncoding:
        if name not in {"o200k_base", "cl100k_base"}:
            raise ValueError(f"Unknown encoding {name}")
        loaded.append(name)
        return _FakeEncoding()

    module = ModuleType("tiktoken")
    module.get_encoding = get_encoding  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "tiktoken", module)
    return loaded


class _FakeMessages:
    """Fake ``client.messages`` whose count is a fixed framing plus text length."""

    def __init__(self, framing: int) -> None:
        self.framing = framing
        self.calls: list[dict[str, Any]] = []

    def count_tokens(self, *, model: str, messages: list[dict[str, str]]) -> Any:
        self.calls.append({"model": model, "messages": messages})
        return SimpleNamespace(input_tokens=self.framing + len(messages[0]["content"]))


class _FakeAnthropicClient:
    """Fake Anthropic client exposing only ``messages.count_tokens``."""

    def __init__(self, framing: int = 7) -> None:
        self.messages = _FakeMessages(framing)


def _install_fake_client(monkeypatch: pytest.MonkeyPatch, client: Any) -> list[Any]:
    """Make the Claude counter use ``client``; returns the list of built clients."""
    built: list[Any] = []

    def build() -> Any:
        built.append(client)
        return client

    monkeypatch.setattr(tokenizers, "_anthropic_client", build)
    return built


# ---------------------------------------------------------------------------
# Spec parsing: auto, chars, tiktoken, unknown, callables
# ---------------------------------------------------------------------------


def test_auto_resolves_to_tiktoken_when_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_tiktoken(monkeypatch)
    counter, name = resolve_tokenizer("auto")
    assert name == "tiktoken:o200k_base"
    assert counter("abcd") == 4


def test_auto_falls_back_to_chars_without_tiktoken(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "tiktoken", None)  # type: ignore[arg-type]
    counter, name = resolve_tokenizer("auto")
    assert name == "chars:3"
    assert counter("x" * 30) == 10


def test_auto_rejects_an_argument() -> None:
    with pytest.raises(DatoonError, match="takes no argument"):
        resolve_tokenizer("auto:x")


def test_chars_defaults_to_three_chars_per_token() -> None:
    counter, name = resolve_tokenizer("chars")
    assert name == "chars:3"
    assert counter("x" * 31) == 11


def test_chars_accepts_a_float_divisor() -> None:
    counter, name = resolve_tokenizer("chars:2.5")
    assert name == "chars:2.5"
    assert counter("x" * 10) == 4


def test_chars_never_returns_below_one() -> None:
    counter, _ = resolve_tokenizer("chars:4")
    assert counter("") == 1


@pytest.mark.parametrize("spec", ["chars:", "chars:0", "chars:-2", "chars:abc", "chars:nan", "chars:inf"])
def test_chars_rejects_malformed_divisor(spec: str) -> None:
    with pytest.raises(DatoonError, match="chars"):
        resolve_tokenizer(spec)


def test_tiktoken_defaults_to_o200k_base(monkeypatch: pytest.MonkeyPatch) -> None:
    loaded = _install_fake_tiktoken(monkeypatch)
    counter, name = resolve_tokenizer("tiktoken")
    assert name == "tiktoken:o200k_base"
    assert loaded == ["o200k_base"]
    assert counter("abc") == 3


def test_tiktoken_accepts_an_encoding(monkeypatch: pytest.MonkeyPatch) -> None:
    loaded = _install_fake_tiktoken(monkeypatch)
    _, name = resolve_tokenizer("tiktoken:cl100k_base")
    assert name == "tiktoken:cl100k_base"
    assert loaded == ["cl100k_base"]


def test_tiktoken_rejects_missing_encoding_after_colon() -> None:
    with pytest.raises(DatoonError, match="missing encoding"):
        resolve_tokenizer("tiktoken:")


def test_tiktoken_rejects_unknown_encoding(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_tiktoken(monkeypatch)
    with pytest.raises(DatoonError, match="Unknown tiktoken encoding 'nope'"):
        resolve_tokenizer("tiktoken:nope")


def test_explicit_tiktoken_without_package_names_the_extra(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "tiktoken", None)  # type: ignore[arg-type]
    with pytest.raises(DatoonError, match=r'pip install "datoon\[tokens\]"'):
        resolve_tokenizer("tiktoken:o200k_base")


def test_unknown_kind_is_an_error() -> None:
    with pytest.raises(DatoonError, match="Unknown tokenizer 'gpt:4'"):
        resolve_tokenizer("gpt:4")


@pytest.mark.parametrize("spec", ["", "   "])
def test_empty_spec_is_an_error(spec: str) -> None:
    with pytest.raises(DatoonError, match="must not be empty"):
        resolve_tokenizer(spec)


def test_non_string_non_callable_is_an_error() -> None:
    with pytest.raises(DatoonError, match="spec string or a callable"):
        resolve_tokenizer(3)  # type: ignore[arg-type]


def test_callable_passes_through_named_custom() -> None:
    def counter(text: str) -> int:
        return len(text)

    resolved, name = resolve_tokenizer(counter)
    assert resolved is counter
    assert name == "custom"


# ---------------------------------------------------------------------------
# claude:<model-id>
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("spec", ["claude", "claude:", "claude:  "])
def test_claude_requires_a_model_id(spec: str) -> None:
    with pytest.raises(DatoonError, match="needs a model id"):
        resolve_tokenizer(spec)


def test_claude_without_package_names_the_extra(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "anthropic", None)  # type: ignore[arg-type]
    with pytest.raises(DatoonError, match=r'pip install "datoon\[claude\]"'):
        resolve_tokenizer("claude:test-model")


def test_claude_subtracts_measured_overhead(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _FakeAnthropicClient(framing=7)
    _install_fake_client(monkeypatch, client)

    counter, name = resolve_tokenizer("claude:test-model")

    assert name == "claude:test-model"
    # Marker "x" counts 7 + 1 = 8 -> overhead 7; "abcde" counts 12 -> 12 - 7.
    assert counter("abcde") == 5
    assert client.messages.calls[0] == {
        "model": "test-model",
        "messages": [{"role": "user", "content": "x"}],
    }
    assert client.messages.calls[1] == {
        "model": "test-model",
        "messages": [{"role": "user", "content": "abcde"}],
    }


def test_claude_measures_overhead_once_per_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeAnthropicClient()
    built = _install_fake_client(monkeypatch, client)

    first, _ = resolve_tokenizer("claude:model-a")
    again, _ = resolve_tokenizer("claude:model-a")
    first("one")
    again("two")
    resolve_tokenizer("claude:model-b")

    marker_calls = [call["model"] for call in client.messages.calls if call["messages"][0]["content"] == "x"]
    assert marker_calls == ["model-a", "model-b"]
    assert len(built) == 2


def test_claude_caches_counts_per_text(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _FakeAnthropicClient()
    _install_fake_client(monkeypatch, client)
    counter, _ = resolve_tokenizer("claude:test-model")

    assert counter("payload") == counter("payload")
    payload_calls = [call for call in client.messages.calls if call["messages"][0]["content"] == "payload"]
    assert len(payload_calls) == 1


def test_claude_count_never_below_one(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _FakeAnthropicClient()
    client.messages.count_tokens = (  # type: ignore[method-assign]
        lambda *, model, messages: SimpleNamespace(input_tokens=9 if messages[0]["content"] == "x" else 3)
    )
    _install_fake_client(monkeypatch, client)
    counter, _ = resolve_tokenizer("claude:test-model")

    assert counter("tiny") == 1


def test_claude_empty_text_counts_one_without_a_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeAnthropicClient()
    _install_fake_client(monkeypatch, client)
    counter, _ = resolve_tokenizer("claude:test-model")
    calls_before = len(client.messages.calls)

    assert counter("") == 1
    assert len(client.messages.calls) == calls_before


def test_claude_missing_credentials_is_an_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeAnthropicClient()

    def no_credentials(**_kwargs: Any) -> Any:
        raise TypeError('"Could not resolve authentication method. Expected one of"')

    client.messages.count_tokens = no_credentials  # type: ignore[method-assign]
    _install_fake_client(monkeypatch, client)

    with pytest.raises(DatoonError, match="ANTHROPIC_API_KEY"):
        resolve_tokenizer("claude:test-model")


def test_claude_api_failure_is_a_datoon_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeAnthropicClient()

    def fail(**_kwargs: Any) -> Any:
        raise RuntimeError("model not found")

    client.messages.count_tokens = fail  # type: ignore[method-assign]
    _install_fake_client(monkeypatch, client)

    with pytest.raises(DatoonError, match="Anthropic token counting failed"):
        resolve_tokenizer("claude:test-model")


# ---------------------------------------------------------------------------
# hf:<repo-id>
# ---------------------------------------------------------------------------


class _FakeHFTokenizer:
    """Fake ``tokenizers.Tokenizer``: one id per whitespace-separated word."""

    def __init__(self) -> None:
        self.special_tokens_flags: list[bool] = []

    def encode(self, text: str, add_special_tokens: bool = True) -> Any:
        self.special_tokens_flags.append(add_special_tokens)
        return SimpleNamespace(ids=list(range(len(text.split()))))


def test_hf_counts_token_ids_without_special_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeHFTokenizer()
    loaded: list[str] = []

    def load(repo_id: str) -> _FakeHFTokenizer:
        loaded.append(repo_id)
        return fake

    monkeypatch.setattr(tokenizers, "_hf_tokenizer", load)

    counter, name = resolve_tokenizer("hf:org/model")
    resolve_tokenizer("hf:org/model")

    assert name == "hf:org/model"
    assert counter("one two three") == 3
    assert counter("") == 1
    assert fake.special_tokens_flags == [False, False]
    assert loaded == ["org/model"]


@pytest.mark.parametrize("spec", ["hf", "hf:"])
def test_hf_requires_a_repo_id(spec: str) -> None:
    with pytest.raises(DatoonError, match="needs a Hugging Face repo id"):
        resolve_tokenizer(spec)


def test_hf_without_package_names_the_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "tokenizers", None)  # type: ignore[arg-type]
    with pytest.raises(DatoonError, match=r'pip install "datoon\[hf\]"'):
        resolve_tokenizer("hf:org/model")
