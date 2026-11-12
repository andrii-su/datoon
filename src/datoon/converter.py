"""Conversion service that transforms JSON payloads into TOON when beneficial."""

from __future__ import annotations

import json
from typing import Any

from toon_format import encode

from datoon.analyzer import analyze_payload
from datoon.errors import DatoonError
from datoon.models import (
    ConversionConfig,
    ConversionOutcome,
    ConversionReport,
    PayloadAnalysis,
)
from datoon.readers import rows_to_json
from datoon.tokenizers import estimate_tokens, resolve_tokenizer

__all__ = [
    "DatoonError",
    "convert_data_for_llm",
    "convert_json_for_llm",
    "estimate_tokens",
]


def _reject_non_finite(constant: str) -> Any:
    """Reject Infinity/-Infinity/NaN, which are invalid JSON and break serialization."""
    raise DatoonError(
        f"Input contains non-finite constant '{constant}', which is not valid JSON."
    )


def _normalize_json(raw_text: str) -> tuple[Any, str]:
    """Parse and re-serialize JSON into a deterministic compact representation."""
    try:
        parsed = json.loads(raw_text, parse_constant=_reject_non_finite)
        normalized = json.dumps(
            parsed, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        )
    except json.JSONDecodeError as exc:
        raise DatoonError(f"Invalid JSON input: {exc.msg} (pos={exc.pos}).") from exc
    except RecursionError as exc:
        raise DatoonError("Invalid JSON input: nested too deeply.") from exc
    except ValueError as exc:
        # Not a syntax error: e.g. an integer past Python's digit limit.
        raise DatoonError(f"Invalid JSON input: {exc}.") from exc

    try:
        normalized.encode("utf-8")
    except UnicodeEncodeError as exc:
        # A lone surrogate ("\ud800") parses, but neither TOON nor the JSON
        # fallback could be sent anywhere as UTF-8.
        raise DatoonError(
            "Invalid JSON input: text holds an unpaired surrogate."
        ) from exc
    return parsed, normalized


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
    tokenizer_name: str,
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
        tokenizer=tokenizer_name,
        analysis=analysis,
    )
    return ConversionOutcome(payload_text=normalized_json, report=report)


def convert_json_for_llm(raw_text: str, config: ConversionConfig) -> ConversionOutcome:
    """Convert JSON to TOON when structure and savings meet configured policy.

    The tokenizer is resolved once per call and counts both the JSON and the
    TOON text. A tokenizer that cannot be resolved is a configuration error and
    raises ``DatoonError`` in auto and force mode alike.
    """
    parsed, normalized_json = _normalize_json(raw_text)
    counter, tokenizer_name = resolve_tokenizer(config.tokenizer)
    try:
        analysis = analyze_payload(parsed, config)
    except RecursionError as exc:
        raise DatoonError("Invalid JSON input: nested too deeply.") from exc
    input_tokens = estimate_tokens(normalized_json, counter)

    if not analysis.is_candidate and not config.force:
        return _build_skip_outcome(
            normalized_json,
            reason=analysis.reason,
            config=config,
            input_tokens=input_tokens,
            tokenizer_name=tokenizer_name,
            analysis=analysis,
        )

    try:
        toon_text = _encode_toon(parsed)
    except DatoonError as exc:
        if config.force:
            raise

        # Keep the stable prefix and suffix; the cause goes in between so a
        # caller can see why without rerunning with force.
        cause = exc.__cause__ or exc
        return _build_skip_outcome(
            normalized_json,
            reason=f"TOON encoding failed ({cause}); falling back to JSON.",
            config=config,
            input_tokens=input_tokens,
            tokenizer_name=tokenizer_name,
            analysis=analysis,
        )

    output_tokens = estimate_tokens(toon_text, counter)
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
            tokenizer_name=tokenizer_name,
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
        tokenizer=tokenizer_name,
        analysis=analysis,
    )
    return ConversionOutcome(payload_text=toon_text, report=report)


def convert_data_for_llm(
    data: Any, config: ConversionConfig | None = None
) -> ConversionOutcome:
    """Convert Python data to TOON under the same policy as ``convert_json_for_llm``.

    For a caller that holds rows or a parsed payload, not JSON text: a list of
    dicts from a database cursor, ``read_tabular`` or an API client. The data is
    serialised with ``rows_to_json``, so dates, datetimes, decimals and bytes
    are accepted; any other non-JSON type raises ``DatoonError``. ``config``
    defaults to ``ConversionConfig()``.
    """
    return convert_json_for_llm(rows_to_json(data), config or ConversionConfig())
