#!/usr/bin/env python3
"""A/B benchmark for datoon skill usage in Claude CLI.

This script compares the same prompts in two modes:
1. without skill: plugin disabled, plain prompt
2. with skill: plugin enabled, `/datoon` prefixed prompt

It collects token usage, cost, latency, and reliability metrics, then writes
both raw runs and aggregated summary to JSON.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import statistics
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_PAYLOADS_PATH = Path("benchmarks/payloads.json")
DEFAULT_OUTPUT_DIR = Path("benchmarks/results/ab")
DEFAULT_PROMPT_TEMPLATE = (
    "Read this payload and return ONLY minified JSON with keys: "
    "records_count, top_level_keys, has_nested_objects. "
    "No explanation, no markdown. "
    "Payload: {payload_json}"
)
DEFAULT_SYSTEM_PROMPT = (
    "You are a deterministic JSON transformer for benchmark runs. "
    "Return exactly one minified JSON object and nothing else. "
    "Do not mention skills, plugins, tools, TOON, datoon, fallback behavior, "
    "or internal workflow details."
)


@dataclass(slots=True, frozen=True)
class RunResult:
    """One Claude invocation result for a single payload iteration."""

    mode: str
    payload_id: str
    iteration: int
    ok: bool
    is_error: bool
    error: str | None
    duration_ms: int
    cost_usd: float
    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: int
    result_token_estimate: int
    num_turns: int
    valid_result_json: bool
    format_used: str | None
    result_preview: str


@dataclass(slots=True, frozen=True)
class ModeSummary:
    """Aggregated metrics for one mode."""

    count: int
    ok_count: int
    success_rate: float | None
    valid_json_rate: float | None
    avg_input_tokens: float | None
    avg_output_tokens: float | None
    avg_cache_read_input_tokens: float | None
    avg_result_token_estimate: float | None
    avg_cost_usd: float | None
    avg_duration_ms: float | None
    p50_duration_ms: int | None
    p95_duration_ms: int | None
    avg_output_tokens_per_second: float | None
    avg_num_turns: float | None
    format_counts: dict[str, int]


@dataclass(slots=True, frozen=True)
class BenchmarkMode:
    """Execution settings for one A/B benchmark mode."""

    name: str
    plugin_enabled: bool
    prompt_prefix: str
    claude_args: tuple[str, ...]


def estimate_visible_tokens(text: str) -> int:
    """Estimate tokens for visible result text using a stable char heuristic."""
    return max(1, math.ceil(len(text) / 4))


def configure_logging(log_path: Path, *, verbose: bool) -> logging.Logger:
    """Configure logger with console and file handlers."""
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("ab-skill-benchmark")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    console_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    return logger


def run_subprocess(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run subprocess with captured output."""
    return subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )


def get_plugin_enabled_state(
    *,
    plugin_id: str,
    cwd: Path,
    logger: logging.Logger,
) -> bool:
    """Read current plugin enabled state from `claude plugins list --json`."""
    process = run_subprocess(["claude", "plugins", "list", "--json"], cwd=cwd)
    if process.returncode != 0:
        raise RuntimeError(
            "Failed to list plugins. "
            f"stderr={process.stderr.strip() or '<empty>'}"
        )

    try:
        data = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Invalid JSON from `claude plugins list --json`.") from exc

    for item in data:
        if item.get("id") == plugin_id:
            state = bool(item.get("enabled"))
            logger.debug("Detected plugin state: %s enabled=%s", plugin_id, state)
            return state

    raise RuntimeError(f"Plugin not found in local installation: {plugin_id}")


def set_plugin_enabled_state(
    *,
    plugin_id: str,
    enabled: bool,
    cwd: Path,
    logger: logging.Logger,
) -> None:
    """Enable or disable plugin through Claude CLI."""
    action = "enable" if enabled else "disable"
    process = run_subprocess(["claude", "plugins", action, plugin_id], cwd=cwd)
    stderr = process.stderr.strip()
    if process.returncode != 0:
        already_enabled = enabled and "already enabled" in stderr.lower()
        already_disabled = (not enabled) and "already disabled" in stderr.lower()
        if already_enabled or already_disabled:
            logger.debug(
                "Plugin action noop: %s %s (%s)",
                action,
                plugin_id,
                stderr or "<empty>",
            )
            return
        raise RuntimeError(
            f"Failed to {action} plugin {plugin_id}. "
            f"stderr={stderr or '<empty>'}"
        )
    logger.debug("Plugin action completed: %s %s", action, plugin_id)


