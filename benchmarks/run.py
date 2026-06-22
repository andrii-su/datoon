#!/usr/bin/env python3
"""Benchmark JSON vs TOON efficiency and datoon auto-conversion decisions."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import datoon
from datoon.converter import DatoonError, convert_json_for_llm, estimate_tokens
from datoon.models import ConversionConfig
from datoon.readers import read_tabular

SCRIPT_VERSION = datoon.__version__
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_DIR = SCRIPT_DIR.parent
PAYLOADS_PATH = SCRIPT_DIR / "payloads.json"
README_PATH = REPO_DIR / "README.md"
RESULTS_DIR = SCRIPT_DIR / "results"
BENCHMARK_START = "<!-- BENCHMARK-TABLE-START -->"
BENCHMARK_END = "<!-- BENCHMARK-TABLE-END -->"
FORMAT_BENCHMARK_START = "<!-- FORMAT-BENCHMARK-TABLE-START -->"
FORMAT_BENCHMARK_END = "<!-- FORMAT-BENCHMARK-TABLE-END -->"


@dataclass(slots=True, frozen=True)
class BenchmarkRow:
    """Single payload benchmark result."""

    payload_id: str
    category: str
    description: str
    json_tokens: int
    toon_tokens: int | None
    raw_savings_pct: float | None
    auto_decision: str
    auto_tokens: int
    auto_savings_pct: float
    auto_reason: str
    raw_error: str | None = None


@dataclass(slots=True, frozen=True)
class BenchmarkSummary:
    """Aggregated benchmark statistics."""

    payload_count: int
    raw_success_count: int
    auto_convert_count: int
    avg_json_tokens: int
    avg_toon_tokens: int | None
    avg_raw_savings_pct: float | None
    avg_auto_tokens: int
    avg_auto_savings_pct: float


def load_payloads(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Load benchmark payloads from JSON config file.

    Returns (json_payloads, format_payloads).
    """
    with path.open(encoding="utf-8") as file:
        parsed = json.load(file)

    payloads = parsed.get("payloads")
    if not isinstance(payloads, list) or not payloads:
        raise ValueError("payloads.json must contain a non-empty `payloads` list.")

    format_payloads = parsed.get("format_payloads", [])
    return payloads, format_payloads


