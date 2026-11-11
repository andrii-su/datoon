"""Conversion service that transforms JSON payloads into TOON when beneficial."""

from __future__ import annotations

import json
import math
from functools import lru_cache
from typing import Any

from toon_format import encode

from datoon.analyzer import analyze_payload
from datoon.errors import DatoonError
from datoon.models import (
    DEFAULT_TOKEN_ENCODING,
    ConversionConfig,
    ConversionOutcome,
    ConversionReport,
    PayloadAnalysis,
)

__all__ = ["DatoonError", "convert_json_for_llm", "estimate_tokens"]


def _reject_non_finite(constant: str) -> Any:
    """Reject Infinity/-Infinity/NaN, which are invalid JSON and break serialization."""
    raise DatoonError(
        f"Input contains non-finite constant '{constant}', which is not valid JSON."
    )


def _normalize_json(raw_text: str) -> tuple[Any, str]:
    """Parse and re-serialize JSON into a deterministic compact representation."""
    try:
        parsed = json.loads(raw_text, parse_constant=_reject_non_finite)
    except json.JSONDecodeError as exc:
        raise DatoonError(f"Invalid JSON input: {exc.msg} (pos={exc.pos}).") from exc

    normalized = json.dumps(
        parsed, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    )
    return parsed, normalized


@lru_cache(maxsize=8)
def _load_token_encoder(encoding: str) -> Any | None:
    """Load a token encoder once per name, None when the optional dep is absent."""
    try:
        import tiktoken  # type: ignore
    except ImportError:
        return None

    return tiktoken.get_encoding(encoding)


def estimate_tokens(text: str, encoding: str = DEFAULT_TOKEN_ENCODING) -> int:
    """Estimate token count with tiktoken when installed, else use a char heuristic."""
    encoder = _load_token_encoder(encoding)
    if encoder is not None:
        return len(encoder.encode(text))

    return max(1, math.ceil(len(text) / 3))


def _encode_toon(parsed: Any) -> str:
    """Encode an already-parsed JSON value as TOON with the official encoder."""
    try:
        toon_text = encode(parsed).strip()
    except Exception as exc:  # encoder errors vary; surface all as DatoonError
        raise DatoonError(f"TOON encoding failed: {exc}") from exc

    if not toon_text:
        raise DatoonError("TOON encoding returned empty output.")

    return f"{toon_text}\n"


def _build_skip_outcome(
    normalized_json: str,
    *,
    reason: str,
    config: ConversionConfig,
    input_tokens: int,
    analysis: PayloadAnalysis,
) -> ConversionOutcome:
    """Build a standard skip outcome to keep reporting consistent."""
    report = ConversionReport(
        decision="skip",
        reason=reason,
        was_forced=config.force,
        input_token_estimate=input_tokens,
        output_token_estimate=input_tokens,
        savings_ratio=0.0,
        analysis=analysis,
    )
    return ConversionOutcome(payload_text=normalized_json, report=report)


def convert_json_for_llm(raw_text: str, config: ConversionConfig) -> ConversionOutcome:
    """Convert JSON to TOON when structure and savings meet configured policy."""
    parsed, normalized_json = _normalize_json(raw_text)
    analysis = analyze_payload(parsed, config)
    input_tokens = estimate_tokens(normalized_json, config.token_encoding)

    if not analysis.is_candidate and not config.force:
        return _build_skip_outcome(
            normalized_json,
            reason=analysis.reason,
            config=config,
            input_tokens=input_tokens,
            analysis=analysis,
        )

    try:
        toon_text = _encode_toon(parsed)
    except DatoonError:
        if config.force:
            raise

        return _build_skip_outcome(
            normalized_json,
            reason="TOON encoding failed; falling back to JSON.",
            config=config,
            input_tokens=input_tokens,
            analysis=analysis,
        )

    output_tokens = estimate_tokens(toon_text, config.token_encoding)
    savings_ratio = (input_tokens - output_tokens) / input_tokens

    if savings_ratio < config.min_savings_ratio and not config.force:
        return _build_skip_outcome(
            normalized_json,
            reason=(
                f"Estimated savings {savings_ratio:.2%} below threshold "
                f"{config.min_savings_ratio:.2%}."
            ),
            config=config,
            input_tokens=input_tokens,
            analysis=analysis,
        )

    report = ConversionReport(
        decision="convert",
        reason=(
            f"Estimated savings {savings_ratio:.2%} "
            f"(threshold {config.min_savings_ratio:.2%})."
        ),
        was_forced=config.force,
        input_token_estimate=input_tokens,
        output_token_estimate=output_tokens,
        savings_ratio=savings_ratio,
        analysis=analysis,
    )
    return ConversionOutcome(payload_text=toon_text, report=report)
