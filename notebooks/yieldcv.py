"""Leave-one-year-out cross-validation of within-farm yield models (used to tune crop parameters).

Model: log(yield) = farm level + features . beta (ridge on standardised, farm-demeaned features).
The baseline is the farm's own mean log yield over the training years, i.e. the package's C1
'farm historical mean' baseline.
"""
import numpy as np
import pandas as pd


def _fit(X, y, lam, X_raw=None, min_support=0.05):
    """Ridge on standardised columns. Columns that are non-zero in fewer than `min_support` of the
    *raw* rows (e.g. an 'immature' flag that fires in one season) get beta = 0: with so little
    support a coefficient is noise, and it explodes when a held-out year has a large value."""
    support = (np.abs(X if X_raw is None else X_raw) > 1e-9).mean(0)
    sd = X.std(0)
    use = (support >= min_support) & (sd > 1e-9)
    beta = np.zeros(X.shape[1])
    if use.any():
        Xs = X[:, use] / sd[use]
        beta[use] = np.linalg.solve(Xs.T @ Xs + lam * len(y) * np.eye(use.sum()), Xs.T @ y) / sd[use]
    return beta


def loyo(df: pd.DataFrame, cols, lam=0.01, min_train_years=3):
    """Returns (summary dict, per-row predictions). Rows need farm_id, year, yield_t_ha and `cols`.

    For each season: farm means and coefficients come from the other seasons only; the held-out
    season is predicted as farm mean + (features - farm's mean features) . beta.
    Farms with fewer than `min_train_years` training seasons do not inform beta.
    """
    df = df.dropna(subset=list(cols) + ["yield_t_ha"]).reset_index(drop=True)
    y = np.log(df["yield_t_ha"].values)
    X = df[list(cols)].values.astype(float)
    f, _ = pd.factorize(df["farm_id"])
    nf, years = f.max() + 1, df["year"].values
    pred = np.full(len(df), np.nan)
    base = np.full(len(df), np.nan)
    for yr in np.unique(years):
        tr = years != yr
        cnt = np.bincount(f[tr], minlength=nf)
        my = np.bincount(f[tr], y[tr], minlength=nf) / np.maximum(cnt, 1)
        mx = np.stack([np.bincount(f[tr], X[tr, k], minlength=nf) for k in range(X.shape[1])], 1) / np.maximum(cnt, 1)[:, None]
        ft = f[tr]
        keep = cnt[ft] >= min_train_years
        beta = _fit((X[tr] - mx[ft])[keep], (y[tr] - my[ft])[keep], lam, X_raw=X[tr][keep])
        te = np.where(~tr & (cnt[f] > 0))[0]
        base[te] = my[f[te]]
        pred[te] = base[te] + (X[te] - mx[f[te]]) @ beta
    ok = ~np.isnan(pred)
    rmse = lambda e: float(np.sqrt(np.mean(e ** 2)))
    out = df.assign(log_pred=pred, log_base=base)
    summary = {"n": int(ok.sum()), "rmse_log": rmse(y[ok] - pred[ok]), "rmse_log_baseline": rmse(y[ok] - base[ok])}
    summary["improvement_pct"] = 100 * (1 - summary["rmse_log"] / summary["rmse_log_baseline"])
    return summary, out


def fit_coefficients(df, cols, lam=0.01):
    """Full-sample within-farm fit, for interpretation (effect of +1 SD of each feature, in % yield)."""
    df = df.dropna(subset=list(cols) + ["yield_t_ha"])
    y = np.log(df["yield_t_ha"].values)
    X = df[list(cols)].values.astype(float)
    xm = pd.DataFrame(X).groupby(df["farm_id"].values).transform("mean").values
    ym = pd.Series(y).groupby(df["farm_id"].values).transform("mean").values
    beta = _fit(X - xm, y - ym, lam, X_raw=X)
    sd = (X - xm).std(0)
    return pd.DataFrame({"feature": list(cols), "beta": beta,
                         "effect_of_1sd_pct": 100 * (np.exp(beta * sd) - 1)}).set_index("feature")


# Model specification shared by the tuning step and the modelling notebook.
# Interactions follow the truth-model description: irrigation mitigates drought, sprays mitigate blight.
COMMON_FEATURES = ["drought_stage", "drought_x_irr", "drought_early", "heat_days_27", "waterlog_clay",
                   "harvest_rain_14_mm", "immature_gap", "year_c", "n_mineral_100"]
CROP_EXTRA_FEATURES = {"potato": ["blight_days", "blight_x_sprays"], "turnip_rape": ["may_tmean_c"]}


def model_features(crop):
    return COMMON_FEATURES + CROP_EXTRA_FEATURES.get(crop, [])


def add_model_columns(df):
    df = df.copy()
    irrigated = pd.to_numeric(df["irrigated"], errors="coerce").astype(float)
    df["drought_x_irr"] = df["drought_stage"] * irrigated
    df["blight_x_sprays"] = df["blight_days"] * pd.to_numeric(df["sprays"], errors="coerce").fillna(0.0)
    df["year_c"] = df["year"] - 2019
    df["n_mineral_100"] = df["n_mineral_kg_ha"] / 100
    return df
