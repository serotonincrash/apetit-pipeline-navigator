"""Golden tests for steps 7 to 9: the yield model, the projection and the risk pricing reproduce
`notebooks/c1_yield_model.ipynb`, `c2_yield_projection.ipynb` and `c3_risk_pricing.ipynb`, and
their metrics, insights and tables are in the shape the runner stores."""

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from navigator.analysis import yieldmodel as ym
from navigator.recipes.core import METRIC_COLUMNS, Artifact, RunContext, StepResult
from navigator.recipes.farm_climate_risk import UNITS
from navigator.steps.fit_yield_model import DASH, fit_yield_model
from navigator.steps.price_risk import price_risk
from navigator.steps.project_yields import project_yields
from navigator.storage.objects import frame_to_parquet, parquet_to_frame
from navigator.worker.runner import build_insight_rows, build_metric_rows
from tests.golden.conftest import recipe_step, run_step

pytestmark = pytest.mark.golden

RESULTS = Path(__file__).parents[3] / "notebooks" / "results"
# The notebooks round their CSV files to 3 and 5 decimals.
ROUND_3 = 0.0006
ROUND_5 = 6e-6
CENT = 0.005
EMISSION_RTOL = 1e-5
EURO = 1.0

METRIC_NAMES = {
    "fit_yield_model.production_error_pct",
    "fit_yield_model.baseline_production_error_pct",
    "project_yields.yield_change_pct",
    "project_yields.bad_year_chance",
    "price_risk.expected_cost_eur",
    "price_risk.one_in_ten_cost_eur",
    "price_risk.expected_import_tco2e",
    "price_risk.climate_added_cost_eur",
    "price_risk.foodhills_cover_share",
    "price_risk.foodhills_premium_avoided_eur",
}


@pytest.fixture(scope="session")
def tables(
    clean_tables: dict[str, Artifact],
    calendar: dict[str, pd.DataFrame],
    features: dict[str, pd.DataFrame],
) -> dict[str, Artifact]:
    """Every table steps 1 to 6 wrote, by name."""
    found = dict(clean_tables)
    for frames in (calendar, features):
        found.update({n: Artifact(n, "feature", f) for n, f in frames.items()})
    return found


def chain(ctx: RunContext, func: Any, name: str, tables: dict[str, Artifact]) -> StepResult:
    result = run_step(ctx, func, name, tables)
    tables.update({t.name: t for t in result.tables})
    return result


@pytest.fixture(scope="session")
def fitted(ctx: RunContext, tables: dict[str, Artifact]) -> StepResult:
    return chain(ctx, fit_yield_model, "fit_yield_model", tables)


@pytest.fixture(scope="session")
def projected(ctx: RunContext, tables: dict[str, Artifact], fitted: StepResult) -> StepResult:
    return chain(ctx, project_yields, "project_yields", tables)


@pytest.fixture(scope="session")
def priced(ctx: RunContext, tables: dict[str, Artifact], projected: StepResult) -> StepResult:
    return chain(ctx, price_risk, "price_risk", tables)


def frame(result: StepResult, name: str) -> pd.DataFrame:
    return next(t.frame for t in result.tables if t.name == name)


def test_yield_model(fitted: StepResult) -> None:
    models = ym.models_from_tables(
        frame(fitted, "yield_coefficients"),
        frame(fitted, "yield_fit"),
        frame(fitted, "farm_levels"),
    )
    expected = json.loads((RESULTS / "yield_model.json").read_text())
    assert {f"{r}/{c}" for r, c in models} == set(expected)
    worst = 0.0
    for (region, crop), model in models.items():
        want = expected[f"{region}/{crop}"]
        assert model["features"] == want["features"]
        for feature, beta in model["beta"].items():
            worst = max(worst, abs(beta - want["beta"][feature]))
        for key in ("mean_level", "resid_sd", "resid_sd_shared", "resid_sd_farm", "smearing"):
            worst = max(worst, abs(model[key] - want[key]))
        for key in ("n_rows", "n_farms", "lam", "shrink_seasons"):
            assert model[key] == want[key], key
    assert worst < 1e-9


def test_backtest(fitted: StepResult) -> None:
    summary = ym.backtest_summary(frame(fitted, "yield_backtest"))
    expected = pd.read_csv(RESULTS / "yield_backtest_summary.csv", index_col=0)
    assert [tuple(u) for u in UNITS] == list(summary.index)
    np.testing.assert_allclose(summary.to_numpy(), expected.to_numpy(), atol=ROUND_3)
    detail = pd.read_csv(RESULTS / "yield_backtest.csv")
    actual = frame(fitted, "yield_backtest")
    assert len(actual) == len(detail)
    np.testing.assert_allclose(actual["model_t"], detail["model_t"], atol=ROUND_3 * 10)


