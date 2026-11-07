"""Evidence queries recompute a proposal's numbers deterministically from raw tables."""

import pandas as pd
import pytest
from pydantic import ValidationError

from navigator.evidence import ComputeQuery, Evidence, evaluate, reproduces

SURVEY = pd.DataFrame(
    {
        "record_key": ["s:1", "s:2", "s:3", "s:4"],
        "crop": ["pea", "pea", "pea", "potato"],
        "year": [2020, 2020, 2020, 2020],
        "yield_t_ha": [4.0, 5.0, 50.0, 30.0],
    }
)

R1_LIKE = {
    "kind": "compute",
    "table": "farm_survey",
    "group_by": ["crop", "year"],
    "compute": {
        "median": {"op": "median", "column": "yield_t_ha"},
        "ratio_to_median": {"op": "divide", "left": "yield_t_ha", "right": "median"},
    },
    "where": {"record_key": "s:3"},
}


def evidence(values: dict[str, float], query: dict[str, object] = R1_LIKE) -> Evidence:
    return Evidence.model_validate(
        {
            "summary": "Yield is ten times the median.",
            "record_keys": ["s:3"],
            "query": query,
            "values": values,
        }
    )


def test_aggregates_are_computed_within_groups() -> None:
    rows = evaluate(ComputeQuery.model_validate(R1_LIKE), {"farm_survey": SURVEY})
    assert rows["median"].tolist() == [5.0]
    assert rows["ratio_to_median"].tolist() == [10.0]


def test_claimed_values_that_match_are_accepted() -> None:
    ok, reason = reproduces(
        evidence({"yield_t_ha": 50.0, "ratio_to_median": 10.0}), {"farm_survey": SURVEY}
    )
    assert ok, reason


def test_claimed_values_that_differ_are_rejected() -> None:
    ok, reason = reproduces(evidence({"ratio_to_median": 9.0}), {"farm_survey": SURVEY})
    assert not ok
    assert "ratio_to_median comes out as 10" in reason


def test_a_query_must_select_exactly_one_row() -> None:
    query = {**R1_LIKE, "where": {"crop": "pea"}}
    ok, reason = reproduces(evidence({"median": 5.0}, query), {"farm_survey": SURVEY})
    assert not ok
    assert "3 rows" in reason


def test_ranges_and_lists_filter_like_lineage() -> None:
    query = ComputeQuery.model_validate(
        {**R1_LIKE, "where": {"crop": ["pea", "potato"], "yield_t_ha": {"min": 10, "max": 40}}}
    )
    assert evaluate(query, {"farm_survey": SURVEY})["record_key"].tolist() == ["s:4"]


@pytest.mark.parametrize(
    "change",
    [
        {"compute": {"x": {"op": "explain", "column": "yield_t_ha"}}},
        {"compute": {"x": {"op": "median", "column": "yield_t_ha", "note": "free text"}}},
        {"kind": "sql"},
    ],
)
def test_unknown_operations_and_free_text_fail_validation(change: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        evidence({}, {**R1_LIKE, **change})


def test_unknown_columns_are_named() -> None:
    query = ComputeQuery.model_validate({**R1_LIKE, "where": {"farm": "F1"}})
    with pytest.raises(ValueError, match="'farm'"):
        evaluate(query, {"farm_survey": SURVEY})
