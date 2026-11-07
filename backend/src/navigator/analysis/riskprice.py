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

from collections.abc import Mapping, Sequence

import numpy as np
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


def lifts(
    transition: pd.DataFrame,
    premium_years: Sequence[int] = (2045, 2050),
    override: Mapping[str, float] | None = None,
) -> pd.Series:
    """Rise in the frozen-vegetable import premium from 2025 to the average of `premium_years`,
    as a fraction of the price, per NGFS scenario. `override` replaces a scenario's value."""
    t = transition.pivot(index="scenario", columns="year", values="frozen_veg_import_premium_pct")
    lift = ((t[list(premium_years)].mean(axis=1) - t[2025]) / 100).rename("lift")
    for ngfs, value in (override or {}).items():
        lift.loc[ngfs] = value
    return lift


def premiums(
    prices: pd.DataFrame,
    transition: pd.DataFrame,
    price_year: int = 2025,
    premium_years: Sequence[int] = (2045, 2050),
    overrides: Mapping[str, Mapping[str, float]] | None = None,
    lift_override: Mapping[str, float] | None = None,
) -> pd.DataFrame:
    """Replacement premium per region, crop and NGFS scenario for 2041-60 (plus today's premium).

    `overrides` replaces values in the price file, keyed by its item and then its column.
    `lift_override` replaces the computed premium rise of an NGFS scenario."""
    p = prices[prices["year"].eq(price_year)].set_index("item")
    for item, columns in (overrides or {}).items():
        for column, value in columns.items():
            p[column] = p[column].astype(float)
            p.loc[item, column] = value
    proxy = (
        transition.drop_duplicates("scenario")
        .set_index("scenario")["physical_pathway_proxy"]
        .to_dict()
    )
    lift = lifts(transition, premium_years, lift_override)
    rows = []
    for (r, c), item in PRICE_ITEM.items():
        base = float(p["replacement_import_premium_frac"].loc[item])
        price = float(p["contract_price_eur_t"].loc[item])
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
        for ngfs, rise in lift.items():
            rows.append(
                {
                    "region": r,
                    "crop": c,
                    "ngfs": ngfs,
                    "ssp": proxy[ngfs],
                    "contract_price_eur_t": price,
                    "premium": base + (rise if item in FROZEN else 0.0),
                }
            )
    return pd.DataFrame(rows)


def price_draws(
    draws: pd.DataFrame, contracted: pd.DataFrame, prem: pd.DataFrame, import_ef: dict
) -> pd.DataFrame:
    """Shortfall, extra cost and extra emissions for every simulated season, under every NGFS
    scenario paired with the draw's climate scenario. `import_ef` maps (region, crop) to tCO2e per
    tonne."""
    d = draws[~draws["scenario"].str.endswith("_run")].merge(
        contracted[["region", "crop", "contracted_t"]], on=["region", "crop"]
    )
    d["shortfall_t"] = (d["contracted_t"] - d["production_t"]).clip(lower=0)
    d = d.merge(prem.rename(columns={"ssp": "scenario"}), on=["region", "crop", "scenario"])
    d["extra_cost_eur"] = d["shortfall_t"] * d["contract_price_eur_t"] * d["premium"]
    d["import_tco2e"] = d["shortfall_t"] * [
        import_ef[(r, c)] for r, c in zip(d["region"], d["crop"], strict=True)
    ]
    return d


def _share_short_10pct(seasons: pd.DataFrame) -> float:
    return (seasons["shortfall_t"] > 0.1 * seasons["contracted_t"]).mean()


