"""Step 6: weather_features, from sections 6 and 7 of `notebooks/c1_weather_features.ipynb`.

With the crop calendar from `tune_calendar`, the stress measures are worked out for every
weather cell, soil class, season and climate scenario. They are then attached to parcel-years
(for the C1 forecast) and averaged over each farm's parcels (for the yield model).

The analysis modules are not typed yet (see pyproject.toml), so calls into them carry a pyright
ignore for their untyped parameters.
"""

from __future__ import annotations

from collections.abc import Hashable, Mapping
from typing import Any

import numpy as np
import pandas as pd

from navigator.analysis import cropweather as cw
from navigator.analysis import yieldcv as cv
from navigator.recipes.core import (
    Artifact,
    AssumptionUse,
    Params,
    RunContext,
    StepResult,
    section,
    step,
)

# Measures every C1 template row and every training row must have.
CORE_FEATURES = [
    "drought_stage",
    "heat_days_27",
    "harvest_rain_14_mm",
    "immature_gap",
    "season_gdd",
]
# The climate scenarios and first season of the 2041 to 2060 projection.
FUTURE_SCENARIOS = {"ssp126", "ssp245", "ssp585"}
PROJECTION_FIRST_SEASON = 2041


def crop_calendar(row: Mapping[Hashable, Any]) -> cw.CropParams:
    """The tuned calendar from one row of `crop_params`."""
    return cw.CropParams(
        crop=str(row["crop"]),
        sow_temp_c=float(row["sow_temp_c"]),
        sow_earliest=str(row["sow_earliest"]),
        sow_latest=str(row["sow_latest"]),
        gdd_maturity=float(row["gdd_maturity"]),
        cutoff=str(row["cutoff"]),
        flower=(float(row["flower_start"]), float(row["flower_end"])),
        sensitive=(float(row["sensitive_start"]), float(row["sensitive_end"])),
    )


@step(
    "weather_features",
    kind="transform",
    summary=(
        "Computes drought, heat and rain measures for every weather cell, soil class, crop, "
        "season and climate scenario with the tuned crop calendar. It attaches them to "
        "parcel-years for the C1 forecast and to farm-years for the yield model."
    ),
)
def weather_features(ctx: RunContext, inputs: dict[str, Artifact], params: Params) -> StepResult:
    c1_scenario = str(params["c1_scenario"])
    cell_prefix: Mapping[str, str] = params["region_cell_prefix"]

    with section(
        "soil water",
        "Tracks how dry each soil class gets, day by day, in every weather cell, season and "
        "climate scenario, using the soil water capacity assumption.",
    ):
        keys, arrays = cw.weather_arrays(inputs["weather_daily"].frame)
        stress, saturated = cw.soil_water(arrays)  # pyright: ignore[reportUnknownMemberType]

    with section(
        "stress measures",
        "Works out sowing, ripening, drought, heat and rain measures for every weather cell, "
        "soil class, season and scenario with each region's tuned crop calendar.",
    ):
        calendars = [
            (str(row["region"]), crop_calendar(row))
            for row in inputs["crop_params"].frame.to_dict("records")
        ]
        cell = pd.concat(
            [
                cw.crop_features(  # pyright: ignore[reportUnknownMemberType]
                    keys,
                    arrays,
                    stress,
                    saturated,
                    calendar,
                    np.where(keys["cell_id"].str.startswith(cell_prefix[region]).to_numpy())[0],
                ).assign(region=region)
                for region, calendar in calendars
            ],
            ignore_index=True,
        )
        repeated = int(cell.duplicated(["scenario", "cell_id", "year", "crop", "soil_class"]).sum())
        if repeated:
            raise ValueError(
                f"{repeated} rows repeat a weather cell, season, crop, soil class and scenario. "
                "Check that crop_params has one row per region and crop, and that no two regions "
                "share a weather cell prefix."
            )

    with section(
        "parcels and farm-years",
        "Attaches the measures to each parcel-year and averages them over each farm's parcels by "
        "area, using the C1 climate scenario for planned seasons.",
    ):
        contract = inputs["parcel_year_contract"].frame
        contract = contract.assign(
            scenario=np.where(contract["status"].eq("declared"), "historical", c1_scenario)
        )
        parcel_year = cw.to_parcels(cell, contract)
        farm_year = cw.to_farms(  # pyright: ignore[reportUnknownMemberType]
            parcel_year[parcel_year["status"].eq("declared")], cw.WEATHER_FEATURES
        )
        training = inputs["training_table"].frame
        model: pd.DataFrame = cv.add_model_columns(  # pyright: ignore[reportUnknownMemberType]
            training.merge(
                farm_year, on=["farm_id", "crop", "year"], how="left", validate="one_to_one"
            )
        )

    with section(
        "checks",
        "Stops the run if a C1 template row or farm-year lacks weather measures, or a future "
        "climate scenario is missing.",
    ):
        template = inputs["c1_template"].frame
        c1_rows = template.merge(
            parcel_year, on=["parcel_id", "farm_id", "year", "crop"], how="left"
        )
        c1_missing = int((~c1_rows[CORE_FEATURES].notna().all(axis=1)).sum())
        if c1_missing:
            raise ValueError(f"{c1_missing} C1 template rows have no weather measures.")
        c1_other = int((~c1_rows["scenario"].eq(c1_scenario)).sum())
        if c1_other:
            raise ValueError(f"{c1_other} C1 template rows use weather other than {c1_scenario}.")
        training_missing = int((~model[CORE_FEATURES].notna().all(axis=1)).sum())
        if training_missing:
            raise ValueError(f"{training_missing} farm-years have no weather measures.")
        if len(model) != len(training):
            raise ValueError(
                f"The farm-year table has {len(model)} rows, but the training table has "
                f"{len(training)}."
            )
        projected = set(cell.loc[cell["year"] >= PROJECTION_FIRST_SEASON, "scenario"])
        if projected != FUTURE_SCENARIOS:
            raise ValueError(
                f"Seasons from {PROJECTION_FIRST_SEASON} have the climate scenarios "
                f"{sorted(projected)}, expected {sorted(FUTURE_SCENARIOS)}."
            )

    return StepResult(
        tables=[
            Artifact("weather_features_cell", "feature", cell),
            Artifact("parcel_year_features", "feature", parcel_year),
            Artifact("model_table", "feature", model),
        ],
        assumptions=[
            AssumptionUse(
                "weather_features.soil_water_capacity",
                "Soil water capacity by crop",
                dict(cw.AWC_MM),
                "mm",
                "navigator/analysis/cropweather.py",
            ),
            AssumptionUse(
                "weather_features.c1_scenario",
                "Climate scenario for the delivered 2027 to 2031 yields",
                c1_scenario,
                "",
                "recipe farm_climate_risk, weather_features params",
            ),
        ],
    )
