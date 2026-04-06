"""Unit tests for conversion policy decisions and edge cases."""

from __future__ import annotations

import json

import pytest

from datoon.converter import DatoonError, convert_json_for_llm
from datoon.models import ConversionConfig


def _sample_uniform_payload() -> str:
    """Build a compact JSON payload with a uniform array."""
    payload = {
        "rows": [
            {"id": 1, "value": "a"},
            {"id": 2, "value": "b"},
            {"id": 3, "value": "c"},
        ]
    }
    return json.dumps(payload, separators=(",", ":"))


def test_convert_json_for_llm_rejects_invalid_json() -> None:
    """Invalid JSON must fail fast with explicit error."""
    with pytest.raises(DatoonError, match="Invalid JSON input"):
        convert_json_for_llm("{bad json", ConversionConfig())


def test_policy_skips_non_uniform_arrays(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-uniform arrays should skip conversion before CLI invocation."""
    called = {"value": False}

    def _unexpected(_: str) -> str:
        called["value"] = True
        raise AssertionError("TOON CLI should not be called for non-candidate payloads.")

    monkeypatch.setattr("datoon.converter._run_toon_cli", _unexpected)
    payload = json.dumps(
        {
            "rows": [
                {"id": 1, "name": "Ada"},
                {"id": 2, "email": "lin@example.com"},
                {"id": 3, "name": "Sam", "status": "new"},
            ]
        },
        separators=(",", ":"),
    )

    outcome = convert_json_for_llm(payload, ConversionConfig())
    assert outcome.report.decision == "skip"
    assert called["value"] is False


def test_policy_skips_deep_nested_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    """Depth gate should skip conversion for nested payloads."""
    called = {"value": False}

    def _unexpected(_: str) -> str:
        called["value"] = True
        raise AssertionError("TOON CLI should not be called when depth gate fails.")

    monkeypatch.setattr("datoon.converter._run_toon_cli", _unexpected)
    payload = json.dumps(
        {
            "root": {
                "l1": {
                    "l2": {
                        "l3": {
                            "rows": [
                                {"id": 1, "value": "a"},
                                {"id": 2, "value": "b"},
                                {"id": 3, "value": "c"},
                            ]
                        }
                    }
                }
            }
        },
        separators=(",", ":"),
    )
    outcome = convert_json_for_llm(payload, ConversionConfig(max_depth=4))
    assert outcome.report.decision == "skip"
    assert "max_depth" in outcome.report.reason
    assert called["value"] is False


def test_policy_converts_when_savings_above_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    """Payload should convert when estimated savings clear the threshold."""
    payload = _sample_uniform_payload()
    monkeypatch.setattr("datoon.converter._run_toon_cli", lambda _: "rows[3]{id,value}:\n  1,a\n  2,b\n  3,c\n")

    token_sequence = iter([100, 60])  # input, output
    monkeypatch.setattr("datoon.converter.estimate_tokens", lambda _: next(token_sequence))

    outcome = convert_json_for_llm(payload, ConversionConfig(min_savings_ratio=0.15))
    assert outcome.report.decision == "convert"
    assert outcome.report.output_token_estimate == 60


def test_policy_skips_when_savings_below_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    """Payload should skip when estimated savings are below configured threshold."""
    payload = _sample_uniform_payload()
    monkeypatch.setattr("datoon.converter._run_toon_cli", lambda _: "rows[3]{id,value}:\n  1,a\n  2,b\n  3,c\n")

    token_sequence = iter([100, 95])  # input, output
    monkeypatch.setattr("datoon.converter.estimate_tokens", lambda _: next(token_sequence))

    outcome = convert_json_for_llm(payload, ConversionConfig(min_savings_ratio=0.10))
    assert outcome.report.decision == "skip"
    assert "below threshold" in outcome.report.reason


def test_force_mode_raises_cli_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force mode should propagate CLI failures rather than silently skipping."""
    payload = _sample_uniform_payload()

    def _raise_error(_: str) -> str:
        raise DatoonError("synthetic cli failure")

    monkeypatch.setattr("datoon.converter._run_toon_cli", _raise_error)

    with pytest.raises(DatoonError, match="synthetic cli failure"):
        convert_json_for_llm(payload, ConversionConfig(force=True))


def test_non_force_falls_back_to_json_on_cli_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-force mode should skip and fallback when CLI fails."""
    payload = _sample_uniform_payload()

    def _raise_error(_: str) -> str:
        raise DatoonError("synthetic cli failure")

    monkeypatch.setattr("datoon.converter._run_toon_cli", _raise_error)
    outcome = convert_json_for_llm(payload, ConversionConfig(force=False))
    assert outcome.report.decision == "skip"
    assert "falling back to JSON" in outcome.report.reason
