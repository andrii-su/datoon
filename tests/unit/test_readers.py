"""Unit tests for format readers."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from datoon.errors import DatoonError
from datoon.readers import (
    ALL_FORMATS,
    BINARY_FORMATS,
    TEXT_FORMATS,
    detect_format,
    read_tabular,
)
from datoon.readers.csv import read_csv
from datoon.readers.jsonl import read_jsonl
from datoon.readers.xml import read_xml


# ---------------------------------------------------------------------------
# detect_format
# ---------------------------------------------------------------------------


def test_detect_format_csv() -> None:
    assert detect_format("data.csv") == "csv"


def test_detect_format_jsonl() -> None:
    assert detect_format("data.jsonl") == "jsonl"
    assert detect_format("data.ndjson") == "jsonl"


def test_detect_format_yaml() -> None:
    assert detect_format("data.yaml") == "yaml"
    assert detect_format("data.yml") == "yaml"


def test_detect_format_xml() -> None:
    assert detect_format("data.xml") == "xml"


def test_detect_format_excel() -> None:
    assert detect_format("data.xlsx") == "excel"
    assert detect_format("data.xls") == "excel"


def test_detect_format_columnar() -> None:
    assert detect_format("data.parquet") == "parquet"
    assert detect_format("data.avro") == "avro"
    assert detect_format("data.orc") == "orc"


def test_detect_format_numbers() -> None:
    assert detect_format("data.numbers") == "numbers"


def test_detect_format_unknown_returns_none() -> None:
    assert detect_format("data.txt") is None
    assert detect_format("data") is None


# ---------------------------------------------------------------------------
# CSV reader
# ---------------------------------------------------------------------------

_CSV_TEXT = "id,name,role\n1,Ada,admin\n2,Lin,analyst\n3,Grace,viewer\n"


def test_read_csv_basic() -> None:
    rows = read_csv(_CSV_TEXT)
    assert len(rows) == 3
    assert rows[0] == {"id": 1, "name": "Ada", "role": "admin"}
    assert rows[1]["name"] == "Lin"


def test_read_csv_type_coercion_int() -> None:
    rows = read_csv("count\n42\n7\n")
    assert rows[0]["count"] == 42
    assert isinstance(rows[0]["count"], int)


def test_read_csv_type_coercion_float() -> None:
    rows = read_csv("ratio\n0.5\n1.25\n")
    assert rows[0]["ratio"] == 0.5
    assert isinstance(rows[0]["ratio"], float)


def test_read_csv_type_coercion_bool() -> None:
    rows = read_csv("active\ntrue\nfalse\n")
    assert rows[0]["active"] is True
    assert rows[1]["active"] is False


def test_read_csv_empty_value_is_none() -> None:
    rows = read_csv("id,note\n1,\n2,ok\n")
    assert rows[0]["note"] is None


def test_read_csv_no_coercion() -> None:
    rows = read_csv(_CSV_TEXT, coerce_types=False)
    assert rows[0]["id"] == "1"


def test_read_csv_preserves_leading_zero_ids() -> None:
    # Zip codes, phone numbers, and IDs must not lose leading zeros.
    rows = read_csv("code\n00123\n0042\n")
    assert rows[0]["code"] == "00123"
    assert rows[1]["code"] == "0042"


def test_read_csv_rejects_non_finite_floats() -> None:
    # float("inf")/float("nan") would serialize to invalid JSON (Infinity/NaN).
    rows = read_csv("v\ninf\nnan\n-inf\nInfinity\n")
    assert rows[0]["v"] == "inf"
    assert rows[1]["v"] == "nan"
    assert rows[2]["v"] == "-inf"
    assert rows[3]["v"] == "Infinity"


def test_read_csv_float_overflow_stays_string() -> None:
    # 1e400 overflows to inf; keep the original string instead.
    rows = read_csv("v\n1e400\n")
    assert rows[0]["v"] == "1e400"


def test_read_csv_underscore_number_stays_string() -> None:
    rows = read_csv("v\n1_000\n")
    assert rows[0]["v"] == "1_000"


# ---------------------------------------------------------------------------
# JSONL reader
# ---------------------------------------------------------------------------

_JSONL_TEXT = (
    '{"id":1,"name":"Ada","role":"admin"}\n'
    '{"id":2,"name":"Lin","role":"analyst"}\n'
    '{"id":3,"name":"Grace","role":"viewer"}\n'
)


def test_read_jsonl_basic() -> None:
    rows = read_jsonl(_JSONL_TEXT)
    assert len(rows) == 3
    assert rows[0] == {"id": 1, "name": "Ada", "role": "admin"}


def test_read_jsonl_skips_blank_lines() -> None:
    rows = read_jsonl('{"a":1}\n\n{"a":2}\n')
    assert len(rows) == 2


def test_read_jsonl_invalid_raises() -> None:
    from datoon.converter import DatoonError

    with pytest.raises(DatoonError, match="line 2"):
        read_jsonl('{"a":1}\nbad json\n')


def test_read_jsonl_non_object_raises() -> None:
    from datoon.converter import DatoonError

    with pytest.raises(DatoonError, match="not a JSON object"):
        read_jsonl("[1,2,3]\n")


# ---------------------------------------------------------------------------
# YAML reader
# ---------------------------------------------------------------------------


def test_read_yaml_list(monkeypatch: pytest.MonkeyPatch) -> None:
    yaml_mock = MagicMock()
    yaml_mock.safe_load.return_value = [
        {"id": 1, "name": "Ada"},
        {"id": 2, "name": "Lin"},
        {"id": 3, "name": "Grace"},
    ]
    monkeypatch.setitem(sys.modules, "yaml", yaml_mock)

    from datoon.readers.yaml import read_yaml

    rows = read_yaml("- id: 1\n  name: Ada\n")
    assert len(rows) == 3
    assert rows[0]["name"] == "Ada"


def test_read_yaml_dict_with_single_list(monkeypatch: pytest.MonkeyPatch) -> None:
    yaml_mock = MagicMock()
    yaml_mock.safe_load.return_value = {
        "users": [
            {"id": 1, "name": "Ada"},
            {"id": 2, "name": "Lin"},
            {"id": 3, "name": "Grace"},
        ]
    }
    monkeypatch.setitem(sys.modules, "yaml", yaml_mock)

    from datoon.readers.yaml import read_yaml

    rows = read_yaml("users:\n  - id: 1\n")
    assert len(rows) == 3


def test_read_yaml_missing_dep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "yaml", None)  # type: ignore

    from datoon.readers import yaml as yaml_reader

    with pytest.raises(ImportError, match="datoon\\[yaml\\]"):
        yaml_reader.read_yaml("- id: 1")


def test_read_yaml_rejects_list_of_scalars(monkeypatch: pytest.MonkeyPatch) -> None:
    yaml_mock = MagicMock()
    yaml_mock.safe_load.return_value = [1, 2, 3]
    monkeypatch.setitem(sys.modules, "yaml", yaml_mock)

    from datoon.readers.yaml import read_yaml

    with pytest.raises(DatoonError, match="list of objects"):
        read_yaml("- 1\n- 2\n")


def test_read_yaml_rejects_mixed_list(monkeypatch: pytest.MonkeyPatch) -> None:
    yaml_mock = MagicMock()
    yaml_mock.safe_load.return_value = [{"id": 1}, "oops", {"id": 3}]
    monkeypatch.setitem(sys.modules, "yaml", yaml_mock)

    from datoon.readers.yaml import read_yaml

    with pytest.raises(DatoonError, match="list of objects"):
        read_yaml("- id: 1\n- oops\n")


def test_read_yaml_rejects_bad_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    yaml_mock = MagicMock()
    yaml_mock.safe_load.return_value = 42
    monkeypatch.setitem(sys.modules, "yaml", yaml_mock)

    from datoon.readers.yaml import read_yaml

    with pytest.raises(DatoonError, match="list of objects"):
        read_yaml("42\n")


# ---------------------------------------------------------------------------
# XML reader
# ---------------------------------------------------------------------------

_XML_TEXT = """<users>
  <user><id>1</id><name>Ada</name><role>admin</role></user>
  <user><id>2</id><name>Lin</name><role>analyst</role></user>
  <user><id>3</id><name>Grace</name><role>viewer</role></user>