def parse_claude_result(
    *,
    mode: str,
    payload_id: str,
    iteration: int,
    stdout: str,
) -> RunResult:
    """Parse Claude JSON output into normalized run result."""
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError:
        return RunResult(
            mode=mode,
            payload_id=payload_id,
            iteration=iteration,
            ok=False,
            is_error=True,
            error="invalid_json_output",
            duration_ms=0,
            cost_usd=0.0,
            input_tokens=0,
            output_tokens=0,
            cache_read_input_tokens=0,
            result_token_estimate=0,
            num_turns=0,
            valid_result_json=False,
            format_used=None,
            result_preview=stdout[:250],
        )

    model_usage: dict[str, Any] = {}
    if isinstance(parsed.get("modelUsage"), dict) and parsed["modelUsage"]:
        model_usage = next(iter(parsed["modelUsage"].values()))

    result_text = parsed.get("result") or ""
    result_text_normalized = (
        result_text if isinstance(result_text, str) else str(result_text)
    )
    valid_result_json = False
    format_used: str | None = None
    if isinstance(result_text, str):
        try:
            obj = json.loads(result_text)
            if isinstance(obj, dict):
                valid_result_json = True
                if isinstance(obj.get("format_used"), str):
                    format_used = obj["format_used"]
        except json.JSONDecodeError:
            valid_result_json = False

    return RunResult(
        mode=mode,
        payload_id=payload_id,
        iteration=iteration,
        ok=not bool(parsed.get("is_error", False)),
        is_error=bool(parsed.get("is_error", False)),
        error=None,
        duration_ms=int(parsed.get("duration_ms", 0) or 0),
        cost_usd=float(parsed.get("total_cost_usd", 0.0) or 0.0),
        input_tokens=int(model_usage.get("inputTokens", 0) or 0),
        output_tokens=int(model_usage.get("outputTokens", 0) or 0),
        cache_read_input_tokens=int(model_usage.get("cacheReadInputTokens", 0) or 0),
        result_token_estimate=estimate_visible_tokens(result_text_normalized),
        num_turns=int(parsed.get("num_turns", 0) or 0),
        valid_result_json=valid_result_json,
        format_used=format_used,
        result_preview=result_text_normalized[:250],
    )


def percentile(values: list[int], p: float) -> int | None:
    """Return nearest-rank percentile value."""
    if not values:
        return None
    sorted_values = sorted(values)
    index = min(len(sorted_values) - 1, max(0, math.ceil(p * len(sorted_values)) - 1))
    return sorted_values[index]


def summarize_mode(results: list[RunResult]) -> ModeSummary:
    """Compute aggregate metrics for one mode."""
    ok_results = [r for r in results if r.ok]
    format_counts: dict[str, int] = {}
    for result in ok_results:
        if result.format_used:
            format_counts[result.format_used] = format_counts.get(result.format_used, 0) + 1

    if not ok_results:
        return ModeSummary(
            count=len(results),
            ok_count=0,
            success_rate=None,
            valid_json_rate=None,
            avg_input_tokens=None,
            avg_output_tokens=None,
            avg_cache_read_input_tokens=None,
            avg_result_token_estimate=None,
            avg_cost_usd=None,
            avg_duration_ms=None,
            p50_duration_ms=None,
            p95_duration_ms=None,
            avg_output_tokens_per_second=None,
            avg_num_turns=None,
            format_counts=format_counts,
        )

    tps_values = [
        result.output_tokens / (result.duration_ms / 1000)
        for result in ok_results
        if result.duration_ms > 0
    ]

    return ModeSummary(
        count=len(results),
        ok_count=len(ok_results),
        success_rate=round(len(ok_results) / len(results), 4) if results else None,
        valid_json_rate=round(
            sum(1 for result in ok_results if result.valid_result_json) / len(ok_results),
            4,
        ),
        avg_input_tokens=round(
            statistics.mean(result.input_tokens for result in ok_results), 2
        ),
        avg_output_tokens=round(
            statistics.mean(result.output_tokens for result in ok_results), 2
        ),
        avg_cache_read_input_tokens=round(
            statistics.mean(result.cache_read_input_tokens for result in ok_results), 2
        ),
        avg_result_token_estimate=round(
            statistics.mean(result.result_token_estimate for result in ok_results), 2
        ),
        avg_cost_usd=round(statistics.mean(result.cost_usd for result in ok_results), 6),
        avg_duration_ms=round(
            statistics.mean(result.duration_ms for result in ok_results), 2
        ),
        p50_duration_ms=percentile([result.duration_ms for result in ok_results], 0.50),
        p95_duration_ms=percentile([result.duration_ms for result in ok_results], 0.95),
        avg_output_tokens_per_second=(
            round(statistics.mean(tps_values), 2) if tps_values else None
        ),
        avg_num_turns=round(statistics.mean(result.num_turns for result in ok_results), 2),
        format_counts=format_counts,
    )


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Run A/B benchmark for datoon skill (with and without plugin)."
    )
    parser.add_argument(
        "--payloads",
        type=Path,
        default=DEFAULT_PAYLOADS_PATH,
        help="Path to payload list JSON file.",
    )
    parser.add_argument(
        "--payload-limit",
        type=int,
        default=5,
        help="How many payloads to include from file.",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=3,
        help="Runs per payload for each mode.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for benchmark JSON and log files.",
    )
    parser.add_argument(
        "--model",
        default="sonnet",
        help="Claude model alias/name passed to CLI.",
    )
    parser.add_argument(
        "--effort",
        default="low",
        choices=["low", "medium", "high", "max"],
        help="Reasoning effort passed to Claude CLI.",
    )
    parser.add_argument(
        "--max-budget-usd",
        type=float,
        default=0.5,
        help="Max budget per Claude call.",
    )
    parser.add_argument(
        "--plugin-id",
        default="datoon@datoon",
        help="Plugin id in Claude plugins list.",
    )
    parser.add_argument(
        "--skill-command",
        default="/datoon",
        help="Skill command to prepend in with-skill mode.",
    )
    parser.add_argument(
        "--prompt-template",
        default=DEFAULT_PROMPT_TEMPLATE,
        help="Prompt template. Must include '{payload_json}'.",
    )
    parser.add_argument(
        "--system-prompt",
        default=DEFAULT_SYSTEM_PROMPT,
        help="System prompt used to enforce deterministic machine-readable outputs.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose debug logs in console.",
    )
    return parser.parse_args()


