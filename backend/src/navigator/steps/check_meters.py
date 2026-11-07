"""check_meters: rules M1 to M3 on the monthly energy meter readings, and their backtest.

A reading is judged against the same month in the other years of the same meter, so a seasonal
peak that repeats every year is never an error. The step only proposes and writes no decisions.
Fixes reach the cleaned readings in apply_approved_meters, once a reviewer has approved them.
"""

from collections.abc import Mapping
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
from navigator.steps.backtest_meters import READINGS, score_each_rule
from navigator.steps.check_farm_data import evidence_dict, rule_proposals

METER = ["site_id", "carrier"]
SOURCE = "recipe energy_meter_check, check_meters params"
VALIDATION_COLUMNS = ["rule_id", "description", "precision", "recall"]


def reading_key(site_id: str, year: int, month: int, carrier: str) -> str:
    return f"energy:{site_id}:{year}-{month:02d}:{carrier}"


def monthly_grid(readings: pd.DataFrame) -> pd.DataFrame:
    """One row per month from each meter's first reading to its last, empty where unread."""
    readings = readings.copy()
    readings["month_index"] = readings["year"] * 12 + readings["month"] - 1
    span = readings.groupby(METER)["month_index"].agg(["min", "max"]).reset_index()
    months = pd.DataFrame(
        [
            {"site_id": site, "carrier": carrier, "month_index": index}
            for site, carrier, first, last in zip(
                span["site_id"], span["carrier"], span["min"], span["max"], strict=True
            )
            for index in range(first, last + 1)
        ]
    )
    grid = months.merge(
        readings[[*METER, "month_index", "value", "unit"]],
        on=[*METER, "month_index"],
        how="left",
        validate="one_to_one",
    )
    grid["year"] = grid["month_index"] // 12
    grid["month"] = grid["month_index"] % 12 + 1
    grid["record_key"] = [
        reading_key(site, year, month, carrier)
        for site, year, month, carrier in zip(
            grid["site_id"], grid["year"], grid["month"], grid["carrier"], strict=True
        )
    ]
    return grid


def median_of_others(values: "pd.Series[float]") -> "pd.Series[float]":
    """For each year, the median of the other years' values. Empty values are skipped."""
    others = [values.drop(index).dropna() for index in values.index]
    return pd.Series([o.median() if len(o) else np.nan for o in others], index=values.index)


def same_month_reference(grid: pd.DataFrame, usable: "pd.Series[float]") -> "pd.Series[float]":
    """The median of the same month in the other years of the same meter."""
    return usable.groupby([grid["site_id"], grid["carrier"], grid["month"]]).transform(
        median_of_others
    )


def assess_readings(grid: pd.DataFrame, params: Params) -> pd.DataFrame:
    """The grid with each reading's unit check, spike check and estimate in MWh.

    A reading in kilowatt hours is first converted, then compared with its reference. The
    reference is built twice, the second time without the spikes of the first, so one spike does
    not lift the reference of the same month in other years.
    """
    assessed = grid.copy()
    meter_median = assessed.groupby(METER)["value"].transform("median")
    assessed["meter_median"] = meter_median
    assessed["unit_error"] = (meter_median > 0) & (
        assessed["value"] >= params["unit_error_min_ratio_to_meter_median"] * meter_median
    )
    assessed["mwh"] = assessed["value"].where(
        ~assessed["unit_error"], assessed["value"] / params["kwh_per_mwh"]
    )
    usable = assessed["mwh"]
    for _ in range(2):
        assessed["reference"] = same_month_reference(assessed, usable)
        assessed["ratio"] = assessed["mwh"] / assessed["reference"]
        assessed["spike"] = (assessed["reference"] > 0) & (
            assessed["ratio"] >= params["spike_min_ratio_to_same_month"]
        )
        usable = assessed["mwh"].where(~assessed["spike"])
    # The meter's level in a year, from the months that are neither spikes nor gaps. It lifts or
    # lowers the reference when the whole year runs above or below the other years.
    normal = assessed["ratio"].where(~assessed["spike"])
    assessed["year_level"] = normal.groupby(
        [assessed["site_id"], assessed["carrier"], assessed["year"]]
    ).transform("median")
    assessed["estimate"] = assessed["reference"] * assessed["year_level"].fillna(1.0)
    return assessed


