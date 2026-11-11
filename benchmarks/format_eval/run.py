"""Measure how accurately a Claude model reads one table in five serializations.

One Messages API call per (table, format, repeat): the system prompt asks for a
JSON object of answers, the user message holds the serialized table and six
questions with Python-computed gold answers. The run records real token usage,
latency and per-question correctness, then summarizes accuracy (with a 95%
Wilson interval) and input tokens per format.

Usage::

    uv run --extra claude python -m benchmarks.format_eval.run \
        --model claude-haiku-5-5 --dry-run

``--dry-run`` builds every prompt and prints the plan with local token
estimates; it imports no SDK and makes no API call. The API key is resolved by
the ``anthropic`` SDK from the environment and is never read here.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

import datoon

from .datasets import DEFAULT_SEEDS, DEFAULT_SHAPES, Table, build_tables, parse_shape
from .formats import BASELINE_FORMAT, FORMATS
from .questions import QUESTION_KINDS, Question, build_questions, score

RESULTS_DIR = Path(__file__).resolve().parents[1] / "results" / "format_eval"

SYSTEM_PROMPT = (
    "You answer questions about a data table. Use only the table. Reply with one "
    "JSON object mapping each question id to its answer, no prose, no code fence."
)
ANSWER_FORMAT_NOTE = (
    "Use JSON numbers for numbers, true or false for booleans, null for NULL "
    "values, and the exact cell text for strings."
)

DEFAULT_REPEATS = 1
DEFAULT_MAX_TOKENS = 8000
DEFAULT_CONCURRENCY = 4
ESTIMATE_TOKENIZER = "auto"
MAX_RETRIES = 4
BACKOFF_BASE_SECONDS = 2.0
WILSON_Z_95 = 1.96
THINKING_DEFAULT = "default"
THINKING_DISABLED = "disabled"
STOP_MAX_TOKENS = "max_tokens"
_FILENAME_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(slots=True, frozen=True)
class CallSpec:
    """One planned API call: a table rendered in one format, one repeat."""

    table: Table
    format_name: str
    repeat: int
    questions: tuple[Question, ...]
    payload: str
    user_message: str


# ---------------------------------------------------------------------------
# Pure helpers: prompts, plan, parsing, grading, statistics, summary.
# ---------------------------------------------------------------------------


def build_user_message(
    format_name: str, payload: str, questions: Sequence[Question]
) -> str:
    """Wrap the payload in a ``<table>`` tag and list the numbered questions."""
    question_lines = [
        f"{index}. [{question.id}] {question.text}"
        for index, question in enumerate(questions, start=1)
    ]
    ids = ", ".join(f'"{question.id}": ...' for question in questions)
    return "\n".join(
        [
            f'<table format="{format_name}">',
            payload,
            "</table>",
            "",
            "Questions:",
            *question_lines,
            "",
            f"Reply as {{{ids}}}. {ANSWER_FORMAT_NOTE}",
        ]
    )


def build_plan(
    tables: Sequence[Table], format_names: Sequence[str], repeats: int
) -> list[CallSpec]:
    """Build every call, ordered by repeat, table, then format."""
    rendered: list[tuple[Table, str, tuple[Question, ...], str, str]] = []
    for table in tables:
        questions = tuple(build_questions(table))
        for format_name in format_names:
            payload = FORMATS[format_name](table)
            message = build_user_message(format_name, payload, questions)
            rendered.append((table, format_name, questions, payload, message))
    return [
        CallSpec(table, format_name, repeat, questions, payload, message)
        for repeat in range(repeats)
        for table, format_name, questions, payload, message in rendered
    ]


def estimate_prompt_tokens(spec: CallSpec, counter: Callable[[str], int]) -> int:
    """Local estimate of one call's input: system prompt plus user message."""
    return counter(SYSTEM_PROMPT) + counter(spec.user_message)


def plan_overview(
    specs: Sequence[CallSpec], counter: Callable[[str], int]
) -> dict[str, dict[str, float | int]]:
    """Per format: calls, mean payload chars/tokens, total estimated input."""
    overview: dict[str, dict[str, float | int]] = {}
    for format_name in dict.fromkeys(spec.format_name for spec in specs):
        group = [spec for spec in specs if spec.format_name == format_name]
        payload_chars = [len(spec.payload) for spec in group]
        payload_tokens = [counter(spec.payload) for spec in group]
        overview[format_name] = {
            "calls": len(group),
            "mean_payload_chars": sum(payload_chars) / len(group),
            "mean_payload_tokens": sum(payload_tokens) / len(group),
            "estimated_input_tokens": sum(
                estimate_prompt_tokens(spec, counter) for spec in group
            ),
        }
    return overview


