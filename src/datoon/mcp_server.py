"""MCP server exposing datoon conversion and analysis as tools."""

from __future__ import annotations

from typing import Any

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:
    raise ImportError(
        "MCP support requires the 'mcp' extra: pip install datoon[mcp]"
    ) from exc

from datoon.analyzer import analyze_payload
from datoon.converter import DatoonError, convert_json_for_llm
from datoon.models import ConversionConfig

mcp = FastMCP(
    "datoon",
    instructions=(
        "Smart JSON-to-TOON gateway. "
        "Use convert_json to compress structured payloads before sending to a model. "
        "Use analyze_json to check if a payload is a good TOON candidate without converting."
    ),
)


@mcp.tool()
def convert_json(
    json_text: str,
    force: bool = False,
    min_savings: float = 0.15,
    max_depth: int = 6,
    min_uniform_rows: int = 3,
    timeout: int = 30,
) -> dict[str, Any]:
    """Convert a JSON payload to TOON when structure and savings meet policy.

    Returns the final payload text (TOON or original JSON) and a report
    explaining the conversion decision.
    """
    try:
        config = ConversionConfig(
            min_savings_ratio=min_savings,
            max_depth=max_depth,
            min_uniform_rows=min_uniform_rows,
            force=force,
            toon_cli_timeout=timeout,
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

    Does not invoke the TOON CLI — safe to call without Node.js installed.
    """
    import json

    try:
        parsed = json.loads(json_text)
    except json.JSONDecodeError as exc:
        return {"error": f"Invalid JSON: {exc.msg} (pos={exc.pos})"}

    try:
        config = ConversionConfig(max_depth=max_depth, min_uniform_rows=min_uniform_rows)
    except ValueError as exc:
        return {"error": f"Invalid config: {exc}"}

    analysis = analyze_payload(parsed, config)
    return {
        "is_candidate": analysis.is_candidate,
        "reason": analysis.reason,
        "max_depth": analysis.max_depth,
        "uniform_array_count": analysis.uniform_array_count,
    }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
