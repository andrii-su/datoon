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


@pytest.mark.parametrize("literal", ["Infinity", "-Infinity", "NaN"])
def test_convert_json_for_llm_rejects_non_finite_constants(literal: str) -> None:
    """Non-finite constants are invalid JSON per spec and must fail loudly."""
    with pytest.raises(DatoonError, match="non-finite"):
        convert_json_for_llm(f'{{"x": {literal}}}', ConversionConfig())


def test_policy_skips_non_uniform_arrays(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-uniform arrays should skip conversion before encoding."""
    called = {"value": False}

    def _unexpected(_: object) -> str:
        called["value"] = True
        raise AssertionError(
            "TOON encoder should not be called for non-candidate payloads."
        )

    monkeypatch.setattr("datoon.converter._encode_toon", _unexpected)
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

    def _unexpected(_: object) -> str:
        called["value"] = True
        raise AssertionError("TOON encoder should not be called when depth gate fails.")

    monkeypatch.setattr("datoon.converter._encode_toon", _unexpected)
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


def test_policy_converts_when_savings_above_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Payload should convert when estimated savings clear the threshold."""
    payload = _sample_uniform_payload()
    monkeypatch.setattr(
        "datoon.converter._encode_toon",
        lambda _: "rows[3]{id,value}:\n  1,a\n  2,b\n  3,c\n",
    )

    token_sequence = iter([100, 60])  # input, output
    monkeypatch.setattr(
        "datoon.converter.estimate_tokens", lambda *_a, **_k: next(token_sequence)
    )

    outcome = convert_json_for_llm(payload, ConversionConfig(min_savings_ratio=0.15))
    assert outcome.report.decision == "convert"
    assert outcome.report.output_token_estimate == 60


def test_policy_skips_when_savings_below_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Payload should skip when estimated savings are below configured threshold."""
    payload = _sample_uniform_payload()
    monkeypatch.setattr(
        "datoon.converter._encode_toon",
        lambda _: "rows[3]{id,value}:\n  1,a\n  2,b\n  3,c\n",
    )

    token_sequence = iter([100, 95])  # input, output
    monkeypatch.setattr(
        "datoon.converter.estimate_tokens", lambda *_a, **_k: next(token_sequence)
    )

    outcome = convert_json_for_llm(payload, ConversionConfig(min_savings_ratio=0.10))
    assert outcome.report.decision == "skip"
    assert "below threshold" in outcome.report.reason


def test_force_mode_raises_encoder_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force mode should propagate encoder failures rather than silently skipping."""
    payload = _sample_uniform_payload()

    def _raise_error(_: object) -> str:
        raise DatoonError("synthetic encoder failure")

    monkeypatch.setattr("datoon.converter._encode_toon", _raise_error)

    with pytest.raises(DatoonError, match="synthetic encoder failure"):
        convert_json_for_llm(payload, ConversionConfig(force=True))


def test_non_force_falls_back_to_json_on_encoder_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-force mode should skip and fallback when the encoder fails."""
    payload = _sample_uniform_payload()

    def _raise_error(_: object) -> str:
        raise DatoonError("synthetic encoder failure")

    monkeypatch.setattr("datoon.converter._encode_toon", _raise_error)
    outcome = convert_json_for_llm(payload, ConversionConfig(force=False))
    assert outcome.report.decision == "skip"
    assert "falling back to JSON" in outcome.report.reason


def test_real_encoder_failure_surfaces_as_datoon_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unexpected encoder exceptions must become DatoonError in force mode."""

    def _boom(*_a: object, **_k: object) -> str:
        raise RuntimeError("encoder exploded")

    monkeypatch.setattr("datoon.converter.encode", _boom)
    with pytest.raises(DatoonError, match="TOON encoding failed: encoder exploded"):
        convert_json_for_llm(_sample_uniform_payload(), ConversionConfig(force=True))


def test_encoder_failure_uses_stable_skip_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Auto mode falls back to JSON with a stable, specific skip reason."""

    def _boom(*_a: object, **_k: object) -> str:
        raise RuntimeError("encoder exploded")

    monkeypatch.setattr("datoon.converter.encode", _boom)
    outcome = convert_json_for_llm(_sample_uniform_payload(), ConversionConfig())
    assert outcome.report.decision == "skip"
    assert outcome.report.reason == "TOON encoding failed; falling back to JSON."


def test_conversion_preserves_values_and_keys() -> None:
    """Decoding the produced TOON must equal the input payload exactly."""
    from toon_format import decode

    payload = {
        "rows": [
            {
                "id": 1,
                "score": 0.5,
                "active": True,
                "note": None,
                "label": "",
                "text": "a,b",
                "created_at": "2026-01-02T03:04:05Z",
            },
            {
                "id": 2,
                "score": 1.25,
                "active": False,
                "note": None,
                "label": "",
                "text": "c,d",
                "created_at": "2026-01-03T03:04:05Z",
            },
            {
                "id": 3,
                "score": 2.0,
                "active": True,
                "note": None,
                "label": "",
                "text": "e,f",
                "created_at": "2026-01-04T03:04:05Z",
            },
        ]
    }
    outcome = convert_json_for_llm(json.dumps(payload), ConversionConfig(force=True))
    assert outcome.report.decision == "convert"
    assert decode(outcome.payload_text) == payload


def test_report_records_resolved_tokenizer_on_convert() -> None:
    """A converted payload reports the tokenizer that produced its estimates."""
    outcome = convert_json_for_llm(
        _sample_uniform_payload(), ConversionConfig(force=True, tokenizer="chars:2")
    )
    assert outcome.report.decision == "convert"
    assert outcome.report.tokenizer == "chars:2"
    assert json.loads(json.dumps(outcome.report.as_dict()))["tokenizer"] == "chars:2"


def test_report_records_resolved_tokenizer_on_skip() -> None:
    """A skipped payload reports the resolved tokenizer name, not the raw spec."""
    outcome = convert_json_for_llm('{"x":1}', ConversionConfig(tokenizer="chars"))
    assert outcome.report.decision == "skip"
    assert outcome.report.tokenizer == "chars:3"


def test_custom_tokenizer_counts_json_and_toon_and_is_named_custom() -> None:
    """A callable tokenizer counts both texts and is reported as custom."""
    seen: list[str] = []

    def counter(text: str) -> int:
        seen.append(text)
        return len(text)

    outcome = convert_json_for_llm(
        _sample_uniform_payload(), ConversionConfig(force=True, tokenizer=counter)
    )
    assert outcome.report.tokenizer == "custom"
    assert seen == [_sample_uniform_payload(), outcome.payload_text]
    assert outcome.report.output_token_estimate == len(outcome.payload_text)


@pytest.mark.parametrize("force", [False, True])
def test_unresolvable_tokenizer_raises_in_auto_and_force_mode(force: bool) -> None:
    """A bad tokenizer is a configuration error, never a silent JSON skip."""
    with pytest.raises(DatoonError, match="Unknown tokenizer 'nope'"):
        convert_json_for_llm(
            _sample_uniform_payload(), ConversionConfig(force=force, tokenizer="nope")
        )
