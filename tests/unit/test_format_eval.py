"""Offline tests for the format reading benchmark in benchmarks/format_eval/."""

from __future__ import annotations

import csv
import importlib
import io
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import toon_format

# `benchmarks` is not an installed package; put the repo root on the path, the
# way test_benchmark_readme.py reaches benchmarks/run.py by file location, and
# import after that.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_datasets = importlib.import_module("benchmarks.format_eval.datasets")
_formats = importlib.import_module("benchmarks.format_eval.formats")
_questions = importlib.import_module("benchmarks.format_eval.questions")
run = importlib.import_module("benchmarks.format_eval.run")

DEFAULT_SHAPES = _datasets.DEFAULT_SHAPES
KEY_COLUMN = _datasets.KEY_COLUMN
KIND_CATEGORY = _datasets.KIND_CATEGORY
KIND_INTEGER = _datasets.KIND_INTEGER
KIND_NULLABLE_INTEGER = _datasets.KIND_NULLABLE_INTEGER
Table = _datasets.Table
build_table = _datasets.build_table
build_tables = _datasets.build_tables
parse_shape = _datasets.parse_shape
FORMATS = _formats.FORMATS
QUESTION_KINDS = _questions.QUESTION_KINDS
Question = _questions.Question
build_questions = _questions.build_questions
score = _questions.score

# ---------------------------------------------------------------------------
# Datasets
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("rows", "columns"), DEFAULT_SHAPES)
def test_table_is_deterministic_and_shaped(rows: int, columns: int) -> None:
    table = build_table(rows, columns, seed=0)
    assert table == build_table(rows, columns, seed=0)
    assert table.rows != build_table(rows, columns, seed=1).rows
    assert table.shape == f"{rows}x{columns}"
    assert len(table.rows) == rows
    assert len(table.columns) == columns == len(set(table.columns))
    assert table.columns[0] == KEY_COLUMN
    assert all(list(row) == table.columns for row in table.rows)
    assert len({row[KEY_COLUMN] for row in table.rows}) == rows
    for kind in (KIND_CATEGORY, KIND_INTEGER, KIND_NULLABLE_INTEGER):
        assert kind in table.kinds.values()


@pytest.mark.parametrize(("rows", "columns"), DEFAULT_SHAPES)
def test_integer_columns_hold_unique_values(rows: int, columns: int) -> None:
    table = build_table(rows, columns, seed=0)
    for column, kind in table.kinds.items():
        if kind == KIND_INTEGER:
            values = [row[column] for row in table.rows]
            assert len(set(values)) == len(values)


def test_category_columns_have_five_to_eight_values() -> None:
    table = build_table(300, 10, seed=0)
    for column, kind in table.kinds.items():
        if kind == KIND_CATEGORY:
            assert 5 <= len({row[column] for row in table.rows}) <= 8


def test_build_tables_covers_shapes_and_seeds() -> None:
    tables = build_tables(seeds=2)
    assert len(tables) == len(DEFAULT_SHAPES) * 2
    assert len({table.name for table in tables}) == len(tables)


def test_parse_shape() -> None:
    assert parse_shape("20x4") == (20, 4)
    assert parse_shape(" 100X11 ") == (100, 11)
    for bad in ("20", "20x", "x4", "20x3", "3x4", "twentyx4"):
        with pytest.raises(ValueError):
            parse_shape(bad)


# ---------------------------------------------------------------------------
# Formats
# ---------------------------------------------------------------------------


def test_format_names_are_fixed() -> None:
    assert list(FORMATS) == ["objects", "arrays", "toon", "markdown", "csv"]


@pytest.mark.parametrize(("rows", "columns"), DEFAULT_SHAPES)
def test_every_format_renders_and_round_trips(rows: int, columns: int) -> None:
    table = build_table(rows, columns, seed=0)
    rendered = {name: render(table) for name, render in FORMATS.items()}
    assert all(text.strip() for text in rendered.values())

    objects = json.loads(rendered["objects"])
    assert objects == {"columns": table.columns, "rows": table.rows}

    arrays = json.loads(rendered["arrays"])
    assert arrays["columns"] == table.columns
    assert [dict(zip(table.columns, row)) for row in arrays["rows"]] == table.rows

    assert toon_format.decode(rendered["toon"]) == {"rows": table.rows}

    csv_rows = list(csv.reader(io.StringIO(rendered["csv"])))
    assert csv_rows[0] == table.columns
    assert len(csv_rows) == rows + 1

    markdown_lines = rendered["markdown"].splitlines()
    assert len(markdown_lines) == rows + 2
    assert markdown_lines[1] == "| " + " | ".join(["---"] * columns) + " |"


