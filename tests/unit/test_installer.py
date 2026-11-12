"""Unit tests for the datoon installer helpers."""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType

import pytest


def _load_installer() -> ModuleType:
    """Load scripts/install.py as a test module."""
    path = Path(__file__).resolve().parents[2] / "scripts" / "install.py"
    spec = importlib.util.spec_from_file_location("datoon_installer", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["datoon_installer"] = module
    spec.loader.exec_module(module)
    return module


installer = _load_installer()


def test_merge_codex_marketplace_replaces_existing_datoon_entry() -> None:
    """Codex install should be idempotent and avoid duplicate entries."""
    config = {
        "name": "custom",
        "interface": {
            "displayName": "Custom",
        },
        "plugins": [
            {"name": "datoon", "source": {"source": "local", "path": "./old"}},
            {"name": "other", "source": {"source": "local", "path": "./plugins/other"}},
        ],
    }

    merged = installer.merge_codex_marketplace(config)

    names = [plugin["name"] for plugin in merged["plugins"]]
    assert names.count("datoon") == 1
    assert "other" in names
    assert merged["name"] == "custom"
    assert merged["interface"]["displayName"] == "Custom"
    datoon = next(plugin for plugin in merged["plugins"] if plugin["name"] == "datoon")
    assert datoon == installer.DATOON_CODEX_ENTRY


def test_unmerge_codex_marketplace_removes_only_datoon() -> None:
    """Codex uninstall should preserve unrelated plugin entries."""
    config = {
        "plugins": [
            installer.DATOON_CODEX_ENTRY,
            {"name": "other", "source": {"source": "local", "path": "./plugins/other"}},
        ]
    }

    unmerged = installer.unmerge_codex_marketplace(config)

    assert [plugin["name"] for plugin in unmerged["plugins"]] == ["other"]


def test_read_json_object_reports_malformed_json(tmp_path: Path) -> None:
    """Malformed config JSON should fail with a clear installer error."""
    path = tmp_path / "config.json"
    path.write_text('{"plugins": ', encoding="utf-8")

    with pytest.raises(ValueError, match="Malformed JSON"):
        installer.read_json_object(path)


def test_apply_codex_does_not_write_backup_for_malformed_json(tmp_path: Path) -> None:
    """Invalid JSON should not be backed up or overwritten."""
    path = tmp_path / "marketplace.json"
    original = '{"plugins": '
    path.write_text(original, encoding="utf-8")

    with pytest.raises(ValueError, match="Malformed JSON"):
        installer.apply_codex(path, "install")

    assert path.read_text(encoding="utf-8") == original
    assert list(tmp_path.glob("marketplace.json.bak.*")) == []


def test_write_json_with_backup_preserves_existing_file(tmp_path: Path) -> None:
    """Existing config writes should leave a backup with the old contents."""
    path = tmp_path / "marketplace.json"
    original = {"plugins": [{"name": "existing"}]}
    path.write_text(json.dumps(original), encoding="utf-8")

    backup = installer.write_json_with_backup(path, {"plugins": []})

    assert backup is not None
    assert json.loads(backup.read_text(encoding="utf-8")) == original
    assert json.loads(path.read_text(encoding="utf-8")) == {"plugins": []}


def test_write_json_with_backup_avoids_timestamp_collision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Repeated writes in the same timestamp should not overwrite backups."""

    class FixedDateTime:
        @classmethod
        def now(cls, tz: timezone) -> datetime:
            return datetime(2026, 5, 28, 12, 0, tzinfo=tz)

    monkeypatch.setattr(installer, "datetime", FixedDateTime)
    path = tmp_path / "marketplace.json"
    path.write_text('{"version": 1}', encoding="utf-8")

    first_backup = installer.write_json_with_backup(path, {"version": 2})
    second_backup = installer.write_json_with_backup(path, {"version": 3})

    assert first_backup is not None
    assert second_backup is not None
    assert first_backup != second_backup
    assert json.loads(first_backup.read_text(encoding="utf-8")) == {"version": 1}
    assert json.loads(second_backup.read_text(encoding="utf-8")) == {"version": 2}


def test_list_prints_only_selected_deduped_targets(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """--list should honor selected targets and avoid duplicate rows."""
    codex_marketplace = tmp_path / "marketplace.json"
    codex_marketplace.write_text("{}", encoding="utf-8")

    result = installer.main(
        [
            "--list",
            "--target",
            "codex",
            "--target",
            "codex",
            "--codex-marketplace",
            str(codex_marketplace),
        ]
    )
    output = capsys.readouterr().out

    assert result == 0
    assert output.count("| codex | configured |") == 1
    assert "| claude |" not in output


def test_dry_run_dedupes_repeated_targets(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Repeated --target values should not plan repeated file writes."""
    result = installer.main(
        [
            "--dry-run",
            "--target",
            "codex",
            "--target",
            "codex",
            "--codex-marketplace",
            str(tmp_path / "marketplace.json"),
        ]
    )
    output = capsys.readouterr().out

    assert result == 0
    assert output.count("[codex] file:") == 1


def test_parse_args_rejects_multiple_actions() -> None:
    """The CLI should reject ambiguous action combinations."""
    with pytest.raises(SystemExit):
        installer.parse_args(["--list", "--install"])


def test_render_command_quotes_shell_sensitive_arguments() -> None:
    """Displayed command plans should be safe to copy into a shell."""
    assert installer.render_command(["cmd", "two words", "semi;colon"]) == (
        "cmd 'two words' 'semi;colon'"
    )


def test_apply_claude_uses_argument_lists(monkeypatch: pytest.MonkeyPatch) -> None:
    """Claude operations should execute predefined argv lists, not shell strings."""
    commands: list[list[str]] = []

    monkeypatch.setattr(installer, "command_available", lambda command: True)
    monkeypatch.setattr(
        installer,
        "run_command",
        lambda command, *, dry_run: commands.append(command),
    )

    installer.apply_claude("install")

    assert commands == [
        installer.CLAUDE_MARKETPLACE_ADD_COMMAND,
        installer.CLAUDE_INSTALL_COMMAND,
    ]


def test_detection_rows_report_configured_paths(tmp_path: Path) -> None:
    """Detection table should report configured local config files."""
    codex_marketplace = tmp_path / "marketplace.json"
    codex_marketplace.write_text("{}", encoding="utf-8")

    rows = installer.build_detection_rows(codex_marketplace=codex_marketplace)
    by_target = {target: status for target, status, _ in rows}

    assert by_target["codex"] == "configured"
    assert "mcp" not in by_target
