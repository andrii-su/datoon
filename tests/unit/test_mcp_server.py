"""Unit tests for MCP server tools (no MCP runtime required)."""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock

import pytest


def _install_mcp_mock() -> None:
    """Inject a minimal mcp stub so mcp_server can be imported without the extra."""
    if "mcp" in sys.modules:
        return

    fastmcp_instance = MagicMock()
    fastmcp_instance.tool.return_value = lambda f: f  # passthrough decorator

    fastmcp_class = MagicMock(return_value=fastmcp_instance)

    fastmcp_mod = ModuleType("mcp.server.fastmcp")
    fastmcp_mod.FastMCP = fastmcp_class  # type: ignore[attr-defined]

    server_mod = ModuleType("mcp.server")
    server_mod.fastmcp = fastmcp_mod  # type: ignore[attr-defined]

    mcp_mod = ModuleType("mcp")
    mcp_mod.server = server_mod  # type: ignore[attr-defined]

    sys.modules["mcp"] = mcp_mod
    sys.modules["mcp.server"] = server_mod
    sys.modules["mcp.server.fastmcp"] = fastmcp_mod


_install_mcp_mock()

from datoon.mcp_server import analyze_json, convert_json  # noqa: E402


def test_analyze_json_detects_candidate() -> None:
    """Uniform object array payload should be identified as TOON candidate."""
    payload = '{"rows":[{"id":1,"v":"a"},{"id":2,"v":"b"},{"id":3,"v":"c"}]}'
    result = analyze_json(payload)
    assert result["is_candidate"] is True
    assert result["uniform_array_count"] == 1


def test_analyze_json_rejects_non_candidate() -> None:
    """Non-uniform payload should not be flagged as candidate."""
    result = analyze_json('{"x":1,"y":2}')
    assert result["is_candidate"] is False
    assert "reason" in result


def test_analyze_json_invalid_json_returns_error() -> None:
    """Invalid JSON must return error key, not raise."""
    result = analyze_json("{bad json")
    assert "error" in result
    assert "Invalid JSON" in result["error"]


def test_analyze_json_invalid_config_returns_error() -> None:
    """Invalid config parameters must return error key, not raise."""
    result = analyze_json('{"x":1}', max_depth=0)
    assert "error" in result
    assert "Invalid config" in result["error"]


def test_convert_json_skips_non_candidate(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-candidate payload should skip without calling CLI."""
    called = {"value": False}

    def _unexpected(_: str, **kw: object) -> str:
        called["value"] = True
        raise AssertionError("CLI must not be called for non-candidates.")

    monkeypatch.setattr("datoon.converter._run_toon_cli", _unexpected)
    result = convert_json('{"x":1}')
    assert "error" not in result
    assert result["report"]["decision"] == "skip"
    assert called["value"] is False


def test_convert_json_converts_when_savings_sufficient(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Candidate payload should convert when savings clear threshold."""
    payload = '{"rows":[{"id":1,"v":"a"},{"id":2,"v":"b"},{"id":3,"v":"c"}]}'
    monkeypatch.setattr(
        "datoon.converter._run_toon_cli",
        lambda _, **kw: "rows[3]{id,v}:\n  1,a\n  2,b\n  3,c\n",
    )
    token_seq = iter([100, 60])
    monkeypatch.setattr("datoon.converter.estimate_tokens", lambda _: next(token_seq))

    result = convert_json(payload, min_savings=0.15)
    assert "error" not in result
    assert result["report"]["decision"] == "convert"


def test_convert_json_invalid_json_returns_error() -> None:
    """Invalid JSON must return error key, not raise."""
    result = convert_json("{bad}")
    assert "error" in result
    assert "Invalid JSON" in result["error"]


def test_convert_json_invalid_config_returns_error() -> None:
    """Invalid config must return error key, not raise."""
    result = convert_json('{"x":1}', min_savings=2.0)
    assert "error" in result
    assert "Invalid config" in result["error"]


def test_convert_json_cli_failure_returns_skip(monkeypatch: pytest.MonkeyPatch) -> None:
    """CLI failure in non-force mode returns skip outcome, not error key."""
    from datoon.converter import DatoonError

    payload = '{"rows":[{"id":1,"v":"a"},{"id":2,"v":"b"},{"id":3,"v":"c"}]}'

    def _fail(_: str, **kw: object) -> str:
        raise DatoonError("cli down")

    monkeypatch.setattr("datoon.converter._run_toon_cli", _fail)
    result = convert_json(payload, force=False)
    assert "error" not in result
    assert result["report"]["decision"] == "skip"
