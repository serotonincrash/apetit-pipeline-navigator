"""Step 2: check_farm_data. Rules R1 to R5 and their backtest, from notebooks/c1_clean.ipynb
sections 1 to 5.

The step only proposes and writes no decisions. Fixes reach the cleaned tables in apply_approved,
once a reviewer has approved them.
"""

from collections.abc import Iterable, Mapping
from typing import Any

import numpy as np
import pandas as pd

from navigator.recipes.core import (
    PROPOSAL_COLUMNS,
    RULE_COLUMNS,
    Artifact,
    AssumptionUse,
    Params,
    RunContext,
    StepResult,
    section,
    step,
)

SURVEY_KEY = ["farm_id", "year", "crop"]
SOURCE_CHECK = "recipe farm_climate_risk, check_farm_data params"

VALIDATION_COLUMNS = [
    "rule_id",
    "issue_type",
    "dev_labels",
    "dev_flagged",
    "tp",
    "fp",
    "fn",
    "precision",
    "recall",
    "fixed_value_matches_truth",
    "flagged_all_years",
]


def declared_area(crop_history: pd.DataFrame, parcels: pd.DataFrame) -> pd.DataFrame:
    """Declared parcel area and its organic part (soil map) per farm, year and crop."""
    declared = crop_history.query("status == 'declared'").merge(
        parcels, on=["parcel_id", "farm_id"], how="left", validate="many_to_one"
    )
    declared["org_area"] = np.where(
        declared["soil_class_soilmap"].eq("organic"), declared["area_ha"], 0.0
    )
    by_crop = (
        declared.groupby(SURVEY_KEY)
        .agg(decl_area_ha=("area_ha", "sum"), org_area=("org_area", "sum"))
        .reset_index()
    )
    by_crop["organic_share_soilmap"] = by_crop["org_area"] / by_crop["decl_area_ha"]
    return by_crop


def survey_with_declared_area(farm_survey: pd.DataFrame, declared: pd.DataFrame) -> pd.DataFrame:
    """The Finnish survey with record keys and the declared area of each row's crop."""
    survey = farm_survey.copy()
    survey["record_key"] = "farm_survey:" + survey["survey_id"]
    survey = survey.merge(declared, on=SURVEY_KEY, how="left", validate="one_to_one")
    if survey["decl_area_ha"].isna().any():
        raise ValueError("Some farm survey rows have no declared parcels for their crop and year.")
    return survey


def evidence_dict(
    summary: str, record_key: str, query: dict[str, Any], values: dict[str, float]
) -> dict[str, Any]:
    """Evidence as stored on a proposal. Values are plain floats so the dict serialises to JSON."""
    return {
        "summary": summary,
        "record_keys": [record_key],
        "query": query,
        "values": {name: float(value) for name, value in values.items()},
    }


def rule_proposals(
    rule_id: str,
    issue_type: str,
    table: str,
    record_keys: Iterable[Any],
    field: str,
    old_values: Iterable[Any],
    new_values: Iterable[Any],
    evidence: Iterable[dict[str, Any]],
    action: str,
) -> pd.DataFrame:
    proposals = pd.DataFrame(
        {
            "rule_id": rule_id,
            "issue_type": issue_type,
            "table": table,
            "record_key": list(record_keys),
            "field": field,
            "old_value": list(old_values),
            "new_value": list(new_values),
            "action": action,
            "evidence": list(evidence),
        }
    )
    # The key is the same on every run, so a decision carries over to the next run.
    proposals["proposal_key"] = rule_id + "|" + proposals["record_key"] + "|" + field
    proposals["explanation"] = ""
    proposals["proposer"] = f"rule {rule_id}"
    return proposals[PROPOSAL_COLUMNS]


