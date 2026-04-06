"""Payload analysis helpers used to decide if TOON conversion is beneficial."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from datoon.models import ConversionConfig, PayloadAnalysis


def _max_depth(value: Any, depth: int = 1) -> int:
    """Compute the maximum nested depth for JSON-like payloads."""
    if isinstance(value, dict):
        if not value:
            return depth
        return max(_max_depth(child, depth + 1) for child in value.values())

    if isinstance(value, list):
        if not value:
            return depth
        return max(_max_depth(child, depth + 1) for child in value)

    return depth


def _iter_arrays(value: Any) -> Iterable[list[Any]]:
    """Yield every list node found within a nested JSON-like structure."""
    if isinstance(value, list):
        yield value
        for child in value:
            yield from _iter_arrays(child)
        return

    if isinstance(value, dict):
        for child in value.values():
            yield from _iter_arrays(child)


def _is_uniform_object_array(items: list[Any], min_rows: int) -> bool:
    """Check whether list entries are object rows with identical key sets."""
    if len(items) < min_rows:
        return False
    if not all(isinstance(item, dict) for item in items):
        return False

    first_keys = set(items[0].keys())
    if not first_keys:
        return False

    return all(set(item.keys()) == first_keys for item in items)


def analyze_payload(data: Any, config: ConversionConfig) -> PayloadAnalysis:
    """Evaluate whether payload structure is a practical TOON candidate."""
    max_depth = _max_depth(data)
    uniform_array_count = sum(
        1
        for items in _iter_arrays(data)
        if _is_uniform_object_array(items, config.min_uniform_rows)
    )

    if uniform_array_count == 0:
        return PayloadAnalysis(
            is_candidate=False,
            reason=(
                "No uniform object arrays found with at least "
                f"{config.min_uniform_rows} rows."
            ),
            max_depth=max_depth,
            uniform_array_count=0,
        )

    if max_depth > config.max_depth:
        return PayloadAnalysis(
            is_candidate=False,
            reason=f"Payload depth {max_depth} exceeds max_depth {config.max_depth}.",
            max_depth=max_depth,
            uniform_array_count=uniform_array_count,
        )

    return PayloadAnalysis(
        is_candidate=True,
        reason=(
            f"Detected {uniform_array_count} uniform object array(s) "
            f"within depth {max_depth}."
        ),
        max_depth=max_depth,
        uniform_array_count=uniform_array_count,
    )
