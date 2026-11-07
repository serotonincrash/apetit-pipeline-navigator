"""Yield model for Track C: fit, predict and describe the uncertainty.

One model per region and crop:

    log(yield) = farm level + features . beta + error

beta is fitted within farms (each farm compared with itself across seasons), the same way the crop
calendar was tuned. The farm level is the farm's average of what the features leave unexplained,
pulled towards the region-crop average when the farm has few seasons. Farms with no history get
the region-crop average.

The error is split into a part shared by all farms in a season (weather the features miss) and a
part that differs farm by farm. The risk step needs both: the shared part moves the whole supply,
the farm part mostly averages out.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from navigator.analysis import yieldcv as cv

# Field features: they vary between a farm's parcels, so the within-farm fit can estimate them,
# and they are what lets predictions differ parcel by parcel.
SOIL_FEATURES = ["organic_share_soilmap", "sandy_share", "clay_pct_wavg", "slope_pct_wavg"]
MANAGEMENT = ["n_mineral_kg_ha", "irrigated", "sprays"]


def features(crop: str) -> list[str]:
    return cv.model_features(crop) + SOIL_FEATURES


def fit(df: pd.DataFrame, cols, lam: float = 0.01, shrink_seasons: float = 2.0) -> dict:
    """Fit one region-crop unit on farm-year rows (needs farm_id, year, yield_t_ha and `cols`)."""
    d = df.dropna(subset=[*cols, "yield_t_ha"]).reset_index(drop=True)
    y = np.log(d["yield_t_ha"].values)
    X = d[list(cols)].values.astype(float)
    farm = d["farm_id"].to_numpy()
    xm = pd.DataFrame(X).groupby(farm).transform("mean").values
    ym = pd.Series(y).groupby(farm).transform("mean").values
    beta = cv._fit(X - xm, y - ym, lam, X_raw=X)

    level = pd.Series(y - X @ beta).groupby(farm).agg(["mean", "size"])
    mu = float(np.average(level["mean"], weights=level["size"]))
    k = shrink_seasons
    farm_level = (level["size"] * level["mean"] + k * mu) / (level["size"] + k)

    resid = y - farm_level.reindex(farm).values - X @ beta
    year_mean = pd.Series(resid).groupby(d["year"].to_numpy()).mean()
    within = resid - d["year"].map(year_mean).values
    sd = float(resid.std())
    return {
        "features": list(cols),
        "beta": dict(zip(cols, beta.tolist(), strict=True)),
        "farm_level": farm_level.to_dict(),
        "mean_level": mu,
        "n_rows": len(d),
        "n_farms": len(level),
        "resid_sd": sd,
        "resid_sd_shared": float(year_mean.std()),
        "resid_sd_farm": float(within.std()),
        "smearing": float(
            np.mean(np.exp(resid))
        ),  # Duan's factor: turns exp(log prediction) into an unbiased mean
        "lam": lam,
        "shrink_seasons": k,
    }


def predict(model: dict, df: pd.DataFrame) -> pd.Series:
    """Expected yield (t/ha) for rows with farm_id and the model's features."""
    cols = model["features"]
    X = df[cols].values.astype(float)
    b = np.array([model["beta"][c] for c in cols])
    level = df["farm_id"].map(model["farm_level"]).fillna(model["mean_level"]).values
    return pd.Series(np.exp(level + X @ b) * model["smearing"], index=df.index)


def management_defaults(
    history: pd.DataFrame, last_n: int = 3
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Management inputs to assume for future seasons: each farm's average over its last `last_n`
    surveyed seasons for that crop, else the region-crop median. Returns one row per farm and
    crop, and the medians per region and crop."""
    h = history.sort_values("year").groupby(["region", "farm_id", "crop"]).tail(last_n)
    per_farm = (
        h.groupby(["region", "farm_id", "crop"])[MANAGEMENT].mean(numeric_only=True).reset_index()
    )
    per_unit = history.groupby(["region", "crop"])[MANAGEMENT].median(numeric_only=True)
    return per_farm, per_unit


def parcel_soil_features(parcels: pd.DataFrame) -> pd.DataFrame:
    """The farm-level soil features, written for a single parcel."""
    s = parcels["soil_class_soilmap"]
    return pd.DataFrame(
        {
            "organic_share_soilmap": s.eq("organic").astype(float),
            "sandy_share": s.isin(["sand", "fine_sand"]).astype(float),
            "clay_pct_wavg": parcels["clay_pct_soilmap"].astype(float),
            "slope_pct_wavg": parcels["slope_pct"].astype(float),
        },
        index=parcels.index,
    )
