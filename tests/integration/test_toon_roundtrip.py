"""End-to-end tests against the real in-process TOON encoder."""

from __future__ import annotations

import json
from pathlib import Path

from toon_format import decode, encode

from datoon.converter import convert_json_for_llm
from datoon.models import ConversionConfig

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"
USERS_JSON_PATH = FIXTURES_DIR / "users.json"
USERS_EXPECTED_TOON_PATH = FIXTURES_DIR / "users.expected.toon"


def test_encoder_round_trips_users_fixture() -> None:
    """The real encoder must round-trip the users fixture without loss."""
    data = json.loads(USERS_JSON_PATH.read_text(encoding="utf-8"))
    assert decode(encode(data)) == data


def test_golden_toon_fixture_decodes_to_users_json() -> None:
    """The committed golden TOON output must decode to the fixture JSON."""
    data = json.loads(USERS_JSON_PATH.read_text(encoding="utf-8"))
    expected = USERS_EXPECTED_TOON_PATH.read_text(encoding="utf-8")
    assert decode(expected) == data


def test_force_conversion_matches_golden_toon_fixture() -> None:
    """Forced conversion must reproduce the committed golden TOON text exactly."""
    raw_json = USERS_JSON_PATH.read_text(encoding="utf-8")
    expected = USERS_EXPECTED_TOON_PATH.read_text(encoding="utf-8")
    outcome = convert_json_for_llm(raw_json, ConversionConfig(force=True))
    assert outcome.payload_text.strip() == expected.strip()


def test_force_conversion_decodes_to_input() -> None:
    """Forced conversion must produce TOON that decodes to the original data."""
    raw_json = USERS_JSON_PATH.read_text(encoding="utf-8")
    outcome = convert_json_for_llm(raw_json, ConversionConfig(force=True))
    assert outcome.report.decision == "convert"
    assert outcome.payload_text.endswith("\n")
    assert decode(outcome.payload_text) == json.loads(raw_json)


def test_auto_mode_converts_uniform_fixture() -> None:
    """Auto mode should convert the uniform fixture because savings are significant."""
    raw_json = json.dumps(
        json.loads(USERS_JSON_PATH.read_text(encoding="utf-8")),
        separators=(",", ":"),
    )
    outcome = convert_json_for_llm(raw_json, ConversionConfig(min_savings_ratio=0.10))
    assert outcome.report.decision == "convert"
    assert outcome.report.savings_ratio >= 0.10
