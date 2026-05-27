#!/usr/bin/env python3
"""Install, dry-run, or uninstall datoon integrations."""

from __future__ import annotations

import argparse
import json
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

Action = Literal["dry-run", "install", "uninstall"]
Target = Literal["claude", "codex", "mcp"]

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGETS: tuple[Target, ...] = ("claude", "codex", "mcp")
DATOON_MCP_ENTRY = {
    "command": "uvx",
    "args": ["datoon[mcp]", "datoon-mcp"],
}
DATOON_CODEX_ENTRY = {
    "name": "datoon",
    "source": {
        "source": "local",
        "path": "./plugins/datoon",
    },
    "policy": {
        "installation": "AVAILABLE",
        "authentication": "ON_INSTALL",
    },
    "category": "Productivity",
}
CLAUDE_MARKETPLACE_ADD_COMMAND = [
    "claude",
    "plugin",
    "marketplace",
    "add",
    "andrii-su/datoon",
]
CLAUDE_INSTALL_COMMAND = ["claude", "plugin", "install", "datoon@datoon"]
CLAUDE_UNINSTALL_COMMAND = ["claude", "plugin", "uninstall", "datoon@datoon"]


@dataclass(slots=True, frozen=True)
class PlanStep:
    """One planned installer action."""

    target: Target
    kind: str
    detail: str


def default_mcp_config_path() -> Path:
    """Return a conservative default MCP config path for datoon-owned config."""
    return Path.home() / ".config" / "datoon" / "mcp.json"


def default_codex_marketplace_path(repo_root: Path) -> Path:
    """Return repo-local Codex marketplace path."""
    return repo_root / ".agents" / "plugins" / "marketplace.json"


def read_json_object(path: Path) -> dict[str, Any]:
    """Read a JSON object, returning an empty object for missing files."""
    if not path.exists():
        return {}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Malformed JSON in {path}: {exc.msg}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return parsed


def write_json_with_backup(path: Path, data: dict[str, Any]) -> Path | None:
    """Write JSON after creating a timestamped backup when file exists."""
    path.parent.mkdir(parents=True, exist_ok=True)
    backup_path: Path | None = None
    if path.exists():
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
        backup_path = path.with_name(f"{path.name}.bak.{timestamp}")
        index = 1
        while backup_path.exists():
            backup_path = path.with_name(f"{path.name}.bak.{timestamp}.{index}")
            index += 1
        shutil.copy2(path, backup_path)

    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return backup_path


def merge_mcp_config(config: dict[str, Any]) -> dict[str, Any]:
    """Return config with datoon MCP server entry installed."""
    updated = dict(config)
    mcp_servers = updated.get("mcpServers")
    if not isinstance(mcp_servers, dict):
        mcp_servers = {}
    else:
        mcp_servers = dict(mcp_servers)
    mcp_servers["datoon"] = dict(DATOON_MCP_ENTRY)
    updated["mcpServers"] = mcp_servers
    return updated


def unmerge_mcp_config(config: dict[str, Any]) -> dict[str, Any]:
    """Return config with only the datoon MCP server entry removed."""
    updated = dict(config)
    mcp_servers = updated.get("mcpServers")
    if isinstance(mcp_servers, dict):
        mcp_servers = dict(mcp_servers)
        mcp_servers.pop("datoon", None)
        updated["mcpServers"] = mcp_servers
    return updated


def merge_codex_marketplace(config: dict[str, Any]) -> dict[str, Any]:
    """Return Codex marketplace config with datoon entry installed."""
    updated = dict(config)
    updated.setdefault("name", "datoon-repo")
    interface = updated.get("interface")
    if not isinstance(interface, dict):
        interface = {}
    interface.setdefault("displayName", "Datoon Repo")
    updated["interface"] = interface

    plugins = updated.get("plugins")
    if not isinstance(plugins, list):
        plugins = []
    next_plugins = [
        plugin
        for plugin in plugins
        if not (isinstance(plugin, dict) and plugin.get("name") == "datoon")
    ]
    next_plugins.append(dict(DATOON_CODEX_ENTRY))
    updated["plugins"] = next_plugins
    return updated