def meter_proposals(
    rule_id: str,
    issue_type: str,
    rows: pd.DataFrame,
    old_values: "pd.Series[Any]",
    new_values: "pd.Series[float]",
    summaries: list[str],
    value_columns: Mapping[str, str],
    rule_params: Mapping[str, Any],
) -> pd.DataFrame:
    """One fix per row, or a flag where there is no value to propose."""
    evidence = [
        evidence_dict(
            summary,
            row["record_key"],
            {
                "kind": "rule",
                "rule_id": rule_id,
                "params": dict(rule_params),
                "group": {
                    "site_id": row["site_id"],
                    "carrier": row["carrier"],
                    "month": int(row["month"]),
                },
            },
            {name: row[column] for name, column in value_columns.items() if pd.notna(row[column])},
        )
        for summary, row in zip(summaries, rows.to_dict("records"), strict=True)
    ]
    proposals = rule_proposals(
        rule_id,
        issue_type,
        READINGS,
        rows["record_key"],
        "value",
        old_values,
        new_values.round(3),
        evidence,
        "fix",
    )
    proposals["action"] = np.where(new_values.notna(), "fix", "flag")
    return proposals


def find_missing_months(assessed: pd.DataFrame) -> pd.DataFrame:
    """M1: a month inside a meter's run of readings that has none, estimated from other years."""
    gaps = assessed[assessed["value"].isna()]
    summaries = [
        f"No reading for {key}; the same month in other years is {reference:.1f} MWh"
        if pd.notna(reference)
        else f"No reading for {key} and no other year to estimate it from"
        for key, reference in zip(gaps["record_key"], gaps["reference"], strict=True)
    ]
    return meter_proposals(
        "M1",
        "missing_record",
        gaps,
        pd.Series([None] * len(gaps), index=gaps.index, dtype=object),
        gaps["estimate"],
        summaries,
        {
            "reference_mwh": "reference",
            "year_level": "year_level",
            "estimate_mwh": "estimate",
        },
        {},
    )


def find_unit_errors(assessed: pd.DataFrame, params: Params) -> pd.DataFrame:
    """M2: a reading far above its meter's usual level, divided by the kilowatt hours per MWh."""
    hits = assessed[assessed["unit_error"]]
    summaries = [
        f"{value:g} is {value / median:.0f} times the meter's median of {median:.1f} MWh; "
        f"read as kWh it is {mwh:.3f} MWh"
        for value, median, mwh in zip(hits["value"], hits["meter_median"], hits["mwh"], strict=True)
    ]
    hits = hits.assign(ratio_to_meter_median=hits["value"] / hits["meter_median"])
    return meter_proposals(
        "M2",
        "unit_error",
        hits,
        hits["value"],
        hits["mwh"],
        summaries,
        {
            "reading": "value",
            "meter_median_mwh": "meter_median",
            "ratio_to_meter_median": "ratio_to_meter_median",
            "converted_mwh": "mwh",
        },
        {
            "unit_error_min_ratio_to_meter_median": params["unit_error_min_ratio_to_meter_median"],
            "kwh_per_mwh": params["kwh_per_mwh"],
        },
    )


def find_spikes(assessed: pd.DataFrame, params: Params) -> pd.DataFrame:
    """M3: a reading, after any unit conversion, far above the same month in other years."""
    hits = assessed[assessed["spike"]]
    summaries = [
        f"{mwh:.1f} MWh is {ratio:.1f} times the same month in other years ({reference:.1f}); "
        f"estimate {estimate:.1f}"
        for mwh, ratio, reference, estimate in zip(
            hits["mwh"], hits["ratio"], hits["reference"], hits["estimate"], strict=True
        )
    ]
    return meter_proposals(
        "M3",
        "meter_spike",
        hits,
        hits["value"],
        hits["estimate"],
        summaries,
        {
            "reading_mwh": "mwh",
            "reference_mwh": "reference",
            "ratio_to_reference": "ratio",
            "estimate_mwh": "estimate",
        },
        {"spike_min_ratio_to_same_month": params["spike_min_ratio_to_same_month"]},
    )


def rule_descriptions(params: Params) -> dict[str, str]:
    return {
        "M1": (
            "Fills a month with no reading, between a meter's first and last reading, with the "
            "median of the same month in other years, scaled to the meter's level that year."
        ),
        "M2": (
            "Divides a reading by "
            f"{params['kwh_per_mwh']:g} when it is at least "
            f"{params['unit_error_min_ratio_to_meter_median']:g} times the meter's median, which "
            "means kilowatt hours were typed in the megawatt hour column."
        ),
        "M3": (
            "Replaces a reading with the estimate for its month when it is at least "
            f"{params['spike_min_ratio_to_same_month']:g} times the median of the same month in "
            "other years. A seasonal peak that repeats every year is not a spike."
        ),
    }


