"""Canonical exception types for datoon.

Kept in a leaf module so any layer — readers, converter, CLI, MCP — can raise
the datoon error taxonomy without importing a higher-level module.
"""

from __future__ import annotations


class DatoonError(RuntimeError):
    """Raised when datoon cannot process the payload safely."""
