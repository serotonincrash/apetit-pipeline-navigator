"""Climate projections for Track C: shifted past seasons, run through the yield model.

The package gives one weather run per scenario. A single 20-year run mixes the climate signal
with chance good and bad summers, so the projection builds many seasons per scenario instead:
every season from 1991-2020 is shifted to the 2041-60 climate of a scenario using the package's
monthly changes (`climate_change_signals.csv`):

- daily mean, maximum and minimum temperature rise by that month's change;
- rain amounts are scaled by that month's factor (dry days stay dry);
- evaporation is recalculated with the Hargreaves formula, which the package uses: for an
  unchanged day length and temperature range it scales with (mean temperature + 17.8).

The unshifted 1991-2020 seasons form the baseline, so model bias cancels in every comparison.
The package's own 2041-60 runs are carried along as a check.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import cropweather as cw

SCENARIOS = ["ssp126", "ssp245", "ssp585"]
BASE_YEARS = (1991, 2020)
FUTURE_YEARS = (2041, 2060)
MONTH_OF_T = pd.date_range("2001-03-01", periods=cw.T).month.values      # month of each season day


def ensemble(keys: pd.DataFrame, arr: dict, signals: pd.DataFrame):
    """Build the weather sets. Returns (keys, arrays) with a `scenario` label per series:
    'baseline' (1991-2020 as recorded), '<ssp>' (1991-2020 shifted to that scenario's 2041-60
    climate) and '<ssp>_run' (the package's delivered 2041-60 run)."""
    hist = keys[keys["scenario"].eq("historical") & keys["year"].between(*BASE_YEARS)]
    hi = hist["sid"].values
    parts_k, parts_a = [hist.assign(scenario="baseline")], [{v: arr[v][hi] for v in cw.VARS}]
    for s in SCENARIOS:
        sig = signals[signals["scenario"].eq(s)].set_index("month")
        dt = sig["delta_tmean_c"].reindex(MONTH_OF_T).values.astype(np.float32)[None, :]
        pf = sig["precip_factor"].reindex(MONTH_OF_T).values.astype(np.float32)[None, :]
        a = {v: arr[v][hi].copy() for v in cw.VARS}
        t0 = a["tmean_c"]
        for v in ["tmean_c", "tmax_c", "tmin_c"]:
            a[v] = a[v] + dt
        a["precip_mm"] = a["precip_mm"] * pf
        a["pet_mm"] = a["pet_mm"] * np.clip((t0 + dt + 17.8) / np.maximum(t0 + 17.8, 0.5), 0, None)
        parts_k.append(hist.assign(scenario=s)); parts_a.append(a)
        run = keys[keys["scenario"].eq(s) & keys["year"].between(*FUTURE_YEARS)]
        parts_k.append(run.assign(scenario=f"{s}_run")); parts_a.append({v: arr[v][run["sid"].values] for v in cw.VARS})
    k = pd.concat(parts_k, ignore_index=True)
    k["sid"] = np.arange(len(k))
    a = {v: np.concatenate([p[v] for p in parts_a]) for v in cw.VARS}
    return k, a


def simulate(lp: pd.DataFrame, model: dict, reps: int = 50, seed: int = 2026) -> pd.DataFrame:
    """Turn expected log yields per parcel and season into simulated regional outcomes.

    `lp` has one row per parcel and season: farm_id, scenario, year (season), parcel_area_ha and
    log_yield (expected log yield, without the smearing factor). Each simulated season adds the
    model's leftover error: one draw shared by all farms in the season and one draw per farm.
    Returns one row per scenario, season and replicate with production and area-weighted yield.
    """
    rng = np.random.default_rng(seed)
    sd_s, sd_f = model["resid_sd_shared"], model["resid_sd_farm"]
    farm_t = (lp.assign(t=lp["parcel_area_ha"] * np.exp(lp["log_yield"]))
                .groupby(["scenario", "year", "farm_id"], as_index=False)["t"].sum())
    area = lp.groupby(["scenario", "year"])["parcel_area_ha"].sum()
    out = []
    for scen, g in farm_t.groupby("scenario", sort=False):
        piv = g.pivot(index="farm_id", columns="year", values="t").fillna(0.0)
        A = piv.values                                            # farms x seasons
        shared = rng.normal(0.0, sd_s, (reps, A.shape[1]))
        farm = rng.normal(0.0, sd_f, (reps, A.shape[0], A.shape[1]))
        prod = np.exp(shared) * (A[None, :, :] * np.exp(farm)).sum(axis=1)   # reps x seasons
        yrs = piv.columns.values
        ar = area.loc[scen].reindex(yrs).values
        for r in range(reps):
            out.append(pd.DataFrame({"scenario": scen, "season": yrs, "rep": r,
                                     "production_t": prod[r], "area_ha": ar, "yield_t_ha": prod[r] / ar}))
    return pd.concat(out, ignore_index=True)


def summarise(draws: pd.DataFrame, bad_share: float = 0.8) -> pd.DataFrame:
    """Mean yield change and chance of a bad year against the simulated 1991-2020 baseline.
    A bad year is a season whose area-weighted yield is below `bad_share` of the baseline mean."""
    base_mean = draws.loc[draws["scenario"].eq("baseline"), "yield_t_ha"].mean()
    rows = []
    for scen, g in draws.groupby("scenario", sort=False):
        y = g["yield_t_ha"]
        rows.append({"scenario": scen, "seasons": g["season"].nunique(), "mean_yield_t_ha": y.mean(),
                     "mean_yield_change_pct": 100 * (y.mean() / base_mean - 1),
                     "p_bad_year": float((y < bad_share * base_mean).mean()),
                     "one_in_ten_yield_t_ha": float(y.quantile(0.1)),
                     "one_in_ten_change_pct": 100 * (y.quantile(0.1) / base_mean - 1)})
    return pd.DataFrame(rows)


def bootstrap(draws: pd.DataFrame, n: int = 300, bad_share: float = 0.8, seed: int = 7) -> pd.DataFrame:
    """90% ranges for the mean change and the chance of a bad year, from resampling whole seasons.

    A shifted season is the same past season as its baseline twin, so the two are resampled
    together (a paired bootstrap): the range then reflects how much the answer depends on which
    past seasons happened, not the gap between unrelated seasons. The package's delivered runs
    are different years and are resampled on their own. The ranges do not include uncertainty in
    the model's coefficients."""
    rng = np.random.default_rng(seed)
    piv = {s: g.pivot(index="rep", columns="season", values="yield_t_ha")
           for s, g in draws.groupby("scenario", sort=False)}
    base_cols = list(piv["baseline"].columns)
    paired = {s for s, p in piv.items() if list(p.columns) == base_cols}
    mats = {s: p.values for s, p in piv.items()}
    base = mats["baseline"]
    out = {s: {"chg": [], "bad": []} for s in mats}
    for _ in range(n):
        idx = rng.integers(0, base.shape[1], base.shape[1])
        b = base[:, idx]
        bm = b.mean()
        for s, m in mats.items():
            x = m[:, idx] if s in paired else m[:, rng.integers(0, m.shape[1], m.shape[1])]
            out[s]["chg"].append(100 * (x.mean() / bm - 1))
            out[s]["bad"].append(float((x < bad_share * bm).mean()))
    rows = []
    for s, v in out.items():
        rows.append({"scenario": s,
                     "change_low_pct": np.percentile(v["chg"], 5), "change_high_pct": np.percentile(v["chg"], 95),
                     "p_bad_low": np.percentile(v["bad"], 5), "p_bad_high": np.percentile(v["bad"], 95)})
    return pd.DataFrame(rows)


def summer_climate(keys: pd.DataFrame, arr: dict) -> pd.DataFrame:
    """June-August averages per weather set and region: mean temperature, days above 27 C, rain."""
    jja = np.isin(MONTH_OF_T, [6, 7, 8])
    df = pd.DataFrame({"scenario": keys["scenario"].values,
                       "region": np.where(keys["cell_id"].str.startswith("GF"), "FI_SW", "SE_SKANE"),
                       "tmean_c": arr["tmean_c"][:, jja].mean(1),
                       "hot_days": (arr["tmax_c"][:, jja] >= 27).sum(1),
                       "rain_mm": arr["precip_mm"][:, jja].sum(1)})
    return df.groupby(["region", "scenario"], sort=False).mean().round(2)


def parcel_seasons(k, a, stress, sat, params, parcels, per_farm, unit_mgmt, model, unit,
                   trend_year: int = 2026, prefix: dict | None = None) -> pd.DataFrame:
    """Every 2025 contract parcel of one region-crop unit paired with every season in every weather
    set, with stress features, today's management, the trend held at `trend_year`, and the model's
    expected log yield (without the smearing factor) in `log_yield`."""
    import yieldcv as cv
    import yieldmodel as ym
    prefix = prefix or {"FI_SW": "GF", "SE_SKANE": "GS"}
    r, c = unit
    idx = np.where(k["cell_id"].str.startswith(prefix[r]).values)[0]
    f = cw.crop_features(k, a, stress, sat, params, idx)
    seasons = k.iloc[idx][["scenario", "year"]].drop_duplicates()
    x = cw.to_parcels(f, parcels[parcels["region"].eq(r) & parcels["crop"].eq(c)].merge(seasons, how="cross"))
    x = x.join(ym.parcel_soil_features(x)).merge(per_farm, on=["region", "farm_id", "crop"], how="left")
    for col in ym.MANAGEMENT:
        x[col] = pd.to_numeric(x[col], errors="coerce").fillna(unit_mgmt[col].get(unit, np.nan))
    x["sprays"] = x["sprays"].fillna(0.0)
    x["year_c"] = trend_year - 2019
    return with_log_yield(x, model)


def with_log_yield(x: pd.DataFrame, model: dict) -> pd.DataFrame:
    """(Re)compute the expected log yield after inputs change. Rebuilds the model's interaction columns."""
    import yieldcv as cv
    import yieldmodel as ym
    held = x["year_c"].copy() if "year_c" in x.columns else None
    x = cv.add_model_columns(x.drop(columns=[c for c in ("drought_x_irr", "blight_x_sprays") if c in x.columns]))
    if held is not None:
        x["year_c"] = held
    x["log_yield"] = np.log(ym.predict(model, x) / model["smearing"])
    return x
