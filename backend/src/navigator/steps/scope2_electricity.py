"""scope2_electricity: location-based and market-based Scope 2 for purchased electricity.

Follows section 3 of the package's METHODOLOGY.md. Location-based emissions are the cleaned
megawatt hours times the national grid factor. Market-based emissions apply the residual mix to
the megawatt hours that no guarantee of origin covers.
"""

from collections.abc import Mapping
from typing import Any

import pandas as pd

from navigator.recipes.core import (
    METRIC_COLUMNS,
    Artifact,
    AssumptionUse,
    Params,
    RunContext,
    StepResult,
    section,
    step,
)

CARRIER = "electricity"
SOURCE = (
    "METHODOLOGY.md section 3 of the challenge package. Finland 2024 residual mix 0.406 is "
    "from AIB; the other years are the package's factors file (tools/ccn_tools/factors.py)"
)
SITE_YEAR_COLUMNS = [
    "site_id",
    "year",
    "country",
    "months_read",
    "n_corrections",
    "electricity_mwh",
    "goo_listed_mwh",
    "goo_counted_mwh",
    "location_t_per_mwh",
    "residual_t_per_mwh",
    "location_based_tco2e",
    "market_based_tco2e",
]
USE = "scope2_electricity.electricity_use_mwh"
LOCATION = "scope2_electricity.location_based_tco2e"
MARKET = "scope2_electricity.market_based_tco2e"
LOCATION_FACTORS = "scope2_electricity.location_t_per_mwh"
RESIDUAL_MIX = "scope2_electricity.residual_t_per_mwh"


def electricity_use(energy: pd.DataFrame, sites: pd.DataFrame) -> pd.DataFrame:
    """Cleaned electricity per site and year, with the site's country."""
    own = energy[energy["carrier"].eq(CARRIER)]
    use = (
        own.groupby(["site_id", "year"])
        .agg(
            months_read=("value", "count"),
            n_corrections=("n_corrections", "sum"),
            electricity_mwh=("value", "sum"),
        )
        .reset_index()
    )
    return use.merge(
        sites[["site_id", "country"]], on="site_id", how="left", validate="many_to_one"
    )


def counted_origin_guarantees(registry: pd.DataFrame) -> pd.DataFrame:
    """Guarantees of origin per site and consumption year, and the part that counts.

    A guarantee counts only when its production period lies in the year it is used for.
    """
    start_year = pd.to_datetime(registry["production_period_start"]).dt.year
    end_year = pd.to_datetime(registry["production_period_end"]).dt.year
    same_year = start_year.eq(registry["consumption_year"]) & end_year.eq(
        registry["consumption_year"]
    )
    listed = registry.groupby(["beneficiary_site", "consumption_year"])["mwh"].sum()
    valid = registry[same_year].groupby(["beneficiary_site", "consumption_year"])["mwh"].sum()
    table = pd.DataFrame({"goo_listed_mwh": listed, "goo_valid_mwh": valid}).fillna(0.0)
    table.index.names = ["site_id", "year"]
    return table.reset_index()


def factor(table: Mapping[str, Mapping[str, float]], country: str, year: int, what: str) -> float:
    try:
        return float(table[country][str(year)])
    except KeyError:
        raise ValueError(f"There is no {what} for {country} in {year}.") from None


def site_years(
    energy: pd.DataFrame,
    sites: pd.DataFrame,
    registry: pd.DataFrame,
    location: Mapping[str, Mapping[str, float]],
    residual: Mapping[str, Mapping[str, float]],
) -> pd.DataFrame:
    use = electricity_use(energy, sites)
    if use["country"].isna().any():
        raise ValueError("Some electricity readings belong to a site that is not in sites.csv.")
    guarantees = counted_origin_guarantees(registry)
    table = use.merge(guarantees, on=["site_id", "year"], how="left", validate="one_to_one")
    table[["goo_listed_mwh", "goo_valid_mwh"]] = table[["goo_listed_mwh", "goo_valid_mwh"]].fillna(
        0.0
    )
    # A guarantee covers at most the site's own consumption.
    table["goo_counted_mwh"] = table[["goo_valid_mwh", "electricity_mwh"]].min(axis=1)
    table["location_t_per_mwh"] = [
        factor(location, c, y, "grid factor")
        for c, y in zip(table["country"], table["year"], strict=True)
    ]
    table["residual_t_per_mwh"] = [
        factor(residual, c, y, "residual mix")
        for c, y in zip(table["country"], table["year"], strict=True)
    ]
    table["location_based_tco2e"] = table["electricity_mwh"] * table["location_t_per_mwh"]
    table["market_based_tco2e"] = (table["electricity_mwh"] - table["goo_counted_mwh"]) * table[
        "residual_t_per_mwh"
    ]
    return table[SITE_YEAR_COLUMNS]