def rules_table(backtests: list[dict[str, Any]], descriptions: Mapping[str, str]) -> pd.DataFrame:
    rows = [
        {
            "rule_id": backtest["rule_id"],
            "version": 1,
            "description": descriptions[backtest["rule_id"]],
            "author": "Team",
            "backtest": {
                name: value
                for name, value in backtest.items()
                if name not in ("rule_id", "issue_types")
            },
        }
        for backtest in backtests
        if backtest["rule_id"] in descriptions
    ]
    return pd.DataFrame(rows, columns=RULE_COLUMNS)


@step(
    "check_meters",
    kind="propose",
    summary=(
        "Checks monthly energy meter readings with rules M1 to M3 for missing months, wrong units "
        "and spikes against the same month in other years, and scores each rule on the 2023-24 "
        "known issues. A person decides every fix."
    ),
)
def check_meters(ctx: RunContext, inputs: dict[str, Artifact], params: Params) -> StepResult:
    with section(
        "build monthly series",
        "Lines up each meter's readings month by month, so a missing month shows as an empty row.",
    ):
        grid = monthly_grid(inputs[READINGS].frame)

    with section(
        "assess readings",
        "Compares each reading with the same month in other years, using the unit and spike "
        "ratio limits, and estimates what a bad reading should be.",
    ):
        assessed = assess_readings(grid, params)

    with section(
        "M1 missing months",
        "Finds months without a reading inside a meter's run and proposes an estimate from the "
        "same month in other years.",
    ):
        m1 = find_missing_months(assessed)

    with section(
        "M2 wrong unit",
        "Finds readings typed in kilowatt hours, using the unit ratio limit against the "
        "meter's median, and proposes the value in megawatt hours.",
    ):
        m2 = find_unit_errors(assessed, params)

    with section(
        "M3 spikes",
        "Finds readings far above the same month in other years, using the spike ratio limit, "
        "and proposes the estimate instead.",
    ):
        m3 = find_spikes(assessed, params)

    proposals = pd.DataFrame(
        [*m1.to_dict("records"), *m2.to_dict("records"), *m3.to_dict("records")],
        columns=PROPOSAL_COLUMNS,
    )

    with section(
        "backtest rules",
        "Scores each rule on the 2023 and 2024 known issues: how many flagged readings were real "
        "errors, and whether the fixed values match.",
    ):
        backtests = score_each_rule(
            proposals, inputs["dev_issue_labels"].frame, params["backtest_value_tolerance"]
        )

    descriptions = rule_descriptions(params)
    rules = rules_table(backtests, descriptions)
    validation = pd.DataFrame(
        [
            {
                "rule_id": rule_id,
                "description": descriptions[rule_id],
                "precision": backtest["precision"],
                "recall": backtest["recall"],
            }
            for backtest in backtests
            if (rule_id := backtest["rule_id"]) in descriptions
        ],
        columns=VALIDATION_COLUMNS,
    )
    return StepResult(
        tables=[
            Artifact(name="rule_validation", layer="result", frame=validation),
            Artifact(name="meter_assessment", layer="feature", frame=assessed),
        ],
        proposals=proposals,
        decisions=None,
        rules=rules,
        assumptions=[
            AssumptionUse(
                "check_meters.unit_error_min_ratio_to_meter_median",
                "Smallest reading, compared with the meter's median, that counts as a unit error",
                params["unit_error_min_ratio_to_meter_median"],
                "times the meter's median",
                SOURCE,
            ),
            AssumptionUse(
                "check_meters.kwh_per_mwh",
                "Kilowatt hours in one megawatt hour",
                params["kwh_per_mwh"],
                "kWh per MWh",
                SOURCE,
            ),
            AssumptionUse(
                "check_meters.spike_min_ratio_to_same_month",
                "Smallest reading, compared with the same month in other years, that counts "
                "as a spike",
                params["spike_min_ratio_to_same_month"],
                "times the median of the same month",
                SOURCE,
            ),
            AssumptionUse(
                "check_meters.backtest_value_tolerance",
                "How close a fixed reading must be to the true reading to count as a match",
                params["backtest_value_tolerance"],
                "share of the true reading",
                SOURCE,
            ),
        ],
    )