def test_projection(projected: StepResult) -> None:
    actual = frame(projected, "yield_projection")
    expected = pd.read_csv(RESULTS / "yield_projection_2041_2060.csv")
    both = actual.merge(expected, on=["region", "crop", "scenario"], suffixes=("", "_ref"))
    assert len(actual) == len(expected) == len(both)
    for column in expected.columns.drop(["region", "crop", "scenario"]):
        np.testing.assert_allclose(
            both[column], both[f"{column}_ref"], atol=ROUND_5, err_msg=column
        )


def test_projection_tables(projected: StepResult) -> None:
    parcel_seasons = frame(projected, "parcel_seasons")
    assert parcel_seasons.shape == (433_800, 42)
    assert not parcel_seasons["log_yield"].isna().any()
    draws = frame(projected, "yield_draws")
    assert list(draws.columns[-2:]) == ["region", "crop"]


def test_climate_risk(priced: StepResult) -> None:
    actual = frame(priced, "climate_risk")
    expected = pd.read_csv(RESULTS / "climate_risk_eur.csv")
    key = ["region", "crop", "scenario", "ngfs"]
    both = actual.merge(expected, on=key, suffixes=("", "_ref"))
    assert len(actual) == len(expected) == len(both)
    for column in expected.columns.drop(key):
        # The import factors are copied rounded to 6 decimals, so emissions differ in the 6th digit.
        np.testing.assert_allclose(
            both[column],
            both[f"{column}_ref"],
            rtol=0 if column.endswith("_eur") else EMISSION_RTOL,
            atol=CENT if column.endswith("_eur") else ROUND_3,
            err_msg=column,
        )


def test_climate_risk_total(priced: StepResult) -> None:
    actual = frame(priced, "climate_risk_total")
    expected = pd.read_csv(RESULTS / "climate_risk_total.csv")
    both = actual.merge(expected, on=["scenario", "ngfs"], suffixes=("", "_ref"))
    assert len(actual) == len(expected) == len(both)
    for column, reference in (
        ("expected_cost_eur", "expected_cost_keur"),
        ("one_in_ten_cost_eur", "one_in_ten_cost_keur"),
        ("climate_added_cost_eur", "climate adds, expected kEUR/yr"),
    ):
        np.testing.assert_allclose(both[column], 1000 * both[reference], atol=EURO, err_msg=column)
    for column in ("expected_import_tco2e", "one_in_ten_import_tco2e"):
        np.testing.assert_allclose(
            both[column], both[f"{column}_ref"], rtol=EMISSION_RTOL, atol=ROUND_3
        )
    assert list(actual.columns) == [
        "scenario",
        "ngfs",
        "expected_cost_eur",
        "one_in_ten_cost_eur",
        "expected_import_tco2e",
        "one_in_ten_import_tco2e",
        "climate_added_cost_eur",
    ]


def test_foodhills_cover(priced: StepResult) -> None:
    actual = frame(priced, "foodhills_cover")
    expected = pd.read_csv(RESULTS / "foodhills_cover_insight.csv")
    assert actual["scenario"].tolist() == ["baseline", "ssp126", "ssp245", "ssp585"]
    assert actual["seasons"].tolist() == expected["seasons"].tolist()
    assert actual["seasons_short"].tolist() == expected["Finnish pea short by >10%"].tolist()
    assert (
        actual["seasons_with_surplus"].tolist()
        == expected["of which Sweden had a surplus"].tolist()
    )
    np.testing.assert_allclose(
        actual["cover_share_pct"],
        expected["share of Finnish shortfall Swedish surplus could cover (%)"],
        atol=ROUND_3,
    )
    np.testing.assert_allclose(
        actual["premium_avoided_eur"],
        1000 * expected["premium avoided at most (kEUR/yr)"],
        atol=EURO,
    )


def test_models_round_trip_through_tables(tables: dict[str, Artifact]) -> None:
    history = tables["model_table"].frame
    models = {
        unit: ym.fit(
            history[history["region"].eq(unit[0]) & history["crop"].eq(unit[1])],
            ym.features(unit[1]),
        )
        for unit in [("FI_SW", "pea"), ("SE_SKANE", "pea")]
    }
    assert ym.models_from_tables(*ym.model_tables(models)) == models


def test_tables_are_stored_as_parquet(
    fitted: StepResult, projected: StepResult, priced: StepResult
) -> None:
    for result in (fitted, projected, priced):
        for table in result.tables:
            stored = parquet_to_frame(frame_to_parquet(table.frame))
            assert stored.shape == table.frame.shape, table.name
            assert list(stored.columns) == list(table.frame.columns), table.name


def plain(value: Any) -> bool:
    """A value that goes into JSON as itself: no numpy types."""
    if isinstance(value, list):
        return all(plain(v) for v in value)  # pyright: ignore[reportUnknownVariableType]
    return type(value) in (str, int, float, bool) or value is None


