"""Conversion service that transforms JSON payloads into TOON when beneficial."""

from __future__ import annotations

import json
import math
import subprocess
from functools import lru_cache
from typing import Any

from datoon.analyzer import analyze_payload
from datoon.models import ConversionConfig, ConversionOutcome, ConversionReport

TOON_CLI_PACKAGE = "@toon-format/cli@3"


class DatoonError(RuntimeError):
    """Raised when datoon cannot process the payload safely."""


def _normalize_json(raw_text: str) -> tuple[Any, str]:
    """Parse and re-serialize JSON into a deterministic compact representation."""
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise DatoonError(f"Invalid JSON input: {exc.msg} (pos={exc.pos}).") from exc

    normalized = json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))
    return parsed, normalized


@lru_cache(maxsize=1)
def _load_token_encoder() -> Any | None:
    """Load a token encoder once, returning None when optional dependency is absent."""
    try:
        import tiktoken  # type: ignore
    except ImportError:
        return None

    return tiktoken.get_encoding("cl100k_base")


def estimate_tokens(text: str) -> int:
    """Estimate token count with tiktoken when installed, else use a char heuristic."""
    encoder = _load_token_encoder()
    if encoder is not None:
        return len(encoder.encode(text))

    return max(1, math.ceil(len(text) / 4))


def _run_toon_cli(normalized_json: str) -> str:
    """Convert normalized JSON to TOON via the official TOON CLI."""
    command = ["npx", "--yes", TOON_CLI_PACKAGE]

    try:
        result = subprocess.run(
            command,
            input=normalized_json,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise DatoonError(
            "`npx` is not available in PATH. Install Node.js before TOON conversion."
        ) from exc

    if result.returncode != 0:
        stderr = result.stderr.strip() or "unknown TOON CLI error"
        raise DatoonError(f"TOON CLI failed: {stderr}")

    toon_text = result.stdout.strip()
    if not toon_text:
        raise DatoonError("TOON CLI returned empty output.")

    return f"{toon_text}\n"


def _build_skip_outcome(
    normalized_json: str,
    *,
    reason: str,
    config: ConversionConfig,
    input_tokens: int,
    analysis: Any,
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
    input_tokens = estimate_tokens(normalized_json)

    if not analysis.is_candidate and not config.force:
        return _build_skip_outcome(
            normalized_json,
            reason=analysis.reason,
            config=config,
            input_tokens=input_tokens,
            analysis=analysis,
        )

    try:
        toon_text = _run_toon_cli(normalized_json)
    except DatoonError:
        if config.force:
            raise

        return _build_skip_outcome(
            normalized_json,
            reason="TOON conversion dependency unavailable; falling back to JSON.",
            config=config,
            input_tokens=input_tokens,
            analysis=analysis,
        )

    output_tokens = estimate_tokens(toon_text)
    savings_ratio = (input_tokens - output_tokens) / input_tokens if input_tokens else 0.0

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
