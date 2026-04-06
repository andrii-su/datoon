"""Unit tests for payload structure analysis."""

from __future__ import annotations

from datoon.analyzer import analyze_payload
from datoon.models import ConversionConfig


def test_analyze_payload_detects_uniform_object_array() -> None:
    """Uniform arrays should be treated as TOON candidates."""
    data = {
        "rows": [
            {"id": 1, "value": "a"},
            {"id": 2, "value": "b"},
            {"id": 3, "value": "c"},
        ]
    }
    analysis = analyze_payload(data, ConversionConfig())
    assert analysis.is_candidate is True
    assert analysis.uniform_array_count == 1


def test_analyze_payload_rejects_non_uniform_array() -> None:
    """Non-uniform object arrays should be skipped."""
    data = {
        "rows": [
            {"id": 1, "value": "a"},
            {"id": 2, "name": "lin"},
            {"id": 3, "value": "c", "status": "new"},
        ]
    }
    analysis = analyze_payload(data, ConversionConfig())
    assert analysis.is_candidate is False
    assert "No uniform object arrays" in analysis.reason


def test_analyze_payload_rejects_excessive_depth() -> None:
    """Deeply nested payloads should be rejected by depth gate."""
    data = {
        "a": {
            "b": {
                "c": {
                    "d": {
                        "e": {
                            "f": {
                                "rows": [
                                    {"id": 1, "value": "a"},
                                    {"id": 2, "value": "b"},
                                    {"id": 3, "value": "c"},
                                ]
                            }
                        }
                    }
                }
            }
        }
    }
    config = ConversionConfig(max_depth=5)
    analysis = analyze_payload(data, config)
    assert analysis.is_candidate is False
    assert "exceeds max_depth" in analysis.reason
