"""Integration tests against the real TOON CLI."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from datoon.converter import convert_json_for_llm
from datoon.models import ConversionConfig

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"
USERS_JSON_PATH = FIXTURES_DIR / "users.json"
USERS_EXPECTED_TOON_PATH = FIXTURES_DIR / "users.expected.toon"


def _npx_available() -> bool:
    """Check whether npx is installed and callable."""
    return shutil.which("npx") is not None


def _can_resolve_toon_cli() -> bool:
    """Check whether the TOON CLI package can be resolved by npx."""
    if not _npx_available():
        return False

    result = subprocess.run(
        ["npx", "--yes", "@toon-format/cli@2", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


pytestmark = pytest.mark.integration


@pytest.mark.skipif(
    not _can_resolve_toon_cli(),
    reason="npx or @toon-format/cli@2 is unavailable in this environment.",
)
def test_force_conversion_matches_golden_fixture() -> None:
    """Forced conversion should match the committed golden TOON output."""
    raw_json = USERS_JSON_PATH.read_text(encoding="utf-8")
    expected = USERS_EXPECTED_TOON_PATH.read_text(encoding="utf-8")

    outcome = convert_json_for_llm(raw_json, ConversionConfig(force=True))
    assert outcome.report.decision == "convert"
    assert outcome.payload_text == expected


@pytest.mark.skipif(
    not _can_resolve_toon_cli(),
    reason="npx or @toon-format/cli@2 is unavailable in this environment.",
)
def test_auto_mode_converts_uniform_fixture() -> None:
    """Auto mode should convert the uniform fixture because savings are significant."""
    raw_json = json.dumps(
        json.loads(USERS_JSON_PATH.read_text(encoding="utf-8")),
        separators=(",", ":"),
    )
    outcome = convert_json_for_llm(raw_json, ConversionConfig(min_savings_ratio=0.10))
    assert outcome.report.decision == "convert"
    assert outcome.report.savings_ratio >= 0.10
