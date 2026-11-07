"""Step 3: apply_approved. The cleaned tables from notebooks/c1_clean.ipynb sections 3 and 6.

Cleaned tables are always rebuilt as raw data plus the approved proposals, so a run can be
replayed from the same inputs and decisions.
"""

import pandas as pd

from navigator.recipes.core import (
    PROPOSALS_INPUT,
    Artifact,
    AssumptionUse,
    Params,
    RunContext,
    StepResult,
    section,
    step,
)
from navigator.steps.check_farm_data import SURVEY_KEY, declared_area, survey_with_declared_area

FOODHILLS_COLUMNS = {
    "odlar_id": "farm_id",
    "skördeår": "year",
    "gröda": "crop_sv",
    "areal_ha": "area_ha",
    "levererad_mängd_ton": "delivered_t",
    "kvävegiva_kg_ha": "n_mineral_kg_ha",
    "diesel_l_ha": "diesel_l_ha",
    "bevattnad": "irrigated_sv",
}
FOODHILLS_CROP = "Ärt (frysärt)"


def apply_fixes(records: pd.DataFrame, table: str, approved: pd.DataFrame) -> pd.DataFrame:
    """The records with each approved fix written over its field, and a count per record."""
    fixed = records.copy()
    fixes = approved[approved["table"].eq(table)]
    for field, field_fixes in fixes.groupby("field"):
        new = field_fixes.set_index("record_key")["new_value"].astype(float)
        rows = fixed["record_key"].isin(new.index)
        fixed.loc[rows, str(field)] = fixed.loc[rows, "record_key"].map(new)
    per_record = fixes.groupby("record_key").size()
    fixed["n_corrections"] = fixed["record_key"].map(per_record).fillna(0).astype(int)
    return fixed


def translate_foodhills(foodhills: pd.DataFrame, declared: pd.DataFrame) -> pd.DataFrame:
    """The Swedish Foodhills table with English column names, yield and record keys."""
    pea = foodhills.rename(columns=FOODHILLS_COLUMNS)
    if set(pea["crop_sv"]) != {FOODHILLS_CROP}:
        raise ValueError(f"The Foodhills file has crops other than {FOODHILLS_CROP}.")
    if not set(pea["irrigated_sv"]) <= {"ja", "nej"}:
        raise ValueError("The Foodhills file has irrigation answers other than ja and nej.")
    pea["crop"] = "pea"
    pea["irrigated"] = pea["irrigated_sv"].eq("ja")
    pea["yield_t_ha"] = pea["delivered_t"] / pea["area_ha"]
    pea["record_key"] = "foodhills:" + pea["farm_id"] + ":" + pea["year"].astype(str)
    pea = pea.merge(declared, on=SURVEY_KEY, how="left", validate="one_to_one")
    if pea.duplicated(["farm_id", "year"]).any():
        raise ValueError("The Foodhills file has more than one row for a farm and year.")
    return pea


def area_mismatch(records: pd.DataFrame, tolerance: float) -> "pd.Series[bool]":
    return (records["area_ha"] / records["decl_area_ha"] - 1).abs() >= tolerance


@step(
    "apply_approved",
    kind="transform",
    summary=(
        "Builds the cleaned Finnish farm survey, farm registry and Swedish Foodhills tables from "
        "the raw data plus the approved fixes, so every cleaned value traces back to a raw row "
        "or a decision."
    ),
)
def apply_approved(ctx: RunContext, inputs: dict[str, Artifact], params: Params) -> StepResult:
    proposals = inputs[PROPOSALS_INPUT].frame
    approved = proposals[proposals["status"].eq("approved") & proposals["action"].eq("fix")]
    tolerance: float = params["r3_area_tolerance"]

    with section(
        "add declared area",
        "Adds up the parcels each farm declared for each crop and year, so the survey can be "
        "compared with them.",
    ):
        declared = declared_area(inputs["crop_history"].frame, inputs["parcels"].frame)
        survey = survey_with_declared_area(inputs["farm_survey"].frame, declared)

    with section(
        "apply survey fixes",
        "Applies the approved fixes to the Finnish farm survey and marks records whose soil "
        "answer is flagged and not rejected.",
    ):
        survey_clean = apply_fixes(survey, "farm_survey", approved)
        soil_flags = proposals[
            proposals["rule_id"].eq("R4")
            & proposals["action"].eq("flag")
            & proposals["status"].ne("rejected")
        ]
        survey_clean["soil_misreport_flag"] = survey_clean["record_key"].isin(
            soil_flags["record_key"]
        )

    with section(
        "apply registry fixes",
        "Applies the approved fixes to the farm registry, such as latitudes and longitudes "
        "swapped back.",
    ):
        registry = inputs["farm_registry"].frame.copy()
        registry["record_key"] = "farm:" + registry["farm_id"]
        registry_clean = apply_fixes(registry, "farm_registry", approved)

    with section(
        "translate Foodhills",
        "Gives the Swedish Foodhills columns English names and works out yield as delivered "
        "tonnes divided by area.",
    ):
        foodhills_clean = translate_foodhills(inputs["foodhills"].frame, declared)

    with section(
        "check areas",
        "Confirms that survey and Foodhills areas match the declared parcels within the area "
        "tolerance, except where an area fix is not approved.",
    ):
        if area_mismatch(foodhills_clean, tolerance).any():
            raise ValueError("Some Foodhills areas differ from the farm's declared parcels.")
        # A reviewer may reject or not yet decide an area fix; only those records may differ.
        unfixed = proposals.loc[
            proposals["rule_id"].eq("R3") & proposals["status"].ne("approved"), "record_key"
        ]
        still_wrong = area_mismatch(survey_clean, tolerance) & ~survey_clean["record_key"].isin(
            unfixed
        )
        if still_wrong.any():
            raise ValueError(
                "Some survey areas differ from the declared parcels after the approved area fixes."
            )

    return StepResult(
        tables=[
            Artifact(name="farm_survey_clean", layer="clean", frame=survey_clean),
            Artifact(name="farm_registry_clean", layer="clean", frame=registry_clean),
            Artifact(name="foodhills_clean", layer="clean", frame=foodhills_clean),
        ],
        assumptions=[
            AssumptionUse(
                "apply_approved.r3_area_tolerance",
                "Allowed gap between survey area and declared area after fixes",
                tolerance,
                "share of the declared area",
                "recipe farm_climate_risk, apply_approved params",
            )
        ],
    )
