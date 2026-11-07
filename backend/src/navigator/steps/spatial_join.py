"""Step 4: spatial_join. Weather cells, parcel-years and the training table, from
notebooks/c1_clean.ipynb sections 7 to 10.
"""

import numpy as np
import pandas as pd

from navigator.recipes.core import (
    PROPOSALS_INPUT,
    Artifact,
    Params,
    RunContext,
    StepResult,
    section,
    step,
)

EARTH_RADIUS_KM = 6371.0
KM_PER_DEGREE_LATITUDE = 111.0
FARM_YEAR_KEY = ["farm_id", "year", "crop"]


def nearest_cell(parcels: pd.DataFrame, grid: pd.DataFrame) -> pd.DataFrame:
    """Each parcel's nearest weather cell in its own region, by great-circle distance."""
    matches: list[pd.DataFrame] = []
    for region, region_parcels in parcels.groupby("region"):
        cells = grid[grid["region"].eq(region)]
        lat1 = np.radians(region_parcels["lat"].to_numpy(dtype=float))[:, None]
        lon1 = np.radians(region_parcels["lon"].to_numpy(dtype=float))[:, None]
        lat2 = np.radians(cells["lat"].to_numpy(dtype=float))[None, :]
        lon2 = np.radians(cells["lon"].to_numpy(dtype=float))[None, :]
        haversine = (
            np.sin((lat2 - lat1) / 2) ** 2
            + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
        )
        distance_km = 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(haversine))
        nearest = distance_km.argmin(axis=1)
        matches.append(
            pd.DataFrame(
                {
                    "parcel_id": region_parcels["parcel_id"].to_numpy(),
                    "cell_id": cells["cell_id"].to_numpy()[nearest],
                    "cell_dist_km": distance_km[np.arange(len(region_parcels)), nearest].round(2),
                }
            )
        )
    return pd.concat(matches, ignore_index=True)


def match_parcels_to_cells(
    parcels: pd.DataFrame, registry_clean: pd.DataFrame, grid: pd.DataFrame, max_km: float
) -> pd.DataFrame:
    features = parcels.merge(
        registry_clean[["farm_id", "region", "country"]],
        on="farm_id",
        how="left",
        validate="many_to_one",
    )
    if features["region"].isna().any():
        raise ValueError("Some parcels belong to farms that are not in the farm registry.")
    features = features.merge(nearest_cell(features, grid), on="parcel_id", validate="one_to_one")
    farthest = features["cell_dist_km"].max()
    if farthest >= max_km:
        raise ValueError(
            f"A parcel is {farthest} km from its nearest weather cell, above the {max_km} km limit."
        )
    return features


def waiting_for_review(
    proposals: pd.DataFrame, record_keys: pd.Series, fields: list[str], label: str
) -> str:
    """A sentence naming the open fixes to these fields of these records, or an empty string.

    A check that fails because known errors have not been reviewed yet says so, so the person
    running the recipe knows to review them and run again.
    """
    waiting = proposals[
        proposals["action"].eq("fix")
        & proposals["status"].eq("open")
        & proposals["field"].isin(fields)
        & proposals["record_key"].isin(record_keys)
    ]
    if waiting.empty:
        return ""
    rules = " and ".join(sorted(waiting["rule_id"].unique()))
    count = len(waiting)
    noun = "fix" if count == 1 else "fixes"
    verb = "is" if count == 1 else "are"
    return (
        f" {count} {label} {noun} from rule {rules} {verb} waiting for review. Review them in "
        "Data review, then run the recipe again."
    )


def check_farms_near_parcels(
    registry_clean: pd.DataFrame, parcels: pd.DataFrame, proposals: pd.DataFrame, max_km: float
) -> None:
    """Stops when a farm's registered location is far from its own parcels."""
    centroid = parcels.groupby("farm_id")[["lat", "lon"]].median()
    farms = registry_clean.join(centroid, on="farm_id", rsuffix="_p").set_index("farm_id")
    north = farms["lat"] - farms["lat_p"]
    east = (farms["lon"] - farms["lon_p"]) * np.cos(np.radians(farms["lat"]))
    distance_km = KM_PER_DEGREE_LATITUDE * pd.Series(np.hypot(north, east), index=farms.index)
    too_far = distance_km[distance_km >= max_km]
    if too_far.empty:
        return
    keys = pd.Series("farm:" + too_far.index.astype(str))
    reason = waiting_for_review(proposals, keys, ["lat", "lon"], "coordinate") or (
        " Check their latitude and longitude in the farm registry."
    )
    raise ValueError(
        f"{len(too_far)} farms are more than {max_km:g} km from their own parcels; the farthest, "
        f"{too_far.idxmax()}, is {too_far.max():,.0f} km away.{reason}"
    )


