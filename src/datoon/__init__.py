"""Core package for datoon JSON-to-TOON conversion tooling."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from datoon.converter import DatoonError, convert_json_for_llm
from datoon.models import (
    ConversionConfig,
    ConversionOutcome,
    ConversionReport,
    PayloadAnalysis,
)

__all__ = [
    "__version__",
    "convert_json_for_llm",
    "ConversionConfig",
    "ConversionOutcome",
    "ConversionReport",
    "PayloadAnalysis",
    "DatoonError",
]

try:
    __version__ = version("datoon")
except PackageNotFoundError:
    __version__ = "0.0.0"
