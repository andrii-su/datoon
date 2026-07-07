"""Canonical exception types for datoon.

Kept in a leaf module so any layer — readers, converter, CLI, MCP — can raise
the datoon error taxonomy without importing a higher-level module.

Convention:

* ``DatoonError`` — the user's *payload* is malformed or unsuitable (invalid
  JSON/XML/YAML, non-object rows, a refused DTD). These are the errors surfaced
  to end users of the CLI/MCP.
* ``ValueError`` — a *usage* error in how datoon was called (unknown format
  name, text passed where a file path is required). Programmer-facing.
* ``ImportError`` — an optional extra needed for a format is not installed.
"""

from __future__ import annotations


class DatoonError(RuntimeError):
    """Raised when datoon cannot process the payload safely."""
