"""The runner's swap of names for ids, tested without a database."""

import math

import pandas as pd
import pytest

from navigator.recipes.core import INSIGHT_COLUMNS, METRIC_COLUMNS
from navigator.worker.runner import build_insight_rows, build_metric_rows

ARTIFACTS = {"parcel_year_contract": "art_1", "model_table": "art_2"}
ASSUMPTIONS = {"tune_calendar.error_tolerance": "asm_1"}


def metric_row(key: str = "k1", **changes: object) -> dict[str, object]:
    row: dict[str, object] = {
        "key": key,
        "name": "project_yields.yield_change_pct",
        "unit": "%",
        "value": -3.5,
        "low": -5.0,
        "high": -2.0,
        "region": "FI_SW",
        "crop": "pea",
        "scenario": "ssp585",
        "ngfs_scenario": None,
        "period": "2041-2060",
        "action_id": None,
        "lineage": [{"table": "model_table", "filter": {"crop": "pea"}}],
        "assumptions": ["tune_calendar.error_tolerance"],
    }
    return row | changes


def metrics(*rows: dict[str, object]) -> pd.DataFrame:
    return pd.DataFrame(list(rows), columns=METRIC_COLUMNS)


def build(*rows: dict[str, object]):
    return build_metric_rows([metrics(*rows)], "rs_1", ARTIFACTS, ASSUMPTIONS)


def test_ids_replace_names() -> None:
    rows, metric_ids = build(metric_row())
    (row,) = rows
    assert metric_ids == {"k1": row.metric_id}
    assert row.metric_id.startswith("met_")
    assert row.result_set_id == "rs_1"
    assert row.lineage == [{"artifact": "art_2", "filter": {"crop": "pea"}}]
    assert row.assumption_ids == ["asm_1"]


def test_missing_values_become_none() -> None:
    nan = math.nan
    rows, _ = build(metric_row(low=nan, high=nan, region=nan, ngfs_scenario=None, crop=nan))
    row = rows[0]
    assert (row.low, row.high, row.region, row.crop, row.ngfs_scenario) == (None,) * 5
    assert row.scenario == "ssp585"


def test_insight_tokens_become_metric_ids() -> None:
    rows, metric_ids = build(metric_row("k1"), metric_row("k2"))
    insights = pd.DataFrame(
        [
            {
                "title": "Cover",
                "text": "Share {{metric:k1}} and {{metric:k2}}.",
                "metric_keys": ["k1"],
            }
        ],
        columns=INSIGHT_COLUMNS,
    )
    (insight,) = build_insight_rows([("price_risk", insights)], "rs_1", metric_ids)
    assert (
        insight.text
        == f"Share {{{{metric:{metric_ids['k1']}}}}} and {{{{metric:{metric_ids['k2']}}}}}."
    )
    assert insight.metric_ids == [metric_ids["k1"]]
    assert insight.step == "price_risk"
    assert insight.insight_id.startswith("ins_")
    assert len(rows) == 2


def test_duplicate_key_fails() -> None:
    with pytest.raises(ValueError, match="'k1' is used twice"):
        build(metric_row("k1"), metric_row("k1"))


def test_unknown_table_fails() -> None:
    row = metric_row(lineage=[{"table": "nope", "filter": {}}])
    with pytest.raises(ValueError, match="'nope'"):
        build(row)


def test_unknown_assumption_fails() -> None:
    with pytest.raises(ValueError, match="'nope\\.param'"):
        build(metric_row(assumptions=["nope.param"]))


def test_unknown_metric_key_fails() -> None:
    insights = pd.DataFrame(
        [{"title": "T", "text": "No tokens.", "metric_keys": ["missing"]}], columns=INSIGHT_COLUMNS
    )
    with pytest.raises(ValueError, match="'missing'"):
        build_insight_rows([("s", insights)], "rs_1", {})


def test_unknown_token_in_text_fails() -> None:
    insights = pd.DataFrame(
        [{"title": "T", "text": "Value {{metric:missing}}.", "metric_keys": []}],
        columns=INSIGHT_COLUMNS,
    )
    with pytest.raises(ValueError, match="'missing'"):
        build_insight_rows([("s", insights)], "rs_1", {})