def parse_reply(text: str) -> dict[str, Any] | None:
    """Parse a reply leniently: drop an optional fence, take the first ``{...}``.

    Returns ``None`` when no JSON object can be decoded.
    """
    body = text.strip()
    if body.startswith("```"):
        newline = body.find("\n")
        body = body[newline + 1 :] if newline != -1 else ""
        body = body.rstrip().removesuffix("```")
    start = body.find("{")
    if start == -1:
        return None
    try:
        value, _ = json.JSONDecoder().raw_decode(body, start)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def grade(
    questions: Sequence[Question], answers: dict[str, Any] | None
) -> list[dict[str, Any]]:
    """Score each question; a missing id or unparsed reply counts as wrong."""
    graded = []
    for question in questions:
        answered = answers is not None and question.id in answers
        answer = answers.get(question.id) if answers is not None else None
        graded.append(
            {
                "id": question.id,
                "kind": question.kind,
                "gold": question.gold,
                "answer": answer,
                "answered": answered,
                "correct": answered and score(question.kind, question.gold, answer),
            }
        )
    return graded


def wilson_interval(
    successes: int, total: int, z: float = WILSON_Z_95
) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion; ``(0, 1)`` when empty."""
    if total <= 0:
        return 0.0, 1.0
    proportion = successes / total
    denominator = 1 + z * z / total
    centre = proportion + z * z / (2 * total)
    margin = z * math.sqrt(
        proportion * (1 - proportion) / total + z * z / (4 * total * total)
    )
    return (
        max(0.0, (centre - margin) / denominator),
        min(1.0, (centre + margin) / denominator),
    )


def _mean(values: Sequence[float]) -> float | None:
    """Arithmetic mean, ``None`` for an empty sequence."""
    return sum(values) / len(values) if values else None


def _accuracy_cell(answers: int, correct: int) -> dict[str, Any]:
    """Answer count, correct count and accuracy (``None`` when no answers)."""
    return {
        "answers": answers,
        "correct": correct,
        "accuracy": correct / answers if answers else None,
    }


def is_truncated(record: dict[str, Any]) -> bool:
    """Tell whether a reply hit the output limit before giving a parseable answer."""
    return (
        record["error"] is None
        and record["stop_reason"] == STOP_MAX_TOKENS
        and bool(record["parse_error"])
    )


def summarize(
    records: Sequence[dict[str, Any]], format_names: Sequence[str]
) -> dict[str, Any]:
    """Aggregate call records per format, per format x kind, per format x shape.

    Calls that ended in an API error are counted in ``errors`` and left out of
    accuracy and token means: they say nothing about reading the format. The
    same goes for a reply cut off by the output limit before a parseable
    answer (``max_tokens_stops``): that measures the harness limit, not the
    format. Any other parse error is a graded call with every answer wrong.
    """
    graded = [
        record
        for record in records
        if record["error"] is None and not is_truncated(record)
    ]
    shapes = list(dict.fromkeys(record["shape"] for record in records))

    baseline_tokens = {
        (record["table"], record["repeat"]): record["input_tokens"]
        for record in graded
        if record["format"] == BASELINE_FORMAT
    }

    formats: dict[str, Any] = {}
    by_kind: dict[str, Any] = {}
    by_shape: dict[str, Any] = {}
    for format_name in format_names:
        calls = [record for record in records if record["format"] == format_name]
        ok = [record for record in graded if record["format"] == format_name]
        answers = [answer for record in ok for answer in record["questions"]]
        correct = sum(1 for answer in answers if answer["correct"])
        low, high = wilson_interval(correct, len(answers))

        paired = [
            (record["input_tokens"], baseline_tokens[key])
            for record in ok
            if (key := (record["table"], record["repeat"])) in baseline_tokens
        ]
        baseline_sum = sum(base for _, base in paired)
        formats[format_name] = {
            "calls": len(calls),
            "graded_calls": len(ok),
            "errors": sum(1 for record in calls if record["error"] is not None),
            "parse_errors": sum(1 for record in ok if record["parse_error"]),
            "max_tokens_stops": sum(1 for record in calls if is_truncated(record)),
            **_accuracy_cell(len(answers), correct),
            "ci95_low": low,
            "ci95_high": high,
            "mean_input_tokens": _mean([record["input_tokens"] for record in ok]),
            "input_tokens_vs_objects": (
                sum(tokens for tokens, _ in paired) / baseline_sum
                if baseline_sum
                else None
            ),
            "mean_output_tokens": _mean([record["output_tokens"] for record in ok]),
            "mean_latency_s": _mean([record["latency_s"] for record in ok]),
        }
        by_kind[format_name] = {
            kind: _accuracy_cell(
                sum(1 for answer in answers if answer["kind"] == kind),
                sum(
                    1
                    for answer in answers
                    if answer["kind"] == kind and answer["correct"]
                ),
            )
            for kind in QUESTION_KINDS
        }
        by_shape[format_name] = {}
        for shape in shapes:
            shape_answers = [
                answer
                for record in ok
                if record["shape"] == shape
                for answer in record["questions"]
            ]
            by_shape[format_name][shape] = _accuracy_cell(
                len(shape_answers),
                sum(1 for answer in shape_answers if answer["correct"]),
            )
    return {"formats": formats, "by_kind": by_kind, "by_shape": by_shape}


def _text_table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    """Render left-aligned columns separated by two spaces."""
    widths = [max(len(str(cell)) for cell in column) for column in zip(headers, *rows)]
    lines = [
        "  ".join(str(cell).ljust(width) for cell, width in zip(line, widths))
        for line in [headers, *rows]
    ]
    lines.insert(1, "  ".join("-" * width for width in widths))
    return "\n".join(line.rstrip() for line in lines)


def _pct(value: float | None) -> str:
    """Format a share as a percentage, ``-`` for ``None``."""
    return "-" if value is None else f"{value * 100:.1f}%"


def _num(value: float | None, digits: int = 0) -> str:
    """Format a number, ``-`` for ``None``."""
    return "-" if value is None else f"{value:,.{digits}f}"


def format_summary(summary: dict[str, Any]) -> str:
    """Render the summary as aligned text tables."""
    formats = summary["formats"]
    overall = _text_table(
        [
            "format",
            "accuracy",
            "95% CI",
            "answers",
            "mean in tok",
            "vs objects",
            "mean out tok",
            "mean latency s",
            "parse err",
            "max_tokens",
            "errors",
        ],
        [
            [
                name,
                _pct(cell["accuracy"]),
                f"{_pct(cell['ci95_low'])}..{_pct(cell['ci95_high'])}",
                str(cell["answers"]),
                _num(cell["mean_input_tokens"]),
                _num(cell["input_tokens_vs_objects"], 3),
                _num(cell["mean_output_tokens"]),
                _num(cell["mean_latency_s"], 2),
                str(cell["parse_errors"]),
                str(cell["max_tokens_stops"]),
                str(cell["errors"]),
            ]
            for name, cell in formats.items()
        ],
    )

    def grid(section: dict[str, Any], label: str) -> str:
        keys = list(dict.fromkeys(key for cells in section.values() for key in cells))
        return _text_table(
            [f"format \\ {label}", *keys],
            [
                [name, *[_pct(cells[key]["accuracy"]) for key in keys]]
                for name, cells in section.items()
            ],
        )

    return "\n\n".join(
        [
            "Accuracy and tokens per format",
            overall,
            "Accuracy per question kind",
            grid(summary["by_kind"], "kind"),
            "Accuracy per shape (rows x columns)",
            grid(summary["by_shape"], "shape"),
        ]
    )


def format_plan(
    specs: Sequence[CallSpec],
    overview: dict[str, dict[str, float | int]],
    tokenizer_name: str,
) -> str:
    """Render the call plan and local input-token estimates."""
    tables = list(dict.fromkeys(spec.table.name for spec in specs))
    repeats = len(dict.fromkeys(spec.repeat for spec in specs))
    total = sum(int(cell["estimated_input_tokens"]) for cell in overview.values())
    table = _text_table(
        [
            "format",
            "calls",
            "mean payload chars",
            "mean payload tok",
            "est input tok (all calls)",
        ],
        [
            [
                name,
                str(cell["calls"]),
                _num(cell["mean_payload_chars"]),
                _num(cell["mean_payload_tokens"]),
                _num(cell["estimated_input_tokens"]),
            ]
            for name, cell in overview.items()
        ],
    )
    return "\n".join(
        [
            (
                f"Plan: {len(specs)} calls = {len(tables)} tables x "
                f"{len(overview)} formats x {repeats} repeat(s); "
                f"{len(tables) * len(QUESTION_KINDS) * repeats} graded answers "
                "per format."
            ),
            f"Token estimates are local ({tokenizer_name}), not Claude counts.",
            "",
            table,
            "",
            f"Estimated input tokens, all calls: {total:,}",
        ]
    )


# ---------------------------------------------------------------------------
# API calls (client injected; the SDK is imported lazily in main).
# ---------------------------------------------------------------------------


def response_text(response: Any) -> str:
    """Concatenate the text blocks of a Messages API response."""
    return "".join(
        block.text
        for block in response.content
        if getattr(block, "type", None) == "text"
    )


def run_call(
    client: Any,
    model: str,
    spec: CallSpec,
    *,
    max_tokens: int,
    retryable: tuple[type[BaseException], ...],
    thinking: str = THINKING_DEFAULT,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Make one call (retrying ``retryable`` errors) and return its record.

    Any other exception is recorded in ``error``; it never propagates.
    """
    request: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": spec.user_message}],
    }
    if thinking == THINKING_DISABLED:
        request["thinking"] = {"type": "disabled"}
    record: dict[str, Any] = {
        "table": spec.table.name,
        "shape": spec.table.shape,
        "format": spec.format_name,
        "repeat": spec.repeat,
        "payload_chars": len(spec.payload),
        "input_tokens": None,
        "output_tokens": None,
        "latency_s": None,
        "stop_reason": None,
        "attempts": 0,
        "raw_text": None,
        "answers": None,
        "parse_error": False,
        "error": None,
        "questions": [],
        "correct": 0,
    }
    response = None
    try:
        for attempt in range(MAX_RETRIES + 1):
            record["attempts"] = attempt + 1
            started = time.perf_counter()
            try:
                response = client.messages.create(**request)
            except retryable:
                if attempt == MAX_RETRIES:
                    raise
                sleep(BACKOFF_BASE_SECONDS * 2**attempt)
                continue
            record["latency_s"] = time.perf_counter() - started
            break
    except Exception as exc:  # noqa: BLE001 - recorded per call; the run continues
        record["error"] = f"{type(exc).__name__}: {exc}"
        return record

    text = response_text(response)
    answers = parse_reply(text)
    graded = grade(spec.questions, answers)
    record.update(
        {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "stop_reason": response.stop_reason,
            "raw_text": text,
            "answers": answers,
            "parse_error": answers is None,
            "questions": graded,
            "correct": sum(1 for answer in graded if answer["correct"]),
        }
    )
    return record