def build_parcel_years(
    crop_history: pd.DataFrame, features: pd.DataFrame, contract_crops: list[str]
) -> pd.DataFrame:
    history = crop_history.sort_values(["parcel_id", "year"]).copy()
    history["prev_crop"] = history.groupby("parcel_id")["crop"].shift(1)
    # The previous crop counts only when it is from the year right before.
    history.loc[history.groupby("parcel_id")["year"].diff().ne(1), "prev_crop"] = np.nan
    parcel_years = history[history["crop"].isin(contract_crops)].merge(
        features.drop(columns=["lat", "lon"]).rename(columns={"area_ha": "parcel_area_ha"}),
        on=["parcel_id", "farm_id"],
        how="left",
        validate="many_to_one",
    )
    if parcel_years["cell_id"].isna().any():
        raise ValueError("Some parcel-years have no weather cell.")
    return parcel_years


def check_template(template: pd.DataFrame, parcel_years: pd.DataFrame, tolerance_ha: float) -> None:
    """Stops when a row of the yield submission template is missing or has another area."""
    rows = template.merge(parcel_years, on=["parcel_id", "farm_id", "year", "crop"], how="left")
    if rows["cell_id"].isna().any():
        raise ValueError("Some rows of the yield submission template are not in the parcel-years.")
    if not np.allclose(rows["area_ha"], rows["parcel_area_ha"], atol=tolerance_ha):
        raise ValueError("Some template areas differ from the parcel areas.")


def declared_parcel_features(parcel_years: pd.DataFrame) -> pd.DataFrame:
    """Soil, slope and crop history per farm, year and crop, weighted by declared parcel area."""
    declared = parcel_years[parcel_years["status"].eq("declared")].copy()
    area = declared["parcel_area_ha"]
    declared["clay_x_a"] = declared["clay_pct_soilmap"] * area
    declared["slope_x_a"] = declared["slope_pct"] * area
    declared["org_a"] = np.where(declared["soil_class_soilmap"].eq("organic"), area, 0.0)
    declared["sandy_a"] = np.where(
        declared["soil_class_soilmap"].isin(["sand", "fine_sand"]), area, 0.0
    )
    declared["same_prev_a"] = np.where(declared["prev_crop"].eq(declared["crop"]), area, 0.0)
    declared["catch_a"] = np.where(declared["catch_crop"].astype(bool), area, 0.0)

    features = declared.groupby(FARM_YEAR_KEY).agg(
        n_parcels=("parcel_id", "size"),
        parcel_area_ha=("parcel_area_ha", "sum"),
        clay_x_a=("clay_x_a", "sum"),
        slope_x_a=("slope_x_a", "sum"),
        org_a=("org_a", "sum"),
        sandy_a=("sandy_a", "sum"),
        same_prev_a=("same_prev_a", "sum"),
        catch_a=("catch_a", "sum"),
        n_cells=("cell_id", "nunique"),
    )
    for area_column, share_column in [
        ("clay_x_a", "clay_pct_wavg"),
        ("slope_x_a", "slope_pct_wavg"),
        ("org_a", "organic_share_soilmap"),
        ("sandy_a", "sandy_share"),
        ("same_prev_a", "same_crop_prev_year_share"),
        ("catch_a", "catch_crop_share_parcels"),
    ]:
        features[share_column] = features.pop(area_column) / features["parcel_area_ha"]
    # The main cell holds most of the farm's area for that crop and year.
    main_cell = (
        declared.groupby([*FARM_YEAR_KEY, "cell_id"])["parcel_area_ha"]
        .sum()
        .reset_index()
        .sort_values("parcel_area_ha")
        .drop_duplicates(FARM_YEAR_KEY, keep="last")
        .set_index(FARM_YEAR_KEY)["cell_id"]
    )
    features["main_cell_id"] = main_cell
    return features.reset_index()