def metric_rows(table: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in table.to_dict("records"):
        site, year = str(record["site_id"]), int(record["year"])
        own = {"site_id": site, "year": year}
        energy = {"table": "energy_clean", "filter": {**own, "carrier": CARRIER}}
        result = {"table": "scope2_site_year", "filter": own}
        guarantees = {
            "table": "goo_registry_statement",
            "filter": {"beneficiary_site": site, "consumption_year": year},
        }
        with_guarantees = record["goo_listed_mwh"] > 0
        measures = [
            (USE, "MWh", "electricity_mwh", [result, energy], [LOCATION_FACTORS]),
            (
                LOCATION,
                "t CO2e",
                "location_based_tco2e",
                [result, energy],
                [LOCATION_FACTORS],
            ),
            (
                MARKET,
                "t CO2e",
                "market_based_tco2e",
                [result, energy, *([guarantees] if with_guarantees else [])],
                [RESIDUAL_MIX],
            ),
        ]
        for name, unit, column, lineage, assumptions in measures:
            rows.append(
                {
                    "key": f"{name}|{site}|{year}",
                    "name": name,
                    "unit": unit,
                    "value": float(record[column]),
                    "low": None,
                    "high": None,
                    "region": None,
                    "crop": None,
                    "site": site,
                    "scenario": None,
                    "ngfs_scenario": None,
                    "period": str(year),
                    "action_id": None,
                    "lineage": lineage,
                    "assumptions": assumptions,
                }
            )
    return rows


@step(
    "scope2_electricity",
    kind="model",
    summary=(
        "Prices purchased electricity per site and year as location-based and market-based "
        "Scope 2, from the cleaned readings, the national factors and the guarantees of origin "
        "the registry shows for the same year."
    ),
)
def scope2_electricity(ctx: RunContext, inputs: dict[str, Artifact], params: Params) -> StepResult:
    location: Mapping[str, Mapping[str, float]] = params["location_t_per_mwh"]
    residual: Mapping[str, Mapping[str, float]] = params["residual_t_per_mwh"]
    with section(
        "total electricity",
        "Adds up the cleaned monthly readings of each site's electricity meters for each year.",
    ):
        energy = inputs["energy_clean"].frame
        sites = inputs["sites"].frame

    with section(
        "count guarantees of origin",
        "Counts a guarantee of origin only when its production period lies in the year it is "
        "used for, up to the site's consumption.",
    ):
        registry = inputs["goo_registry_statement"].frame

    with section(
        "price emissions",
        "Multiplies the megawatt hours by the grid factor for location-based Scope 2, and the "
        "uncovered megawatt hours by the residual mix for market-based Scope 2.",
    ):
        table = site_years(energy, sites, registry, location, residual)

    with section(
        "write metrics",
        "Gives each site and year its electricity use and both Scope 2 figures, with the "
        "readings and guarantees behind them.",
    ):
        metrics = pd.DataFrame(metric_rows(table), columns=METRIC_COLUMNS)

    return StepResult(
        tables=[Artifact(name="scope2_site_year", layer="result", frame=table)],
        metrics=metrics,
        assumptions=[
            AssumptionUse(
                LOCATION_FACTORS,
                "Grid emission factor of national electricity production",
                location,
                "t CO2e per MWh, by country and year",
                SOURCE,
            ),
            AssumptionUse(
                RESIDUAL_MIX,
                "Residual mix emission factor, for electricity not covered by guarantees of origin",
                residual,
                "t CO2e per MWh, by country and year",
                SOURCE,
            ),
        ],
    )
