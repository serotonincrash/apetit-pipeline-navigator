"""Step 10: compare_actions, from sections 1 to 6 of `notebooks/c4_actions.ipynb`.

Each approved action changes one assumption about the future on a copy of the parcel seasons. The
copy is simulated with the same random draws as the no-action case and priced against the same
contracted volume, premiums and import factors, so the difference is the action's effect alone.

Prices come from the `premiums` and `import_factors` tables of step 9, so a price or premium
override queued on step 9 reaches this step too. The number of simulated outcomes and the seed
are params of this step, set in the recipe from the same constants as step 8; a check against
step 9's no-action cost stops the run if they ever differ.

The step never reads the weather, so it cannot move the sowing date. An action whose override it
cannot run is refused with a reason.

The analysis modules are not typed yet (see pyproject.toml), so calls into them carry a pyright
ignore for their untyped parameters.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from navigator.analysis import actions as ac
from navigator.analysis import climateproj as cp
from navigator.analysis import riskprice as rp
from navigator.analysis import yieldmodel as ym
from navigator.recipes.core import (
    ACTION_OPTION_COLUMNS,
    Artifact,
    AssumptionUse,
    Params,
    RunContext,
    StepResult,
    section,
    step,
)
from navigator.steps.fit_yield_model import MODEL_ASSUMPTIONS, metric_frame, metric_key
from navigator.steps.price_risk import (
    PREMIUM_LIFT,
    PREMIUM_YEARS,
    PRICE_YEAR,
    climate_period,
    unit_assumptions,
)
from navigator.steps.project_yields import CONTRACT_YEAR, TREND_YEAR

SIMULATED_OUTCOMES = "compare_actions.simulated_outcomes"
SIMULATION_SEED = "compare_actions.simulation_seed"

# The override types this step can run. Moving the sowing date needs the weather, which this
# step does not read.
RUNNABLE = {"relocate_area", "set_irrigated", "scale_feature"}
SCENARIOS = ["baseline", *cp.SCENARIOS]
# A rebuilt no-action cost may differ from step 9's by this much, in euros, and still match.
NO_ACTION_TOLERANCE_EUR = 0.01
PARCEL_COLUMNS = ["farm_id", "scenario", "year", "parcel_area_ha", "log_yield"]

ACTION_RESULT_COLUMNS = [
    "action_id",
    "name",
    "scenario",
    "expected_cost_no_action_eur",
    "expected_cost_with_action_eur",
    "risk_removed_eur",
    "one_in_ten_removed_eur",
    "import_tco2e_removed",
    "action_cost_eur",
    "net_benefit_eur",
    "break_even_cost_eur",
    "confidence",
    "climate_driven_removed_eur",
]
NOT_RUN_COLUMNS = ["action_id", "name", "why_not"]
LOSS_DRIVER_COLUMNS = ["unit", "region", "crop", "scenario", "driver", "yield_effect_pct"]

# The model feature behind each weather driver, and the words the app shows for it.
DRIVERS = {
    "drought_stage": "drought in the sensitive stage",
    "drought_early": "early drought",
    "heat_days_27": "heat at flowering",
    "harvest_rain_14_mm": "rain before harvest",
    "may_tmean_c": "warm May (pollen beetle)",
    "blight_days": "blight weather",
    "waterlog_clay": "waterlogging on clay",
    "immature_gap": "failure to mature",
    "drought_x_irr": "irrigation offset",
    "blight_x_sprays": "spraying offset",
}
UNIT_LABEL = {
    ("FI_SW", "pea"): "Pea, Finland",
    ("SE_SKANE", "pea"): "Pea, Sweden",
    ("FI_SW", "turnip_rape"): "Turnip rape, Finland",
    ("FI_SW", "potato"): "Potato, Finland",
    ("FI_SW", "carrot"): "Carrot, Finland",
    ("FI_SW", "spinach"): "Spinach, Finland",
}

Unit = tuple[str, str]


def action_units(spec: dict[str, Any]) -> list[Unit]:
    return [(str(region), str(crop)) for region, crop in spec["scope"]["units"]]


def action_cost_name(action_id: str) -> str:
    return f"compare_actions.action_cost.{action_id}"


def action_override_name(action_id: str) -> str:
    return f"compare_actions.action_override.{action_id}"


@step(
    "compare_actions",
    kind="model",
    summary=(
        "Prices each approved action by changing the assumption it targets on a copy of the "
        "parcel seasons and comparing the cost with no action. It refuses actions the model "
        "cannot price and splits each crop's loss into weather drivers."
    ),
)
def compare_actions(ctx: RunContext, inputs: dict[str, Artifact], params: Params) -> StepResult:
    outcomes = int(params["simulated_outcomes"])
    simulation_seed = int(params["simulation_seed"])
    seasons = inputs["parcel_seasons"].frame
    contracted = inputs["contracted_volume"].frame
    premiums = inputs["premiums"].frame
    import_ef = {
        (str(row["region"]), str(row["crop"])): float(row["import_ef_t_per_t"])
        for row in inputs["import_factors"].frame.to_dict("records")
    }
    models: dict[Unit, ym.Model] = ym.models_from_tables(
        inputs["yield_coefficients"].frame,
        inputs["yield_fit"].frame,
        inputs["farm_levels"].frame,
    )
    specs: list[dict[str, Any]] = [
        {str(column): value for column, value in record.items()}
        for record in inputs["actions"].frame.to_dict("records")
    ]
    normal_yield = contracted.set_index(["region", "crop"])["normal_yield_t_ha"]

    def rows_of(unit: Unit) -> pd.DataFrame:
        return seasons[seasons["region"].eq(unit[0]) & seasons["crop"].eq(unit[1])]

    def price(unit: Unit, rows: pd.DataFrame) -> pd.DataFrame:
        draws = cp.simulate(rows[PARCEL_COLUMNS], models[unit], outcomes, simulation_seed)  # pyright: ignore[reportUnknownMemberType]
        return rp.price_draws(  # pyright: ignore[reportUnknownMemberType]
            draws.assign(region=unit[0], crop=unit[1]), contracted, premiums, import_ef
        )

    with section(
        "loss drivers",
        "Splits each crop's yield change under each climate scenario into weather drivers, "
        "using the yield model's own coefficients.",
    ):
        drivers = loss_drivers(models, rows_of)

    with section(
        "check actions",
        "Refuses actions the model cannot price, such as irrigation where no grower irrigates "
        "in the data, and records the reason.",
    ):
        runnable: list[dict[str, Any]] = []
        refused: list[dict[str, str]] = []
        for spec in specs:
            ok, why = refusal(spec, models, rows_of)
            if ok:
                runnable.append(spec)
            else:
                refused.append(
                    {
                        "action_id": spec["action_id"],
                        "name": spec.get("short_name") or spec["name"],
                        "why_not": why,
                    }
                )

    with section(
        "price no action",
        "Simulates today's parcels under every climate scenario with the simulated outcomes and "
        "seed assumptions, and stops if the cost differs from step 9.",
    ):
        needed = sorted({unit for spec in runnable for unit in action_units(spec)})
        no_action = {unit: price(unit, rows_of(unit)) for unit in needed}
        check_no_action(no_action, inputs["climate_risk"].frame)

    with section(
        "price actions",
        "Applies each action's override to a copy of the parcel seasons, simulates the same "
        "seasons and prices them against the same contracted volume.",
    ):
        results: list[dict[str, Any]] = []
        for spec in runnable:
            before: list[pd.DataFrame] = []
            after: list[pd.DataFrame] = []
            for unit in action_units(spec):
                base_rows = rows_of(unit)
                what_if = override_copy(
                    spec, base_rows, models[unit], float(normal_yield.loc[unit])
                )
                check_area_kept(spec, unit, base_rows, what_if)
                before.append(no_action[unit])
                after.append(price(unit, what_if))
            results += action_rows(spec, per_climate(before), per_climate(after))

    results_table = pd.DataFrame(results, columns=ACTION_RESULT_COLUMNS)
    today = results_table[results_table["scenario"].eq("baseline")].set_index("action_id")[
        "risk_removed_eur"
    ]
    results_table["climate_driven_removed_eur"] = results_table["risk_removed_eur"] - (
        results_table["action_id"].map(today)
    )

    with section(
        "checks",
        "Stops the run if an action is missing a climate scenario or a refused action was priced.",
    ):
        check_results(results_table, runnable, refused)

    metrics = action_metrics(results_table, runnable)
    options = action_options(results_table, runnable)

    return StepResult(
        tables=[
            Artifact("action_results", "result", results_table),
            Artifact("actions_not_run", "result", pd.DataFrame(refused, columns=NOT_RUN_COLUMNS)),
            Artifact("loss_drivers", "result", drivers),
        ],
        metrics=metric_frame(metrics),
        action_options=options,
        assumptions=assumptions(outcomes, simulation_seed, runnable),
    )


def loss_drivers(models: dict[Unit, ym.Model], rows_of: Any) -> pd.DataFrame:
    """Yield change from 1991-2020 to 2041-60 per weather driver: the coefficient times the
    change in the driver's area-weighted average."""
    records: list[dict[str, Any]] = []
    for unit, model in models.items():
        rows = rows_of(unit)
        weight = rows["parcel_area_ha"]
        mean = (
            rows[list(DRIVERS)]
            .mul(weight, axis=0)
            .groupby(rows["scenario"])
            .sum()
            .div(weight.groupby(rows["scenario"]).sum(), axis=0)
        )
        for scenario in cp.SCENARIOS:
            for feature, name in DRIVERS.items():
                change = mean.loc[scenario, feature] - mean.loc["baseline", feature]
                effect = 100 * (np.exp(model["beta"].get(feature, 0.0) * change) - 1)
                records.append(
                    {
                        "unit": UNIT_LABEL.get(unit, f"{unit[1]}, {unit[0]}"),
                        "region": unit[0],
                        "crop": unit[1],
                        "scenario": scenario,
                        "driver": name,
                        "yield_effect_pct": float(effect),
                    }
                )
    return pd.DataFrame(records, columns=LOSS_DRIVER_COLUMNS)


