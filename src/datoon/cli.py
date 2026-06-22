"""Command-line interface for datoon JSON-to-TOON conversion."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from datoon import __version__
from datoon.converter import DatoonError, convert_json_for_llm
from datoon.models import ConversionConfig
from datoon.readers import ALL_FORMATS, BINARY_FORMATS, detect_format, read_tabular


def build_parser() -> argparse.ArgumentParser:
    """Create CLI parser with conversion policy and reporting options."""
    parser = argparse.ArgumentParser(
        prog="datoon",
        description=(
            "Convert structured data (JSON, CSV, YAML, XML, JSONL, Parquet, "
            "Avro, ORC, Excel, Numbers) to TOON only when conversion is beneficial."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "input",
        nargs="?",
        help="Path to input file. If omitted, reads from stdin (JSON/CSV/YAML/XML/JSONL).",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Path to write resulting payload. If omitted, writes to stdout.",
    )
    parser.add_argument(
        "--format",
        choices=sorted(ALL_FORMATS | {"json"}),
        help=(
            "Input format. Auto-detected from file extension when omitted; "
            "defaults to 'json' for stdin."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force TOON conversion and bypass gating thresholds.",
    )
    parser.add_argument(
        "--min-savings",
        type=float,
        default=0.15,
        help="Minimum relative token savings required for conversion (default: 0.15).",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=6,
        help="Maximum nested depth allowed for automatic conversion (default: 6).",
    )
    parser.add_argument(
        "--min-uniform-rows",
        type=int,
        default=3,
        help="Minimum row count for uniform object arrays (default: 3).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Seconds to wait for the TOON CLI before aborting (default: 30).",
    )
    parser.add_argument(
        "--report",
        help="Optional path to write conversion report as JSON.",
    )
    parser.add_argument(
        "--report-stdout",
        action="store_true",
        help="Print conversion report JSON to stderr.",
    )
    return parser


def _read_input(path: str | None) -> str:
    """Read input payload from file path or stdin."""
    if path is None:
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8")


def _write_text(path: str | None, text: str) -> None:
    """Write output payload to file path or stdout."""
    if path is None:
        sys.stdout.write(text)
        return
    Path(path).write_text(text, encoding="utf-8")


def _emit_report(
    *, report_path: str | None, report_stdout: bool, payload: dict[str, object]
) -> None:
    """Emit conversion report to selected destinations."""
    report_json = json.dumps(payload, ensure_ascii=False, indent=2)
    if report_path:
        Path(report_path).write_text(f"{report_json}\n", encoding="utf-8")
    if report_stdout:
        sys.stderr.write(f"{report_json}\n")


def _resolve_format(input_path: str | None, format_override: str | None) -> str:
    """Determine input format from explicit flag, file extension, or default."""
    if format_override:
        return format_override
    if input_path is not None:
        detected = detect_format(input_path)
        if detected is not None:
            return detected
    return "json"


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint that executes conversion and returns process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        config = ConversionConfig(
            min_savings_ratio=args.min_savings,
            max_depth=args.max_depth,
            min_uniform_rows=args.min_uniform_rows,
            force=args.force,
            toon_cli_timeout=args.timeout,
        )

        fmt = _resolve_format(args.input, args.format)

        if fmt == "json":
            raw_input = _read_input(args.input)
            outcome = convert_json_for_llm(raw_input, config)
        elif fmt in BINARY_FORMATS:
            if args.input is None:
                sys.stderr.write(
                    f"datoon error: --format {fmt} requires a file path, not stdin.\n"
                )
                return 1
            rows = read_tabular(fmt, path=Path(args.input))
            json_text = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
            outcome = convert_json_for_llm(json_text, config)
        else:
            raw_input = _read_input(args.input)
            rows = read_tabular(fmt, text=raw_input)
            json_text = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
            outcome = convert_json_for_llm(json_text, config)

        _write_text(args.output, outcome.payload_text)
        _emit_report(
            report_path=args.report,
            report_stdout=args.report_stdout,
            payload=outcome.report.as_dict(),
        )
        return 0
    except (OSError, ValueError, DatoonError) as exc:
        sys.stderr.write(f"datoon error: {exc}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
