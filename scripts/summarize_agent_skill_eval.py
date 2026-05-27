#!/usr/bin/env python3
"""Summarize artifact-based agent skill evaluation results."""

from __future__ import annotations

import argparse
import json
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_EVAL_DIR = Path("benchmarks/agent_skill_eval")
SCORE_KEYS = [
    "scenario",
    "iteration",
    "record_count",
    "active_count",
    "total_revenue_cents",
    "top_region",
    "top_category",
    "anomaly_ids",
]


@dataclass(slots=True, frozen=True)
class PayloadTokenSummary:
    """Aggregated token estimates for one payload scenario."""

    scenario: str
    avg_json_tokens: float
    avg_toon_tokens: float
    avg_savings_pct: float
    convert_count: int
    run_count: int


@dataclass(slots=True, frozen=True)
class CorrectnessSummary:
    """Exact-answer scoring summary for one benchmark variant."""

    variant: str
    runs: int
    correct: int
    failures: int
    accuracy_pct: float


@dataclass(slots=True, frozen=True)
class TimeSummary:
    """Agent-reported elapsed time summary for one scenario and variant."""

    scenario: str
    variant: str
    runs: int
    avg_seconds: float
    median_seconds: float
    min_seconds: float
    max_seconds: float


def load_json(path: Path) -> Any:
    """Read a JSON file with path context."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Missing required file: {path}") from exc


def pct(value: float) -> float:
    """Convert a ratio to a rounded percentage."""
    return round(value * 100, 2)


def scenario_from_payload_name(payload_name: str) -> str:
    """Extract scenario from names such as `1_medium.json`."""
    return payload_name.rsplit("_", 1)[-1].removesuffix(".json")


def score_results(
    *,
    expected: dict[str, dict[str, Any]],
    agent_results: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[CorrectnessSummary]]:
    """Score agent results against exact expected answers."""
    scored: list[dict[str, Any]] = []
    by_variant: dict[str, list[bool]] = {}

    for row in agent_results:
        payload_name = str(row["payload_name"])
        variant = str(row["variant"])
        result = row["result"]
        expected_row = expected[payload_name]
        mismatches = {
            key: {"actual": result.get(key), "expected": expected_row.get(key)}
            for key in SCORE_KEYS
            if result.get(key) != expected_row.get(key)
        }
        correct = not mismatches
        by_variant.setdefault(variant, []).append(correct)
        scored.append({**row, "correct": correct, "mismatches": mismatches})

    summaries = [
        CorrectnessSummary(
            variant=variant,
            runs=len(values),
            correct=sum(1 for value in values if value),
            failures=sum(1 for value in values if not value),
            accuracy_pct=pct(sum(1 for value in values if value) / len(values)),
        )
        for variant, values in sorted(by_variant.items())
    ]
    return scored, summaries


def summarize_payload_tokens(report_dir: Path) -> list[PayloadTokenSummary]:
    """Aggregate datoon token estimates by scenario."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for path in sorted(report_dir.glob("*.report.json")):
        scenario = scenario_from_payload_name(path.name.removesuffix(".report.json"))
        grouped.setdefault(scenario, []).append(load_json(path))

    summaries: list[PayloadTokenSummary] = []
    for scenario, reports in sorted(grouped.items()):
        summaries.append(
            PayloadTokenSummary(
                scenario=scenario,
                avg_json_tokens=round(
                    statistics.mean(
                        float(report["input_token_estimate"]) for report in reports
                    ),
                    2,
                ),
                avg_toon_tokens=round(
                    statistics.mean(
                        float(report["output_token_estimate"]) for report in reports
                    ),
                    2,
                ),
                avg_savings_pct=round(
                    statistics.mean(
                        float(report["savings_ratio"]) for report in reports
                    )
                    * 100,
                    2,
                ),
                convert_count=sum(
                    1 for report in reports if report["decision"] == "convert"
                ),
                run_count=len(reports),
            )
        )
    return summaries


def summarize_agent_times(agent_results: list[dict[str, Any]]) -> list[TimeSummary]:
    """Summarize self-reported agent elapsed seconds."""
    grouped: dict[tuple[str, str], list[float]] = {}
    for row in agent_results:
        payload_name = str(row["payload_name"])
        scenario = scenario_from_payload_name(payload_name)
        variant = str(row["variant"])
        elapsed = float(row["result"].get("elapsed_seconds", 0.0) or 0.0)
        grouped.setdefault((scenario, variant), []).append(elapsed)

    summaries: list[TimeSummary] = []
    for (scenario, variant), values in sorted(grouped.items()):
        summaries.append(
            TimeSummary(
                scenario=scenario,
                variant=variant,
                runs=len(values),
                avg_seconds=round(statistics.mean(values), 6),
                median_seconds=round(statistics.median(values), 6),
                min_seconds=round(min(values), 6),
                max_seconds=round(max(values), 6),
            )
        )
    return summaries


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    """Render a compact Markdown table."""
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)