def to_compact_json(data: Any) -> str:
    """Normalize payload into compact deterministic JSON."""
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def sha256_file(path: Path) -> str:
    """Compute SHA-256 digest for reproducibility tracking."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def to_pct(value: float) -> float:
    """Convert ratio to percentage with one decimal."""
    return round(value * 100, 1)


def benchmark_payload(
    payload: dict[str, Any],
    *,
    auto_config: ConversionConfig,
    force_config: ConversionConfig,
) -> BenchmarkRow:
    """Run one benchmark entry against forced and auto datoon flows."""
    payload_id = str(payload.get("id", "unknown"))
    category = str(payload.get("category", "unknown"))
    description = str(payload.get("description", ""))
    data = payload.get("data")
    fmt = str(payload.get("format", "json"))

    if fmt == "json":
        raw_json = to_compact_json(data)
    else:
        try:
            rows = read_tabular(fmt, text=str(data))
            raw_json = to_compact_json(rows)
        except ImportError as exc:
            return BenchmarkRow(
                payload_id=payload_id,
                category=category,
                description=description,
                json_tokens=0,
                toon_tokens=None,
                raw_savings_pct=None,
                auto_decision="skip",
                auto_tokens=0,
                auto_savings_pct=0.0,
                auto_reason=f"Missing dependency: {exc}",
                raw_error=str(exc),
            )

    json_tokens = estimate_tokens(raw_json)

    toon_tokens: int | None = None
    raw_savings_pct: float | None = None
    raw_error: str | None = None

    try:
        forced = convert_json_for_llm(raw_json, force_config)
        toon_tokens = forced.report.output_token_estimate
        raw_ratio = 1 - (toon_tokens / json_tokens) if json_tokens else 0.0
        raw_savings_pct = to_pct(raw_ratio)
    except DatoonError as exc:
        raw_error = str(exc)

    auto = convert_json_for_llm(raw_json, auto_config)
    auto_tokens = auto.report.output_token_estimate
    auto_ratio = 1 - (auto_tokens / json_tokens) if json_tokens else 0.0

    return BenchmarkRow(
        payload_id=payload_id,
        category=category,
        description=description,
        json_tokens=json_tokens,
        toon_tokens=toon_tokens,
        raw_savings_pct=raw_savings_pct,
        auto_decision=auto.report.decision,
        auto_tokens=auto_tokens,
        auto_savings_pct=to_pct(auto_ratio),
        auto_reason=auto.report.reason,
        raw_error=raw_error,
    )


def compute_summary(rows: list[BenchmarkRow]) -> BenchmarkSummary:
    """Compute aggregate metrics across benchmark rows."""
    raw_rows = [
        row
        for row in rows
        if row.toon_tokens is not None and row.raw_savings_pct is not None
    ]
    avg_toon = (
        round(
            statistics.mean(
                row.toon_tokens for row in raw_rows if row.toon_tokens is not None
            )
        )
        if raw_rows
        else None
    )
    avg_raw_savings = (
        round(
            statistics.mean(
                row.raw_savings_pct
                for row in raw_rows
                if row.raw_savings_pct is not None
            ),
            1,
        )
        if raw_rows
        else None
    )

    return BenchmarkSummary(
        payload_count=len(rows),
        raw_success_count=len(raw_rows),
        auto_convert_count=sum(1 for row in rows if row.auto_decision == "convert"),
        avg_json_tokens=round(statistics.mean(row.json_tokens for row in rows)),
        avg_toon_tokens=avg_toon,
        avg_raw_savings_pct=avg_raw_savings,
        avg_auto_tokens=round(statistics.mean(row.auto_tokens for row in rows)),
        avg_auto_savings_pct=round(
            statistics.mean(row.auto_savings_pct for row in rows), 1
        ),
    )


def format_table(rows: list[BenchmarkRow], summary: BenchmarkSummary) -> str:
    """Render markdown table for README and terminal output."""
    lines = [
        "| Dataset | JSON | TOON (forced) | Raw Saved | Auto | Auto Tokens | Auto Saved |",
        "|---|---:|---:|---:|---|---:|---:|",
    ]
    for row in rows:
        toon_value = str(row.toon_tokens) if row.toon_tokens is not None else "n/a"
        raw_saved = (
            f"{row.raw_savings_pct:.1f}%" if row.raw_savings_pct is not None else "n/a"
        )
        lines.append(
            f"| {row.payload_id} | {row.json_tokens} | {toon_value} | "
            f"{raw_saved} | {row.auto_decision} | {row.auto_tokens} | "
            f"{row.auto_savings_pct:.1f}% |"
        )

    avg_toon = (
        str(summary.avg_toon_tokens) if summary.avg_toon_tokens is not None else "n/a"
    )
    avg_raw_saved = (
        f"{summary.avg_raw_savings_pct:.1f}%"
        if summary.avg_raw_savings_pct is not None
        else "n/a"
    )
    lines.append(
        f"| **Average** | **{summary.avg_json_tokens}** | **{avg_toon}** | "
        f"**{avg_raw_saved}** | **{summary.auto_convert_count}/{summary.payload_count} convert** | "
        f"**{summary.avg_auto_tokens}** | **{summary.avg_auto_savings_pct:.1f}%** |"
    )
    lines.append("")
    lines.append(
        f"*Forced conversion succeeded for {summary.raw_success_count}/{summary.payload_count} payloads.*"
    )
    return "\n".join(lines)


def save_results(
    rows: list[BenchmarkRow],
    summary: BenchmarkSummary,
    *,
    payloads_sha: str,
    config: ConversionConfig,
) -> Path:
    """Save benchmark output to versioned JSON artifact."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output = {
        "metadata": {
            "script_version": SCRIPT_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "payloads_sha256": payloads_sha,
            "config": {
                "min_savings_ratio": config.min_savings_ratio,
                "max_depth": config.max_depth,
                "min_uniform_rows": config.min_uniform_rows,
            },
        },
        "summary": asdict(summary),
        "rows": [asdict(row) for row in rows],
    }
    output_path = RESULTS_DIR / f"benchmark_{timestamp}.json"
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(output, file, ensure_ascii=False, indent=2)
        file.write("\n")
    return output_path


def format_table_formats(rows: list[BenchmarkRow], summary: BenchmarkSummary) -> str:
    """Render markdown table for format benchmark results."""
    lines = [
        "| Dataset | Format | JSON Tokens | TOON (forced) | Auto | Auto Tokens | Auto Saved |",
        "|---|---|---:|---:|---|---:|---:|",
    ]
    for row in rows:
        toon_value = str(row.toon_tokens) if row.toon_tokens is not None else "n/a"
        fmt = row.category
        skipped = row.json_tokens == 0
        json_col = str(row.json_tokens) if not skipped else "n/a"
        lines.append(
            f"| {row.payload_id} | {fmt} | {json_col} | {toon_value} | "
            f"{row.auto_decision} | {row.auto_tokens if not skipped else 'n/a'} | "
            f"{row.auto_savings_pct:.1f}% |"
        )

    avg_toon = (
        str(summary.avg_toon_tokens) if summary.avg_toon_tokens is not None else "n/a"
    )
    valid = [r for r in rows if r.json_tokens > 0]
    if valid:
        lines.append(
            f"| **Average** | — | **{summary.avg_json_tokens}** | **{avg_toon}** | "
            f"**{summary.auto_convert_count}/{summary.payload_count} convert** | "
            f"**{summary.avg_auto_tokens}** | **{summary.avg_auto_savings_pct:.1f}%** |"
        )
    lines.append("")
    lines.append(
        f"*Forced conversion succeeded for {summary.raw_success_count}/{summary.payload_count} payloads.*"
    )
    return "\n".join(lines)