def unmerge_codex_marketplace(config: dict[str, Any]) -> dict[str, Any]:
    """Return Codex marketplace config with only the datoon entry removed."""
    updated = dict(config)
    plugins = updated.get("plugins")
    if isinstance(plugins, list):
        updated["plugins"] = [
            plugin
            for plugin in plugins
            if not (isinstance(plugin, dict) and plugin.get("name") == "datoon")
        ]
    return updated


def command_available(command: str) -> bool:
    """Return whether a command is available on PATH."""
    return shutil.which(command) is not None


def render_command(command: list[str]) -> str:
    """Return a shell-safe display form for a command list."""
    return " ".join(shlex.quote(part) for part in command)


def build_detection_rows(
    targets: list[Target] | None = None, *, mcp_config: Path, codex_marketplace: Path
) -> list[tuple[str, str, str]]:
    """Build installer target detection rows."""
    targets = dedupe_targets(targets)
    rows: list[tuple[str, str, str]] = []
    for target in targets:
        if target == "claude":
            rows.append(
                (
                    "claude",
                    "available" if command_available("claude") else "missing",
                    "Claude Code plugin via claude CLI",
                )
            )
        elif target == "codex":
            rows.append(
                (
                    "codex",
                    "configured" if codex_marketplace.exists() else "not configured",
                    str(codex_marketplace),
                )
            )
        elif target == "mcp":
            rows.append(
                (
                    "mcp",
                    "configured" if mcp_config.exists() else "not configured",
                    str(mcp_config),
                )
            )
    return rows


def print_detection_table(rows: list[tuple[str, str, str]]) -> None:
    """Print target detection table."""
    print("| target | status | detail |")
    print("|---|---|---|")
    for target, status, detail in rows:
        print(f"| {target} | {status} | {detail} |")


def run_command(command: list[str], *, dry_run: bool) -> None:
    """Run or print a command."""
    rendered = render_command(command)
    if dry_run:
        print(f"DRY-RUN command: {rendered}")
        return
    subprocess.run(command, check=True)


def plan_claude(action: Action) -> list[PlanStep]:
    """Build Claude Code plugin plan steps."""
    detected = command_available("claude")
    steps = [
        PlanStep(
            target="claude",
            kind="detect",
            detail=f"claude command {'found' if detected else 'not found'}",
        )
    ]
    if action in {"dry-run", "install"}:
        steps.extend(
            [
                PlanStep(
                    target="claude",
                    kind="command",
                    detail=render_command(CLAUDE_MARKETPLACE_ADD_COMMAND),
                ),
                PlanStep(
                    target="claude",
                    kind="command",
                    detail=render_command(CLAUDE_INSTALL_COMMAND),
                ),
            ]
        )
    else:
        steps.append(
            PlanStep(
                target="claude",
                kind="command",
                detail=render_command(CLAUDE_UNINSTALL_COMMAND),
            )
        )
    return steps


def apply_claude(action: Action) -> None:
    """Apply Claude Code plugin action."""
    if not command_available("claude"):
        raise RuntimeError("claude command not found on PATH")
    if action == "install":
        run_command(CLAUDE_MARKETPLACE_ADD_COMMAND, dry_run=False)
        run_command(CLAUDE_INSTALL_COMMAND, dry_run=False)
    elif action == "uninstall":
        run_command(CLAUDE_UNINSTALL_COMMAND, dry_run=False)


def plan_codex(path: Path, action: Action) -> list[PlanStep]:
    """Build Codex marketplace plan steps."""
    exists = path.exists()
    verb = "merge into" if action in {"dry-run", "install"} else "remove from"
    return [
        PlanStep(
            target="codex",
            kind="file",
            detail=f"{verb} {path} ({'exists' if exists else 'will be created if installing'})",
        ),
        PlanStep(
            target="codex",
            kind="entry",
            detail="Codex marketplace plugin entry: datoon -> ./plugins/datoon",
        ),
    ]


