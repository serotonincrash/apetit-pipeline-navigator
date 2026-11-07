"""Step 9: price_risk, from sections 1 to 8 of `notebooks/c3_risk_pricing.ipynb`.

A shortfall is priced as a market import: the shortfall times the contract price times the
replacement premium, and the extra emissions are the shortfall times the import's emission
factor. The calculations live in `analysis/riskprice.py`.

The analysis modules are not typed yet (see pyproject.toml), so calls into them carry a pyright
ignore for their untyped parameters.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd

from navigator.analysis import climateproj as cp
from navigator.analysis import riskprice as rp
from navigator.recipes.core import (
    INSIGHT_COLUMNS,
    Artifact,
    AssumptionUse,
    Params,
    RunContext,
    StepResult,
    section,
    step,
)
from navigator.steps.fit_yield_model import metric_frame, metric_key
from navigator.steps.project_yields import PROJECTION_ASSUMPTIONS, period

PRICE_YEAR = "price_risk.price_year"
PREMIUM_YEARS = "price_risk.premium_years"
PREMIUM_LIFT = "price_risk.replacement_premium_lift"
FOODHILLS_SHORT_SHARE = "price_risk.foodhills_short_share"
PRICE_FILE = "contract_prices_and_replacement_premiums.csv"
# A year's expected shortfall in today's weather must stay under this share of the contract.
MAX_TODAY_SHORTFALL_SHARE = 0.1
UNIT_CLIMATE_SCENARIOS = ["baseline", *cp.SCENARIOS]


def label_of(region: str, crop: str) -> str:
    return f"{region} {crop.replace('_', ' ')}"


def contract_price_name(item: str) -> str:
    return f"price_risk.contract_price_eur_t.{item}"


def replacement_premium_name(item: str) -> str:
    return f"price_risk.replacement_premium.{item}"


def import_ef_name(region: str, crop: str) -> str:
    return f"price_risk.import_ef.{region}.{crop}"


def contracted_volume_name(region: str, crop: str) -> str:
    return f"price_risk.contracted_volume.{region}.{crop}"


@step(
    "price_risk",
    kind="transform",
    summary=(
        "Prices each simulated shortfall as a replacement import, in euros and tonnes of CO2e, "
        "under every transition scenario paired with its climate scenario. It also sizes how "
        "much Swedish pea surplus could cover Finnish pea shortfalls, without pricing it."
    ),
)
def price_risk(ctx: RunContext, inputs: dict[str, Artifact], params: Params) -> StepResult:
    import_ef_param: Mapping[str, float] = params["import_ef"]
    import_ef = {
        (region, crop): float(value)
        for key, value in import_ef_param.items()
        for region, crop in [key.split("/")]
    }
    price_year = int(params["price_year"])
    premium_years = [int(year) for year in params["premium_years"]]
    price_overrides: Mapping[str, Mapping[str, float]] = params["price_overrides"]
    lift_override: Mapping[str, float] = params["replacement_premium_lift"]
    short_share = float(params["foodhills_short_share"])
    draws = inputs["yield_draws"].frame
    import_factors = pd.DataFrame(
        [(region, crop, factor) for (region, crop), factor in import_ef.items()],
        columns=["region", "crop", "import_ef_t_per_t"],
    )

    with section(
        "contracted volume",
        "Sets each crop's contracted volume as its 2025 contract area times the normal yield of "
        "today's farms.",
    ):
        contracted = rp.contracted_volume(draws)

    with section(
        "prices and premiums",
        "Reads each crop's contract price and replacement premium, and raises the frozen "
        "vegetable premium by each transition scenario's rise (premium lift assumption).",
    ):
        premium_table = rp.premiums(
            inputs["contract_prices"].frame,
            inputs["transition_scenarios"].frame,
            price_year,
            premium_years,
            price_overrides,
            lift_override,
        )
        lift = rp.lifts(inputs["transition_scenarios"].frame, premium_years, lift_override)

    with section(
        "price seasons",
        "Prices the shortfall of every simulated season under each transition scenario paired "
        "with its climate scenario, using the import emission factor assumption.",
    ):
        priced = rp.price_draws(  # pyright: ignore[reportUnknownMemberType]
            draws, contracted, premium_table, import_ef
        )

    with section(
        "summarise cost",
        "Works out the expected cost per year and the cost in a 1-in-10 bad year for each crop, "
        "and for all crops together.",
    ):
        climate_risk = rp.summarise(priced)  # pyright: ignore[reportUnknownMemberType]
        climate_risk_total = rp.totals(priced)

    with section(
        "Foodhills cover",
        "Sizes how much of the Finnish pea shortfall Swedish pea surplus could cover, as an "
        "upper bound that is not priced into the risk.",
    ):
        foodhills = rp.foodhills_cover(draws, contracted, premium_table, short_share)

    with section(
        "checks",
        "Stops the run if a crop has no contracted volume, a cost is negative, or a climate "
        "scenario lacks its paired transition scenarios.",
    ):
        check_pricing(draws, contracted, priced, climate_risk, import_ef, inputs)

    metrics = unit_metrics(climate_risk)
    metrics += total_metrics(climate_risk_total)
    metrics += foodhills_metrics(foodhills)
    insights = foodhills_insight(foodhills)

    return StepResult(
        tables=[
            Artifact("contracted_volume", "result", contracted),
            Artifact("priced_draws", "result", priced),
            Artifact("climate_risk", "result", climate_risk),
            Artifact("climate_risk_total", "result", climate_risk_total),
            Artifact("foodhills_cover", "result", foodhills),
            Artifact("premiums", "result", premium_table),
            Artifact("import_factors", "result", import_factors),
        ],
        metrics=metric_frame(metrics),
        insights=insights,
        assumptions=assumptions(
            import_ef, contracted, premium_table, lift, price_year, premium_years, short_share
        ),
    )


def unit_assumptions(region: str, crop: str) -> list[str]:
    item = rp.PRICE_ITEM[(region, crop)]
    return [
        contract_price_name(item),
        replacement_premium_name(item),
        import_ef_name(region, crop),
        contracted_volume_name(region, crop),
    ]


def shared_assumptions() -> list[str]:
    return [*PROJECTION_ASSUMPTIONS, PRICE_YEAR, PREMIUM_YEARS]


def unit_metrics(climate_risk: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in climate_risk.to_dict("records"):
        region, crop = str(row["region"]), str(row["crop"])
        scenario, ngfs = str(row["scenario"]), str(row["ngfs"])
        filter_ = {"region": region, "crop": crop, "scenario": scenario, "ngfs": ngfs}
        lineage = [
            {"table": "climate_risk", "filter": filter_},
            {"table": "priced_draws", "filter": filter_},
            {
                "table": "parcel_seasons",
                "filter": {"region": region, "crop": crop, "scenario": scenario},
            },
            {"table": "model_table", "filter": {"region": region, "crop": crop}},
        ]
        used = [*shared_assumptions(), *unit_assumptions(region, crop)]
        if ngfs != "today":
            used.append(PREMIUM_LIFT)
        for name, unit, column in measures():
            rows.append(
                metric_row(
                    name, unit, float(row[column]), scenario, ngfs, lineage, used, region, crop
                )
            )
    return rows


def measures() -> list[tuple[str, str, str]]:
    return [
        ("price_risk.expected_cost_eur", "€ per year", "expected_cost_eur"),
        ("price_risk.one_in_ten_cost_eur", "€", "one_in_ten_cost_eur"),
        ("price_risk.expected_import_tco2e", "t CO2e per year", "expected_import_tco2e"),
    ]


def climate_period(scenario: str) -> str:
    return period(cp.BASE_YEARS if scenario == "baseline" else cp.FUTURE_YEARS)


def metric_row(
    name: str,
    unit: str,
    value: float,
    scenario: str,
    ngfs: str | None,
    lineage: list[dict[str, Any]],
    used: list[str],
    region: str | None = None,
    crop: str | None = None,
) -> dict[str, Any]:
    return {
        "key": metric_key(name, region, crop, scenario, ngfs),
        "name": name,
        "unit": unit,
        "value": value,
        "low": None,
        "high": None,
        "region": region,
        "crop": crop,
        "scenario": scenario,
        "ngfs_scenario": ngfs,
        "period": climate_period(scenario),
        "action_id": None,
        "lineage": lineage,
        "assumptions": used,
    }


def total_metrics(total: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    every_unit = [name for region, crop in rp.PRICE_ITEM for name in unit_assumptions(region, crop)]
    for record in total.to_dict("records"):
        scenario, ngfs = str(record["scenario"]), str(record["ngfs"])
        used = [*shared_assumptions(), *every_unit]
        if ngfs != "today":
            used.append(PREMIUM_LIFT)
        filter_ = {"scenario": scenario, "ngfs": ngfs}
        lineage = [
            {"table": "climate_risk_total", "filter": filter_},
            {"table": "priced_draws", "filter": filter_},
        ]
        wanted = [*measures()]
        if scenario != "baseline":
            wanted.append(
                ("price_risk.climate_added_cost_eur", "€ per year", "climate_added_cost_eur")
            )
        for name, unit, column in wanted:
            rows.append(
                metric_row(name, unit, float(record[column]), scenario, ngfs, lineage, used)
            )
    return rows


def foodhills_metrics(foodhills: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    pea = [("FI_SW", "pea"), ("SE_SKANE", "pea")]
    used = [
        *shared_assumptions(),
        FOODHILLS_SHORT_SHARE,
        *(name for region, crop in pea for name in unit_assumptions(region, crop)),
    ]
    for record in foodhills.to_dict("records"):
        scenario = str(record["scenario"])
        lineage = [
            {"table": "foodhills_cover", "filter": {"scenario": scenario}},
            {"table": "yield_draws", "filter": {"crop": "pea", "scenario": scenario}},
        ]
        for name, unit, column in (
            ("price_risk.foodhills_cover_share", "%", "cover_share_pct"),
            ("price_risk.foodhills_premium_avoided_eur", "€ per year", "premium_avoided_eur"),
        ):
            rows.append(
                metric_row(name, unit, float(record[column]), scenario, None, lineage, used)
            )
    return rows


def foodhills_insight(foodhills: pd.DataFrame) -> pd.DataFrame:
    """One insight on the Swedish pea surplus, citing the cover share and premium avoided."""
    keys = {
        name: {str(s): metric_key(name, str(s)) for s in foodhills["scenario"]}
        for name in ("price_risk.foodhills_cover_share", "price_risk.foodhills_premium_avoided_eur")
    }
    share, avoided = (
        keys["price_risk.foodhills_cover_share"],
        keys["price_risk.foodhills_premium_avoided_eur"],
    )
    before = period(cp.BASE_YEARS)
    text = (
        "Swedish pea surplus could cover part of the Finnish pea shortfall. This is an upper "
        "bound and it is not priced into the risk. It assumes Bjuv could freeze every tonne of "
        "the surplus and send it to Finland, so what it can cover depends on Bjuv's spare "
        "capacity in harvest weeks. "
        f"With {before} weather the surplus could cover {{{{metric:{share['baseline']}}}}} "
        f"of the Finnish shortfall, which avoids at most {{{{metric:{avoided['baseline']}}}}} "
        "of replacement premium. "
        f"With High emissions (SSP5-8.5) it could cover {{{{metric:{share['ssp585']}}}}}, "
        f"which avoids at most {{{{metric:{avoided['ssp585']}}}}}."
    )
    cited = [share["baseline"], avoided["baseline"], share["ssp585"], avoided["ssp585"]]
    return pd.DataFrame(
        [
            {
                "title": "Swedish pea surplus could cover part of Finnish pea shortfalls",
                "text": text,
                "metric_keys": cited,
            }
        ],
        columns=INSIGHT_COLUMNS,
    )


def check_pricing(
    draws: pd.DataFrame,
    contracted: pd.DataFrame,
    priced: pd.DataFrame,
    climate_risk: pd.DataFrame,
    import_ef: Mapping[tuple[str, str], float],
    inputs: dict[str, Artifact],
) -> None:
    """The notebook's checks, as plain-word errors."""
    found = set(zip(contracted["region"], contracted["crop"], strict=True))
    if found != set(import_ef) or not (contracted["contracted_t"] > 0).all():
        raise ValueError(
            "Not every region and crop has a contracted volume above zero, or the emission "
            "factors cover other regions and crops than the yield draws."
        )
    if not (priced[["shortfall_t", "extra_cost_eur", "import_tco2e"]] >= 0).all().all():
        raise ValueError("A shortfall, extra cost or extra emission is negative.")
    transition = inputs["transition_scenarios"].frame.drop_duplicates("scenario")
    expected = transition.groupby("physical_pathway_proxy").size().to_dict() | {"baseline": 1}
    actual = priced.groupby("scenario")["ngfs"].nunique().to_dict()
    if actual != expected:
        raise ValueError(
            f"The climate scenarios are priced with {actual} transition scenarios each, "
            f"but the transition file pairs them with {expected}."
        )
    today = climate_risk[climate_risk["scenario"].eq("baseline")]
    if not (
        today["expected_shortfall_t"] < MAX_TODAY_SHORTFALL_SHARE * today["contracted_t"]
    ).all():
        raise ValueError(
            "In today's weather a crop's expected shortfall is more than "
            f"{MAX_TODAY_SHORTFALL_SHARE:.0%} of its contract, so the yield draws look wrong."
        )
    base = draws[draws["scenario"].eq("baseline")].groupby(["region", "crop"]).size()
    rows = priced.groupby(["region", "crop", "scenario", "ngfs"]).size()
    outcomes = rows.reset_index(name="rows").merge(base.rename("expected").reset_index())
    if not (outcomes["rows"] == outcomes["expected"]).all():
        raise ValueError(
            "A crop and transition scenario does not have as many priced seasons and outcomes "
            "as the baseline weather."
        )