def test_json_formats_are_compact_and_keep_unicode() -> None:
    table = Table(
        name="unicode",
        columns=["row_id", "country"],
        rows=[{"row_id": "r-0001", "country": "Україна"}],
    )
    for name in ("objects", "arrays"):
        text = FORMATS[name](table)
        assert "Україна" in text
        assert ": " not in text and ", " not in text


def _null_and_empty_table() -> Table:
    return Table(
        name="nulls",
        columns=["row_id", "note", "flag"],
        rows=[
            {"row_id": "r-0001", "note": None, "flag": True},
            {"row_id": "r-0002", "note": "", "flag": False},
            {"row_id": "r-0003", "note": "a|b, c", "flag": None},
        ],
    )


def test_csv_keeps_null_distinct_from_empty_string() -> None:
    parsed = list(csv.reader(io.StringIO(FORMATS["csv"](_null_and_empty_table()))))
    assert parsed[1] == ["r-0001", "NULL", "true"]
    assert parsed[2] == ["r-0002", "", "false"]
    assert parsed[3] == ["r-0003", "a|b, c", "NULL"]


def test_markdown_keeps_null_distinct_and_escapes_pipes() -> None:
    lines = FORMATS["markdown"](_null_and_empty_table()).splitlines()
    assert lines[0] == "| row_id | note | flag |"
    assert lines[2] == "| r-0001 | NULL | true |"
    assert lines[3] == "| r-0002 |  | false |"
    assert lines[4] == "| r-0003 | a\\|b, c | NULL |"


# ---------------------------------------------------------------------------
# Questions and scoring
# ---------------------------------------------------------------------------

_TINY_ROWS = [
    {"row_id": "r-0001", "plan_name": "Free", "sessions": 10, "refunds": None},
    {"row_id": "r-0002", "plan_name": "Pro Annual", "sessions": 40, "refunds": 3},
    {"row_id": "r-0003", "plan_name": "Pro Annual", "sessions": 90, "refunds": None},
    {"row_id": "r-0004", "plan_name": "Free", "sessions": 20, "refunds": 0},
    {"row_id": "r-0005", "plan_name": "Pro Annual", "sessions": 30, "refunds": 7},
]
_TINY_PLAN_COUNTS = {"Free": 2, "Pro Annual": 3}


def _tiny_table() -> Table:
    return Table(
        name="tiny",
        columns=["row_id", "plan_name", "sessions", "refunds"],
        rows=[dict(row) for row in _TINY_ROWS],
        kinds={
            "plan_name": KIND_CATEGORY,
            "sessions": KIND_INTEGER,
            "refunds": KIND_NULLABLE_INTEGER,
        },
    )


def test_gold_answers_on_tiny_table() -> None:
    by_id = {row["row_id"]: row for row in _TINY_ROWS}
    questions = {question.kind: question for question in build_questions(_tiny_table())}
    assert list(questions) == list(QUESTION_KINDS)

    assert questions["row_count"].gold == 5

    lookup = re.search(
        r'value of `(\w+)` in the row where `row_id` is "([^"]+)"',
        questions["lookup"].text,
    )
    assert lookup is not None
    column, row_id = lookup.groups()
    assert row_id in {"r-0003", "r-0004", "r-0005"}  # middle or end, not first rows
    assert questions["lookup"].gold == by_id[row_id][column]

    filtered = re.search(
        r'`plan_name` equal to "([^"]+)"', questions["filter_count"].text
    )
    assert filtered is not None
    assert questions["filter_count"].gold == _TINY_PLAN_COUNTS[filtered.group(1)]

    assert questions["argmax"].gold == "r-0003"

    diff = re.search(
        r'`sessions` in the row where `row_id` is "([^"]+)" minus `sessions` in '
        r'the row where `row_id` is "([^"]+)"',
        questions["diff"].text,
    )
    assert diff is not None
    first, second = diff.groups()
    assert first != second
    assert (
        questions["diff"].gold == by_id[first]["sessions"] - by_id[second]["sessions"]
    )

    assert questions["null_count"].gold == 2


def test_questions_are_stable_and_numbered() -> None:
    table = build_table(100, 11, seed=0)
    questions = build_questions(table)
    assert questions == build_questions(table)
    assert [question.id for question in questions] == [f"q{i}" for i in range(1, 7)]