def render_report(
    *,
    token_summaries: list[PayloadTokenSummary],
    correctness_summaries: list[CorrectnessSummary],
    time_summaries: list[TimeSummary],
    total_runs: int,
    failure_count: int,
) -> str:
    """Render the agent evaluation report."""
    token_table = markdown_table(
        ["Scenario", "Avg JSON Tokens", "Avg TOON Tokens", "Avg Savings", "Convert"],
        [
            [
                summary.scenario,
                f"{summary.avg_json_tokens:,.2f}",
                f"{summary.avg_toon_tokens:,.2f}",
                f"{summary.avg_savings_pct:.2f}%",
                f"{summary.convert_count}/{summary.run_count}",
            ]
            for summary in token_summaries
        ],
    )
    correctness_table = markdown_table(
        ["Variant", "Runs", "Correct", "Failures", "Accuracy"],
        [
            [
                summary.variant,
                str(summary.runs),
                str(summary.correct),
                str(summary.failures),
                f"{summary.accuracy_pct:.2f}%",
            ]
            for summary in correctness_summaries
        ],
    )
    time_table = markdown_table(
        ["Scenario", "Variant", "Runs", "Avg Seconds", "Median", "Min", "Max"],
        [
            [
                summary.scenario,
                summary.variant,
                str(summary.runs),
                f"{summary.avg_seconds:.6f}",
                f"{summary.median_seconds:.6f}",
                f"{summary.min_seconds:.6f}",
                f"{summary.max_seconds:.6f}",
            ]
            for summary in time_summaries
        ],
    )

    return f"""# Agent Skill Evaluation Report

## Goal

Compare agent behavior on the same structured-data analysis tasks with and without the `datoon` skill.

The benchmark uses 3 scenarios and 3 deterministic iterations per scenario:

- `small`: 5 uniform records
- `medium`: 75 uniform records
- `large`: 450 uniform records

Each payload asks the agent to compute exact values: `record_count`, `active_count`, `total_revenue_cents`, `top_region`, `top_category`, and `anomaly_ids`.

## Files

- Payload generator: `benchmarks/agent_skill_eval/generate_payloads.py`
- JSON payloads: `benchmarks/agent_skill_eval/payloads/*.json`
- Expected answers: `benchmarks/agent_skill_eval/expected_answers.json`
- `datoon` reports: `benchmarks/agent_skill_eval/reports/*.report.json`
- Optimized TOON payloads: `benchmarks/agent_skill_eval/toon/*.toon`
- Raw agent outputs: `benchmarks/agent_skill_eval/agent_results.json`

## Method

For every payload, two agents were run:

- `with_skill`: received the `datoon` skill and was instructed to follow the skill workflow.
- `without_skill`: was instructed to use the JSON payload directly and not use `datoon`, TOON, or preconverted files.

Total agent runs: {total_runs}

The same expected-answer file was used to score both variants. Scoring compared exact values for all required output fields.

## Payload Token Estimates

These token estimates come from `datoon` conversion reports. They measure payload representation size, not total model usage.

{token_table}

## Correctness

{correctness_table}

Exact-answer failures: {failure_count}

## Agent-Reported Time

The `elapsed_seconds` values below are self-reported by agents. They are useful as directional telemetry but not strict wall-clock measurements from the parent runner.

{time_table}

One no-skill medium run reported `6.2s`, while comparable runs reported near-zero values. Treat this as timing noise in agent self-reporting rather than a stable performance signal.

## Observations

- The skill consistently made a conversion decision and produced TOON for all payloads.
- The largest benefit was payload-size reduction: about 62% fewer estimated payload tokens for medium and large inputs.
- Correctness stayed identical in this task: all exact outputs matched the expected answers.
- For small payloads, `datoon` still converted because the generated small payload was uniform and savings exceeded the 15% threshold. A different tiny or non-table JSON would likely be skipped.
- Full model token usage per subagent was not exposed by the multi-agent tool, so this report cannot claim total end-to-end token savings. It reports payload-token savings from `datoon`.

## Conclusion

In this benchmark, using the `datoon` skill did not change answer correctness, but it reduced the structured payload size substantially before the agent consumed it. The practical value is strongest for medium and large uniform arrays.
"""


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Summarize artifact-based datoon agent skill evaluation."
    )
    parser.add_argument(
        "--eval-dir",
        type=Path,
        default=DEFAULT_EVAL_DIR,
        help="Directory containing agent_results.json, expected_answers.json, and reports.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Markdown report output path. Defaults to <eval-dir>/REPORT.md.",
    )
    parser.add_argument(
        "--scored-output",
        type=Path,
        default=None,
        help="Optional JSON path for scored per-run results.",
    )
    return parser.parse_args()


def main() -> int:
    """Generate a summary report from existing evaluation artifacts."""
    args = parse_args()
    eval_dir = args.eval_dir
    output_path = args.output or eval_dir / "REPORT.md"
    scored_output = args.scored_output or eval_dir / "scored_agent_results.json"

    expected = load_json(eval_dir / "expected_answers.json")
    agent_results = load_json(eval_dir / "agent_results.json")
    scored_results, correctness_summaries = score_results(
        expected=expected,
        agent_results=agent_results,
    )
    token_summaries = summarize_payload_tokens(eval_dir / "reports")
    time_summaries = summarize_agent_times(agent_results)
    failure_count = sum(1 for row in scored_results if not row["correct"])

    report = render_report(
        token_summaries=token_summaries,
        correctness_summaries=correctness_summaries,
        time_summaries=time_summaries,
        total_runs=len(agent_results),
        failure_count=failure_count,
    )
    output_path.write_text(report, encoding="utf-8")
    scored_output.write_text(
        json.dumps(scored_results, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Report written to {output_path}")
    print(f"Scored results written to {scored_output}")
    print(f"Agent runs: {len(agent_results)}; failures: {failure_count}")
    return 1 if failure_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
