"""Filter strings, spreadsheet cells and workbooks, tested without a database or storage."""

import datetime as dt
import io
import math

import numpy as np
import pandas as pd
import pytest
from openpyxl import load_workbook

from navigator.api.risk import lineage_filter_strings
from navigator.api.runs import build_workbook, export_filename, xlsx_cell


def test_single_values_and_lists_become_repeated_filters() -> None:
    strings = lineage_filter_strings(
        {"region": "FI_SW", "farm_id": ["F0012", "F0040"], "season": 2041, "kept": True}
    )
    assert strings == ["region=FI_SW", "farm_id=F0012", "farm_id=F0040", "season=2041", "kept=true"]


def test_empty_filter_means_the_whole_table() -> None:
    assert lineage_filter_strings({}) == []


def test_a_range_is_refused_with_its_column() -> None:
    with pytest.raises(ValueError, match="filter on season is a range"):
        lineage_filter_strings({"season": {"min": 2041, "max": 2060}})


def test_cells_are_plain_python_values() -> None:
    assert xlsx_cell(np.int64(3)) == 3
    assert type(xlsx_cell(np.int64(3))) is int
    assert type(xlsx_cell(np.float64(1.5))) is float
    assert type(xlsx_cell(np.bool_(True))) is bool
    assert xlsx_cell(math.nan) is None
    assert xlsx_cell(np.float64("nan")) is None
    assert xlsx_cell(None) is None
    assert xlsx_cell(pd.NaT) is None
    assert xlsx_cell("a\x00b") == "ab"
    assert xlsx_cell(["a", "b"]) == "['a', 'b']"


def test_times_lose_their_time_zone() -> None:
    aware = dt.datetime(2026, 1, 1, 12, tzinfo=dt.timezone(dt.timedelta(hours=2)))
    assert xlsx_cell(aware) == dt.datetime(2026, 1, 1, 10)
    stamp = xlsx_cell(pd.Timestamp("2026-01-01 12:00", tz="UTC"))
    assert stamp == dt.datetime(2026, 1, 1, 12)
    assert type(stamp) is dt.datetime


def test_workbook_has_a_header_and_the_rows() -> None:
    frame = pd.DataFrame(
        {
            "farm_id": ["FS1", "FS2"],
            "yield_t_ha": [3.1, None],
            "n": np.array([1, 2], dtype="int64"),
            "at": pd.to_datetime(["2026-01-01", "2026-01-02"], utc=True),
        }
    )
    content = build_workbook("farm/survey", frame)
    sheet = load_workbook(io.BytesIO(content)).active
    assert sheet is not None
    assert sheet.title == "farm_survey"
    assert [[c.value for c in row] for row in sheet.iter_rows()] == [
        ["farm_id", "yield_t_ha", "n", "at"],
        ["FS1", 3.1, 1, dt.datetime(2026, 1, 1)],
        ["FS2", None, 2, dt.datetime(2026, 1, 2)],
    ]


def test_empty_table_still_has_its_header() -> None:
    content = build_workbook("t", pd.DataFrame({"a": [], "b": []}))
    sheet = load_workbook(io.BytesIO(content)).active
    assert sheet is not None
    assert [[c.value for c in row] for row in sheet.iter_rows()] == [["a", "b"]]


def test_file_name_comes_from_the_table_name() -> None:
    assert export_filename("farm_survey") == "farm_survey.xlsx"
    assert export_filename('a/b"c') == "a_b_c.xlsx"
    assert export_filename("///") == "table.xlsx"