@pytest.mark.parametrize(
    ("gold", "answer", "expected"),
    [
        (5, 5, True),
        (5, "5", True),
        (5, " 5 ", True),
        (5, 5.0, True),
        (5, "5.0", True),
        (5, 5.5, False),
        (5, True, False),
        (5, "five", False),
        (5, None, False),
        (5, [5], False),
        (5, "inf", False),
        (5, float("inf"), False),
        (5, "1e400", False),
        (-12, "-12", True),
        (1234.5678, 1234.5678, True),
        (1234.5678, "1234.5678", True),
        (1234.5678, 1234.5678 + 5e-7, True),
        (1234.5678, 1234.568, False),
        (1.25, "abc", False),
        (1.25, float("nan"), False),
        (1.25, "inf", False),
        (1.25, False, False),
        ("r-0003", "r-0003", True),
        ("r-0003", " r-0003\n", True),
        ("r-0003", "r-0004", False),
        ("r-0003", 3, False),
        ("r-0003", None, False),
        (True, True, True),
        (True, "TRUE", True),
        (False, "false", True),
        (False, " False ", True),
        (True, False, False),
        (True, 1, False),
        (True, "yes", False),
        (None, None, True),
        (None, "NULL", True),
        (None, "null", True),
        (None, "", False),
        (None, 0, False),
        (None, "None", False),
    ],
)
def test_score_edge_cases(gold: Any, answer: Any, expected: bool) -> None:
    assert score("lookup", gold, answer) is expected


def test_score_never_raises_on_odd_types() -> None:
    for answer in ({"a": 1}, object(), b"5", complex(1, 2)):
        assert score("row_count", 5, answer) is False
        assert score("lookup", "x", answer) is False


# ---------------------------------------------------------------------------
# Prompts, reply parsing, grading
# ---------------------------------------------------------------------------


def test_prompt_wraps_table_and_shares_questions_across_formats() -> None:
    table = build_table(20, 4, seed=0)
    specs = run.build_plan([table], list(FORMATS), repeats=2)
    assert len(specs) == len(FORMATS) * 2
    question_parts = {spec.user_message.split("</table>", 1)[1] for spec in specs}
    assert len(question_parts) == 1
    for spec in specs:
        assert spec.user_message.startswith(f'<table format="{spec.format_name}">\n')
        assert spec.payload in spec.user_message
        for question in spec.questions:
            assert f"[{question.id}] {question.text}" in spec.user_message


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('{"q1": 5, "q2": "r-0001"}', {"q1": 5, "q2": "r-0001"}),
        ('```json\n{"q1": 5}\n```', {"q1": 5}),
        ('```\n{"q1": null}\n```\n', {"q1": None}),
        ('Here you go: {"q1": {"a": 1}} done', {"q1": {"a": 1}}),
        ('{"q1": "a}b"} {"q2": 2}', {"q1": "a}b"}),
        ("no json here", None),
        ("[1, 2, 3]", None),
        ('{"q1": 5', None),
        ("", None),
        ("```json\n```", None),
    ],
)
def test_parse_reply(text: str, expected: dict[str, Any] | None) -> None:
    assert run.parse_reply(text) == expected


def test_grade_treats_missing_ids_as_wrong_even_for_null_gold() -> None:
    questions = [
        Question(id="q1", kind="lookup", text="?", gold=None),
        Question(id="q2", kind="row_count", text="?", gold=3),
    ]
    graded = run.grade(questions, {"q2": "3"})
    assert [item["correct"] for item in graded] == [False, True]
    assert [item["answered"] for item in graded] == [False, True]
    assert all(item["correct"] is False for item in run.grade(questions, None))


# ---------------------------------------------------------------------------
# Statistics and summary
# ---------------------------------------------------------------------------


def test_wilson_interval_known_values() -> None:
    low, high = run.wilson_interval(8, 10)
    assert low == pytest.approx(0.4902, abs=1e-4)
    assert high == pytest.approx(0.9433, abs=1e-4)
    low, high = run.wilson_interval(10, 10)
    assert low == pytest.approx(0.7225, abs=1e-4)
    assert high == pytest.approx(1.0, abs=1e-12)
    low, high = run.wilson_interval(0, 10)
    assert low == pytest.approx(0.0, abs=1e-12)
    assert high == pytest.approx(0.2775, abs=1e-4)
    assert run.wilson_interval(0, 0) == (0.0, 1.0)