def run_calls(
    client: Any,
    model: str,
    specs: Sequence[CallSpec],
    *,
    max_tokens: int,
    concurrency: int,
    retryable: tuple[type[BaseException], ...],
    thinking: str = THINKING_DEFAULT,
    sleep: Callable[[float], None] = time.sleep,
    progress: TextIO | None = None,
) -> list[dict[str, Any]]:
    """Run every call with bounded concurrency; records keep plan order.

    One progress line per finished call goes to ``progress`` when given.
    """
    records: list[dict[str, Any] | None] = [None] * len(specs)
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {
            pool.submit(
                run_call,
                client,
                model,
                spec,
                max_tokens=max_tokens,
                retryable=retryable,
                thinking=thinking,
                sleep=sleep,
            ): index
            for index, spec in enumerate(specs)
        }
        for done, future in enumerate(as_completed(futures), start=1):
            index = futures[future]
            record = future.result()
            records[index] = record
            if progress is not None:
                if record["error"] is not None:
                    status = f"ERROR {record['error']}"
                else:
                    status = (
                        f"{record['correct']}/{len(record['questions'])} correct, "
                        f"in={record['input_tokens']} out={record['output_tokens']}, "
                        f"{record['latency_s']:.1f}s"
                    )
                    if record["parse_error"]:
                        status += ", parse_error"
                print(
                    f"[{done}/{len(specs)}] {record['table']} {record['format']} "
                    f"r{record['repeat']}: {status}",
                    file=progress,
                    flush=True,
                )
    return [record for record in records if record is not None]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    """Parse and validate command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Measure how accurately a Claude model reads one table serialized "
            "as JSON objects, JSON arrays, TOON, markdown and CSV."
        )
    )
    parser.add_argument(
        "--model", required=True, help="Model id, e.g. claude-haiku-5-5."
    )
    parser.add_argument("--repeats", type=int, default=DEFAULT_REPEATS)
    parser.add_argument("--seeds", type=int, default=DEFAULT_SEEDS)
    parser.add_argument(
        "--shapes", help="Comma list of ROWSxCOLUMNS shapes, e.g. 20x4,100x11."
    )
    parser.add_argument(
        "--formats", help=f"Comma list from: {', '.join(FORMATS)}. Default: all."
    )
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    parser.add_argument(
        "--thinking",
        choices=(THINKING_DEFAULT, THINKING_DISABLED),
        default=THINKING_DEFAULT,
        help=(
            "default: send no thinking parameter (model default); disabled: send "
            "thinking={type: disabled} where the model accepts it."
        ),
    )
    parser.add_argument("--out", type=Path, help="Result JSON path.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build prompts and print the plan; make no API call.",
    )
    args = parser.parse_args(argv)

    for name in ("repeats", "seeds", "max_tokens", "concurrency"):
        if getattr(args, name) < 1:
            parser.error(f"--{name.replace('_', '-')} must be at least 1.")
    try:
        args.shapes = (
            [parse_shape(item) for item in args.shapes.split(",") if item.strip()]
            if args.shapes
            else list(DEFAULT_SHAPES)
        )
    except ValueError as exc:
        parser.error(str(exc))
    if args.formats:
        args.formats = [
            item.strip() for item in args.formats.split(",") if item.strip()
        ]
        unknown = [name for name in args.formats if name not in FORMATS]
        if unknown:
            parser.error(f"Unknown format(s): {', '.join(unknown)}.")
    else:
        args.formats = list(FORMATS)
    if not args.shapes or not args.formats:
        parser.error("--shapes and --formats must not be empty.")
    return args


def _default_out_path(model: str, started: datetime) -> Path:
    """``benchmarks/results/format_eval/<model>-<UTC timestamp>.json``."""
    safe_model = _FILENAME_UNSAFE.sub("_", model)
    return RESULTS_DIR / f"{safe_model}-{started:%Y%m%dT%H%M%SZ}.json"


def _anthropic_client_and_retryable() -> tuple[Any, tuple[type[BaseException], ...]]:
    """Create the SDK client and the exception classes worth retrying.

    The SDK's own retries are turned off so this harness's retry policy is
    the only one in play.
    """
    import anthropic

    retryable: tuple[type[BaseException], ...] = (
        anthropic.RateLimitError,
        anthropic.OverloadedError,
        anthropic.APIConnectionError,
    )
    return anthropic.Anthropic(max_retries=0), retryable


def main(argv: Sequence[str] | None = None) -> int:
    """Run the benchmark (or print the plan with ``--dry-run``)."""
    args = _parse_args(argv)
    tables = build_tables(args.shapes, args.seeds)
    specs = build_plan(tables, args.formats, args.repeats)
    counter, tokenizer_name = datoon.resolve_tokenizer(ESTIMATE_TOKENIZER)
    overview = plan_overview(specs, counter)
    print(format_plan(specs, overview, tokenizer_name))

    if args.dry_run:
        smallest = min(tables, key=lambda table: len(table.rows) * len(table.columns))
        print(f"\nDry run: no API call made. Prompts for {smallest.name}:")
        print(f"\n=== system ===\n{SYSTEM_PROMPT}")
        for spec in specs:
            if spec.table is smallest and spec.repeat == 0:
                print(f"\n=== user ({spec.format_name}) ===\n{spec.user_message}")
        return 0

    try:
        client, retryable = _anthropic_client_and_retryable()
    except ImportError:
        print(
            "The anthropic package is missing; run with `uv run --extra claude`.",
            file=sys.stderr,
        )
        return 2

    started = datetime.now(UTC)
    out_path = args.out or _default_out_path(args.model, started)
    records = run_calls(
        client,
        args.model,
        specs,
        max_tokens=args.max_tokens,
        concurrency=args.concurrency,
        retryable=retryable,
        thinking=args.thinking,
        progress=sys.stderr,
    )
    finished = datetime.now(UTC)
    summary = summarize(records, args.formats)
    ok = [record for record in records if record["error"] is None]
    result = {
        "meta": {
            "model": args.model,
            "repeats": args.repeats,
            "seeds": args.seeds,
            "shapes": [f"{rows}x{columns}" for rows, columns in args.shapes],
            "formats": args.formats,
            "max_tokens": args.max_tokens,
            "concurrency": args.concurrency,
            "thinking": args.thinking,
            "started_at": started.isoformat(),
            "finished_at": finished.isoformat(),
            "datoon_version": datoon.__version__,
            "estimate_tokenizer": tokenizer_name,
            "estimated_input_tokens": sum(
                int(cell["estimated_input_tokens"]) for cell in overview.values()
            ),
            "total_input_tokens": sum(record["input_tokens"] for record in ok),
            "total_output_tokens": sum(record["output_tokens"] for record in ok),
            "calls": len(records),
            "errors": len(records) - len(ok),
        },
        "calls": records,
        "summary": summary,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print()
    print(format_summary(summary))
    print(f"\nWrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
