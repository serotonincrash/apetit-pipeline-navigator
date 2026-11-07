"""Step 5: tune_calendar, from sections 1, 2 and 4 of `notebooks/c1_weather_features.ipynb`.

The package does not publish the crop calendar behind its yields, so this step tunes it. The
yields show when in the season a crop is sensitive to drought and heat, but not when it is
harvested: a long season with a late sensitive window fits about as well as a short season with
an early one. So each setting is also checked against the ERP delivery dates, and a setting
that fits them wins if its error is within the tolerance of the best fit.

The analysis modules are not typed yet (see pyproject.toml), so calls into them carry a pyright
ignore for their untyped parameters.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, replace
from itertools import product
from typing import Any, cast

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

# The ERP movement type of a goods receipt, which is a delivery to the factory.
GOODS_RECEIPT = 101
SOURCE_PARAMS = "recipe farm_climate_risk, tune_calendar params"
# The ready date does not depend on the soil, so one soil class counts each cell-season once.
READY_DATE_SOIL = "clay"


def calendar_setting(
    crop: str,
    gdd_maturity: float,
    sow_temp_c: float,
    window_start: float,
    window_span: float,
    flower_share: float,
) -> cw.CropParams:
    """The crop's starting calendar with one grid setting applied.

    The heat-sensitive (flowering) window starts with the drought-sensitive window and lasts
    `flower_share` of the season's degree-days.
    """
    return replace(
        cw.DEFAULT_PARAMS[crop],
        gdd_maturity=float(gdd_maturity),
        sow_temp_c=float(sow_temp_c),
        sensitive=(window_start, round(window_start + window_span, 2)),
        flower=(window_start, round(min(window_start + flower_share, 1.0), 2)),
    )


def day_label(day_of_year: float) -> str:
    """A day of the year as '14 Aug', or 'never' when the crop never gets ready."""
    if pd.isna(day_of_year):
        return "never"
    day = pd.Timestamp(2001, 1, 1) + pd.Timedelta(days=float(day_of_year) - 1)
    return day.strftime("%d %b")


def calendar_row(region: str, setting: cw.CropParams) -> dict[str, Any]:
    """One row of `crop_params`, with each window split into its start and end."""
    fields = asdict(setting)
    flower_start, flower_end = fields.pop("flower")
    sensitive_start, sensitive_end = fields.pop("sensitive")
    return {
        "region": region,
        **fields,
        "flower_start": float(flower_start),
        "flower_end": float(flower_end),
        "sensitive_start": float(sensitive_start),
        "sensitive_end": float(sensitive_end),
    }


@step(
    "tune_calendar",
    kind="model",
    summary=(
        "Picks the crop calendar for each region and crop (sowing temperature, degree-days to "
        "harvest, drought-sensitive window) from daily weather, past farm yields and ERP "
        "delivery dates. The calendar decides when drought and heat count against yield."
    ),
)
def tune_calendar(ctx: RunContext, inputs: dict[str, Artifact], params: Params) -> StepResult:
    units = [(str(region), str(crop)) for region, crop in params["units"]]
    cell_prefix: Mapping[str, str] = params["region_cell_prefix"]
    flower_share = float(params["flower_window_share"])

    with section(
        "soil water",
        "Tracks how dry each soil class gets, day by day, in every weather cell and season, "
        "using the soil water capacity assumption.",
    ):
        keys, arrays = cw.weather_arrays(inputs["weather_daily"].frame)
        stress, saturated = cw.soil_water(arrays)  # pyright: ignore[reportUnknownMemberType]

    with section(
        "farm-year tables",
        "Links each farm's declared parcels to their weather cells, so stress measures average "
        "over the farm's area for each crop and season.",
    ):
        training = inputs["training_table"].frame
        contract = inputs["parcel_year_contract"].frame
        declared = contract[contract["status"].eq("declared")].assign(scenario="historical")
        is_historical = keys["scenario"].eq("historical").to_numpy()
        series = {
            (region, crop): np.where(
                keys["cell_id"].str.startswith(cell_prefix[region]).to_numpy() & is_historical
            )[0]
            for region, crop in units
        }
        aggregators = {
            (region, crop): cw.FarmAggregator(
                keys, series[(region, crop)], declared[declared["crop"].eq(crop)]
            )
            for region, crop in units
        }
        yields = {
            (region, crop): training[training["crop"].eq(crop) & training["region"].eq(region)]
            for region, crop in units
        }

    def farm_years(unit: tuple[str, str], features: pd.DataFrame) -> pd.DataFrame:
        weather = aggregators[unit](features, cw.WEATHER_FEATURES)
        table = yields[unit].merge(
            weather, on=["farm_id", "crop", "year"], how="left", validate="one_to_one"
        )
        return cv.add_model_columns(table)  # pyright: ignore[reportUnknownMemberType]

    with section(
        "ready windows",
        "Sets when each crop should be ready from its ERP deliveries and the ready "
        "window lead time, with Swedish pea using Finnish pea deliveries.",
    ):
        erp = inputs["erp_purchase_lines"].frame
        materials: Mapping[str, str] = params["delivery_materials"]
        deliveries = erp[
            erp["material_id"].isin(list(materials)) & erp["movement_type"].eq(GOODS_RECEIPT)
        ].copy()
        deliveries["crop"] = deliveries["material_id"].map(materials)
        deliveries["doy"] = pd.to_datetime(deliveries["posting_date"]).dt.dayofyear
        early, late = params["delivery_quantiles"]
        early_day = deliveries.groupby("crop")["doy"].quantile(early)
        late_day = deliveries.groupby("crop")["doy"].quantile(late)
        lead_days = params["ready_window_lead_days"]
        ready_window = {
            (region, crop): (float(early_day[crop]) - lead_days, float(late_day[crop]))
            for region, crop in units
        }

    with section(
        "score settings",
        "Tries every calendar setting in the grid and scores how well it predicts each farm's "
        "yield in seasons left out of the fit.",
    ):
        # The ready date is the median over the seasons that have yield history.
        first_season = int(training["year"].min())
        rows: list[dict[str, Any]] = []
        for region, crop in units:
            first, last, stride = params["gdd_maturity_grid"][crop]
            grid = product(
                range(first, last + 1, stride),
                params["sowing_temp_grid"],
                params["window_start_grid"],
                params["window_span_grid"],
            )
            for gdd_maturity, sow_temp_c, window_start, window_span in grid:
                setting = calendar_setting(
                    crop, gdd_maturity, sow_temp_c, window_start, window_span, flower_share
                )
                features = cw.crop_features(  # pyright: ignore[reportUnknownMemberType]
                    keys, arrays, stress, saturated, setting, series[(region, crop)]
                )
                columns: list[str] = cv.model_features(crop)  # pyright: ignore[reportUnknownMemberType]
                farm_year = farm_years((region, crop), features)
                score = cast(
                    "dict[str, float]",
                    cv.loyo(farm_year, columns)[0],  # pyright: ignore[reportUnknownMemberType]
                )
                ready = features[
                    (features["year"] >= first_season) & features["soil_class"].eq(READY_DATE_SOIL)
                ]
                window_end = min(window_start + window_span, 1) * gdd_maturity
                rows.append(
                    {
                        "region": region,
                        "crop": crop,
                        "gdd_maturity": gdd_maturity,
                        "sow_temp_c": sow_temp_c,
                        "win_start": window_start,
                        "win_span": window_span,
                        "window_gdd": f"{window_start * gdd_maturity:.0f}-{window_end:.0f}",
                        "ready_doy_median": ready["mat_doy"].median(),
                        "immature_share": ready["immature"].mean(),
                        **score,
                    }
                )
        tuning = pd.DataFrame(rows)
        windows = [
            ready_window[unit] for unit in zip(tuning["region"], tuning["crop"], strict=True)
        ]
        tuning["ready_plausible"] = [
            low <= day <= high
            for day, (low, high) in zip(tuning["ready_doy_median"], windows, strict=True)
        ]

    with section(
        "pick settings",
        "Takes the best setting ready inside the ready window, unless it predicts worse than the "
        "best setting by more than the calendar error tolerance.",
    ):
        tolerance = params["error_tolerance"]
        weak_below = params["weak_identification_farm_years"]
        choices: list[dict[str, Any]] = []
        calendars: list[dict[str, Any]] = []
        for region, crop in units:
            settings = tuning[tuning["region"].eq(region) & tuning["crop"].eq(crop)]
            best_any = settings.nsmallest(1, "rmse_log").iloc[0]
            within_tolerance = settings["rmse_log"].le(best_any["rmse_log"] * (1 + tolerance))
            candidates = settings[settings["ready_plausible"].astype(bool) & within_tolerance]
            pick = candidates.nsmallest(1, "rmse_log").iloc[0] if len(candidates) else best_any
            setting = calendar_setting(
                crop,
                pick["gdd_maturity"],
                pick["sow_temp_c"],
                float(pick["win_start"]),
                float(pick["win_span"]),
                flower_share,
            )
            calendars.append(calendar_row(region, setting))
            choices.append(
                {
                    "region": region,
                    "crop": crop,
                    "farm_years": int(pick["n"]),
                    "gdd_maturity": pick["gdd_maturity"],
                    "sow_temp_c": pick["sow_temp_c"],
                    "sensitive_window_gdd": pick["window_gdd"],
                    "ready_median": day_label(pick["ready_doy_median"]),
                    "calendar": "plausible" if len(candidates) else "later than deliveries",
                    "rmse_baseline": pick["rmse_log_baseline"],
                    "rmse_best_any": best_any["rmse_log"],
                    "rmse_chosen": pick["rmse_log"],
                    "improvement_vs_baseline_pct": pick["improvement_pct"],
                    "best_any_window_gdd": best_any["window_gdd"],
                    "best_any_ready": day_label(best_any["ready_doy_median"]),
                    "identification": "weak (few farms)" if pick["n"] < weak_below else "clear",
                }
            )
        choice = pd.DataFrame(choices)
        no_gain = choice[~(choice["improvement_vs_baseline_pct"] > 0)]
        if len(no_gain):
            units_text = ", ".join(
                f"{r} {c}" for r, c in zip(no_gain["region"], no_gain["crop"], strict=True)
            )
            raise ValueError(
                f"The tuned calendar predicts yields no better than each farm's average yield "
                f"for {units_text}."
            )

    return StepResult(
        tables=[
            Artifact("calendar_tuning", "result", tuning),
            Artifact("calendar_choice", "result", choice),
            Artifact("crop_params", "feature", pd.DataFrame(calendars)),
        ],
        assumptions=[
            AssumptionUse(
                "tune_calendar.soil_water_capacity",
                "Soil water capacity by crop",
                dict(cw.AWC_MM),
                "mm",
                "navigator/analysis/cropweather.py",
            ),
            AssumptionUse(
                "tune_calendar.error_tolerance",
                "Calendar error tolerance",
                tolerance,
                "share of the best error",
                SOURCE_PARAMS,
            ),
            AssumptionUse(
                "tune_calendar.ready_window_lead_days",
                "Ready window lead time",
                lead_days,
                "days before early deliveries",
                SOURCE_PARAMS,
            ),
            AssumptionUse(
                "tune_calendar.delivery_quantiles",
                "Share of deliveries that marks the early and late end of the ready window",
                params["delivery_quantiles"],
                "share of deliveries",
                SOURCE_PARAMS,
            ),
            AssumptionUse(
                "tune_calendar.flower_window_share",
                "Share of the season's growing degree days counted as the flowering window",
                flower_share,
                "share of the season",
                SOURCE_PARAMS,
            ),
            AssumptionUse(
                "tune_calendar.weak_identification_farm_years",
                "Farm-years below which a setting is marked weakly identified",
                weak_below,
                "farm-years",
                SOURCE_PARAMS,
            ),
            AssumptionUse(
                "tune_calendar.gdd_maturity_grid",
                "Maturity lengths tried, by crop (first, last, step)",
                params["gdd_maturity_grid"],
                "growing degree days",
                SOURCE_PARAMS,
            ),
            AssumptionUse(
                "tune_calendar.sowing_temp_grid",
                "Sowing temperatures tried",
                params["sowing_temp_grid"],
                "degrees C",
                SOURCE_PARAMS,
            ),
            AssumptionUse(
                "tune_calendar.window_start_grid",
                "Start of the sowing window tried",
                params["window_start_grid"],
                "share of the season",
                SOURCE_PARAMS,
            ),
            AssumptionUse(
                "tune_calendar.window_span_grid",
                "Length of the sowing window tried",
                params["window_span_grid"],
                "share of the season",
                SOURCE_PARAMS,
            ),
            AssumptionUse(
                "tune_calendar.swedish_pea_delivery_dates",
                "Delivery dates used for Swedish pea",
                "Finnish pea ERP deliveries",
                "",
                "notebooks/c1_weather_features.ipynb, section 4a",
            ),
        ],
    )
