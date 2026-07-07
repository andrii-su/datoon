"""XML reader using stdlib xml.etree.ElementTree."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

from datoon.readers._coerce import coerce_scalar as _coerce


def read_xml(text: str) -> list[dict[str, Any]]:
    """Parse XML into a list of row dicts from the dominant repeated child element."""
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid XML: {exc}") from exc

    children = list(root)
    if not children:
        raise ValueError("XML root element has no children.")

    tag_counts: dict[str, int] = {}
    for child in children:
        tag_counts[child.tag] = tag_counts.get(child.tag, 0) + 1
    dominant_tag = max(tag_counts, key=lambda t: tag_counts[t])
    items = [c for c in children if c.tag == dominant_tag]

    return [_element_to_dict(item) for item in items]


def _element_to_dict(element: ET.Element) -> dict[str, Any]:
    result: dict[str, Any] = {k: _coerce(v) for k, v in element.attrib.items()}
    for child in element:
        if list(child):
            result[child.tag] = _element_to_dict(child)
        else:
            result[child.tag] = _coerce(child.text or "")
    if not list(element) and element.text and element.text.strip():
        result["_text"] = element.text.strip()
    return result