def find_tenfold_yields(survey: pd.DataFrame, max_ratio: float) -> pd.DataFrame:
    """R1: yields far above the crop and year median, fixed by dividing by 10."""
    median = survey.groupby(["crop", "year"])["yield_t_ha"].transform("median")
    ratio = survey["yield_t_ha"] / median
    hits = survey[ratio > max_ratio]
    query = {
        "kind": "rule",
        "rule_id": "R1",
        "params": {"r1_yield_max_ratio_to_median": max_ratio},
    }
    evidence = [
        evidence_dict(
            f"{y} t/ha is {r:.1f}x the {c} {yr} median ({m:.2f}); /10 = {y / 10:.2f}",
            key,
            {**query, "group": {"crop": c, "year": int(yr)}},
            {"yield_t_ha": y, "median": m, "ratio_to_median": r},
        )
        for key, y, r, c, yr, m in zip(
            hits["record_key"],
            hits["yield_t_ha"],
            ratio[hits.index],
            hits["crop"],
            hits["year"],
            median[hits.index],
            strict=True,
        )
    ]
    return rule_proposals(
        "R1",
        "outlier_implausible",
        "farm_survey",
        hits["record_key"],
        "yield_t_ha",
        hits["yield_t_ha"],
        (hits["yield_t_ha"] / 10).round(3),
        evidence,
        "fix",
    )


def find_shifted_nitrogen(
    survey: pd.DataFrame, ratio_high: float, ratio_low: float
) -> pd.DataFrame:
    """R2: nitrogen rates far from the farm's usual rate for the crop, shifted by 10."""
    rate = survey["n_mineral_kg_ha"]
    farm_median = survey.groupby(["farm_id", "crop"])["n_mineral_kg_ha"].transform("median")
    crop_median = survey.groupby("crop")["n_mineral_kg_ha"].transform("median")
    # Farms that usually apply no nitrogen to a crop are compared with the crop's usual rate.
    reference = farm_median.where(farm_median > 0, crop_median)
    ratio = rate / reference
    high = ratio > ratio_high
    low = (ratio < ratio_low) & (rate > 0)
    hits = survey[high | low]
    new = np.where(high[hits.index], hits["n_mineral_kg_ha"] / 10, hits["n_mineral_kg_ha"] * 10)
    new = new.round(1)
    query = {
        "kind": "rule",
        "rule_id": "R2",
        "params": {"r2_nitrogen_ratio_high": ratio_high, "r2_nitrogen_ratio_low": ratio_low},
    }
    evidence = [
        evidence_dict(
            f"{v} kg N/ha is {r:.2f}x the farm/crop reference ({f:.1f}); shifted value {nv}",
            key,
            {**query, "group": {"farm_id": fid, "crop": c}},
            {"n_mineral_kg_ha": v, "reference": f, "ratio_to_reference": r, "shifted_value": nv},
        )
        for key, fid, c, v, r, f, nv in zip(
            hits["record_key"],
            hits["farm_id"],
            hits["crop"],
            hits["n_mineral_kg_ha"],
            ratio[hits.index],
            reference[hits.index],
            new,
            strict=True,
        )
    ]
    return rule_proposals(
        "R2",
        "decimal_shift",
        "farm_survey",
        hits["record_key"],
        "n_mineral_kg_ha",
        hits["n_mineral_kg_ha"],
        new,
        evidence,
        "fix",
    )


def find_area_mismatches(survey: pd.DataFrame, tolerance: float) -> pd.DataFrame:
    """R3: survey areas that differ from the declared parcels, replaced by the parcel total."""
    ratio: pd.Series[float] = survey["area_ha"] / survey["decl_area_ha"]
    hits = survey[(ratio - 1).abs() > tolerance]
    query = {"kind": "rule", "rule_id": "R3", "params": {"r3_area_tolerance": tolerance}}
    evidence = [
        evidence_dict(
            f"survey {a} ha vs {d:.2f} ha in declared parcels (ratio {a / d:.2f})",
            key,
            query,
            {"area_ha": a, "declared_area_ha": d, "ratio_to_declared": a / d},
        )
        for key, a, d in zip(hits["record_key"], hits["area_ha"], hits["decl_area_ha"], strict=True)
    ]
    return rule_proposals(
        "R3",
        "area_mismatch",
        "farm_survey",
        hits["record_key"],
        "area_ha",
        hits["area_ha"],
        hits["decl_area_ha"].round(2),
        evidence,
        "fix",
    )