def _record(
    format_name: str,
    table: str,
    flags: list[bool],
    input_tokens: int | None,
    *,
    error: str | None = None,
    parse_error: bool = False,
    shape: str = "20x4",
) -> dict[str, Any]:
    return {
        "table": table,
        "shape": shape,
        "format": format_name,
        "repeat": 0,
        "input_tokens": input_tokens,
        "output_tokens": None if error else 40,
        "latency_s": None if error else 1.5,
        "stop_reason": None if error else "end_turn",
        "parse_error": parse_error,
        "error": error,
        "questions": [
            {"id": f"q{i}", "kind": QUESTION_KINDS[i - 1], "correct": flag}
            for i, flag in enumerate(flags, start=1)
        ],
    }


def test_summary_math() -> None:
    records = [
        _record("objects", "t1", [True] * 6, 1000),
        _record("objects", "t2", [True] * 3 + [False] * 3, 3000, shape="100x4"),
        _record("toon", "t1", [True] * 6, 600),
        _record("toon", "t2", [], None, error="APIStatusError: boom", shape="100x4"),
        _record("csv", "t1", [False] * 6, 500, parse_error=True),
        _record("csv", "t2", [True] * 6, 1500, shape="100x4"),
    ]
    summary = run.summarize(records, ["objects", "toon", "csv"])
    formats = summary["formats"]

    objects = formats["objects"]
    assert (objects["answers"], objects["correct"]) == (12, 9)
    assert objects["accuracy"] == pytest.approx(0.75)
    assert (objects["ci95_low"], objects["ci95_high"]) == pytest.approx(
        run.wilson_interval(9, 12)
    )
    assert objects["mean_input_tokens"] == pytest.approx(2000)
    assert objects["input_tokens_vs_objects"] == pytest.approx(1.0)

    toon = formats["toon"]
    assert (toon["calls"], toon["graded_calls"], toon["errors"]) == (2, 1, 1)
    assert (toon["answers"], toon["accuracy"]) == (6, 1.0)
    assert toon["input_tokens_vs_objects"] == pytest.approx(0.6)  # paired with t1 only

    csv_cell = formats["csv"]
    assert csv_cell["parse_errors"] == 1
    assert csv_cell["accuracy"] == pytest.approx(0.5)
    assert csv_cell["input_tokens_vs_objects"] == pytest.approx(2000 / 4000)

    assert summary["by_kind"]["objects"]["row_count"] == {
        "answers": 2,
        "correct": 2,
        "accuracy": 1.0,
    }
    assert summary["by_kind"]["objects"]["null_count"]["accuracy"] == pytest.approx(0.5)
    assert summary["by_shape"]["objects"]["100x4"]["accuracy"] == pytest.approx(0.5)
    assert summary["by_shape"]["toon"]["100x4"] == {
        "answers": 0,
        "correct": 0,
        "accuracy": None,
    }

    text = run.format_summary(summary)
    for name in ("objects", "toon", "csv", "row_count", "100x4"):
        assert name in text


# ---------------------------------------------------------------------------
# Full runs with fake clients
# ---------------------------------------------------------------------------


def _response(text: str, input_tokens: int = 100) -> SimpleNamespace:
    return SimpleNamespace(
        content=[
            SimpleNamespace(type="thinking", thinking=""),
            SimpleNamespace(type="text", text=text),
        ],
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=30),
        stop_reason="end_turn",
    )


class _FakeClient:
    """Stands in for anthropic.Anthropic: ``client.messages.create(**kwargs)``."""

    def __init__(self, reply: Any) -> None:
        self.reply = reply
        self.requests: list[dict[str, Any]] = []
        self.messages = self

    def create(self, **kwargs: Any) -> SimpleNamespace:
        self.requests.append(kwargs)
        return self.reply(kwargs)


def _small_plan() -> list[run.CallSpec]:
    tables = build_tables([(20, 4), (20, 11)], seeds=1)
    return run.build_plan(tables, list(FORMATS), repeats=1)


def test_full_run_with_gold_answers_scores_one() -> None:
    specs = _small_plan()
    gold_by_message = {
        spec.user_message: json.dumps({q.id: q.gold for q in spec.questions})
        for spec in specs
    }
    client = _FakeClient(
        lambda kwargs: _response(
            gold_by_message[kwargs["messages"][0]["content"]],
            input_tokens=len(kwargs["messages"][0]["content"]),
        )
    )
    records = run.run_calls(
        client, "fake-model", specs, max_tokens=600, concurrency=3, retryable=()
    )
    assert len(records) == len(specs)
    assert [(r["table"], r["format"]) for r in records] == [
        (spec.table.name, spec.format_name) for spec in specs
    ]
    request = client.requests[0]
    assert request["system"] == run.SYSTEM_PROMPT
    assert request["max_tokens"] == 600
    assert "temperature" not in request and "thinking" not in request

    summary = run.summarize(records, list(FORMATS))
    for cell in summary["formats"].values():
        assert cell["accuracy"] == 1.0
        assert cell["answers"] == 2 * 6
        assert cell["parse_errors"] == 0
        assert cell["errors"] == 0
    assert summary["formats"]["objects"]["input_tokens_vs_objects"] == 1.0
    assert summary["formats"]["csv"]["input_tokens_vs_objects"] < 1.0