</users>"""


def test_read_xml_basic() -> None:
    rows = read_xml(_XML_TEXT)
    assert len(rows) == 3
    assert rows[0] == {"id": 1, "name": "Ada", "role": "admin"}


def test_read_xml_type_coercion() -> None:
    rows = read_xml(_XML_TEXT)
    assert isinstance(rows[0]["id"], int)


def test_read_xml_preserves_leading_zero() -> None:
    xml = "<rows><r><code>00755</code></r><r><code>00644</code></r></rows>"
    rows = read_xml(xml)
    assert rows[0]["code"] == "00755"
    assert rows[1]["code"] == "00644"


def test_read_xml_rejects_non_finite() -> None:
    xml = "<rows><r><v>inf</v></r><r><v>nan</v></r></rows>"
    rows = read_xml(xml)
    assert rows[0]["v"] == "inf"
    assert rows[1]["v"] == "nan"


def test_read_xml_rejects_dtd_billion_laughs() -> None:
    # Internal entity expansion (billion laughs) is a DoS vector; DTDs are refused.
    payload = (
        '<!DOCTYPE lolz [<!ENTITY lol "lol">'
        '<!ENTITY lol2 "&lol;&lol;&lol;">]>'
        "<rows><r>&lol2;</r></rows>"
    )
    with pytest.raises(DatoonError, match="DOCTYPE"):
        read_xml(payload)


def test_read_xml_rejects_external_entity_dtd() -> None:
    payload = (
        '<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
        "<rows><r>&xxe;</r></rows>"
    )
    with pytest.raises(DatoonError, match="DOCTYPE"):
        read_xml(payload)


def test_read_xml_invalid_raises() -> None:
    with pytest.raises(DatoonError, match="Invalid XML"):
        read_xml("<not closed>")


def test_read_xml_empty_root_raises() -> None:
    with pytest.raises(DatoonError, match="no children"):
        read_xml("<root/>")


# ---------------------------------------------------------------------------
# read_tabular dispatcher
# ---------------------------------------------------------------------------


def test_read_tabular_csv() -> None:
    rows = read_tabular("csv", text=_CSV_TEXT)
    assert len(rows) == 3


def test_read_tabular_jsonl() -> None:
    rows = read_tabular("jsonl", text=_JSONL_TEXT)
    assert len(rows) == 3


def test_read_tabular_xml() -> None:
    rows = read_tabular("xml", text=_XML_TEXT)
    assert len(rows) == 3


def test_read_tabular_unknown_format_raises() -> None:
    with pytest.raises(ValueError, match="Unknown format"):
        read_tabular("toml", text="x = 1")


def test_read_tabular_binary_without_path_raises() -> None:
    for fmt in BINARY_FORMATS:
        with pytest.raises(ValueError, match="requires a file path"):
            read_tabular(fmt, text="irrelevant")


def test_read_tabular_text_without_text_raises() -> None:
    for fmt in TEXT_FORMATS:
        with pytest.raises(ValueError, match="requires text input"):
            read_tabular(fmt, path=None)


def test_read_tabular_forwards_sheet_to_excel(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, int] = {}

    def fake_read_excel(path: Path, *, sheet: int = 0) -> list[dict[str, int]]:
        captured["sheet"] = sheet
        return [{"a": 1}]

    monkeypatch.setattr("datoon.readers.excel.read_excel", fake_read_excel)
    read_tabular("excel", path=Path("x.xlsx"), sheet=2)
    assert captured["sheet"] == 2


def test_read_tabular_forwards_sheet_and_table_to_numbers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, int] = {}

    def fake_read_numbers(
        path: Path, *, sheet: int = 0, table: int = 0
    ) -> list[dict[str, int]]:
        captured["sheet"] = sheet
        captured["table"] = table
        return [{"a": 1}]

    monkeypatch.setattr("datoon.readers.numbers.read_numbers", fake_read_numbers)
    read_tabular("numbers", path=Path("x.numbers"), sheet=1, table=3)
    assert captured == {"sheet": 1, "table": 3}


# ---------------------------------------------------------------------------
# Format sets sanity
# ---------------------------------------------------------------------------


def test_format_sets_disjoint() -> None:
    assert BINARY_FORMATS.isdisjoint(TEXT_FORMATS)


def test_all_formats_is_union() -> None:
    assert ALL_FORMATS == BINARY_FORMATS | TEXT_FORMATS
