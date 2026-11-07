"""apply_approved_meters: the cleaned energy readings, rebuilt as raw readings plus approved fixes.

A month with no reading is filled only from an approved fix. A rejected or undecided proposal
leaves the reading as delivered, or the month empty.
"""

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
from navigator.steps.backtest_meters import READINGS
from navigator.steps.check_meters import reading_key

CLEAN_COLUMNS = [
    "record_key",
    "site_id",
    "year",
    "month",
    "carrier",
    "value",
    "unit",
    "raw_value",
    "n_corrections",
]
# A unit fix is applied first, so a later estimate for the same reading replaces it.
APPLY_FIRST = "unit_error"


def approved_value_fixes(proposals: pd.DataFrame) -> pd.DataFrame:
    """Approved fixes to a reading's value, unit fixes first. Anything else cannot be applied."""
    approved = proposals[proposals["status"].eq("approved") & proposals["action"].eq("fix")]
    approved = approved[approved["table"].eq(READINGS)]
    other_fields = approved[approved["field"].ne("value")]
    if len(other_fields):
        raise ValueError(
            f"An approved fix changes {other_fields['field'].iat[0]}, but only the value of a "
            "reading can change."
        )
    first = approved["issue_type"].ne(APPLY_FIRST)
    return approved.assign(after_unit_fix=first).sort_values(["after_unit_fix", "proposal_key"])


def new_months(fixes: pd.DataFrame, readings: pd.DataFrame) -> pd.DataFrame:
    """Rows for approved fixes that name a month the raw file has no row for."""
    known = set(readings["record_key"])
    rows: list[dict[str, object]] = []
    units = readings.groupby(["site_id", "carrier"])["unit"].first()
    for key in dict.fromkeys(fixes["record_key"]):
        if key in known:
            continue
        # Keys are energy:<site>:<year>-<month>:<carrier>.
        _, site_id, month_text, carrier = key.split(":")
        year, month = (int(part) for part in month_text.split("-"))
        rows.append(
            {
                "record_key": key,
                "site_id": site_id,
                "year": year,
                "month": month,
                "carrier": carrier,
                "value": float("nan"),
                "unit": units[(site_id, carrier)],
                "raw_value": float("nan"),
                "n_corrections": 0,
            }
        )
    return pd.DataFrame(rows, columns=CLEAN_COLUMNS)


@step(
    "apply_approved_meters",
    kind="transform",
    summary=(
        "Builds the cleaned energy readings from the raw readings plus the approved fixes, and "
        "adds a month only when an approved fix fills it, so every cleaned value traces back to a "
        "meter reading or a decision."
    ),
)
def apply_approved_meters(
    ctx: RunContext, inputs: dict[str, Artifact], params: Params
) -> StepResult:
    raw = inputs[READINGS].frame
    with section(
        "key the readings",
        "Gives each raw reading its record key and keeps the delivered value beside the "
        "cleaned one.",
    ):
        readings = raw.assign(
            record_key=[
                reading_key(site, year, month, carrier)
                for site, year, month, carrier in zip(
                    raw["site_id"], raw["year"], raw["month"], raw["carrier"], strict=True
                )
            ],
            raw_value=raw["value"],
            n_corrections=0,
        )[CLEAN_COLUMNS]

    with section(
        "fill approved gaps",
        "Adds a row for each month with no reading that has an approved estimate, and no row "
        "for any other gap.",
    ):
        fixes = approved_value_fixes(inputs[PROPOSALS_INPUT].frame)
        filled = new_months(fixes, readings)
        cleaned = pd.concat([readings, filled], ignore_index=True) if len(filled) else readings

    with section(
        "apply approved fixes",
        "Writes each approved value over the delivered one and counts the corrections made to "
        "each reading.",
    ):
        cleaned = cleaned.set_index("record_key")
        for key, new_value in zip(fixes["record_key"], fixes["new_value"], strict=True):
            cleaned.loc[key, "value"] = float(new_value)
            cleaned.loc[key, "n_corrections"] += 1
        cleaned = cleaned.reset_index()[CLEAN_COLUMNS].sort_values(
            ["site_id", "carrier", "year", "month"], ignore_index=True
        )

    return StepResult(tables=[Artifact(name="energy_clean", layer="clean", frame=cleaned)])
