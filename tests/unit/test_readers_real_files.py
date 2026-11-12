"""Spreadsheet and columnar readers against real files written by the real libraries.

The other reader tests replace the parser with a mock, which cannot notice a
value type the parser really returns (a date cell, a decimal column) or a
parser API that changed.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from datoon.cli import main
from datoon.readers import read_tabular, rows_to_json


def _write_xlsx(path: Path) -> None:
    openpyxl = pytest.importorskip("openpyxl")
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["id", "name", "signed_up"])
    sheet.append([1, "Ada", datetime(2026, 11, 1, 9, 30)])
    sheet.append([2, "Lin", datetime(2026, 11, 2, 10, 0)])
    sheet.append([3, "Grace", datetime(2026, 11, 3, 11, 15)])
    workbook.save(path)


def _write_parquet(path: Path) -> None:
    pyarrow = pytest.importorskip("pyarrow")
    parquet = pytest.importorskip("pyarrow.parquet")
    table = pyarrow.table(
        {
            "id": [1, 2, 3],
            "day": [date(2026, 11, 1), date(2026, 11, 2), date(2026, 11, 3)],
            "price": [Decimal("9.50"), Decimal("12.25"), Decimal("0.10")],
        }
    )
    parquet.write_table(table, path)


def test_excel_rows_with_dates_convert_through_the_cli(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "users.xlsx"
    _write_xlsx(path)

    rows = read_tabular("excel", path=path)
    assert rows[0] == {
        "id": 1,
        "name": "Ada",
        "signed_up": datetime(2026, 11, 1, 9, 30),
    }
    assert json.loads(rows_to_json(rows))[0]["signed_up"] == "2026-11-01T09:30:00"

    assert main([str(path), "--force", "--tokenizer", "chars"]) == 0
    assert "2026-11-01T09:30:00" in capsys.readouterr().out


def test_excel_sheet_out_of_range_is_a_clean_cli_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "users.xlsx"
    _write_xlsx(path)

    assert main([str(path), "--sheet", "5"]) == 1
    assert "Sheet index 5 is out of range" in capsys.readouterr().err


def test_parquet_rows_with_dates_and_decimals_convert_through_the_cli(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "orders.parquet"
    _write_parquet(path)

    rows = read_tabular("parquet", path=path)
    assert json.loads(rows_to_json(rows)) == [
        {"id": 1, "day": "2026-11-01", "price": 9.5},
        {"id": 2, "day": "2026-11-02", "price": 12.25},
        {"id": 3, "day": "2026-11-03", "price": 0.1},
    ]

    assert main([str(path), "--force", "--tokenizer", "chars"]) == 0
    assert "2026-11-02" in capsys.readouterr().out
