"""Crop-weather features for Track C: phenology, soil water and stage-specific stress.

Everything is vectorised over *weather series*: one series = one grid cell x scenario x year,
covering 1 March - 31 October. `t` is days since 1 March (0..244); because the window starts
after February, `t` is the same calendar day in leap and non-leap years.

The structure follows the package's SIMULATION_DESIGN.md (sowing after a crop-specific
temperature trigger, GDD base 5 C stages, bucket soil water reset on 1 April, stress in
sensitive stages). The *numbers* are not published: CropParams holds agronomic starting
values, and the notebook tunes the maturity targets against the yield history.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, replace
import numpy as np
import pandas as pd

T = 245                                   # 1 Mar .. 31 Oct
VARS = ["tmean_c", "tmax_c", "tmin_c", "precip_mm", "rad_mj_m2", "pet_mm"]
SOILS = ["sand", "fine_sand", "silt", "clay", "organic"]
AWC_MM = {"sand": 60.0, "fine_sand": 90.0, "silt": 150.0, "clay": 130.0, "organic": 180.0}  # plant-available water, root zone
GDD_BASE_C = 5.0
_t = np.arange(T)


def t_of(mmdd: str) -> int:
    """Days since 1 March for a 'MM-DD' date (leap-year independent)."""
    m, d = map(int, mmdd.split("-"))
    return (pd.Timestamp(2001, m, d) - pd.Timestamp(2001, 3, 1)).days


def doy_of_t(t):
    """Day of year (non-leap convention) for a season index."""
    return np.asarray(t, dtype=float) + 60


@dataclass(frozen=True)
class CropParams:
    crop: str
    sow_temp_c: float          # 5-day mean temperature that triggers sowing
    sow_earliest: str          # 'MM-DD'
    sow_latest: str            # sown on this date if never triggered
    gdd_maturity: float        # degree-days (base 5 C) from sowing to harvest-ready
    cutoff: str                # harvest deadline; not reached by then = immature
    flower: tuple              # flowering window as fractions of gdd_maturity (heat)
    sensitive: tuple           # drought-sensitive window as fractions of gdd_maturity

    def as_dict(self):
        return asdict(self)


DEFAULT_PARAMS = {
    "pea":         CropParams("pea",         6.0, "04-20", "06-10",  850, "08-31", (0.45, 0.70), (0.45, 1.00)),
    "turnip_rape": CropParams("turnip_rape", 6.0, "04-20", "06-10", 1200, "09-30", (0.40, 0.65), (0.40, 0.85)),
    "potato":      CropParams("potato",      8.0, "05-01", "06-15", 1300, "09-30", (0.35, 0.55), (0.35, 0.90)),
    "carrot":      CropParams("carrot",      7.0, "04-25", "06-15", 1300, "10-15", (0.40, 0.70), (0.40, 0.95)),
    "spinach":     CropParams("spinach",     5.0, "04-15", "05-31",  500, "07-15", (0.50, 1.00), (0.40, 1.00)),
}

FEATURE_DOCS = {
    "sow_doy": "Sowing day of year: first 5-day period with mean temperature >= sow_temp_c",
    "mat_doy": "Day of year the maturity degree-days are reached (NaN if never)",
    "immature": "1 if maturity not reached by the cutoff date",
    "immature_gap": "1 - (degree-days reached by cutoff / maturity target), 0 if mature",
    "season_gdd": "Degree-days (base 5 C) from sowing to harvest",
    "rad_season_mj": "Radiation sum from sowing to harvest",
    "heat_days_27": "Days with tmax >= 27 C in the flowering window",
    "heat_days_30": "Days with tmax >= 30 C in the flowering window",
    "deficit_stage_mm": "PET - rain in the drought-sensitive window (soil independent)",
    "drought_stage": "Mean soil-water stress (1 - AET/PET) in the drought-sensitive window",
    "drought_early": "Mean soil-water stress from sowing to the start of the sensitive window",
    "waterlog_days": "Days with the soil bucket overflowing in the 21 days after sowing",
    "waterlog_clay": "waterlog_days on clay soils, 0 otherwise (the truth model's clay waterlogging)",
    "rain_post_sow_21_mm": "Rain in the 21 days after sowing",
    "harvest_rain_14_mm": "Rain in the 14 days before harvest",
    "harvest_wetdays_14": "Days with >= 1 mm rain in the 14 days before harvest",
    "blight_days": "Warm wet days in Jul-Aug (rain >= 1 mm and 15-22 C mean): late-blight pressure",
    "may_tmean_c": "Mean temperature in May: pollen-beetle pressure on turnip rape",
}


def load_weather(path) -> tuple[pd.DataFrame, dict]:
    """Read the daily Parquet into dense arrays of shape (n_series, T), Mar-Oct only."""
    w = pd.read_parquet(path)
    w = w[w["date"].dt.month.between(3, 10)]
    year = w["date"].dt.year
    t = w["date"].dt.dayofyear.values - 60 - w["date"].dt.is_leap_year.values.astype(int)
    keys = (pd.DataFrame({"scenario": w["scenario"].values, "cell_id": w["cell_id"].values, "year": year.values})
            .drop_duplicates().sort_values(["scenario", "cell_id", "year"]).reset_index(drop=True))
    keys["sid"] = np.arange(len(keys))
    sid = (pd.DataFrame({"scenario": w["scenario"].values, "cell_id": w["cell_id"].values, "year": year.values})
           .merge(keys, on=["scenario", "cell_id", "year"], how="left")["sid"].values)
    arr = {}
    for v in VARS:
        a = np.full((len(keys), T), np.nan, dtype=np.float32)
        a[sid, t] = w[v].values
        arr[v] = a
    assert not np.isnan(arr["tmean_c"]).any(), "gaps in weather series"
    return keys, arr


def soil_water(arr: dict, start: str = "04-01"):
    """Daily bucket model per series x soil class, full on `start`.

    Each day: add rain, evaporate PET scaled down linearly below half capacity, spill above capacity.
    Returns stress = 1 - AET/PET and a boolean 'bucket overflowing' (waterlogging) array,
    both shaped (n_series, n_soils, T).
    """
    P, E = arr["precip_mm"], arr["pet_mm"]
    caps = np.array([AWC_MM[s] for s in SOILS], dtype=np.float32)[None, :]
    W = np.repeat(caps, P.shape[0], axis=0)
    stress = np.zeros((P.shape[0], len(SOILS), T), dtype=np.float32)
    sat = np.zeros_like(stress, dtype=bool)
    for k in range(t_of(start), T):
        W = W + P[:, k:k + 1]
        pet = E[:, k:k + 1]
        aet = pet * np.clip(W / (0.5 * caps), 0.0, 1.0)
        W = W - aet
        sat[:, :, k] = W > caps
        W = np.minimum(W, caps)
        stress[:, :, k] = np.where(pet > 0, 1.0 - aet / np.maximum(pet, 1e-6), 0.0)
    return stress, sat


def phenology(tmean: np.ndarray, p: CropParams) -> dict:
    """Sowing, degree-day accumulation, maturity and harvest index per series."""
    n = tmean.shape[0]
    c = np.cumsum(np.pad(tmean, ((0, 0), (1, 0))), axis=1)
    r5 = np.full_like(tmean, -99.0)
    r5[:, :T - 4] = (c[:, 5:] - c[:, :T - 4]) / 5.0
    e, l = t_of(p.sow_earliest), t_of(p.sow_latest)
    ok = (r5 >= p.sow_temp_c) & (_t >= e) & (_t <= l)
    sow = np.where(ok.any(1), ok.argmax(1), l)
    gdd = np.where(_t[None, :] >= sow[:, None], np.clip(tmean - GDD_BASE_C, 0, None), 0.0)
    cg = np.cumsum(gdd, axis=1)
    cut = t_of(p.cutoff)
    reached = cg >= p.gdd_maturity
    mat = np.where(reached.any(1), reached.argmax(1), -1)
    harvest = np.where((mat < 0) | (mat > cut), cut, mat)
    return {"sow": sow, "cg": cg, "mat": mat, "harvest": harvest,
            "immature": ((mat < 0) | (mat > cut)).astype(np.int8),
            "gdd_ratio": np.minimum(cg[np.arange(n), cut] / p.gdd_maturity, 1.0)}


def _window(ph, lo, hi, M):
    return ((ph["cg"] >= lo * M) & (ph["cg"] < hi * M)
            & (_t[None, :] >= ph["sow"][:, None]) & (_t[None, :] <= ph["harvest"][:, None]))


def _msum(x, m):
    return np.where(m, x, 0).sum(axis=-1)


def _mmean(x, m):
    n = m.sum(axis=-1)
    return np.where(n > 0, _msum(x, m) / np.maximum(n, 1), np.nan)


def crop_features(keys: pd.DataFrame, arr: dict, stress, sat, p: CropParams, idx=None) -> pd.DataFrame:
    """One row per series x soil class for crop `p`. `idx` restricts to a subset of series."""
    if idx is None:
        idx = np.arange(len(keys))
    a = {v: arr[v][idx] for v in VARS}
    st, wl = stress[idx], sat[idx]
    ph = phenology(a["tmean_c"], p)
    M = p.gdd_maturity
    n = len(idx)
    sow, harvest = ph["sow"][:, None], ph["harvest"][:, None]

    w_flower = _window(ph, *p.flower, M)
    w_sens = _window(ph, *p.sensitive, M)
    w_early = _window(ph, 0.0, p.sensitive[0], M)
    w_post = (_t >= sow) & (_t < sow + 21)
    w_preh = (_t > harvest - 14) & (_t <= harvest)
    w_season = (_t >= sow) & (_t <= harvest)
    w_julaug = (_t >= t_of("07-01")) & (_t <= t_of("08-31"))
    w_may = (_t >= t_of("05-01")) & (_t <= t_of("05-31"))
    P, tm, tx = a["precip_mm"], a["tmean_c"], a["tmax_c"]

    base = pd.DataFrame({
        "sid": keys["sid"].values[idx],
        "sow_doy": doy_of_t(ph["sow"]),
        "mat_doy": np.where(ph["mat"] >= 0, doy_of_t(ph["mat"]), np.nan),
        "immature": ph["immature"],
        "immature_gap": np.where(ph["gdd_ratio"] > 0.999, 0.0, 1.0 - ph["gdd_ratio"]),   # drop float noise
        "season_gdd": ph["cg"][np.arange(n), ph["harvest"]],
        "rad_season_mj": _msum(a["rad_mj_m2"], w_season),
        "heat_days_27": _msum(tx >= 27, w_flower),
        "heat_days_30": _msum(tx >= 30, w_flower),
        "deficit_stage_mm": _msum(a["pet_mm"] - P, w_sens),
        "rain_post_sow_21_mm": _msum(P, w_post),
        "harvest_rain_14_mm": _msum(P, w_preh),
        "harvest_wetdays_14": _msum(P >= 1, w_preh),
        "blight_days": _msum((P >= 1) & (tm >= 15) & (tm <= 22), np.broadcast_to(w_julaug, P.shape)),
        "may_tmean_c": _mmean(tm, np.broadcast_to(w_may, tm.shape)),
    })
    out = []
    for j, soil in enumerate(SOILS):
        f = base.copy()
        f["soil_class"] = soil
        f["drought_stage"] = _mmean(st[:, j, :], w_sens)
        f["drought_early"] = _mmean(st[:, j, :], w_early)
        f["waterlog_days"] = _msum(wl[:, j, :], w_post)
        f["waterlog_clay"] = f["waterlog_days"] if soil == "clay" else 0
        out.append(f)
    out = pd.concat(out, ignore_index=True)
    out = keys.iloc[out["sid"].values][["scenario", "cell_id", "year"]].reset_index(drop=True).join(out)
    out.insert(3, "crop", p.crop)
    return out.drop(columns="sid")


WEATHER_FEATURES = ["sow_doy", "mat_doy", "immature", "immature_gap", "season_gdd", "rad_season_mj",
                    "heat_days_27", "heat_days_30", "deficit_stage_mm", "drought_stage", "drought_early",
                    "waterlog_days", "waterlog_clay", "rain_post_sow_21_mm", "harvest_rain_14_mm",
                    "harvest_wetdays_14", "blight_days", "may_tmean_c"]


def to_parcels(feat: pd.DataFrame, parcel_years: pd.DataFrame) -> pd.DataFrame:
    """Attach cell x soil x crop x year features to parcel-years. Declared years use the historical
    series; planned years (2027+) use the scenario given in `parcel_years['scenario']`."""
    # cells belong to one region, so a region column on the features adds nothing to the join
    feat = feat.drop(columns=[c for c in ("region",) if c in feat.columns and c in parcel_years.columns])
    return parcel_years.merge(
        feat, left_on=["scenario", "cell_id", "year", "crop", "soil_class_soilmap"],
        right_on=["scenario", "cell_id", "year", "crop", "soil_class"], how="left", validate="many_to_one")


def to_farms(parcel_feat: pd.DataFrame, cols, weight="parcel_area_ha") -> pd.DataFrame:
    """Area-weighted mean of parcel features per farm x crop x year (the grain yields are reported at)."""
    w = parcel_feat[weight]
    num = parcel_feat[cols].mul(w, axis=0).groupby([parcel_feat["farm_id"], parcel_feat["crop"], parcel_feat["year"]]).sum(min_count=1)
    den = w.groupby([parcel_feat["farm_id"], parcel_feat["crop"], parcel_feat["year"]]).sum()
    return num.div(den, axis=0).reset_index()


class FarmAggregator:
    """Fast version of to_parcels + to_farms for a fixed set of weather series, for tuning loops.

    Precomputes, for every parcel-year, which row of `crop_features(..., idx)` it reads
    (rows are ordered soil-major, then series in `idx` order), and the farm x crop x year group.
    Each call is then a weighted bincount instead of a merge and a groupby.
    """

    def __init__(self, keys: pd.DataFrame, idx, parcel_years: pd.DataFrame):
        k = keys.iloc[idx]
        pos = pd.Series(np.arange(len(idx)),
                        index=pd.MultiIndex.from_arrays([k["scenario"].values, k["cell_id"].values, k["year"].values]))
        p = pos.reindex(pd.MultiIndex.from_arrays([parcel_years["scenario"].values, parcel_years["cell_id"].values,
                                                   parcel_years["year"].values])).values
        ok = ~np.isnan(p)
        py = parcel_years[ok]
        soil = py["soil_class_soilmap"].map({s: j for j, s in enumerate(SOILS)}).values
        self.rows = soil * len(idx) + p[ok].astype(int)
        gk = ["farm_id", "crop", "year"]
        codes, uniq = pd.factorize(pd.MultiIndex.from_frame(py[gk]))
        self.group, self.n = codes, len(uniq)
        self.keys = py[gk].drop_duplicates().reset_index(drop=True)   # same first-appearance order as factorize
        assert len(self.keys) == self.n
        self.w = py["parcel_area_ha"].values.astype(float)

    def __call__(self, feat: pd.DataFrame, cols) -> pd.DataFrame:
        X = feat[list(cols)].values.astype(float)[self.rows]
        out = self.keys.copy()
        for j, c in enumerate(cols):
            x = X[:, j]
            v = ~np.isnan(x)
            num = np.bincount(self.group[v], self.w[v] * x[v], minlength=self.n)
            den = np.bincount(self.group[v], self.w[v], minlength=self.n)
            out[c] = np.where(den > 0, num / np.maximum(den, 1e-12), np.nan)
        return out