def test_full_run_with_garbage_replies_scores_zero() -> None:
    specs = _small_plan()
    client = _FakeClient(lambda kwargs: _response("I am unable to read tables."))
    records = run.run_calls(
        client, "fake-model", specs, max_tokens=600, concurrency=2, retryable=()
    )
    summary = run.summarize(records, list(FORMATS))
    for cell in summary["formats"].values():
        assert cell["accuracy"] == 0.0
        assert cell["parse_errors"] == cell["graded_calls"] == 2
    assert all(record["answers"] is None for record in records)


class _Transient(Exception):
    """Stands in for a retryable SDK error (rate limit, overload, connection)."""


def test_retry_then_success_and_other_errors_are_recorded() -> None:
    spec = _small_plan()[0]
    attempts: list[int] = []

    def flaky(kwargs: dict[str, Any]) -> SimpleNamespace:
        attempts.append(1)
        if len(attempts) < 3:
            raise _Transient("overloaded")
        return _response('{"q1": 20}')

    sleeps: list[float] = []
    record = run.run_call(
        _FakeClient(flaky),
        "fake-model",
        spec,
        max_tokens=600,
        retryable=(_Transient,),
        sleep=sleeps.append,
    )
    assert record["error"] is None
    assert record["attempts"] == 3
    assert sleeps == [2.0, 4.0]

    def broken(kwargs: dict[str, Any]) -> SimpleNamespace:
        raise ValueError("bad request")

    failed = run.run_call(
        _FakeClient(broken),
        "fake-model",
        spec,
        max_tokens=600,
        retryable=(_Transient,),
        sleep=sleeps.append,
    )
    assert failed["error"] == "ValueError: bad request"
    assert failed["attempts"] == 1
    assert failed["questions"] == []


def test_retries_stop_after_four() -> None:
    spec = _small_plan()[0]

    def always_busy(kwargs: dict[str, Any]) -> SimpleNamespace:
        raise _Transient("rate limited")

    sleeps: list[float] = []
    record = run.run_call(
        _FakeClient(always_busy),
        "fake-model",
        spec,
        max_tokens=600,
        retryable=(_Transient,),
        sleep=sleeps.append,
    )
    assert record["attempts"] == run.MAX_RETRIES + 1 == 5
    assert sleeps == [2.0, 4.0, 8.0, 16.0]
    assert record["error"] == "_Transient: rate limited"


def test_thinking_disabled_is_sent_only_when_asked() -> None:
    spec = _small_plan()[0]
    client = _FakeClient(lambda kwargs: _response("{}"))
    run.run_call(
        client,
        "fake-model",
        spec,
        max_tokens=600,
        retryable=(),
        thinking=run.THINKING_DISABLED,
    )
    assert client.requests[0]["thinking"] == {"type": "disabled"}


def test_dry_run_makes_no_api_call(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def forbidden() -> None:
        raise AssertionError("dry run must not build an API client")

    monkeypatch.setattr(run, "_anthropic_client_and_retryable", forbidden)
    exit_code = run.main(
        ["--model", "fake-model", "--dry-run", "--shapes", "20x4", "--seeds", "1"]
    )
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "Plan: 5 calls" in out
    assert "Dry run: no API call made" in out
    for name in FORMATS:
        assert f'<table format="{name}">' in out


def test_summary_leaves_truncated_replies_out_of_accuracy() -> None:
    cut = _record("toon", "t2", [False] * 6, 900, parse_error=True, shape="100x4")
    cut["stop_reason"] = "max_tokens"
    finished = _record("toon", "t3", [True] * 6, 900, shape="100x4")
    finished["stop_reason"] = "max_tokens"  # hit the limit but the answer parsed
    records = [
        _record("objects", "t1", [True] * 6, 1000),
        _record("toon", "t1", [True] * 5 + [False], 600),
        cut,
        finished,
    ]
    cell = run.summarize(records, ["objects", "toon"])["formats"]["toon"]
    assert cell["max_tokens_stops"] == 1
    assert cell["graded_calls"] == 2
    assert cell["answers"] == 12
    assert cell["correct"] == 11
    assert cell["parse_errors"] == 0
