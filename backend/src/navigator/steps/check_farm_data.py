"""Step 2: check_farm_data. Rules R1 to R5 and their backtest, from notebooks/c1_clean.ipynb
sections 1 to 5.

The step only proposes. Fixes reach the cleaned tables in apply_approved, once they are approved
here by the rule policy or later by a reviewer.
"""

from collections.abc import Iterable, Mapping
from typing import Any

import numpy as np
import pandas as pd

from navigator.recipes.core import (
    DECISION_COLUMNS,
    PROPOSAL_COLUMNS,
    RULE_COLUMNS,
    Artifact,
    Params,
    RunContext,
    StepResult,
    section,
    step,
)

SURVEY_KEY = ["farm_id", "year", "crop"]

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


def rule_proposals(
    rule_id: str,
    issue_type: str,
    table: str,
    record_keys: Iterable[Any],
    field: str,
    old_values: Iterable[Any],
    new_values: Iterable[Any],
    evidence: Iterable[str],
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
    evidence = [
        f"{y} t/ha is {r:.1f}x the {c} {yr} median ({m:.2f}); /10 = {y / 10:.2f}"
        for y, r, c, yr, m in zip(
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
    evidence = [
        f"{v} kg N/ha is {r:.2f}x the farm/crop reference ({f:.1f}); shifted value {nv}"
        for v, r, f, nv in zip(
            hits["n_mineral_kg_ha"], ratio[hits.index], reference[hits.index], new, strict=True
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
    evidence = [
        f"survey {a} ha vs {d:.2f} ha in declared parcels (ratio {a / d:.2f})"
        for a, d in zip(hits["area_ha"], hits["decl_area_ha"], strict=True)
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
    evidence = [
        f"{o:.1f} of {d:.1f} ha on organic soil per soil map (~88% accurate)"
        for o, d in zip(hits["org_area"], hits["decl_area_ha"], strict=True)
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
    evidence = [
        f"lat {a} < lon {b}; parcel centroid at ({c:.3f}, {d:.3f})"
        for a, b, c, d in zip(
            hits["lat"], hits["lon"], hits["lat_parcels"], hits["lon_parcels"], strict=True
        )
    ]
    keys = "farm:" + hits["farm_id"]
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
                evidence,
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
                evidence,
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


def approval_comment(
    backtest: Mapping[str, Any], policy: Mapping[str, Any], dev_years: str
) -> str | None:
    """Why the rule policy approves this rule's fixes, or None when it does not."""
    rule_id = backtest["rule_id"]
    if rule_id in policy["deterministic_rules"]:
        return (
            f"Approved by rule policy. Rule {rule_id} is listed as deterministic: each record it "
            "finds has only one possible fix."
        )
    precision = backtest.get("precision")
    value_match = backtest.get("fixed_value_matches_truth")
    if precision is None or value_match is None:
        return None
    if precision < policy["min_precision"] or value_match < policy["min_value_match"]:
        return None
    tp = backtest["tp"]
    return (
        f"Approved by rule policy. On the {dev_years} answer key, {tp} of "
        f"{backtest['dev_flagged']} flagged records were real errors, and "
        f"{round(value_match * tp)} of {tp} fixed values matched the true value."
    )


def policy_decisions(
    proposals: pd.DataFrame,
    backtests: list[dict[str, Any]],
    policy: Mapping[str, Any],
    dev_years: str,
) -> pd.DataFrame:
    rows: list[dict[str, str]] = []
    for backtest in backtests:
        comment = approval_comment(backtest, policy, dev_years)
        if comment is None:
            continue
        fixes = proposals[
            proposals["rule_id"].eq(backtest["rule_id"]) & proposals["action"].eq("fix")
        ]
        for key in fixes["proposal_key"]:
            rows.append(
                {
                    "proposal_key": str(key),
                    "decision": "approve",
                    "reviewer": "Rule policy",
                    "comment": comment,
                }
            )
    return pd.DataFrame(rows, columns=DECISION_COLUMNS)


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
        "or flags, scores each rule on the 2023-24 answer key and approves fixes from rules "
        "that pass."
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
        "Scores each rule on the 2023 and 2024 answer key: how many flagged records were real "
        "errors, and whether the fixed values match.",
    ):
        labels = inputs["dev_issue_labels"].frame
        backtests = backtest_rules(proposals, survey, labels, params["backtest_value_tolerance"])
        validation = pd.DataFrame(backtests, columns=VALIDATION_COLUMNS)

    with section(
        "approve by policy",
        "Approves the fixes of rules that meet the auto-approve policy on the answer key, and "
        "of rules listed there as deterministic.",
    ):
        years = sorted(labels.loc[labels["table"].eq("farm_survey"), "year"].unique().tolist())
        decisions = policy_decisions(
            proposals, backtests, params["auto_approve"], " and ".join(str(y) for y in years)
        )

    return StepResult(
        tables=[Artifact(name="rule_validation", layer="result", frame=validation)],
        proposals=proposals,
        decisions=decisions,
        rules=rules_table(backtests, rule_descriptions(params)),
    )