def main() -> int:
    """Run benchmark and print summary table."""
    args = parse_args()
    if "{payload_json}" not in args.prompt_template:
        raise ValueError("--prompt-template must include '{payload_json}'.")
    if args.iterations < 1:
        raise ValueError("--iterations must be >= 1.")
    if args.payload_limit < 1:
        raise ValueError("--payload-limit must be >= 1.")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_path = args.output_dir / "logs" / f"ab_skill_{timestamp}.log"
    logger = configure_logging(log_path, verbose=args.verbose)

    logger.info("Starting A/B benchmark")
    logger.info("Log file: %s", log_path)
    logger.info(
        "Config: payloads=%s limit=%d iterations=%d model=%s effort=%s budget=%.3f",
        args.payloads,
        args.payload_limit,
        args.iterations,
        args.model,
        args.effort,
        args.max_budget_usd,
    )
    logger.info("System prompt: %s", args.system_prompt)

    payloads_parsed = json.loads(args.payloads.read_text(encoding="utf-8"))
    payloads = payloads_parsed["payloads"][: args.payload_limit]
    payload_ids = [str(payload.get("id", "unknown")) for payload in payloads]
    logger.info("Payload ids: %s", ", ".join(payload_ids))

    initial_plugin_state = get_plugin_enabled_state(
        plugin_id=args.plugin_id,
        cwd=Path.cwd(),
        logger=logger,
    )
    logger.info("Initial plugin state: %s=%s", args.plugin_id, initial_plugin_state)

    all_results: list[RunResult] = []
    modes = [
        BenchmarkMode(
            name="without_skill",
            plugin_enabled=False,
            prompt_prefix="",
            # Prevent accidental implicit skill invocation in baseline mode.
            claude_args=("--disable-slash-commands",),
        ),
        BenchmarkMode(
            name="with_skill",
            plugin_enabled=True,
            prompt_prefix=f"{args.skill_command}\n",
            claude_args=(),
        ),
    ]

    try:
        for mode in modes:
            logger.info("Mode start: %s", mode.name)
            set_plugin_enabled_state(
                plugin_id=args.plugin_id,
                enabled=mode.plugin_enabled,
                cwd=Path.cwd(),
                logger=logger,
            )

            for payload in payloads:
                payload_id = str(payload.get("id", "unknown"))
                payload_json = json.dumps(
                    payload.get("data"),
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                prompt = mode.prompt_prefix + args.prompt_template.format(
                    payload_json=payload_json
                )

                for iteration in range(1, args.iterations + 1):
                    logger.info(
                        "Run: mode=%s payload=%s iter=%d",
                        mode.name,
                        payload_id,
                        iteration,
                    )
                    claude_command = [
                        "claude",
                        "-p",
                        "--output-format",
                        "json",
                        "--model",
                        args.model,
                        "--effort",
                        args.effort,
                        "--max-budget-usd",
                        str(args.max_budget_usd),
                        "--system-prompt",
                        args.system_prompt,
                        *mode.claude_args,
                        prompt,
                    ]
                    process = run_subprocess(claude_command, cwd=Path.cwd())

                    if process.returncode != 0:
                        logger.warning(
                            "Claude CLI non-zero exit: code=%d stderr=%s",
                            process.returncode,
                            process.stderr.strip() or "<empty>",
                        )

                    result = parse_claude_result(
                        mode=mode.name,
                        payload_id=payload_id,
                        iteration=iteration,
                        stdout=process.stdout,
                    )
                    all_results.append(result)
                    logger.info(
                        "Done: mode=%s payload=%s iter=%d ok=%s out_tok=%d ms=%d cost=%.6f",
                        mode.name,
                        payload_id,
                        iteration,
                        result.ok,
                        result.output_tokens,
                        result.duration_ms,
                        result.cost_usd,
                    )
                    logger.debug("Result preview: %s", result.result_preview)
    finally:
        set_plugin_enabled_state(
            plugin_id=args.plugin_id,
            enabled=initial_plugin_state,
            cwd=Path.cwd(),
            logger=logger,
        )
        logger.info("Plugin state restored to: %s", initial_plugin_state)

    without_summary = summarize_mode([r for r in all_results if r.mode == "without_skill"])
    with_summary = summarize_mode([r for r in all_results if r.mode == "with_skill"])

    delta: dict[str, float] = {}
    if (
        without_summary.avg_result_token_estimate
        and with_summary.avg_result_token_estimate
    ):
        delta["visible_output_tokens_pct"] = round(
            (
                with_summary.avg_result_token_estimate
                - without_summary.avg_result_token_estimate
            )
            / without_summary.avg_result_token_estimate
            * 100,
            2,
        )

    if (
        without_summary.avg_output_tokens
        and with_summary.avg_output_tokens
        and without_summary.avg_duration_ms
        and with_summary.avg_duration_ms
        and without_summary.avg_cost_usd
        and with_summary.avg_cost_usd
    ):
        delta.update(
            {
                "output_tokens_pct": round(
                    (with_summary.avg_output_tokens - without_summary.avg_output_tokens)
                    / without_summary.avg_output_tokens
                    * 100,
                    2,
                ),
                "latency_pct": round(
                    (with_summary.avg_duration_ms - without_summary.avg_duration_ms)
                    / without_summary.avg_duration_ms
                    * 100,
                    2,
                ),
                "cost_pct": round(
                    (with_summary.avg_cost_usd - without_summary.avg_cost_usd)
                    / without_summary.avg_cost_usd
                    * 100,
                    2,
                ),
            }
        )

    output = {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "payload_ids": payload_ids,
            "iterations": args.iterations,
            "model": args.model,
            "effort": args.effort,
            "max_budget_usd": args.max_budget_usd,
            "plugin_id": args.plugin_id,
            "skill_command": args.skill_command,
        },
        "summary": {
            "without_skill": asdict(without_summary),
            "with_skill": asdict(with_summary),
            "delta": delta,
        },
        "runs": [asdict(result) for result in all_results],
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output_dir / f"skill_ab_{timestamp}.json"
    output_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(output_path)
    print(
        "| mode | success | valid_json | avg_out_tok | avg_visible_tok | avg_cost_usd | avg_ms | p95_ms | out_tok/s | avg_turns |"
    )
    print("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for mode_name, summary in [
        ("without_skill", without_summary),
        ("with_skill", with_summary),
    ]:
        print(
            f"| {mode_name} | "
            f"{summary.success_rate if summary.success_rate is not None else '-'} | "
            f"{summary.valid_json_rate if summary.valid_json_rate is not None else '-'} | "
            f"{summary.avg_output_tokens if summary.avg_output_tokens is not None else '-'} | "
            f"{summary.avg_result_token_estimate if summary.avg_result_token_estimate is not None else '-'} | "
            f"{summary.avg_cost_usd if summary.avg_cost_usd is not None else '-'} | "
            f"{summary.avg_duration_ms if summary.avg_duration_ms is not None else '-'} | "
            f"{summary.p95_duration_ms if summary.p95_duration_ms is not None else '-'} | "
            f"{summary.avg_output_tokens_per_second if summary.avg_output_tokens_per_second is not None else '-'} | "
            f"{summary.avg_num_turns if summary.avg_num_turns is not None else '-'} |"
        )
    if delta:
        delta_parts: list[str] = []
        if "visible_output_tokens_pct" in delta:
            delta_parts.append(
                f"visible_output_tokens {delta['visible_output_tokens_pct']}%"
            )
        if "output_tokens_pct" in delta:
            delta_parts.append(f"output_tokens {delta['output_tokens_pct']}%")
        if "cost_pct" in delta:
            delta_parts.append(f"cost {delta['cost_pct']}%")
        if "latency_pct" in delta:
            delta_parts.append(f"latency {delta['latency_pct']}%")
        print(f"Delta(with vs without): {', '.join(delta_parts)}.")
    logger.info("Benchmark finished. JSON report: %s", output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
