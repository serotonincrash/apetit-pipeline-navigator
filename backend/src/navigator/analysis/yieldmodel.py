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

from typing import Any

import numpy as np
import pandas as pd

from navigator.analysis import yieldcv as cv

# Field features: they vary between a farm's parcels, so the within-farm fit can estimate them,
# and they are what lets predictions differ parcel by parcel.
SOIL_FEATURES = ["organic_share_soilmap", "sandy_share", "clay_pct_wavg", "slope_pct_wavg"]
MANAGEMENT = ["n_mineral_kg_ha", "irrigated", "sprays"]

# A fitted model, as `fit` returns it.
Model = dict[str, Any]


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


def backtest(
    df: pd.DataFrame, unit: tuple[str, str], lam: float = 0.01, shrink_seasons: float = 2.0
) -> pd.DataFrame:
    """Refit one region-crop unit without each season in turn and predict that season.

    The comparison is each farm's own average yield in the other seasons. Returns one row per
    season with the farms that have a history, the actual, model and baseline production, and
    both production errors in per cent."""
    r, c = unit
    cols = features(c)
    d = df[df["region"].eq(r) & df["crop"].eq(c)].dropna(subset=[*cols, "yield_t_ha"])
    rows = []
    for yr in sorted(d["year"].unique()):
        tr, te = d[d["year"] != yr], d[d["year"] == yr]
        pred = predict(fit(tr, cols, lam, shrink_seasons), te)
        base = te["farm_id"].map(tr.groupby("farm_id")["yield_t_ha"].mean())
        ok = base.notna()
        te, pred, base = te[ok], pred[ok], base[ok]
        a = te["area_ha"]
        rows.append(
            {
                "region": r,
                "crop": c,
                "year": yr,
                "farms": len(te),
                "area_ha": a.sum(),
                "actual_t": (a * te["yield_t_ha"]).sum(),
                "model_t": (a * pred).sum(),
                "baseline_t": (a * base).sum(),
                "farm_rmse_model": np.sqrt(((te["yield_t_ha"] - pred) ** 2).mean()),
                "farm_rmse_baseline": np.sqrt(((te["yield_t_ha"] - base) ** 2).mean()),
                "mean_yield": te["yield_t_ha"].mean(),
            }
        )
    bt = pd.DataFrame(rows)
    bt["production_error_model_pct"] = 100 * (bt["model_t"] / bt["actual_t"] - 1)
    bt["production_error_baseline_pct"] = 100 * (bt["baseline_t"] / bt["actual_t"] - 1)
    return bt


def backtest_summary(bt: pd.DataFrame) -> pd.DataFrame:
    """Per region and crop: seasons, mean absolute production error of the model and of the farm
    average (in per cent), and the farm-level errors as a share of the mean yield."""
    g = bt.groupby(["region", "crop"], sort=False)
    return pd.DataFrame(
        {
            "seasons": g.size(),
            "production error, model (%)": g["production_error_model_pct"].apply(
                lambda s: s.abs().mean()
            ),
            "production error, baseline (%)": g["production_error_baseline_pct"].apply(
                lambda s: s.abs().mean()
            ),
            "farm error, model (% of mean)": 100
            * g["farm_rmse_model"].mean()
            / g["mean_yield"].mean(),
            "farm error, baseline (% of mean)": 100
            * g["farm_rmse_baseline"].mean()
            / g["mean_yield"].mean(),
        }
    )


def model_tables(
    models: dict[tuple[str, str], Model],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """The fitted models, keyed by (region, crop), as three tables: coefficients (one row per
    feature, in the model's feature order), fit (one row per model) and farm levels."""
    coefficients, fits, levels = [], [], []
    for (region, crop), m in models.items():
        for feature in m["features"]:
            coefficients.append(
                {
                    "region": region,
                    "crop": crop,
                    "feature": feature,
                    "coefficient": m["beta"][feature],
                }
            )
        fits.append(
            {
                "region": region,
                "crop": crop,
                "mean_level": m["mean_level"],
                "smearing": m["smearing"],
                "resid_sd": m["resid_sd"],
                "resid_sd_shared": m["resid_sd_shared"],
                "resid_sd_farm": m["resid_sd_farm"],
                "n_rows": m["n_rows"],
                "n_farms": m["n_farms"],
                "lam": m["lam"],
                "shrink_seasons": m["shrink_seasons"],
            }
        )
        levels.extend(
            {"region": region, "crop": crop, "farm_id": farm, "level": level}
            for farm, level in m["farm_level"].items()
        )
    return pd.DataFrame(coefficients), pd.DataFrame(fits), pd.DataFrame(levels)


def models_from_tables(
    coefficients: pd.DataFrame, fit_table: pd.DataFrame, farm_levels: pd.DataFrame
) -> dict[tuple[str, str], Model]:
    """The inverse of `model_tables`: the model dicts that `predict` and `climateproj` take."""
    models = {}
    for row in fit_table.to_dict("records"):
        unit = (str(row["region"]), str(row["crop"]))
        mine = coefficients[coefficients["region"].eq(unit[0]) & coefficients["crop"].eq(unit[1])]
        levels = farm_levels[farm_levels["region"].eq(unit[0]) & farm_levels["crop"].eq(unit[1])]
        models[unit] = {
            "features": [str(f) for f in mine["feature"]],
            "beta": {
                str(f): float(b) for f, b in zip(mine["feature"], mine["coefficient"], strict=True)
            },
            "farm_level": {
                str(f): float(v) for f, v in zip(levels["farm_id"], levels["level"], strict=True)
            },
            "mean_level": float(row["mean_level"]),
            "n_rows": int(row["n_rows"]),
            "n_farms": int(row["n_farms"]),
            "resid_sd": float(row["resid_sd"]),
            "resid_sd_shared": float(row["resid_sd_shared"]),
            "resid_sd_farm": float(row["resid_sd_farm"]),
            "smearing": float(row["smearing"]),
            "lam": float(row["lam"]),
            "shrink_seasons": float(row["shrink_seasons"]),
        }
    return models
