"""Core package for datoon JSON-to-TOON conversion tooling."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

__all__ = ["__version__"]

try:
    __version__ = version("datoon")
except PackageNotFoundError:
    __version__ = "0.0.0"