def build_training_table(
    parcel_years: pd.DataFrame,
    survey_clean: pd.DataFrame,
    foodhills_clean: pd.DataFrame,
    registry_clean: pd.DataFrame,
) -> pd.DataFrame:
    finnish = survey_clean.assign(source="fi_farm_survey").drop(
        columns=["decl_area_ha", "org_area", "organic_share_soilmap"]
    )
    swedish = foodhills_clean.assign(
        source="se_foodhills", n_corrections=0, soil_misreport_flag=False
    ).drop(columns=["crop_sv", "irrigated_sv", "decl_area_ha", "org_area", "organic_share_soilmap"])
    farm_columns = ["farm_id", "region", "country", "organic_certified", "livestock", "joined_year"]
    training = (
        pd.concat([finnish, swedish], ignore_index=True)
        .merge(registry_clean[farm_columns], on="farm_id", how="left", validate="many_to_one")
        .merge(
            declared_parcel_features(parcel_years),
            on=FARM_YEAR_KEY,
            how="left",
            validate="one_to_one",
        )
    )
    front = [
        "record_key",
        "source",
        "farm_id",
        "region",
        "crop",
        "year",
        "yield_t_ha",
        "area_ha",
        "main_cell_id",
        "n_cells",
    ]
    ordered = front + [c for c in training.columns if c not in front]
    return training[ordered].sort_values(["region", "crop", "farm_id", "year"])


def check_training_table(
    training: pd.DataFrame, proposals: pd.DataFrame, expected_rows: int, max_yield_ratio: float
) -> None:
    if len(training) != expected_rows:
        raise ValueError(
            f"The training table has {len(training)} rows, but the cleaned survey and Foodhills "
            f"tables have {expected_rows}."
        )
    if training.duplicated(["farm_id", "crop", "year"]).any():
        raise ValueError("The training table has more than one row for a farm, crop and year.")
    if training["main_cell_id"].isna().any():
        raise ValueError("Some training rows have no weather cell.")
    if not (training["yield_t_ha"] > 0).all():
        raise ValueError("Some training rows have no yield above zero.")
    median = training.groupby(["region", "crop", "year"])["yield_t_ha"].transform("median")
    too_high = training[training["yield_t_ha"] / median >= max_yield_ratio]
    if len(too_high):
        reason = waiting_for_review(proposals, too_high["record_key"], ["yield_t_ha"], "yield")
        raise ValueError(
            f"{len(too_high)} yields are still at least {max_yield_ratio:g} times the median for "
            f"their region, crop and year after cleaning.{reason}"
        )


@step(
    "spatial_join",
    kind="transform",
    summary=(
        "Matches every parcel to its nearest weather cell, then builds the parcel-year table of "
        "contract crops and the farm-year training table from the cleaned survey and Foodhills "
        "data."
    ),
)
def spatial_join(ctx: RunContext, inputs: dict[str, Artifact], params: Params) -> StepResult:
    parcels = inputs["parcels"].frame
    registry_clean = inputs["farm_registry_clean"].frame
    survey_clean = inputs["farm_survey_clean"].frame
    foodhills_clean = inputs["foodhills_clean"].frame
    proposals = inputs[PROPOSALS_INPUT].frame

    with section(
        "match weather cells",
        "Matches each parcel to the nearest weather cell in its region, and stops if one is "
        "beyond the cell distance limit.",
    ):
        features = match_parcels_to_cells(
            parcels, registry_clean, inputs["grid"].frame, params["max_cell_distance_km"]
        )

    with section(
        "check farm locations",
        "Confirms that every farm lies within the farm-to-parcels distance limit of its own "
        "parcels, once swapped coordinates are fixed.",
    ):
        check_farms_near_parcels(
            registry_clean, parcels, proposals, params["max_farm_to_parcels_km"]
        )

    with section(
        "build parcel years",
        "Lists every parcel and year with a contract crop, declared or planned, with its soil, "
        "weather cell and previous crop.",
    ):
        parcel_years = build_parcel_years(
            inputs["crop_history"].frame, features, params["contract_crops"]
        )

    with section(
        "check yield template",
        "Confirms that every parcel in the yield submission template is in the parcel-years "
        "with the same area.",
    ):
        check_template(
            inputs["c1_template"].frame, parcel_years, params["template_area_tolerance_ha"]
        )

    with section(
        "build training table",
        "Joins the cleaned Finnish survey and Swedish Foodhills rows with farm details and "
        "area-weighted soil, slope and crop history.",
    ):
        training = build_training_table(parcel_years, survey_clean, foodhills_clean, registry_clean)

    with section(
        "check training table",
        "Stops the run on repeated farm, crop and year rows, rows without a weather cell or "
        "yield, or tenfold yields left after cleaning.",
    ):
        check_training_table(
            training,
            proposals,
            len(survey_clean) + len(foodhills_clean),
            params["max_yield_ratio_to_median"],
        )

    return StepResult(
        tables=[
            Artifact(name="parcel_features", layer="feature", frame=features),
            Artifact(name="parcel_year_contract", layer="feature", frame=parcel_years),
            Artifact(name="training_table", layer="feature", frame=training),
        ]
    )