def find_soil_misreports(survey: pd.DataFrame, organic_share_threshold: float) -> pd.DataFrame:
    """R4: mineral soil reported where the soil map shows organic soil. Flags only."""
    hits = survey[
        (survey["organic_share_soilmap"] >= organic_share_threshold)
        & survey["soil_type_reported"].eq("Mineral soil")
    ]
    query = {
        "kind": "rule",
        "rule_id": "R4",
        "params": {"r4_organic_share_threshold": organic_share_threshold},
    }
    evidence = [
        evidence_dict(
            f"{o:.1f} of {d:.1f} ha on organic soil per soil map (~88% accurate)",
            key,
            query,
            {"organic_area_ha": o, "declared_area_ha": d, "organic_share": s},
        )
        for key, o, d, s in zip(
            hits["record_key"],
            hits["org_area"],
            hits["decl_area_ha"],
            hits["organic_share_soilmap"],
            strict=True,
        )
    ]
    return rule_proposals(
        "R4",
        "soil_misreport",
        "farm_survey",
        hits["record_key"],
        "soil_type_reported",
        hits["soil_type_reported"],
        [f"organic share {s:.2f} (soil map)" for s in hits["organic_share_soilmap"]],
        evidence,
        "flag",
    )


def find_swapped_coordinates(registry: pd.DataFrame, parcels: pd.DataFrame) -> pd.DataFrame:
    """R5: farms whose latitude is below their longitude, which no farm in the package has."""
    centroid = parcels.groupby("farm_id")[["lat", "lon"]].median()
    hits = registry[registry["lat"] < registry["lon"]].join(
        centroid, on="farm_id", rsuffix="_parcels"
    )
    keys = "farm:" + hits["farm_id"]
    query: dict[str, Any] = {"kind": "rule", "rule_id": "R5", "params": {}}

    def evidence() -> list[dict[str, Any]]:
        return [
            evidence_dict(
                f"lat {a} < lon {b}; parcel centroid at ({c:.3f}, {d:.3f})",
                key,
                query,
                {"lat": a, "lon": b, "parcel_lat": c, "parcel_lon": d},
            )
            for key, a, b, c, d in zip(
                keys,
                hits["lat"],
                hits["lon"],
                hits["lat_parcels"],
                hits["lon_parcels"],
                strict=True,
            )
        ]

    return pd.concat(
        [
            rule_proposals(
                "R5",
                "coordinate_swap",
                "farm_registry",
                keys,
                "lat",
                hits["lat"],
                hits["lon"],
                evidence(),
                "fix",
            ),
            rule_proposals(
                "R5",
                "coordinate_swap",
                "farm_registry",
                keys,
                "lon",
                hits["lon"],
                hits["lat"],
                evidence(),
                "fix",
            ),
        ]
    )