def test_metrics_and_insights_reach_the_runner(
    tables: dict[str, Artifact], fitted: StepResult, projected: StepResult, priced: StepResult
) -> None:
    results = (fitted, projected, priced)
    assert [len(r.metrics) for r in results if r.metrics is not None] == [12, 42, 183]
    for result in results:
        assert result.metrics is not None
        assert list(result.metrics.columns) == METRIC_COLUMNS
    metrics = [r.metrics for r in results if r.metrics is not None]
    artifact_ids = {name: f"art_{name}" for name in tables}
    assumption_names = [a.name for r in results for a in r.assumptions]
    assert len(assumption_names) == len(set(assumption_names))
    assert priced.insights is not None
    rows, metric_ids = build_metric_rows(
        metrics, "rs_1", artifact_ids, {name: f"asm_{name}" for name in assumption_names}
    )
    assert len(rows) == 237
    insights = build_insight_rows([("price_risk", priced.insights)], "rs_1", metric_ids)
    assert len(insights) == 1
    assert len(insights[0].metric_ids) == 4

    names = {r.name for r in rows}
    assert names == METRIC_NAMES
    assert not any((r.scenario or "").endswith("_run") for r in rows)
    for row in rows:
        json.dumps(row.lineage)
        assert row.unit
        assert row.period


def test_metric_lineage_selects_rows(
    tables: dict[str, Artifact], fitted: StepResult, projected: StepResult, priced: StepResult
) -> None:
    seen: set[str] = set()
    for result in (fitted, projected, priced):
        assert result.metrics is not None
        for record in result.metrics.to_dict("records"):
            assert plain([record[c] for c in METRIC_COLUMNS if c != "lineage"])
            for entry in record["lineage"]:
                assert plain(list(entry["filter"].values()))
                label = json.dumps([entry["table"], entry["filter"]], sort_keys=True)
                if label in seen:
                    continue
                seen.add(label)
                data = tables[entry["table"]].frame
                mask = pd.Series(True, index=data.index)
                for column, value in entry["filter"].items():
                    assert column in data.columns, label
                    mask &= data[column].isin(value if isinstance(value, list) else [value])
                assert mask.any(), label


def test_unit_keys_and_periods(fitted: StepResult, projected: StepResult) -> None:
    assert fitted.metrics is not None and projected.metrics is not None
    assert fitted.metrics["key"].is_unique and projected.metrics["key"].is_unique
    periods = fitted.metrics.groupby(["region", "crop"])["period"].first()
    assert periods[("FI_SW", "pea")] == f"2012{DASH}2026"
    assert periods[("SE_SKANE", "pea")] == f"2018{DASH}2026"
    bad = projected.metrics[projected.metrics["name"].eq("project_yields.bad_year_chance")]
    assert set(bad.loc[bad["scenario"].eq("baseline"), "period"]) == {f"1991{DASH}2020"}
    assert set(bad.loc[~bad["scenario"].eq("baseline"), "period"]) == {f"2041{DASH}2060"}


def test_price_override_moves_the_cost(
    ctx: RunContext, tables: dict[str, Artifact], priced: StepResult
) -> None:
    spec = recipe_step("price_risk")
    params: Mapping[str, Any] = {
        **spec.params,
        "price_overrides": {"pea": {"contract_price_eur_t": 430}},
    }
    inputs = {n: tables[n] for n in spec.inputs}
    changed = price_risk(ctx, inputs, params)

    def cost(result: StepResult) -> float:
        risk = frame(result, "climate_risk")
        row = risk[
            risk["region"].eq("FI_SW") & risk["crop"].eq("pea") & risk["scenario"].eq("baseline")
        ]
        return float(row["expected_cost_eur"].iloc[0])

    assert cost(changed) == pytest.approx(cost(priced) * 430 / 420)
    named = {a.name: a.value for a in changed.assumptions}
    assert named["price_risk.contract_price_eur_t.pea"] == 430.0
    assert named["price_risk.contract_price_eur_t.pea_SE"] == 410.0


def test_premium_lift_override(
    ctx: RunContext, tables: dict[str, Artifact], priced: StepResult
) -> None:
    spec = recipe_step("price_risk")
    inputs = {n: tables[n] for n in spec.inputs}
    changed = price_risk(ctx, inputs, {**spec.params, "replacement_premium_lift": {"ndcs": 0.0}})
    named = {a.name: a.value for a in changed.assumptions}
    assert named["price_risk.replacement_premium_lift"]["ndcs"] == 0.0
    total = frame(changed, "climate_risk_total").set_index(["scenario", "ngfs"])[
        "expected_cost_eur"
    ]
    before = frame(priced, "climate_risk_total").set_index(["scenario", "ngfs"])[
        "expected_cost_eur"
    ]
    after, base = total.to_dict(), before.to_dict()
    assert after[("ssp245", "ndcs")] < base[("ssp245", "ndcs")]
    assert after[("ssp585", "current_policies")] == pytest.approx(
        base[("ssp585", "current_policies")]
    )