def _replace_between_markers(
    content: str, start_marker: str, end_marker: str, replacement: str
) -> str:
    """Replace content between two markers."""
    start = content.find(start_marker)
    end = content.find(end_marker)
    if start == -1 or end == -1:
        raise RuntimeError(
            f"README markers '{start_marker}' / '{end_marker}' are missing."
        )
    before = content[: start + len(start_marker)]
    after = content[end:]
    return f"{before}\n{replacement}\n{after}"


def update_readme(table_md: str) -> None:
    """Replace benchmark table block in README by marker comments."""
    content = README_PATH.read_text(encoding="utf-8")
    updated = _replace_between_markers(
        content, BENCHMARK_START, BENCHMARK_END, table_md
    )
    README_PATH.write_text(updated, encoding="utf-8")


def update_format_readme(table_md: str) -> None:
    """Replace format benchmark table block in README by marker comments."""
    content = README_PATH.read_text(encoding="utf-8")
    updated = _replace_between_markers(
        content, FORMAT_BENCHMARK_START, FORMAT_BENCHMARK_END, table_md
    )
    README_PATH.write_text(updated, encoding="utf-8")


def dry_run(
    payloads: list[dict[str, Any]],
    format_payloads: list[dict[str, Any]],
    config: ConversionConfig,
) -> None:
    """Print benchmark configuration without running conversions."""
    print("Dry run configuration:")
    print(f"- min_savings_ratio: {config.min_savings_ratio}")
    print(f"- max_depth: {config.max_depth}")
    print(f"- min_uniform_rows: {config.min_uniform_rows}")
    print(f"- json payloads: {len(payloads)}")
    for payload in payloads:
        print(
            f"  - {payload.get('id', 'unknown')} ({payload.get('category', 'unknown')})"
        )
    print(f"- format payloads: {len(format_payloads)}")
    for payload in format_payloads:
        print(
            f"  - {payload.get('id', 'unknown')} "
            f"({payload.get('format', 'json')}: {payload.get('category', 'unknown')})"
        )


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Run datoon JSON/TOON benchmarks.")
    parser.add_argument(
        "--payloads",
        default=str(PAYLOADS_PATH),
        help="Path to benchmark payload config (default: benchmarks/payloads.json).",
    )
    parser.add_argument(
        "--min-savings",
        type=float,
        default=0.15,
        help="Auto mode min savings threshold.",
    )
    parser.add_argument(
        "--max-depth", type=int, default=6, help="Auto mode max payload depth."
    )
    parser.add_argument(
        "--min-uniform-rows",
        type=int,
        default=3,
        help="Auto mode minimum rows for uniform object arrays.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print benchmark plan without conversion.",
    )
    parser.add_argument(
        "--update-readme",
        action="store_true",
        help="Update README benchmark block between markers.",
    )
    parser.add_argument(
        "--formats",
        action="store_true",
        help="Run format conversion benchmarks (CSV, JSONL, XML, YAML).",
    )
    return parser.parse_args()


def main() -> int:
    """Execute benchmark and return process exit code."""
    args = parse_args()
    payload_path = Path(args.payloads)
    payloads, format_payloads = load_payloads(payload_path)

    config = ConversionConfig(
        min_savings_ratio=args.min_savings,
        max_depth=args.max_depth,
        min_uniform_rows=args.min_uniform_rows,
        force=False,
    )
    force_config = ConversionConfig(
        min_savings_ratio=0.0,
        max_depth=max(64, args.max_depth),
        min_uniform_rows=2,
        force=True,
    )

    if args.dry_run:
        dry_run(payloads, format_payloads, config)
        return 0

    # --- JSON benchmark ---
    rows: list[BenchmarkRow] = []
    for index, payload in enumerate(payloads, start=1):
        payload_id = payload.get("id", "unknown")
        print(f"[{index}/{len(payloads)}] {payload_id}", file=sys.stderr)
        row = benchmark_payload(payload, auto_config=config, force_config=force_config)
        rows.append(row)

    summary = compute_summary(rows)
    table = format_table(rows, summary)
    payloads_sha = sha256_file(payload_path)
    output_path = save_results(rows, summary, payloads_sha=payloads_sha, config=config)
    print(f"Results saved to {output_path}", file=sys.stderr)

    if args.update_readme:
        update_readme(table)
        print("README benchmark table updated.", file=sys.stderr)

    print(table)

    # --- Format benchmark ---
    if args.formats and format_payloads:
        print("\n--- Format conversion benchmarks ---\n", file=sys.stderr)
        fmt_rows: list[BenchmarkRow] = []
        for index, payload in enumerate(format_payloads, start=1):
            payload_id = payload.get("id", "unknown")
            print(f"[{index}/{len(format_payloads)}] {payload_id}", file=sys.stderr)
            row = benchmark_payload(
                payload, auto_config=config, force_config=force_config
            )
            fmt_rows.append(row)

        fmt_summary = compute_summary(fmt_rows)
        fmt_table = format_table_formats(fmt_rows, fmt_summary)

        if args.update_readme:
            update_format_readme(fmt_table)
            print("README format benchmark table updated.", file=sys.stderr)

        print(fmt_table)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
