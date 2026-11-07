"""backtest_meters: scores the meter checks against the 2023-24 labelled issues.

The labelled issues of the energy file are the answer key. A check counts as right for a record
when it names the same record and the same kind of issue in a labelled year. The scoring is also
used by check_meters, so each rule carries its own backtest.
"""

import re
from typing import Any

import numpy as np
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

READINGS = "energy_meter_readings"
ALL_RULES = "all"
BACKTEST_COLUMNS = [
    "rule_id",
    "issue_types",
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
SOURCE = "recipe energy_meter_check, backtest_meters params"
KEY_YEAR = re.compile(r"^energy:[^:]+:(\d{4})-\d{2}:")


def key_year(record_key: str) -> int:
    found = KEY_YEAR.match(record_key)
    if found is None:
        raise ValueError(f"The record key {record_key!r} is not an energy reading key.")
    return int(found.group(1))


def labelled_issues(labels: pd.DataFrame) -> pd.DataFrame:
    """The labelled energy issues, with the true value as a number (empty where none)."""
    issues = labels[labels["table"].eq(READINGS)].copy()
    issues["true_value"] = pd.to_numeric(issues["true_value"], errors="coerce")
    return issues


def score(
    rule_id: str,
    proposals: pd.DataFrame,
    issues: pd.DataFrame,
    tolerance: float,
) -> dict[str, Any]:
    """One rule's proposals in the labelled years against the answer key.

    `proposals` are the proposals being scored. `issues` are the labelled issues of the kinds
    they look for. The same keys as a farm data rule's backtest, plus the kinds scored.
    """
    dev_years = set(issues["year"].astype(int))
    in_dev = proposals[[key_year(k) in dev_years for k in proposals["record_key"]]]
    flagged = set(zip(in_dev["record_key"], in_dev["issue_type"], strict=True))
    truth = set(zip(issues["record_key"], issues["issue_type"], strict=True))
    found = flagged & truth
    value_match: float | None = None
    fixes = in_dev[in_dev["action"].eq("fix")]
    matched = fixes.merge(
        issues[["record_key", "issue_type", "true_value"]], on=["record_key", "issue_type"]
    )
    if len(matched):
        close = np.isclose(
            matched["new_value"].astype(float),
            matched["true_value"].astype(float),
            rtol=tolerance,
            atol=0.0,
        )
        value_match = float(np.mean(close))
    return {
        "rule_id": rule_id,
        "issue_types": ", ".join(sorted(set(issues["issue_type"]))),
        "dev_labels": len(truth),
        "dev_flagged": len(flagged),
        "tp": len(found),
        "fp": len(flagged - truth),
        "fn": len(truth - found),
        "precision": len(found) / max(len(flagged), 1),
        "recall": len(found) / max(len(truth), 1),
        "fixed_value_matches_truth": value_match,
        "flagged_all_years": len(proposals),
    }


def score_each_rule(
    proposals: pd.DataFrame, labels: pd.DataFrame, tolerance: float
) -> list[dict[str, Any]]:
    """One row per rule or agent that proposed on the readings, then one for all of them.

    A rule is scored on the labelled kinds of issue it proposed. The last row scores every
    proposal against every label.
    """
    issues = labelled_issues(labels)
    own = proposals[proposals["table"].eq(READINGS)]
    rows = [
        score(
            str(rule_id),
            hits,
            issues[issues["issue_type"].isin(hits["issue_type"])],
            tolerance,
        )
        for rule_id, hits in own.groupby("rule_id")
    ]
    return [*rows, score(ALL_RULES, own, issues, tolerance)]


@step(
    "backtest_meters",
    kind="model",
    summary=(
        "Scores every data check and the fix proposer against the labelled energy issues of 2023 "
        "and 2024, by rule and for all of them together, so a reviewer sees what the "
        "checks catch and miss."
    ),
)
def backtest_meters(ctx: RunContext, inputs: dict[str, Artifact], params: Params) -> StepResult:
    tolerance: float = params["value_tolerance"]
    with section(
        "score proposals",
        "Counts the labelled issues each check found, missed or wrongly flagged in 2023 and "
        "2024, using the value tolerance.",
    ):
        scores = score_each_rule(
            inputs[PROPOSALS_INPUT].frame, inputs["dev_issue_labels"].frame, tolerance
        )
    return StepResult(
        tables=[
            Artifact(
                name="meter_backtest",
                layer="result",
                frame=pd.DataFrame(scores, columns=BACKTEST_COLUMNS),
            )
        ],
        assumptions=[
            AssumptionUse(
                "backtest_meters.value_tolerance",
                "How close a fixed reading must be to the true reading to count as a match",
                tolerance,
                "share of the true reading",
                SOURCE,
            )
        ],
    )