def assumptions(
    import_ef: Mapping[tuple[str, str], float],
    contracted: pd.DataFrame,
    premium_table: pd.DataFrame,
    lift: pd.Series,
    price_year: int,
    premium_years: list[int],
    short_share: float,
) -> list[AssumptionUse]:
    source = "recipe farm_climate_risk, price_risk params"
    used: list[AssumptionUse] = []
    for (region, crop), factor in import_ef.items():
        item = rp.PRICE_ITEM[(region, crop)]
        label = label_of(region, crop)
        row = premium_table[
            premium_table["region"].eq(region)
            & premium_table["crop"].eq(crop)
            & premium_table["ngfs"].eq("today")
        ].iloc[0]
        volume = contracted[contracted["region"].eq(region) & contracted["crop"].eq(crop)].iloc[0]
        file_row = f"{PRICE_FILE}, {item}, {price_year}"
        used += [
            AssumptionUse(
                contract_price_name(item),
                f"Contract price, {label}",
                float(row["contract_price_eur_t"]),
                "€ per t",
                file_row,
            ),
            AssumptionUse(
                replacement_premium_name(item),
                f"Replacement premium today, {label}",
                float(row["premium"]),
                "fraction of price",
                file_row,
            ),
            AssumptionUse(
                import_ef_name(region, crop),
                f"Import emission factor, {label}",
                factor,
                "t CO2e per t",
                "Section 1 of c3_risk_pricing.ipynb",
            ),
            AssumptionUse(
                contracted_volume_name(region, crop),
                f"Contracted volume, {label}",
                round(float(volume["contracted_t"]), 1),
                "t",
                "2025 contract parcels times the model yield on 1991 to 2020 weather "
                "(step project_yields)",
            ),
        ]
    used += [
        AssumptionUse(
            PREMIUM_LIFT,
            "Rise in the frozen vegetable import premium by 2041 to 2060, per transition scenario",
            {str(name): float(value) for name, value in lift.items()},
            "fraction of price",
            "transition_scenarios.csv, frozen_veg_import_premium_pct (illustrative values)",
        ),
        AssumptionUse(PRICE_YEAR, "Year of the contract prices", price_year, "year", source),
        AssumptionUse(
            PREMIUM_YEARS,
            "Years averaged for the premium rise",
            premium_years,
            "year",
            source,
        ),
        AssumptionUse(
            FOODHILLS_SHORT_SHARE,
            "Share of the Finnish pea contract that makes a season short",
            short_share,
            "share",
            source,
        ),
    ]
    return used