def override_copy(
    spec: dict[str, Any], rows: pd.DataFrame, model: ym.Model, normal_yield: float
) -> pd.DataFrame:
    """A copy of the unit's parcel seasons with the action's override applied."""
    changed, _ = ac.apply_override(spec, rows, model, normal_yield)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    return changed  # pyright: ignore[reportUnknownVariableType]


def refusal(spec: dict[str, Any], models: dict[Unit, ym.Model], rows_of: Any) -> tuple[bool, str]:
    """Whether this step can price the action, and if not, why in plain words."""
    named = {f"{region}/{crop}": model for (region, crop), model in models.items()}
    ok, why = ac.support(spec, named, RUNNABLE)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    if not ok:
        return False, why
    for unit in action_units(spec):
        if rows_of(unit).empty:
            return False, f"the parcel seasons have no rows for {unit[0]}/{unit[1]}"
    return True, ""


def per_climate(priced: list[pd.DataFrame]) -> dict[str, dict[str, float]]:
    """Expected cost, 1-in-10 bad year cost and emissions per climate scenario, summed over the
    action's crops season by season and averaged over the transition scenarios."""
    season = (
        pd.concat(priced)
        .groupby(["scenario", "ngfs", "season", "rep"], sort=False)[
            ["extra_cost_eur", "import_tco2e"]
        ]
        .sum()
        .reset_index()
    )
    cost = season.groupby(["scenario", "ngfs"], sort=False)["extra_cost_eur"]
    by_ngfs = pd.DataFrame(
        {
            "expected": cost.mean(),
            "one_in_ten": cost.quantile(0.9),
            "tco2e": season.groupby(["scenario", "ngfs"], sort=False)["import_tco2e"].mean(),
        }
    )
    per_scenario: dict[str, dict[str, float]] = (
        by_ngfs.groupby(level="scenario", sort=False).mean().to_dict("index")
    )  # pyright: ignore[reportAssignmentType]
    return per_scenario


