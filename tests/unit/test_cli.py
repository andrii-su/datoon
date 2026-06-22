"""Unit tests for the datoon CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from datoon.cli import _resolve_format, main


# ---------------------------------------------------------------------------
# _resolve_format
# ---------------------------------------------------------------------------


def test_resolve_format_explicit_flag_wins() -> None:
    assert _resolve_format("data.csv", "yaml") == "yaml"


def test_resolve_format_detects_csv_from_extension() -> None:
    assert _resolve_format("data.csv", None) == "csv"


def test_resolve_format_detects_parquet_from_extension() -> None:
    assert _resolve_format("data.parquet", None) == "parquet"


def test_resolve_format_defaults_to_json_for_stdin() -> None:
    assert _resolve_format(None, None) == "json"


def test_resolve_format_defaults_to_json_for_unknown_extension() -> None:
    assert _resolve_format("data.txt", None) == "json"


# ---------------------------------------------------------------------------
# JSON path (default behaviour, unchanged)
# ---------------------------------------------------------------------------


def test_main_converts_json_from_stdin(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = '{"rows":[{"id":1,"v":"a"},{"id":2,"v":"b"},{"id":3,"v":"c"}]}'
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(payload))
    monkeypatch.setattr(
        "datoon.converter._run_toon_cli",
        lambda _, **kw: "rows[3]{id,v}:\n  1,a\n  2,b\n  3,c\n",
    )
    token_seq = iter([100, 40])
    monkeypatch.setattr("datoon.converter.estimate_tokens", lambda _: next(token_seq))

    rc = main([])
    assert rc == 0
    assert "rows[3]" in capsys.readouterr().out


def test_main_returns_1_on_invalid_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO("{bad}"))
    rc = main([])
    assert rc == 1
    assert "datoon error" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# CSV path
# ---------------------------------------------------------------------------

_CSV = "id,name,role\n1,Ada,admin\n2,Lin,analyst\n3,Grace,viewer\n"


def test_main_converts_csv_via_flag(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    csv_file = tmp_path / "data.csv"
    csv_file.write_text(_CSV)
    monkeypatch.setattr(
        "datoon.converter._run_toon_cli",
        lambda _, **kw: "rows[3]{id,name,role}:\n  1,Ada,admin\n",
    )
    token_seq = iter([100, 30])
    monkeypatch.setattr("datoon.converter.estimate_tokens", lambda _: next(token_seq))

    rc = main([str(csv_file), "--format", "csv"])
    assert rc == 0
    assert "rows[3]" in capsys.readouterr().out


def test_main_auto_detects_csv_from_extension(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    csv_file = tmp_path / "users.csv"
    csv_file.write_text(_CSV)
    monkeypatch.setattr(
        "datoon.converter._run_toon_cli",
        lambda _, **kw: "rows[3]{id,name,role}:\n  1,Ada,admin\n",
    )
    token_seq = iter([100, 30])
    monkeypatch.setattr("datoon.converter.estimate_tokens", lambda _: next(token_seq))

    rc = main([str(csv_file)])
    assert rc == 0
    assert "rows[3]" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# JSONL path
# ---------------------------------------------------------------------------

_JSONL = (
    '{"id":1,"name":"Ada","role":"admin"}\n'
    '{"id":2,"name":"Lin","role":"analyst"}\n'
    '{"id":3,"name":"Grace","role":"viewer"}\n'
)


def test_main_converts_jsonl_from_stdin(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(_JSONL))
    monkeypatch.setattr(
        "datoon.converter._run_toon_cli",
        lambda _, **kw: "rows[3]{id,name,role}:\n  1,Ada,admin\n",
    )
    token_seq = iter([100, 30])
    monkeypatch.setattr("datoon.converter.estimate_tokens", lambda _: next(token_seq))

    rc = main(["--format", "jsonl"])
    assert rc == 0
    assert "rows[3]" in capsys.readouterr().out


def test_main_auto_detects_jsonl_from_extension(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    f = tmp_path / "data.jsonl"
    f.write_text(_JSONL)
    monkeypatch.setattr(
        "datoon.converter._run_toon_cli",
        lambda _, **kw: "rows[3]{id,name,role}:\n  1,Ada,admin\n",
    )
    token_seq = iter([100, 30])
    monkeypatch.setattr("datoon.converter.estimate_tokens", lambda _: next(token_seq))

    rc = main([str(f)])
    assert rc == 0


# ---------------------------------------------------------------------------
# XML path
# ---------------------------------------------------------------------------

_XML = """<users>
  <user><id>1</id><name>Ada</name><role>admin</role></user>
  <user><id>2</id><name>Lin</name><role>analyst</role></user>
  <user><id>3</id><name>Grace</name><role>viewer</role></user>
</users>"""


def test_main_converts_xml_via_flag(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    f = tmp_path / "data.xml"
    f.write_text(_XML)
    monkeypatch.setattr(
        "datoon.converter._run_toon_cli",
        lambda _, **kw: "rows[3]{id,name,role}:\n  1,Ada,admin\n",
    )
    token_seq = iter([100, 30])
    monkeypatch.setattr("datoon.converter.estimate_tokens", lambda _: next(token_seq))

    rc = main([str(f), "--format", "xml"])
    assert rc == 0
    assert "rows[3]" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Binary format without file path
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fmt", ["excel", "parquet", "orc", "avro", "numbers"])
def test_main_binary_format_without_path_returns_1(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    fmt: str,
) -> None:
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(""))
    rc = main(["--format", fmt])
    assert rc == 1
    assert "requires a file path" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Report output with tabular format
# ---------------------------------------------------------------------------


def test_main_csv_report_stdout(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    csv_file = tmp_path / "data.csv"
    csv_file.write_text(_CSV)
    monkeypatch.setattr(
        "datoon.converter._run_toon_cli",
        lambda _, **kw: "rows[3]{id,name,role}:\n  1,Ada,admin\n",
    )
    token_seq = iter([100, 30])
    monkeypatch.setattr("datoon.converter.estimate_tokens", lambda _: next(token_seq))

    rc = main([str(csv_file), "--report-stdout"])
    assert rc == 0
    captured = capsys.readouterr()
    report = json.loads(captured.err)
    assert report["decision"] == "convert"


def test_main_csv_skips_when_savings_insufficient(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    csv_file = tmp_path / "data.csv"
    csv_file.write_text(_CSV)
    monkeypatch.setattr(
        "datoon.converter._run_toon_cli",
        lambda _, **kw: "rows[3]{id,name,role}:\n  1,Ada,admin\n",
    )
    token_seq = iter([100, 98])
    monkeypatch.setattr("datoon.converter.estimate_tokens", lambda _: next(token_seq))

    rc = main([str(csv_file), "--report-stdout"])
    assert rc == 0
    report = json.loads(capsys.readouterr().err)
    assert report["decision"] == "skip"
    assert "below threshold" in report["reason"]
