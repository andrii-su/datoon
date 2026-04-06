"""Unit tests for datoon domain models."""

from __future__ import annotations

import pytest

from datoon.models import ConversionConfig


def test_conversion_config_accepts_valid_defaults() -> None:
    """Default config should be valid and stable."""
    config = ConversionConfig()
    assert config.min_savings_ratio == 0.15
    assert config.max_depth == 6
    assert config.min_uniform_rows == 3
    assert config.force is False


@pytest.mark.parametrize("value", [-0.1, 1.1])
def test_conversion_config_rejects_invalid_savings_ratio(value: float) -> None:
    """Savings ratio outside [0, 1] must be rejected."""
    with pytest.raises(ValueError, match="min_savings_ratio"):
        ConversionConfig(min_savings_ratio=value)


def test_conversion_config_rejects_invalid_depth() -> None:
    """Depth lower than 1 is invalid."""
    with pytest.raises(ValueError, match="max_depth"):
        ConversionConfig(max_depth=0)


def test_conversion_config_rejects_invalid_uniform_row_threshold() -> None:
    """At least two rows are required for uniform-array analysis."""
    with pytest.raises(ValueError, match="min_uniform_rows"):
        ConversionConfig(min_uniform_rows=1)