def action_rows(
    spec: dict[str, Any], before: dict[str, dict[str, float]], after: dict[str, dict[str, float]]
) -> list[dict[str, Any]]:
    cost = spec["cost"].get("eur_per_year")
    rows: list[dict[str, Any]] = []
    for scenario in SCENARIOS:
        was, now = before[scenario], after[scenario]
        removed = was["expected"] - now["expected"]
        rows.append(
            {
                "action_id": spec["action_id"],
                "name": spec["name"],
                "scenario": scenario,
                "expected_cost_no_action_eur": was["expected"],
                "expected_cost_with_action_eur": now["expected"],
                "risk_removed_eur": removed,
                "one_in_ten_removed_eur": was["one_in_ten"] - now["one_in_ten"],
                "import_tco2e_removed": was["tco2e"] - now["tco2e"],
                "action_cost_eur": np.nan if cost is None else float(cost),
                "net_benefit_eur": np.nan if cost is None else removed - float(cost),
                "break_even_cost_eur": removed,
                "confidence": spec["confidence"],
                "climate_driven_removed_eur": np.nan,
            }
        )
    return rows


def check_no_action(no_action: dict[Unit, pd.DataFrame], climate_risk: pd.DataFrame) -> None:
    """The no-action cost rebuilt here must equal step 9's, or the simulation settings differ."""
    if not no_action:
        return
    rebuilt = rp.summarise(pd.concat(no_action.values(), ignore_index=True))  # pyright: ignore[reportUnknownMemberType]
    key = ["region", "crop", "scenario", "ngfs"]
    paired = rebuilt.merge(climate_risk, on=key, suffixes=("", "_step9"))
    gap = (paired["expected_cost_eur"] - paired["expected_cost_eur_step9"]).abs()
    if len(paired) != len(rebuilt) or not (gap <= NO_ACTION_TOLERANCE_EUR).all():
        raise ValueError(
            "The cost with no action differs from the cost priced in step 9. The simulated "
            "outcomes and seed of this step must equal those of project_yields."
        )


