"""compare_inventory: our Scope 2 for electricity against the 2023 and 2024 answer inventories.

The difference is ours minus the answer. It comes from readings the checks could not repair
yet, from estimates that differ from the true readings, or from a different factor.
"""

from typing import Any, cast

import pandas as pd

from navigator.recipes.core import (
    METRIC_COLUMNS,
    Artifact,
    Params,
    RunContext,
    StepResult,
    section,
    step,
)

COMPARISON_COLUMNS = [
    "year",
    "basis",
    "ours_tco2e",
    "answer_tco2e",
    "difference_tco2e",
    "difference_pct",
]
BASIS_NAMES = {
    "location_based": "compare_inventory.location_based_difference_tco2e",
    "market_based": "compare_inventory.market_based_difference_tco2e",
}


def compare_years(
    site_years: pd.DataFrame, answers: pd.DataFrame, scopes: dict[str, str], category: str
) -> pd.DataFrame:
    """One row per year and basis in the answer inventory: ours, the answer and the gap."""
    ours = site_years.groupby("year")[list(scopes.values())].sum()
    rows: list[dict[str, Any]] = []
    for record in answers[answers["category"].eq(category)].to_dict("records"):
        if record["scope"] not in scopes:
            continue
        year, column = int(record["year"]), scopes[record["scope"]]
        if year not in ours.index:
            raise ValueError(f"There is no Scope 2 for electricity in {year} to compare.")
        ours_tco2e, answer = float(cast(float, ours.at[year, column])), float(record["tco2e"])
        rows.append(
            {
                "year": year,
                "basis": column.removesuffix("_tco2e"),
                "ours_tco2e": ours_tco2e,
                "answer_tco2e": answer,
                "difference_tco2e": ours_tco2e - answer,
                "difference_pct": (ours_tco2e - answer) / answer * 100,
            }
        )
    return pd.DataFrame(rows, columns=COMPARISON_COLUMNS)


def difference_metrics(comparison: pd.DataFrame, answer_tables: dict[int, str]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for record in comparison.to_dict("records"):
        year, basis = int(record["year"]), str(record["basis"])
        name = BASIS_NAMES[basis]
        scope = f"scope2_{basis.removesuffix('_based')}"
        rows.append(
            {
                "key": f"{name}|{year}",
                "name": name,
                "unit": "t CO2e",
                "value": float(record["difference_tco2e"]),
                "low": None,
                "high": None,
                "region": None,
                "crop": None,
                "site": None,
                "scenario": None,
                "ngfs_scenario": None,
                "period": str(year),
                "action_id": None,
                "lineage": [
                    {"table": "scope2_vs_answer", "filter": {"year": year, "basis": basis}},
                    {"table": "scope2_site_year", "filter": {"year": year}},
                    {
                        "table": answer_tables[year],
                        "filter": {"scope": scope, "category": "purchased_electricity"},
                    },
                ],
                "assumptions": [],
            }
        )
    return pd.DataFrame(rows, columns=METRIC_COLUMNS)


@step(
    "compare_inventory",
    kind="model",
    summary=(
        "Compares the Scope 2 for electricity from the cleaned readings with the 2023 and 2024 "
        "answer inventories, location-based and market-based, and shows the difference in tonnes "
        "and percent for each year."
    ),
)
def compare_inventory(ctx: RunContext, inputs: dict[str, Artifact], params: Params) -> StepResult:
    scopes: dict[str, str] = params["answer_scopes"]
    category: str = params["answer_category"]
    with section(
        "read answer inventories",
        "Reads the answer inventory of each year and keeps its purchased electricity lines.",
    ):
        answers = {name: inputs[name].frame for name in params["answer_tables"]}
        answer_tables = {
            int(cast(int, frame["year"].iat[0])): name
            for name, frame in answers.items()
            if len(frame)
        }

    with section(
        "compare totals",
        "Adds our Scope 2 over all sites for each year and basis and subtracts the answer.",
    ):
        comparison = compare_years(
            inputs["scope2_site_year"].frame,
            pd.concat(answers.values(), ignore_index=True),
            scopes,
            category,
        )

    return StepResult(
        tables=[Artifact(name="scope2_vs_answer", layer="result", frame=comparison)],
        metrics=difference_metrics(comparison, answer_tables),
    )