def summarise(priced: pd.DataFrame, by=("region", "crop", "scenario", "ngfs")) -> pd.DataFrame:
    """Expected value per year and the 1-in-10 bad year (90th percentile) per group."""
    g = priced.groupby(list(by), sort=False)
    return pd.DataFrame(
        {
            "contracted_t": g["contracted_t"].first(),
            "expected_shortfall_t": g["shortfall_t"].mean(),
            # pandas-stubs 3 dropped include_groups, which pandas 2.3 still takes
            "share_of_seasons_short_10pct": g.apply(_share_short_10pct, include_groups=False),  # pyright: ignore[reportCallIssue]
            "expected_cost_eur": g["extra_cost_eur"].mean(),
            "one_in_ten_cost_eur": g["extra_cost_eur"].quantile(0.9),
            "expected_import_tco2e": g["import_tco2e"].mean(),
            "one_in_ten_import_tco2e": g["import_tco2e"].quantile(0.9),
        }
    ).reset_index()


def totals(priced: pd.DataFrame) -> pd.DataFrame:
    """All crops together, season by season (every crop uses the same past seasons, so a season
    that is bad everywhere is bad in the total). Per climate and NGFS scenario: expected cost and
    emissions, the 1-in-10 bad year, and what the climate adds to the expected cost compared with
    today (the baseline weather)."""
    season = (
        priced.groupby(["scenario", "ngfs", "season", "rep"], sort=False)[
            ["extra_cost_eur", "import_tco2e"]
        ]
        .sum()
        .reset_index()
    )
    g = season.groupby(["scenario", "ngfs"], sort=False)
    out = pd.DataFrame(
        {
            "expected_cost_eur": g["extra_cost_eur"].mean(),
            "one_in_ten_cost_eur": g["extra_cost_eur"].quantile(0.9),
            "expected_import_tco2e": g["import_tco2e"].mean(),
            "one_in_ten_import_tco2e": g["import_tco2e"].quantile(0.9),
        }
    ).reset_index()
    today = out.loc[out["scenario"].eq("baseline"), "expected_cost_eur"].iloc[0]
    out["climate_added_cost_eur"] = out["expected_cost_eur"] - today
    return out


def foodhills_cover(
    draws: pd.DataFrame,
    contracted: pd.DataFrame,
    prem: pd.DataFrame,
    short_share: float = 0.1,
) -> pd.DataFrame:
    """Upper bound on how much of the Finnish pea shortfall Swedish pea surplus could cover.

    Per climate scenario and season (averaged over the simulated outcomes, so it reflects the
    weather, not chance farm noise), the Finnish shortfall is compared with the Swedish surplus
    above its contracted volume. Not priced into the risk. Assumes every tonne of surplus could be
    frozen at Bjuv and sent to Finland. A season is short when the shortfall is above
    `short_share` of the Finnish contract. The premium avoided uses today's Finnish pea premium."""
    pea = draws[draws["crop"].eq("pea") & ~draws["scenario"].str.endswith("_run")]
    season = pea.groupby(["scenario", "region", "season"])["production_t"].mean().unstack("region")
    ct = contracted[contracted["crop"].eq("pea")].set_index("region")["contracted_t"]
    fi_short = (ct["FI_SW"] - season["FI_SW"]).clip(lower=0)
    se_surplus = (season["SE_SKANE"] - ct["SE_SKANE"]).clip(lower=0)
    today = prem[prem["region"].eq("FI_SW") & prem["crop"].eq("pea") & prem["ngfs"].eq("today")]
    price, premium = (
        float(today["contract_price_eur_t"].to_numpy()[0]),
        float(today["premium"].to_numpy()[0]),
    )
    rows = []
    for scenario in fi_short.index.get_level_values("scenario").unique():
        fs, ss = fi_short.loc[scenario], se_surplus.loc[scenario]
        short = fs > short_share * ct["FI_SW"]
        covered = np.minimum(fs, ss)
        rows.append(
            {
                "scenario": scenario,
                "seasons": len(fs),
                "seasons_short": int(short.sum()),
                "seasons_with_surplus": int((short & (ss > 0)).sum()),
                "cover_share_pct": 100 * covered.sum() / max(fs.sum(), 1e-9),
                "premium_avoided_eur": covered.mean() * price * premium,
            }
        )
    return pd.DataFrame(rows)
