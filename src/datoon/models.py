"""Domain models for conversion configuration and results."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

Decision = Literal["convert", "skip"]


@dataclass(frozen=True, slots=True)
class ConversionConfig:
    """Runtime configuration that governs auto-conversion behavior."""

    min_savings_ratio: float = 0.15
    max_depth: int = 6
    min_uniform_rows: int = 3
    force: bool = False

    def __post_init__(self) -> None:
        """Validate boundary values to avoid ambiguous runtime decisions."""
        if not 0 <= self.min_savings_ratio <= 1:
            raise ValueError("min_savings_ratio must be between 0 and 1.")
        if self.max_depth < 1:
            raise ValueError("max_depth must be at least 1.")
        if self.min_uniform_rows < 2:
            raise ValueError("min_uniform_rows must be at least 2.")


@dataclass(frozen=True, slots=True)
class PayloadAnalysis:
    """Heuristic analysis of whether a JSON payload is TOON-friendly."""

    is_candidate: bool
    reason: str
    max_depth: int
    uniform_array_count: int


@dataclass(frozen=True, slots=True)
class ConversionReport:
    """Metadata report for a conversion decision and savings estimate."""

    decision: Decision
    reason: str
    was_forced: bool
    input_token_estimate: int
    output_token_estimate: int
    savings_ratio: float
    analysis: PayloadAnalysis

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the report."""
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ConversionOutcome:
    """Container holding final payload text and its conversion report."""

    payload_text: str
    report: ConversionReport
