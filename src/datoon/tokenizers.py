"""Selectable token counters for datoon's token estimates.

A tokenizer is chosen with one value in one of two forms:

* a spec string ``kind[:arg]``:

  - ``auto`` (default): ``tiktoken:o200k_base`` when tiktoken is installed,
    else ``chars:3``. The only spec that falls back silently.
  - ``chars`` / ``chars:<N>``: ``ceil(len(text) / N)``, default ``N = 3``.
  - ``tiktoken`` / ``tiktoken:<encoding>``: default ``o200k_base``; needs
    ``datoon[tokens]``.
  - ``claude:<model-id>``: Anthropic token counting API; needs
    ``datoon[claude]`` and Anthropic credentials in the environment.
  - ``hf:<repo-id>``: a Hugging Face ``tokenizers`` tokenizer; needs
    ``datoon[hf]``.

* any callable ``str -> int``, reported as ``custom``.

Every count is an estimate of the payload's own tokens and is never below 1.
Optional packages are imported lazily, so datoon stays importable without them.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from functools import lru_cache
from typing import Any

from datoon.errors import DatoonError

__all__ = [
    "DEFAULT_TOKENIZER",
    "TOKENIZER_ENV_VAR",
    "TokenCounter",
    "estimate_tokens",
    "resolve_tokenizer",
]

TokenCounter = Callable[[str], int]

DEFAULT_TOKENIZER = "auto"
TOKENIZER_ENV_VAR = "DATOON_TOKENIZER"

# o200k_base matches GPT-4o and the o-series; closer to modern targets than
# the older cl100k_base.
DEFAULT_TIKTOKEN_ENCODING = "o200k_base"
DEFAULT_CHARS_PER_TOKEN = 3.0
CUSTOM_TOKENIZER_NAME = "custom"

# A single ASCII character the Claude counter sends once per model to measure
# the message framing that count_tokens adds around the payload.
_CLAUDE_OVERHEAD_MARKER = "x"
_CLAUDE_COUNT_CACHE_SIZE = 4096
_SPEC_CACHE_SIZE = 32

_SPEC_HELP = (
    "Expected one of: auto, chars[:N], tiktoken[:ENCODING], claude:MODEL_ID, "
    "hf:REPO_ID, or a callable str -> int."
)


def _missing_package(kind: str, package: str, extra: str) -> DatoonError:
    """Build the error raised when an explicit spec needs an absent package."""
    return DatoonError(
        f"The '{kind}' tokenizer needs the '{package}' package: "
        f'pip install "datoon[{extra}]"'
    )


def _chars_counter(arg: str) -> tuple[TokenCounter, str]:
    """Build the character-heuristic counter, ``ceil(len / N)``."""
    if not arg:
        chars_per_token = DEFAULT_CHARS_PER_TOKEN
    else:
        try:
            chars_per_token = float(arg)
        except ValueError:
            chars_per_token = math.nan
        if not math.isfinite(chars_per_token) or chars_per_token <= 0:
            raise DatoonError(
                f"Invalid tokenizer 'chars:{arg}': N must be a number greater than 0."
            )

    def count(text: str) -> int:
        return max(1, math.ceil(len(text) / chars_per_token))

    return count, f"chars:{chars_per_token:g}"


def _tiktoken_counter(encoding_name: str) -> tuple[TokenCounter, str]:
    """Build a tiktoken counter; raises when tiktoken or the encoding is absent."""
    try:
        import tiktoken  # type: ignore
    except ImportError as exc:
        raise _missing_package("tiktoken", "tiktoken", "tokens") from exc

    try:
        encoder = tiktoken.get_encoding(encoding_name)
    except ValueError as exc:
        raise DatoonError(
            f"Unknown tiktoken encoding '{encoding_name}': {exc}"
        ) from exc
    except Exception as exc:  # first use downloads the encoding file
        raise DatoonError(
            f"Could not load tiktoken encoding '{encoding_name}': "
            f"{type(exc).__name__}: {exc}"
        ) from exc

    def count(text: str) -> int:
        return max(1, len(encoder.encode(text)))

    return count, f"tiktoken:{encoding_name}"


def _auto_counter() -> tuple[TokenCounter, str]:
    """Pick tiktoken o200k_base when installed, else the char heuristic."""
    try:
        import tiktoken  # type: ignore  # noqa: F401
    except ImportError:
        return _chars_counter("")
    return _tiktoken_counter(DEFAULT_TIKTOKEN_ENCODING)


def _anthropic_client() -> Any:
    """Create an Anthropic client that resolves credentials the SDK's own way.

    Kept as a module-level builder so tests can replace it with a fake client.
    """
    try:
        import anthropic
    except ImportError as exc:
        raise _missing_package("claude", "anthropic", "claude") from exc

    try:
        return anthropic.Anthropic()
    except anthropic.AnthropicError as exc:
        raise DatoonError(
            f"Could not create an Anthropic client: {type(exc).__name__}: {exc}"
        ) from exc


def _claude_counter(model: str, client: Any) -> TokenCounter:
    """Build a counter backed by the Anthropic token counting API.

    ``count_tokens`` counts a whole user message, not a bare string, so the
    counter subtracts a per-model framing overhead measured once: it counts a
    one-character message and takes ``overhead = count(marker) - 1``. This is
    an approximation; Anthropic documents the count as an estimate and does not
    state that the overhead is constant. Counts are cached per text, and the
    result is never below 1. Empty text returns 1 without an API call.
    """

    def count_message(text: str) -> int:
        try:
            response = client.messages.count_tokens(
                model=model, messages=[{"role": "user", "content": text}]
            )
        except Exception as exc:  # SDK/network errors vary; surface as DatoonError
            # The SDK raises TypeError when no credentials resolve.
            if isinstance(exc, TypeError) and "authentication" in str(exc).lower():
                raise DatoonError(
                    "The 'claude' tokenizer needs Anthropic credentials: set "
                    "ANTHROPIC_API_KEY in the environment."
                ) from exc
            raise DatoonError(
                f"Anthropic token counting failed for model '{model}': "
                f"{type(exc).__name__}: {exc}"
            ) from exc
        return int(response.input_tokens)

    overhead = count_message(_CLAUDE_OVERHEAD_MARKER) - 1

    @lru_cache(maxsize=_CLAUDE_COUNT_CACHE_SIZE)
    def count(text: str) -> int:
        if not text:
            return 1
        return max(1, count_message(text) - overhead)

    return count


def _hf_tokenizer(repo_id: str) -> Any:
    """Load a Hugging Face tokenizer by repo id.

    Kept as a module-level builder so tests can replace it with a fake.
    """
    try:
        from tokenizers import Tokenizer  # type: ignore
    except ImportError as exc:
        raise _missing_package("hf", "tokenizers", "hf") from exc

    try:
        return Tokenizer.from_pretrained(repo_id)
    except Exception as exc:  # hub/network errors vary; surface as DatoonError
        raise DatoonError(
            f"Could not load Hugging Face tokenizer '{repo_id}': "
            f"{type(exc).__name__}: {exc}"
        ) from exc


def _hf_counter(tokenizer: Any) -> TokenCounter:
    """Build a counter over a loaded ``tokenizers.Tokenizer``.

    Special tokens (BOS/EOS) are not added: the count covers the payload text
    only, as it would appear inside a larger prompt.
    """

    def count(text: str) -> int:
        return max(1, len(tokenizer.encode(text, add_special_tokens=False).ids))

    return count


@lru_cache(maxsize=_SPEC_CACHE_SIZE)
def _resolve_spec(spec: str) -> tuple[TokenCounter, str]:
    """Resolve one spec string to a counter; cached so clients load once."""
    kind, separator, arg = spec.strip().partition(":")
    kind = kind.strip().lower()
    arg = arg.strip()

    if kind == "auto":
        if separator:
            raise DatoonError(f"Invalid tokenizer '{spec}': 'auto' takes no argument.")
        return _auto_counter()
    if kind == "chars":
        if separator and not arg:
            raise DatoonError(f"Invalid tokenizer '{spec}': missing N after 'chars:'.")
        return _chars_counter(arg)
    if kind == "tiktoken":
        if separator and not arg:
            raise DatoonError(
                f"Invalid tokenizer '{spec}': missing encoding after 'tiktoken:'."
            )
        return _tiktoken_counter(arg or DEFAULT_TIKTOKEN_ENCODING)
    if kind == "claude":
        if not arg:
            raise DatoonError(
                "The 'claude' tokenizer needs a model id, "
                "e.g. 'claude:claude-opus-5-5'."
            )
        return _claude_counter(arg, _anthropic_client()), f"claude:{arg}"
    if kind == "hf":
        if not arg:
            raise DatoonError(
                "The 'hf' tokenizer needs a Hugging Face repo id, "
                "e.g. 'hf:Qwen/Qwen2.5-7B-Instruct'."
            )
        return _hf_counter(_hf_tokenizer(arg)), f"hf:{arg}"

    raise DatoonError(f"Unknown tokenizer '{spec}'. {_SPEC_HELP}")


def resolve_tokenizer(spec: str | TokenCounter) -> tuple[TokenCounter, str]:
    """Resolve a tokenizer spec or callable to ``(counter, name)``.

    The name is what reports show: ``custom`` for a callable, and the resolved
    form for a spec string (``auto`` becomes ``tiktoken:o200k_base`` or
    ``chars:3``). Raises ``DatoonError`` for an unknown kind, a malformed
    argument, a missing optional package or missing credentials.
    """
    if isinstance(spec, str):
        if not spec.strip():
            raise DatoonError(f"Tokenizer spec must not be empty. {_SPEC_HELP}")
        return _resolve_spec(spec)
    if callable(spec):
        return spec, CUSTOM_TOKENIZER_NAME
    raise DatoonError(
        f"Tokenizer must be a spec string or a callable, got {type(spec).__name__}. "
        f"{_SPEC_HELP}"
    )


def estimate_tokens(
    text: str, tokenizer: str | TokenCounter = DEFAULT_TOKENIZER
) -> int:
    """Estimate the token count of ``text`` with the selected tokenizer.

    The result is never below 1. A custom counter must return an ``int``.
    """
    counter, name = resolve_tokenizer(tokenizer)
    count = counter(text)
    if isinstance(count, bool) or not isinstance(count, int):
        raise DatoonError(
            f"Tokenizer '{name}' returned {type(count).__name__}, expected int."
        )
    return max(1, count)
