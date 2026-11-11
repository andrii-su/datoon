"""MCP server exposing datoon conversion and analysis as tools."""

from __future__ import annotations

import json
import os
from typing import Any

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:
    raise ImportError(
        "MCP support requires the 'mcp' extra: pip install datoon[mcp]"
    ) from exc

from datoon import __version__
from datoon.analyzer import analyze_payload
from datoon.converter import DatoonError, convert_json_for_llm
from datoon.models import ConversionConfig
from datoon.readers import TEXT_FORMATS, read_tabular
from datoon.tokenizers import DEFAULT_TOKENIZER, TOKENIZER_ENV_VAR

mcp = FastMCP(
    "datoon",
    instructions=(
        "Smart JSON-to-TOON gateway. "
        "Use convert_json to compress structured payloads before sending to a model. "
        "Use analyze_json to check if a payload is a good TOON candidate without converting."
    ),
)
# FastMCP has no `version` parameter; set it on the underlying server so the
# MCP `initialize` handshake reports datoon's version instead of the mcp
# library's default.
mcp._mcp_server.version = __version__


def _tokenizer_spec(tokenizer: str | None) -> str:
    """Pick the tokenizer spec: argument, then environment, then the default."""
    return tokenizer or os.environ.get(TOKENIZER_ENV_VAR) or DEFAULT_TOKENIZER


@mcp.tool()
def convert_json(
    json_text: str,
    force: bool = False,
    min_savings: float = 0.15,
    max_depth: int = 6,
    min_uniform_rows: int = 3,
    tokenizer: str | None = None,
) -> dict[str, Any]:
    """Convert a JSON payload to TOON when structure and savings meet policy.

    Returns the final payload text (TOON or original JSON) and a report
    explaining the conversion decision.

    `tokenizer` picks the token counter for the estimates: auto (tiktoken
    o200k_base when installed, else chars:3), chars[:N], tiktoken[:ENCODING],
    claude:MODEL_ID (Anthropic token counting API, makes network calls) or
    hf:REPO_ID. Defaults to $DATOON_TOKENIZER, else auto. Counts are estimates.
    """
    try:
        config = ConversionConfig(
            min_savings_ratio=min_savings,
            max_depth=max_depth,
            min_uniform_rows=min_uniform_rows,
            force=force,
            tokenizer=_tokenizer_spec(tokenizer),
        )
        outcome = convert_json_for_llm(json_text, config)
        return {
            "payload": outcome.payload_text,
            "report": outcome.report.as_dict(),
        }
    except DatoonError as exc:
        return {"error": str(exc)}
    except ValueError as exc:
        return {"error": f"Invalid config: {exc}"}


@mcp.tool()
def analyze_json(
    json_text: str,
    max_depth: int = 6,
    min_uniform_rows: int = 3,
) -> dict[str, Any]:
    """Analyze a JSON payload and report whether it is a TOON candidate.

    Inspects structure only; it does not run the TOON encoder.
    """
    try:
        parsed = json.loads(json_text)
    except json.JSONDecodeError as exc:
        return {"error": f"Invalid JSON: {exc.msg} (pos={exc.pos})"}

    try:
        config = ConversionConfig(
            max_depth=max_depth, min_uniform_rows=min_uniform_rows
        )
    except ValueError as exc:
        return {"error": f"Invalid config: {exc}"}

    analysis = analyze_payload(parsed, config)
    return {
        "is_candidate": analysis.is_candidate,
        "reason": analysis.reason,
        "max_depth": analysis.max_depth,
        "uniform_array_count": analysis.uniform_array_count,
    }


@mcp.tool()
def convert_text(
    text: str,
    fmt: str = "csv",
    force: bool = False,
    min_savings: float = 0.15,
    max_depth: int = 6,
    min_uniform_rows: int = 3,
    tokenizer: str | None = None,
) -> dict[str, Any]:
    """Convert structured text (csv, yaml, xml, jsonl) to TOON with policy gating.

    Supported formats: csv, yaml, xml, jsonl.
    For JSON input use convert_json. Binary formats (parquet, excel, etc.) require the CLI.

    `tokenizer` picks the token counter for the estimates: auto (tiktoken
    o200k_base when installed, else chars:3), chars[:N], tiktoken[:ENCODING],
    claude:MODEL_ID (Anthropic token counting API, makes network calls) or
    hf:REPO_ID. Defaults to $DATOON_TOKENIZER, else auto. Counts are estimates.
    """
    if fmt not in TEXT_FORMATS:
        return {
            "error": (
                f"Unsupported format '{fmt}' for text input. "
                f"Supported: {sorted(TEXT_FORMATS)}."
            )
        }
    try:
        rows = read_tabular(fmt, text=text)
        json_text = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
        config = ConversionConfig(
            min_savings_ratio=min_savings,
            max_depth=max_depth,
            min_uniform_rows=min_uniform_rows,
            force=force,
            tokenizer=_tokenizer_spec(tokenizer),
        )
        outcome = convert_json_for_llm(json_text, config)
        return {
            "payload": outcome.payload_text,
            "report": outcome.report.as_dict(),
        }
    except (DatoonError, ValueError, ImportError) as exc:
        return {"error": str(exc)}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
