"""Step 7: fit_yield_model, from sections 2 and 3 of `notebooks/c1_yield_model.ipynb`.

One within-farm model per region and crop, checked season by season on held-out years. The
fitted model leaves as three tables, because steps pass only tables.

The analysis modules are not typed yet (see pyproject.toml), so calls into them carry a pyright
ignore for their untyped parameters.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pandas as pd

from navigator.analysis import yieldmodel as ym
from navigator.recipes.core import (
    METRIC_COLUMNS,
    Artifact,
    AssumptionUse,
    Params,
    RunContext,
    StepResult,
    section,
    step,
)

RIDGE_STRENGTH = "fit_yield_model.ridge_strength"
SHRINK_SEASONS = "fit_yield_model.shrink_seasons"
# The assumptions every yield and cost number rests on through the fitted model.
MODEL_ASSUMPTIONS = [RIDGE_STRENGTH, SHRINK_SEASONS]

DASH = "–"  # noqa: RUF001


def unit_list(params: Params) -> list[tuple[str, str]]:
    """The region and crop pairs from a step's `units` param."""
    return [(str(region), str(crop)) for region, crop in params["units"]]


def metric_frame(rows: Sequence[dict[str, Any]]) -> pd.DataFrame:
    """A step's metrics as the table the runner reads: the exact metric columns."""
    return pd.DataFrame(list(rows), columns=METRIC_COLUMNS)


def metric_key(name: str, *dimensions: str | None) -> str:
    """The metric's name and the dimensions it has, joined with a vertical bar."""
    return "|".join([name, *(d for d in dimensions if d is not None)])


@step(
    "fit_yield_model",
    kind="model",
    summary=(
        "Fits one yield model per region and crop on the farm-year table, with each farm's own "
        "level plus weather and management effects. It tests the model on held-out seasons "
        "and stops if the farm average predicts better."
    ),
)
def fit_yield_model(ctx: RunContext, inputs: dict[str, Artifact], params: Params) -> StepResult:
    units = unit_list(params)
    ridge_strength = float(params["ridge_strength"])
    shrink_seasons = float(params["shrink_seasons"])
    history = inputs["model_table"].frame

    with section(
        "fit",
        "Fits each region and crop on every season with a recorded yield, using the ridge "
        "strength and farm shrinkage assumptions.",
    ):
        models: dict[tuple[str, str], ym.Model] = {
            (region, crop): ym.fit(  # pyright: ignore[reportUnknownMemberType]
                history[history["region"].eq(region) & history["crop"].eq(crop)],
                ym.features(crop),
                ridge_strength,
                shrink_seasons,
            )
            for region, crop in units
        }
        coefficients, fit_table, farm_levels = ym.model_tables(models)

    with section(
        "test on unseen seasons",
        "Refits without each season in turn and predicts it, then compares the regional "
        "production error with the farm's own average yield.",
    ):
        backtest = pd.concat(
            [ym.backtest(history, unit, ridge_strength, shrink_seasons) for unit in units],
            ignore_index=True,
        )
        summary = ym.backtest_summary(backtest)

    with section(
        "checks",
        "Stops the run if the model does not beat the farm average on production error for "
        "every region and crop.",
    ):
        worse = summary[
            ~(summary["production error, model (%)"] < summary["production error, baseline (%)"])
        ]
        if len(worse):
            names = ", ".join(f"{region} {crop}" for region, crop in worse.index)
            raise ValueError(
                f"The yield model no longer beats the farm average on production error for "
                f"{names}. Check the model table and the ridge strength before going on."
            )

    metrics: list[dict[str, Any]] = []
    for row in summary.reset_index().to_dict("records"):
        region, crop = str(row["region"]), str(row["crop"])
        seasons = backtest[backtest["region"].eq(region) & backtest["crop"].eq(crop)]["year"]
        period = f"{int(seasons.min())}{DASH}{int(seasons.max())}"
        lineage = [
            {"table": "yield_backtest", "filter": {"region": str(region), "crop": str(crop)}},
            {"table": "model_table", "filter": {"region": str(region), "crop": str(crop)}},
        ]
        for name, column in (
            ("fit_yield_model.production_error_pct", "production error, model (%)"),
            ("fit_yield_model.baseline_production_error_pct", "production error, baseline (%)"),
        ):
            metrics.append(
                {
                    "key": metric_key(name, str(region), str(crop)),
                    "name": name,
                    "unit": "%",
                    "value": float(row[column]),
                    "low": None,
                    "high": None,
                    "region": str(region),
                    "crop": str(crop),
                    "scenario": None,
                    "ngfs_scenario": None,
                    "period": period,
                    "action_id": None,
                    "lineage": lineage,
                    "assumptions": list(MODEL_ASSUMPTIONS),
                }
            )

    source = "recipe farm_climate_risk, fit_yield_model params"
    return StepResult(
        tables=[
            Artifact("yield_coefficients", "feature", coefficients),
            Artifact("yield_fit", "feature", fit_table),
            Artifact("farm_levels", "feature", farm_levels),
            Artifact("yield_backtest", "result", backtest),
        ],
        metrics=metric_frame(metrics),
        assumptions=[
            AssumptionUse(
                RIDGE_STRENGTH,
                "Ridge strength of the yield model",
                ridge_strength,
                "penalty weight",
                source,
            ),
            AssumptionUse(
                SHRINK_SEASONS,
                "Seasons of history a farm needs before its own level counts fully",
                shrink_seasons,
                "seasons",
                source,
            ),
        ],
    )