def check_area_kept(
    spec: dict[str, Any], unit: Unit, before: pd.DataFrame, after: pd.DataFrame
) -> None:
    """An action may move area between farms but never changes a unit's total area."""
    total = ["scenario", "year"]
    if not np.allclose(
        before.groupby(total)["parcel_area_ha"].sum(),
        after.groupby(total)["parcel_area_ha"].sum(),
    ):
        raise ValueError(
            f"The action {spec['action_id']} changes the total area of {unit[0]} {unit[1]}."
        )


def check_results(
    results: pd.DataFrame, runnable: list[dict[str, Any]], refused: list[dict[str, str]]
) -> None:
    if results.groupby("action_id")["scenario"].nunique().ne(len(SCENARIOS)).any():
        raise ValueError("An action is not priced under all four climate scenarios.")
    if set(results["action_id"]) & {row["action_id"] for row in refused}:
        raise ValueError("A refused action was priced.")
    if set(results["action_id"]) != {spec["action_id"] for spec in runnable}:
        raise ValueError("An action that can run has no result.")


def scope_of(spec: dict[str, Any]) -> tuple[list[str], list[str]]:
    """The regions and crops of an action's scope, each once, in order."""
    scope = action_units(spec)
    return list(dict.fromkeys(r for r, _ in scope)), list(dict.fromkeys(c for _, c in scope))


def used_assumptions(spec: dict[str, Any], scenario: str) -> list[str]:
    used = [
        *MODEL_ASSUMPTIONS,
        CONTRACT_YEAR,
        TREND_YEAR,
        SIMULATED_OUTCOMES,
        SIMULATION_SEED,
        PRICE_YEAR,
        PREMIUM_YEARS,
        action_cost_name(spec["action_id"]),
        action_override_name(spec["action_id"]),
    ]
    if scenario != "baseline":
        used.append(PREMIUM_LIFT)
    for region, crop in action_units(spec):
        used += unit_assumptions(region, crop)
    return used


