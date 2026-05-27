#!/usr/bin/env python3
"""Validate plugin and marketplace metadata consistency."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]

CANONICAL = {
    "name": "datoon",
    "version": "1.4.1",
    "description": "Smart JSON-to-TOON conversion with pragmatic auto-gating for LLM prompts.",
    "author_name": "Andrii Suruhov",
    "author_url": "https://github.com/andrii-su",
    "homepage": "https://github.com/andrii-su/datoon",
    "repository": "https://github.com/andrii-su/datoon",
    "license": "MIT",
    "keywords": ["llm", "prompt-engineering", "json", "toon", "data"],
}

CLAUDE_PLUGIN = REPO_ROOT / ".claude-plugin" / "plugin.json"
CLAUDE_MARKETPLACE = REPO_ROOT / ".claude-plugin" / "marketplace.json"
CODEX_PLUGIN = REPO_ROOT / "plugins" / "datoon" / ".codex-plugin" / "plugin.json"
CODEX_MARKETPLACE = REPO_ROOT / ".agents" / "plugins" / "marketplace.json"


def read_json(path: Path) -> dict[str, Any]:
    """Read JSON object with path context."""
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Missing required metadata file: {path}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return parsed


def expect(errors: list[str], condition: bool, message: str) -> None:
    """Append message when condition is false."""
    if not condition:
        errors.append(message)


def validate_plugin(path: Path, plugin: dict[str, Any]) -> list[str]:
    """Validate common plugin manifest fields."""
    errors: list[str] = []
    expect(errors, plugin.get("name") == CANONICAL["name"], f"{path}: name mismatch")
    expect(
        errors,
        plugin.get("version") == CANONICAL["version"],
        f"{path}: version mismatch",
    )
    expect(
        errors,
        plugin.get("description") == CANONICAL["description"],
        f"{path}: description mismatch",
    )
    author = plugin.get("author")
    expect(errors, isinstance(author, dict), f"{path}: author must be an object")
    if isinstance(author, dict):
        expect(
            errors,
            author.get("name") == CANONICAL["author_name"],
            f"{path}: author.name mismatch",
        )
        expect(
            errors,
            author.get("url") == CANONICAL["author_url"],
            f"{path}: author.url mismatch",
        )
    expect(
        errors,
        plugin.get("homepage") == CANONICAL["homepage"],
        f"{path}: homepage mismatch",
    )
    expect(
        errors,
        plugin.get("repository") == CANONICAL["repository"],
        f"{path}: repository mismatch",
    )
    expect(
        errors,
        plugin.get("license") == CANONICAL["license"],
        f"{path}: license mismatch",
    )
    expect(
        errors,
        plugin.get("keywords") == CANONICAL["keywords"],
        f"{path}: keywords mismatch",
    )
    return errors


def validate_claude_marketplace(marketplace: dict[str, Any]) -> list[str]:
    """Validate Claude marketplace metadata."""
    errors: list[str] = []
    expect(
        errors,
        marketplace.get("name") == CANONICAL["name"],
        f"{CLAUDE_MARKETPLACE}: name mismatch",
    )
    expect(
        errors,
        marketplace.get("description") == CANONICAL["description"],
        f"{CLAUDE_MARKETPLACE}: description mismatch",
    )
    owner = marketplace.get("owner")
    expect(
        errors,
        isinstance(owner, dict),
        f"{CLAUDE_MARKETPLACE}: owner must be an object",
    )
    if isinstance(owner, dict):
        expect(
            errors,
            owner.get("name") == CANONICAL["author_name"],
            f"{CLAUDE_MARKETPLACE}: owner.name mismatch",
        )
        expect(
            errors,
            owner.get("url") == CANONICAL["author_url"],
            f"{CLAUDE_MARKETPLACE}: owner.url mismatch",
        )
    plugins = marketplace.get("plugins")
    expect(
        errors,
        isinstance(plugins, list) and len(plugins) == 1,
        f"{CLAUDE_MARKETPLACE}: expected one plugin",
    )
    if isinstance(plugins, list) and plugins:
        entry = plugins[0]
        expect(
            errors,
            isinstance(entry, dict),
            f"{CLAUDE_MARKETPLACE}: plugin entry must be object",
        )
        if isinstance(entry, dict):
            expect(
                errors,
                entry.get("name") == CANONICAL["name"],
                f"{CLAUDE_MARKETPLACE}: plugin name mismatch",
            )
            expect(
                errors,
                entry.get("category") == "productivity",
                f"{CLAUDE_MARKETPLACE}: plugin category mismatch",
            )
    return errors


def validate_codex_marketplace(marketplace: dict[str, Any]) -> list[str]:
    """Validate Codex marketplace entry."""
    errors: list[str] = []
    expect(
        errors,
        marketplace.get("name") == "datoon-repo",
        f"{CODEX_MARKETPLACE}: marketplace name mismatch",
    )
    plugins = marketplace.get("plugins")
    expect(
        errors,
        isinstance(plugins, list) and len(plugins) == 1,
        f"{CODEX_MARKETPLACE}: expected one plugin",
    )
    if isinstance(plugins, list) and plugins:
        entry = plugins[0]
        expect(
            errors,
            isinstance(entry, dict),
            f"{CODEX_MARKETPLACE}: plugin entry must be object",
        )
        if isinstance(entry, dict):
            expect(
                errors,
                entry.get("name") == CANONICAL["name"],
                f"{CODEX_MARKETPLACE}: plugin name mismatch",
            )
            expect(
                errors,
                entry.get("category") == "Productivity",
                f"{CODEX_MARKETPLACE}: plugin category mismatch",
            )
            source = entry.get("source")
            expect(
                errors,
                isinstance(source, dict) and source.get("path") == "./plugins/datoon",
                f"{CODEX_MARKETPLACE}: source.path mismatch",
            )
    return errors


def validate() -> list[str]:
    """Validate all plugin metadata files."""
    errors: list[str] = []
    errors.extend(validate_plugin(CLAUDE_PLUGIN, read_json(CLAUDE_PLUGIN)))
    errors.extend(validate_plugin(CODEX_PLUGIN, read_json(CODEX_PLUGIN)))
    errors.extend(validate_claude_marketplace(read_json(CLAUDE_MARKETPLACE)))
    errors.extend(validate_codex_marketplace(read_json(CODEX_MARKETPLACE)))
    return errors


def main() -> int:
    """Run validation and return shell-style exit code."""
    try:
        errors = validate()
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(f"plugin-metadata check failed: {exc}", file=sys.stderr)
        return 1

    if errors:
        print("plugin-metadata check failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print("plugin-metadata check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