def backtest_rules(
    proposals: pd.DataFrame,
    survey: pd.DataFrame,
    labels: pd.DataFrame,
    tolerance: Mapping[str, float],
) -> list[dict[str, Any]]:
    """Each rule's hits in the labelled years against the answer key, one dict per rule.

    Rules on tables the answer key does not cover get only their number of flagged records.
    """
    truth_all = labels[labels["table"].eq("farm_survey")].copy()
    truth_all["record_key"] = truth_all["record_key"].astype(str)
    dev_years = sorted(truth_all["year"].unique().tolist())
    year_of = survey.set_index("record_key")["year"]

    results: list[dict[str, Any]] = []
    on_survey = proposals["table"].eq("farm_survey")
    for rule_id, rule_hits in proposals[on_survey].groupby("rule_id"):
        issue_type = str(rule_hits["issue_type"].iat[0])
        dev = rule_hits[rule_hits["record_key"].map(year_of).isin(dev_years)]
        truth = truth_all[truth_all["issue_type"].eq(issue_type)]
        flagged = set(dev["record_key"])
        true_keys = set(truth["record_key"])
        tp_keys = flagged & true_keys
        tp, fp, fn = len(tp_keys), len(flagged - tp_keys), len(true_keys - tp_keys)
        value_match: float | None = None
        if rule_hits["action"].iat[0] == "fix" and tp:
            matched = dev[dev["record_key"].isin(tp_keys)].merge(
                truth[["record_key", "true_value"]], on="record_key"
            )
            close = np.isclose(
                matched["new_value"].astype(float),
                matched["true_value"].astype(float),
                rtol=tolerance["relative"],
                atol=tolerance["absolute"],
            )
            value_match = float(np.mean(close))
        results.append(
            {
                "rule_id": str(rule_id),
                "issue_type": issue_type,
                "dev_labels": len(truth),
                "dev_flagged": len(dev),
                "tp": tp,
                "fp": fp,
                "fn": fn,
                "precision": tp / max(tp + fp, 1),
                "recall": tp / max(tp + fn, 1),
                "fixed_value_matches_truth": value_match,
                "flagged_all_years": len(rule_hits),
            }
        )
    for rule_id, rule_hits in proposals[~on_survey].groupby("rule_id"):
        results.append(
            {
                "rule_id": str(rule_id),
                "issue_type": str(rule_hits["issue_type"].iat[0]),
                "flagged_all_years": int(rule_hits["record_key"].nunique()),
            }
        )
    return results


def rule_descriptions(params: Params) -> dict[str, str]:
    return {
        "R1": (
            "Divides a yield by 10 when it is more than "
            f"{params['r1_yield_max_ratio_to_median']:g} times the median yield for the same "
            "crop and year."
        ),
        "R2": (
            "Divides a nitrogen rate by 10 when it is more than "
            f"{params['r2_nitrogen_ratio_high']:g} times the farm's usual rate for the crop, and "
            f"multiplies it by 10 when it is less than {params['r2_nitrogen_ratio_low']:g} times."
        ),
        "R3": (
            "Replaces a survey area with the total of the farm's declared parcels when the two "
            f"differ by more than {params['r3_area_tolerance'] * 100:.1f}%."
        ),
        "R4": (
            "Flags a record for review when the farmer reported mineral soil but the soil map puts "
            f"at least {params['r4_organic_share_threshold'] * 100:.1f}% of the crop's area on "
            "organic soil."
        ),
        "R5": (
            "Swaps a farm's latitude and longitude back when the latitude is smaller than the "
            "longitude, which no farm in Finland or Sweden can have."
        ),
    }


def rules_table(backtests: list[dict[str, Any]], descriptions: Mapping[str, str]) -> pd.DataFrame:
    rows = [
        {
            "rule_id": backtest["rule_id"],
            "version": 1,
            "description": descriptions[backtest["rule_id"]],
            "author": "Team",
            # Measures a rule has no answer key for are None, so the backtest stores as JSON.
            "backtest": {
                column: backtest.get(column)
                for column in VALIDATION_COLUMNS
                if column not in ("rule_id", "issue_type")
            },
        }
        for backtest in backtests
    ]
    return pd.DataFrame(rows, columns=RULE_COLUMNS)


