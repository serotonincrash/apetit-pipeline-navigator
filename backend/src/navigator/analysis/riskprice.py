"""Pricing climate risk for Track C: shortfalls from the yield projection, in euros and tCO2e.

When contract farms deliver less than the contracted volume, Apetit buys the gap on the market:

    extra cost = shortfall (t) x contract price (EUR/t) x replacement premium
    extra emissions = shortfall (t) x import emission factor (tCO2e/t)

- Contracted volume = 2025 contract area x the normal yield of today's farms (the model on
  1991-2020 weather, trend at 2026). A surplus in a good season is not credited.
- The replacement premium is the package's premium per crop. For frozen vegetables (all crops but
  turnip rape) it rises by the increase in the NGFS scenario's frozen-vegetable import premium from
  2025 to 2041-60 (average of its 2045 and 2050 values). Each NGFS scenario is priced with the
  climate scenario the package pairs it with.
- The import adds its full footprint. The domestic fields were still sown, fertilised and
  harvested, so their emissions happen anyway.
- Prices are 2025 euros, held constant.
"""

from __future__ import annotations

import pandas as pd

PRICE_ITEM = {
    ("FI_SW", "pea"): "pea",
    ("SE_SKANE", "pea"): "pea_SE",
    ("FI_SW", "turnip_rape"): "turnip_rape",
    ("FI_SW", "potato"): "potato",
    ("FI_SW", "carrot"): "carrot",
    ("FI_SW", "spinach"): "spinach",
}
FROZEN = {"pea", "pea_SE", "potato", "carrot", "spinach"}


def contracted_volume(draws: pd.DataFrame) -> pd.DataFrame:
    """Contracted tonnes per region and crop: 2025 contract area x normal yield (baseline mean)."""
    b = draws[draws["scenario"].eq("baseline")]
    g = b.groupby(["region", "crop"])
    return pd.DataFrame(
        {
            "area_ha": g["area_ha"].first(),
            "normal_yield_t_ha": g["yield_t_ha"].mean(),
            "contracted_t": g["area_ha"].first() * g["yield_t_ha"].mean(),
        }
    ).reset_index()


def premiums(
    prices: pd.DataFrame, transition: pd.DataFrame, price_year: int = 2025
) -> pd.DataFrame:
    """Replacement premium per region, crop and NGFS scenario for 2041-60 (plus today's premium)."""
    p = prices[prices["year"].eq(price_year)].set_index("item")
    t = transition.pivot(index="scenario", columns="year", values="frozen_veg_import_premium_pct")
    proxy = transition.drop_duplicates("scenario").set_index("scenario")["physical_pathway_proxy"]
    lift = ((t[[2045, 2050]].mean(axis=1) - t[2025]) / 100).rename("lift")
    rows = []
    for (r, c), item in PRICE_ITEM.items():
        base = float(p.loc[item, "replacement_import_premium_frac"])
        price = float(p.loc[item, "contract_price_eur_t"])
        rows.append(
            {
                "region": r,
                "crop": c,
                "ngfs": "today",
                "ssp": "baseline",
                "contract_price_eur_t": price,
                "premium": base,
            }
        )
        for ngfs, l in lift.items():
            rows.append(
                {
                    "region": r,
                    "crop": c,
                    "ngfs": ngfs,
                    "ssp": proxy[ngfs],
                    "contract_price_eur_t": price,
                    "premium": base + (l if item in FROZEN else 0.0),
                }
            )
    return pd.DataFrame(rows)


def price_draws(
    draws: pd.DataFrame, contracted: pd.DataFrame, prem: pd.DataFrame, import_ef: dict
) -> pd.DataFrame:
    """Shortfall, extra cost and extra emissions for every simulated season, under every NGFS scenario
    paired with the draw's climate scenario. `import_ef` maps (region, crop) to tCO2e per tonne."""
    d = draws[~draws["scenario"].str.endswith("_run")].merge(
        contracted[["region", "crop", "contracted_t"]], on=["region", "crop"]
    )
    d["shortfall_t"] = (d["contracted_t"] - d["production_t"]).clip(lower=0)
    d = d.merge(prem.rename(columns={"ssp": "scenario"}), on=["region", "crop", "scenario"])
    d["extra_cost_eur"] = d["shortfall_t"] * d["contract_price_eur_t"] * d["premium"]
    d["import_tco2e"] = d["shortfall_t"] * [
        import_ef[(r, c)] for r, c in zip(d["region"], d["crop"])
    ]
    return d


def summarise(priced: pd.DataFrame, by=("region", "crop", "scenario", "ngfs")) -> pd.DataFrame:
    """Expected value per year and the 1-in-10 bad year (90th percentile) per group."""
    g = priced.groupby(list(by), sort=False)
    return pd.DataFrame(
        {
            "contracted_t": g["contracted_t"].first(),
            "expected_shortfall_t": g["shortfall_t"].mean(),
            "share_of_seasons_short_10pct": g.apply(
                lambda x: (x["shortfall_t"] > 0.1 * x["contracted_t"]).mean(), include_groups=False
            ),
            "expected_cost_eur": g["extra_cost_eur"].mean(),
            "one_in_ten_cost_eur": g["extra_cost_eur"].quantile(0.9),
            "expected_import_tco2e": g["import_tco2e"].mean(),
            "one_in_ten_import_tco2e": g["import_tco2e"].quantile(0.9),
        }
    ).reset_index()
