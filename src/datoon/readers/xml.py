"""XML reader using stdlib xml.etree.ElementTree.

The stdlib parser rejects external entities but expands internal ones, so a DTD
can smuggle a billion-laughs DoS. datoon may process untrusted payloads, so DTDs
are refused outright. ``<!DOCTYPE`` is a fixed XML token (no internal
whitespace), so a literal scan reliably catches every declaration expat would
process.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any

from datoon.errors import DatoonError
from datoon.readers._coerce import coerce_scalar as _coerce

_DOCTYPE_RE = re.compile(r"<!DOCTYPE", re.IGNORECASE)


def read_xml(text: str) -> list[dict[str, Any]]:
    """Parse XML into a list of row dicts from the dominant repeated child element."""
    if _DOCTYPE_RE.search(text):
        raise DatoonError(
            "XML with a DOCTYPE/DTD is not allowed (entity-expansion risk)."
        )

    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise DatoonError(f"Invalid XML: {exc}") from exc

    children = list(root)
    if not children:
        raise DatoonError("XML root element has no children.")

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