@step(
    "check_farm_data",
    kind="propose",
    summary=(
        "Checks the Finnish farm survey and the farm registry with rules R1 to R5, proposes fixes "
        "or flags, and scores each rule on the 2023-24 known issues. A person decides every fix."
    ),
)
def check_farm_data(ctx: RunContext, inputs: dict[str, Artifact], params: Params) -> StepResult:
    with section(
        "add declared area",
        "Adds up the parcels each farm declared for each crop and year, so the survey can be "
        "compared with them.",
    ):
        declared = declared_area(inputs["crop_history"].frame, inputs["parcels"].frame)
        survey = survey_with_declared_area(inputs["farm_survey"].frame, declared)

    with section(
        "R1 yields",
        "Finds yields typed 10 times too large, using the yield ratio limit against the median "
        "for the same crop and year.",
    ):
        r1 = find_tenfold_yields(survey, params["r1_yield_max_ratio_to_median"])

    with section(
        "R2 nitrogen",
        "Finds nitrogen rates with a misplaced decimal point, using the nitrogen ratio limits "
        "against the farm's usual rate for that crop.",
    ):
        r2 = find_shifted_nitrogen(
            survey, params["r2_nitrogen_ratio_high"], params["r2_nitrogen_ratio_low"]
        )

    with section(
        "R3 area",
        "Finds survey areas that differ from the declared parcels by more than the area "
        "tolerance, and proposes the parcel total instead.",
    ):
        r3 = find_area_mismatches(survey, params["r3_area_tolerance"])

    with section(
        "R4 soil",
        "Flags mineral soil answers where the soil map puts at least the organic share "
        "threshold of the crop's area on organic soil.",
    ):
        r4 = find_soil_misreports(survey, params["r4_organic_share_threshold"])

    with section(
        "R5 coordinates",
        "Finds farms whose latitude and longitude are swapped, with the farm's parcel locations "
        "as evidence.",
    ):
        r5 = find_swapped_coordinates(inputs["farm_registry"].frame, inputs["parcels"].frame)

    proposals = pd.concat([r1, r2, r3, r4, r5], ignore_index=True)

    with section(
        "backtest rules",
        "Scores each rule on the 2023 and 2024 known issues: how many flagged records were real "
        "errors, and whether the fixed values match.",
    ):
        labels = inputs["dev_issue_labels"].frame
        backtests = backtest_rules(proposals, survey, labels, params["backtest_value_tolerance"])
        validation = pd.DataFrame(backtests, columns=VALIDATION_COLUMNS)

    return StepResult(
        tables=[Artifact(name="rule_validation", layer="result", frame=validation)],
        proposals=proposals,
        decisions=None,
        rules=rules_table(backtests, rule_descriptions(params)),
        assumptions=[
            AssumptionUse(
                "check_farm_data.r1_yield_max_ratio_to_median",
                "Highest yield compared with the median",
                params["r1_yield_max_ratio_to_median"],
                "times the median yield",
                SOURCE_CHECK,
            ),
            AssumptionUse(
                "check_farm_data.r2_nitrogen_ratio_high",
                "Highest nitrogen rate compared with the farm's usual rate",
                params["r2_nitrogen_ratio_high"],
                "times the usual rate",
                SOURCE_CHECK,
            ),
            AssumptionUse(
                "check_farm_data.r2_nitrogen_ratio_low",
                "Lowest nitrogen rate compared with the farm's usual rate",
                params["r2_nitrogen_ratio_low"],
                "times the usual rate",
                SOURCE_CHECK,
            ),
            AssumptionUse(
                "check_farm_data.r3_area_tolerance",
                "Allowed gap between survey area and declared area",
                params["r3_area_tolerance"],
                "share of the declared area",
                SOURCE_CHECK,
            ),
            AssumptionUse(
                "check_farm_data.r4_organic_share_threshold",
                "Organic share of a crop's area that makes a conventional soil report doubtful",
                params["r4_organic_share_threshold"],
                "share of the crop's area",
                SOURCE_CHECK,
            ),
            AssumptionUse(
                "check_farm_data.backtest_value_tolerance",
                "How close a fixed value must be to the true value to count as a match",
                params["backtest_value_tolerance"],
                "share and absolute gap",
                SOURCE_CHECK,
            ),
        ],
    )