def apply_codex(path: Path, action: Action) -> Path | None:
    """Apply Codex marketplace config action."""
    current = read_json_object(path)
    updated = (
        merge_codex_marketplace(current)
        if action == "install"
        else unmerge_codex_marketplace(current)
    )
    return write_json_with_backup(path, updated)


def plan_mcp(path: Path, action: Action) -> list[PlanStep]:
    """Build MCP config plan steps."""
    exists = path.exists()
    verb = "merge into" if action in {"dry-run", "install"} else "remove from"
    return [
        PlanStep(
            target="mcp",
            kind="file",
            detail=f"{verb} {path} ({'exists' if exists else 'will be created if installing'})",
        ),
        PlanStep(
            target="mcp",
            kind="entry",
            detail='MCP server entry: "datoon": {"command":"uvx","args":["datoon[mcp]","datoon-mcp"]}',
        ),
    ]


def apply_mcp(path: Path, action: Action) -> Path | None:
    """Apply MCP config action."""
    current = read_json_object(path)
    updated = (
        merge_mcp_config(current)
        if action == "install"
        else unmerge_mcp_config(current)
    )
    return write_json_with_backup(path, updated)


def print_plan(steps: list[PlanStep]) -> None:
    """Print human-readable plan steps."""
    for step in steps:
        print(f"[{step.target}] {step.kind}: {step.detail}")


def dedupe_targets(targets: list[Target] | None) -> list[Target]:
    """Return target list with duplicates removed while preserving order."""
    if targets is None:
        return list(DEFAULT_TARGETS)
    deduped: list[Target] = []
    for target in targets:
        if target not in deduped:
            deduped.append(target)
    return deduped


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse installer arguments."""
    parser = argparse.ArgumentParser(description="Install datoon integrations.")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument(
        "--list", action="store_true", help="List target detection status."
    )
    action.add_argument(
        "--dry-run", action="store_true", help="Print planned actions only."
    )
    action.add_argument(
        "--install", action="store_true", help="Install selected targets."
    )
    action.add_argument(
        "--uninstall", action="store_true", help="Uninstall selected targets."
    )
    parser.add_argument(
        "--target",
        action="append",
        choices=DEFAULT_TARGETS,
        help="Target to operate on. Repeatable. Defaults to all targets.",
    )
    parser.add_argument(
        "--mcp-config",
        type=Path,
        default=default_mcp_config_path(),
        help="MCP JSON config path for merge/unmerge.",
    )
    parser.add_argument(
        "--codex-marketplace",
        type=Path,
        default=default_codex_marketplace_path(REPO_ROOT),
        help="Codex marketplace JSON path.",
    )
    return parser.parse_args(argv)


def resolve_action(args: argparse.Namespace) -> Action:
    """Resolve argparse flags into action string."""
    if args.install:
        return "install"
    if args.uninstall:
        return "uninstall"
    return "dry-run"


def main(argv: list[str] | None = None) -> int:
    """Run installer."""
    args = parse_args(argv)
    targets = dedupe_targets(args.target)
    if args.list:
        print_detection_table(
            build_detection_rows(
                targets,
                mcp_config=args.mcp_config,
                codex_marketplace=args.codex_marketplace,
            )
        )
        return 0

    action = resolve_action(args)

    steps: list[PlanStep] = []
    for target in targets:
        if target == "claude":
            steps.extend(plan_claude(action))
        elif target == "codex":
            steps.extend(plan_codex(args.codex_marketplace, action))
        elif target == "mcp":
            steps.extend(plan_mcp(args.mcp_config, action))

    print_plan(steps)
    if action == "dry-run":
        return 0

    try:
        for target in targets:
            if target == "claude":
                apply_claude(action)
            elif target == "codex":
                backup = apply_codex(args.codex_marketplace, action)
                if backup is not None:
                    print(f"[codex] backup: {backup}")
            elif target == "mcp":
                backup = apply_mcp(args.mcp_config, action)
                if backup is not None:
                    print(f"[mcp] backup: {backup}")
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"install error: {exc}", file=sys.stderr)
        return 1

    print(f"{action} complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
