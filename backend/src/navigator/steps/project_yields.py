"""Step 8: project_yields, from sections 1, 2, 4 and 7 of `notebooks/c2_yield_projection.ipynb`.

Every season of 1991 to 2020 is shifted to each climate scenario's 2041 to 2060 climate with the
package's monthly changes, run through the crop features and the fitted yield model with
today's parcels, and simulated many times with the model's leftover error.

The analysis modules are not typed yet (see pyproject.toml), so calls into them carry a pyright
ignore for their untyped parameters.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd

from navigator.analysis import climateproj as cp
from navigator.analysis import cropweather as cw
from navigator.analysis import yieldmodel as ym
from navigator.recipes.core import (
    Artifact,
    AssumptionUse,
    Params,
    RunContext,
    StepResult,
    section,
    step,
)
from navigator.steps.fit_yield_model import (
    DASH,
    MODEL_ASSUMPTIONS,
    metric_frame,
    metric_key,
    unit_list,
)
from navigator.steps.weather_features import crop_calendar

CONTRACT_YEAR = "project_yields.contract_year"
TREND_YEAR = "project_yields.trend_year"
SIMULATED_OUTCOMES = "project_yields.simulated_outcomes"
SIMULATION_SEED = "project_yields.simulation_seed"
BOOTSTRAP_SAMPLES = "project_yields.bootstrap_samples"
BOOTSTRAP_SEED = "project_yields.bootstrap_seed"
BAD_YEAR_SHARE = "project_yields.bad_year_share"
# The assumptions every projection and cost number rests on, through the model and the ensemble.
PROJECTION_ASSUMPTIONS = [
    *MODEL_ASSUMPTIONS,
    CONTRACT_YEAR,
    TREND_YEAR,
    SIMULATED_OUTCOMES,
    SIMULATION_SEED,
]
RANGE_ASSUMPTIONS = [BOOTSTRAP_SAMPLES, BOOTSTRAP_SEED]

# The parcel columns the weather measures are attached to.
PARCEL_COLUMNS = [
    "parcel_id",
    "farm_id",
    "region",
    "crop",
    "parcel_area_ha",
    "soil_class_soilmap",
    "clay_pct_soilmap",
    "slope_pct",
    "cell_id",
]
# How far a shifted-season mean change may sit from the delivered run's, in percentage points.
DELIVERED_RUN_TOLERANCE_POINTS = 8.0
FUTURE_SCENARIOS = list(cp.SCENARIOS)


def period(years: tuple[int, int]) -> str:
    return f"{years[0]}{DASH}{years[1]}"


@step(
    "project_yields",
    kind="model",
    summary=(
        "Shifts every past season to each climate scenario, runs today's contract parcels "
        "through the yield model and simulates each season many times. It writes the yield "
        "change and bad-year chance for each region, crop and climate scenario."
    ),
)
def project_yields(ctx: RunContext, inputs: dict[str, Artifact], params: Params) -> StepResult:
    units = unit_list(params)
    cell_prefix: Mapping[str, str] = params["region_cell_prefix"]
    contract_year = int(params["contract_year"])
    trend_year = int(params["trend_year"])
    outcomes = int(params["simulated_outcomes"])
    simulation_seed = int(params["simulation_seed"])
    bootstrap_samples = int(params["bootstrap_samples"])
    bootstrap_seed = int(params["bootstrap_seed"])
    bad_year_share = float(params["bad_year_share"])

    models: dict[tuple[str, str], ym.Model] = ym.models_from_tables(
        inputs["yield_coefficients"].frame,
        inputs["yield_fit"].frame,
        inputs["farm_levels"].frame,
    )
    history = inputs["model_table"].frame

    with section(
        "weather sets",
        "Builds the recorded seasons, the same seasons shifted to each climate scenario, and "
        "the delivered 2041 to 2060 runs kept as a check.",
    ):
        keys, arrays = cw.weather_arrays(inputs["weather_daily"].frame)
        shifted_keys, shifted = cp.ensemble(  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            keys, arrays, inputs["climate_change_signals"].frame
        )
        del arrays
        stress, saturated = cw.soil_water(shifted)  # pyright: ignore[reportUnknownMemberType]

    with section(
        "parcels and seasons",
        "Pairs each contract parcel with every season in every weather set, using its own "
        "weather cell, soil and management, trend held at one year.",
    ):
        features = inputs["parcel_year_features"].frame
        contract_parcels = features[
            features["status"].eq("declared") & features["year"].eq(contract_year)
        ][PARCEL_COLUMNS]
        per_farm, unit_management = ym.management_defaults(history)
        calendars = {
            (str(row["region"]), str(row["crop"])): crop_calendar(row)
            for row in inputs["crop_params"].frame.to_dict("records")
        }
        seasons = {
            unit: cp.parcel_seasons(  # pyright: ignore[reportUnknownMemberType]
                shifted_keys,
                shifted,
                stress,
                saturated,
                calendars[unit],
                contract_parcels,
                per_farm,
                unit_management,
                models[unit],
                unit,
                trend_year,
                dict(cell_prefix),
            )
            for unit in units
        }

    with section(
        "simulate seasons",
        "Simulates each season many times with the model's leftover error, shared by all farms "
        "in a season and separate for each farm.",
    ):
        draws: list[pd.DataFrame] = []
        projection: list[pd.DataFrame] = []
        for unit in units:
            region, crop = unit
            lp = seasons[unit][["farm_id", "scenario", "year", "parcel_area_ha", "log_yield"]]
            unit_draws = cp.simulate(  # pyright: ignore[reportUnknownMemberType]
                lp, models[unit], outcomes, simulation_seed
            )
            summary = cp.summarise(unit_draws, bad_year_share).merge(  # pyright: ignore[reportUnknownMemberType]
                cp.bootstrap(unit_draws, bootstrap_samples, bad_year_share, bootstrap_seed),  # pyright: ignore[reportUnknownMemberType]
                on="scenario",
            )
            summary.insert(0, "region", region)
            summary.insert(1, "crop", crop)
            projection.append(summary)
            draws.append(unit_draws.assign(region=region, crop=crop))
        parcel_seasons = pd.concat(list(seasons.values()), ignore_index=True)
        yield_draws = pd.concat(draws, ignore_index=True)
        yield_projection = pd.concat(projection, ignore_index=True)

    with section(
        "checks",
        "Stops the run if a result or parcel-season is missing, the baseline moves, or the "
        "delivered runs disagree with the shifted seasons.",
    ):
        check_projection(parcel_seasons, yield_projection)

    after = period(cp.FUTURE_YEARS)
    before = period(cp.BASE_YEARS)
    metrics: list[dict[str, Any]] = []
    for row in yield_projection.to_dict("records"):
        scenario = str(row["scenario"])
        if scenario.endswith("_run"):
            continue
        region, crop = str(row["region"]), str(row["crop"])
        lineage = [
            {
                "table": table,
                "filter": {"region": region, "crop": crop, "scenario": scenario},
            }
            for table in ("yield_projection", "parcel_seasons")
        ]
        lineage.append({"table": "model_table", "filter": {"region": region, "crop": crop}})
        if scenario in FUTURE_SCENARIOS:
            name = "project_yields.yield_change_pct"
            metrics.append(
                {
                    "key": metric_key(name, region, crop, scenario),
                    "name": name,
                    "unit": "%",
                    "value": float(row["mean_yield_change_pct"]),
                    "low": float(row["change_low_pct"]),
                    "high": float(row["change_high_pct"]),
                    "region": region,
                    "crop": crop,
                    "scenario": scenario,
                    "ngfs_scenario": None,
                    "period": after,
                    "action_id": None,
                    "lineage": lineage,
                    "assumptions": [
                        *PROJECTION_ASSUMPTIONS,
                        *RANGE_ASSUMPTIONS,
                    ],
                }
            )
        name = "project_yields.bad_year_chance"
        metrics.append(
            {
                "key": metric_key(name, region, crop, scenario),
                "name": name,
                "unit": "share",
                "value": float(row["p_bad_year"]),
                "low": float(row["p_bad_low"]),
                "high": float(row["p_bad_high"]),
                "region": region,
                "crop": crop,
                "scenario": scenario,
                "ngfs_scenario": None,
                "period": before if scenario == "baseline" else after,
                "action_id": None,
                "lineage": lineage,
                "assumptions": [
                    *PROJECTION_ASSUMPTIONS,
                    BAD_YEAR_SHARE,
                    *RANGE_ASSUMPTIONS,
                ],
            }
        )

    source = "recipe farm_climate_risk, project_yields params"
    return StepResult(
        tables=[
            Artifact("parcel_seasons", "feature", parcel_seasons),
            Artifact("yield_draws", "result", yield_draws),
            Artifact("yield_projection", "result", yield_projection),
        ],
        metrics=metric_frame(metrics),
        assumptions=[
            AssumptionUse(
                CONTRACT_YEAR,
                "Season whose declared parcels are the contract parcels",
                contract_year,
                "year",
                source,
            ),
            AssumptionUse(
                TREND_YEAR,
                "Year at which the yearly yield trend is held",
                trend_year,
                "year",
                source,
            ),
            AssumptionUse(
                SIMULATED_OUTCOMES,
                "Simulated outcomes per season",
                outcomes,
                "outcomes",
                source,
            ),
            AssumptionUse(
                SIMULATION_SEED,
                "Random seed for the simulated outcomes",
                simulation_seed,
                "",
                source,
            ),
            AssumptionUse(
                BOOTSTRAP_SAMPLES,
                "Resamples for the ranges of the yield change and the bad-year chance",
                bootstrap_samples,
                "resamples",
                source,
            ),
            AssumptionUse(
                BOOTSTRAP_SEED,
                "Random seed for the resampled ranges",
                bootstrap_seed,
                "",
                source,
            ),
            AssumptionUse(
                BAD_YEAR_SHARE,
                "Share of the 1991 to 2020 average yield below which a season is a bad year",
                bad_year_share,
                "share",
                "The package's own definition of a bad year",
            ),
        ],
    )


def check_projection(parcel_seasons: pd.DataFrame, projection: pd.DataFrame) -> None:
    """The notebook's checks that apply inside the run; they raise in plain words."""
    results = projection[projection["scenario"].isin(["baseline", *FUTURE_SCENARIOS])]
    missing = int((~results[["mean_yield_change_pct", "p_bad_year"]].notna().all(axis=1)).sum())
    if missing:
        raise ValueError(f"{missing} region, crop and climate scenario results have no value.")
    if not np.allclose(results.loc[results["scenario"].eq("baseline"), "mean_yield_change_pct"], 0):
        raise ValueError("The baseline yield change is not zero, so the comparison is off.")
    no_prediction = int(parcel_seasons["log_yield"].isna().sum())
    if no_prediction:
        raise ValueError(f"{no_prediction} parcel-seasons have no expected yield.")
    shifted_seasons = cp.BASE_YEARS[1] - cp.BASE_YEARS[0] + 1
    delivered_seasons = cp.FUTURE_YEARS[1] - cp.FUTURE_YEARS[0] + 1
    runs = projection["scenario"].str.endswith("_run")
    if set(projection.loc[~runs, "seasons"]) != {shifted_seasons}:
        raise ValueError(f"Not every shifted weather set has {shifted_seasons} seasons.")
    if set(projection.loc[runs, "seasons"]) != {delivered_seasons}:
        raise ValueError(f"Not every delivered weather run has {delivered_seasons} seasons.")
    delivered = projection[runs].assign(scenario=lambda f: f["scenario"].str.removesuffix("_run"))
    paired = delivered.merge(
        projection[~runs], on=["region", "crop", "scenario"], suffixes=("_run", "")
    )
    gap = (paired["mean_yield_change_pct_run"] - paired["mean_yield_change_pct"]).abs()
    if not (gap < DELIVERED_RUN_TOLERANCE_POINTS).all():
        raise ValueError(
            f"The mean yield change of a delivered run and its shifted seasons differ by "
            f"{gap.max():.1f} points, more than the allowed {DELIVERED_RUN_TOLERANCE_POINTS:.0f}."
        )