def action_metrics(results: pd.DataFrame, runnable: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {spec["action_id"]: spec for spec in runnable}
    measures = [
        ("compare_actions.risk_removed_eur", "€ per year", "risk_removed_eur"),
        ("compare_actions.import_tco2e_removed", "t CO2e per year", "import_tco2e_removed"),
        ("compare_actions.break_even_cost_eur", "€ per year", "break_even_cost_eur"),
    ]
    rows: list[dict[str, Any]] = []
    for record in results.to_dict("records"):
        action_id, scenario = str(record["action_id"]), str(record["scenario"])
        regions, crops = scope_of(by_id[action_id])
        lineage = [
            {"table": "action_results", "filter": {"action_id": action_id, "scenario": scenario}},
            {
                "table": "parcel_seasons",
                "filter": {"region": regions, "crop": crops, "scenario": scenario},
            },
        ]
        for name, unit, column in measures:
            if pd.isna(record[column]):
                continue
            rows.append(
                {
                    "key": metric_key(name, action_id, scenario),
                    "name": name,
                    "unit": unit,
                    "value": float(record[column]),
                    "low": None,
                    "high": None,
                    "region": None,
                    "crop": None,
                    "scenario": scenario,
                    "ngfs_scenario": None,
                    "period": climate_period(scenario),
                    "action_id": action_id,
                    "lineage": lineage,
                    "assumptions": used_assumptions(by_id[action_id], scenario),
                }
            )
    return rows


def action_options(results: pd.DataFrame, runnable: list[dict[str, Any]]) -> pd.DataFrame:
    """One option per action and climate scenario. Emissions change is negative when the action
    avoids imports. An action that spans several regions or crops leaves that column empty."""
    by_id = {spec["action_id"]: spec for spec in runnable}
    rows: list[dict[str, Any]] = []
    for record in results.to_dict("records"):
        action_id, scenario = str(record["action_id"]), str(record["scenario"])
        spec = by_id[action_id]
        regions, crops = scope_of(spec)
        cost = spec["cost"].get("eur_per_year")
        rows.append(
            {
                "key": f"{action_id}|{scenario}",
                "action_id": action_id,
                "name": spec["name"],
                "scenario": scenario,
                "region": regions[0] if len(regions) == 1 else None,
                "crop": crops[0] if len(crops) == 1 else None,
                "cost_eur_per_yr": None if cost is None else float(cost),
                "risk_reduced_eur_per_yr": float(record["risk_removed_eur"]),
                "emissions_change_t": -float(record["import_tco2e_removed"]),
                "assumptions": used_assumptions(spec, scenario),
                "confidence": spec["confidence"],
            }
        )
    return pd.DataFrame(rows, columns=ACTION_OPTION_COLUMNS)


def assumptions(
    outcomes: int, simulation_seed: int, runnable: list[dict[str, Any]]
) -> list[AssumptionUse]:
    source = "recipe farm_climate_risk, compare_actions params"
    used = [
        AssumptionUse(
            SIMULATED_OUTCOMES,
            "Simulated outcomes per season when pricing actions",
            outcomes,
            "outcomes",
            source,
        ),
        AssumptionUse(
            SIMULATION_SEED,
            "Random seed for the simulated outcomes when pricing actions",
            simulation_seed,
            "",
            source,
        ),
    ]
    for spec in runnable:
        label = spec.get("short_name") or spec["name"]
        used += [
            AssumptionUse(
                action_cost_name(spec["action_id"]),
                f"Cost per year, {label}",
                spec["cost"].get("eur_per_year"),
                "€ per year",
                str(spec["cost"].get("source") or "action spec"),
            ),
            AssumptionUse(
                action_override_name(spec["action_id"]),
                f"What the action changes, {label}",
                dict(spec["override"]),
                "",
                f"Action spec {spec['action_id']}, proposed by {spec['proposed_by']}",
            ),
        ]
    return used
