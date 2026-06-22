"""YAML reader (requires pyyaml extra: pip install 'datoon[yaml]')."""

from __future__ import annotations

from typing import Any


def read_yaml(text: str) -> list[dict[str, Any]]:
    """Parse YAML text into a list of row dicts."""
    try:
        import yaml  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "YAML support requires the 'yaml' extra: pip install 'datoon[yaml]'"
        ) from exc

    data = yaml.safe_load(text)
    return _normalize(data)


def _normalize(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        lists = [v for v in data.values() if isinstance(v, list) and v]
        if len(lists) == 1:
            return lists[0]
    raise ValueError(
        "YAML must be a list of objects, or a mapping with exactly one list value."
    )
