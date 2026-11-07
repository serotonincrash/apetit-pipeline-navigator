"""Actions for Track C: action specs, support checks and the overrides that make a what-if run.

An action never edits raw data. It takes the no-action parcel-season rows (or the crop calendar)
and changes one assumption about the future on a copy. The what-if rows are then simulated and
priced exactly like the no-action rows, against the same contracted volume.

Supported override types:
- relocate_area: move a share of a unit's area from the highest-loss farms to the lowest-loss farms
  (whole farms, ranked by expected shortfall per hectare under the same climate). Total area stays.
- set_irrigated: treat the unit's farms as irrigated. Needs an irrigation effect in the model.
- shift_sowing: move the earliest sowing date by a number of days (rebuilds the weather features).
- scale_feature: scale one model input, for example heat at flowering, by a factor.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace

import numpy as np
import pandas as pd

from navigator.analysis import climateproj as cp

SUPPORTED = {"relocate_area", "set_irrigated", "shift_sowing", "scale_feature"}


def load_catalogue(path) -> list[dict]:
    with open(path) as f:
        specs = json.load(f)
    ids = [s["action_id"] for s in specs]
    assert len(ids) == len(set(ids)), "duplicate action ids"
    return specs


def units(spec) -> list[tuple]:
    return [tuple(u) for u in spec["scope"]["units"]]


# The params each override type needs; an action that lacks one is refused, not run.
REQUIRED_PARAMS = {
    "relocate_area": ["share"],
    "set_irrigated": ["value"],
    "shift_sowing": ["days"],
    "scale_feature": ["feature", "factor"],
}


def support(spec: dict, models: dict, supported: set[str] = SUPPORTED) -> tuple[bool, str]:
    """Can the model price this action? Returns (ok, reason). `supported` narrows the override
    types the caller can run, for callers that cannot rebuild the crop calendar."""
    override = spec.get("override") or {}
    t = override.get("type")
    if t not in supported or t not in REQUIRED_PARAMS:
        return False, f"override type '{t}' is not implemented"
    missing = [p for p in REQUIRED_PARAMS[t] if override.get(p) is None]
    if missing:
        return False, f"the {t} override has no {', '.join(missing)}"
    try:
        scope = units(spec)
    except (KeyError, TypeError, ValueError):
        return False, "the scope does not list region and crop pairs"
    if not scope:
        return False, "the scope lists no region and crop"
    for r, c in scope:
        if f"{r}/{c}" not in models:
            return False, f"there is no yield model for {r}/{c}"
        beta = models[f"{r}/{c}"]["beta"]
        if t == "set_irrigated" and beta.get("drought_x_irr", 0) == 0:
            return (
                False,
                f"no irrigation effect in the {r}/{c} model: "
                "these growers never irrigate in the data",
            )
        if t == "scale_feature" and beta.get(override["feature"], 0) == 0:
            return False, f"the {r}/{c} model gives {override['feature']} no effect"
    return True, ""


def farm_loss(rows: pd.DataFrame, normal_yield: float) -> pd.Series:
    """Expected shortfall per hectare for each farm, from expected yields (no noise), per
    scenario."""
    t = rows.assign(t=rows["parcel_area_ha"] * np.exp(rows["log_yield"]))
    g = t.groupby(["scenario", "year", "farm_id"])[["t", "parcel_area_ha"]].sum()
    y = g["t"] / g["parcel_area_ha"]
    return (normal_yield - y).clip(lower=0).groupby(["scenario", "farm_id"]).mean()


def relocate(rows: pd.DataFrame, share: float, normal_yield: float) -> tuple[pd.DataFrame, dict]:
    """Move `share` of the area from the highest-loss farms to the lowest-loss farms, per
    scenario."""
    out, moved = [], {}
    loss = farm_loss(rows, normal_yield)
    for scen, x in rows.groupby("scenario", sort=False):
        x = x.copy()
        area = x.drop_duplicates("parcel_id").groupby("farm_id")["parcel_area_ha"].sum()
        order = loss.loc[scen].reindex(area.index).sort_values(ascending=False)
        total = area.sum()
        drop = order.index[
            (area.reindex(order.index).cumsum().shift(fill_value=0) < share * total).values
        ]
        moved_ha = area[drop].sum()
        keep_order = order.drop(drop).sort_values()
        recv = keep_order.index[
            (area.reindex(keep_order.index).cumsum().shift(fill_value=0) < moved_ha).values
        ]
        factor = 1 + moved_ha / area[recv].sum()
        x.loc[x["farm_id"].isin(drop), "parcel_area_ha"] = 0.0
        x.loc[x["farm_id"].isin(recv), "parcel_area_ha"] *= factor
        moved[scen] = {
            "moved_ha": float(moved_ha),
            "share": float(moved_ha / total),
            "farms_dropped": len(drop),
            "farms_receiving": len(recv),
        }
        out.append(x)
    return pd.concat(out, ignore_index=True), moved


def apply_override(
    spec,
    rows: pd.DataFrame,
    model: dict,
    normal_yield: float,
    rebuild: Callable[[int], pd.DataFrame] | None = None,
):
    """Return (what-if rows, details) for one unit. `rebuild(params_change)` rebuilds rows from the
    weather for overrides that change the crop calendar."""
    o = spec["override"]
    if o["type"] == "relocate_area":
        return relocate(rows, o["share"], normal_yield)
    if o["type"] == "set_irrigated":
        x = rows.copy()
        x["irrigated"] = float(o["value"])
        return cp.with_log_yield(x, model), {}
    if o["type"] == "scale_feature":
        x = rows.copy()
        x[o["feature"]] = x[o["feature"]] * o["factor"]
        return cp.with_log_yield(x, model), {}
    if o["type"] == "shift_sowing":
        if rebuild is None:
            raise ValueError("shift_sowing needs `rebuild` to rebuild rows from the weather")
        return rebuild(o["days"]), {}
    raise ValueError(o["type"])


def shifted_params(params, days: int):
    """Crop parameters with the earliest sowing date moved by `days`."""
    d = pd.Timestamp(f"2001-{params.sow_earliest}") + pd.Timedelta(days=days)
    return replace(params, sow_earliest=d.strftime("%m-%d"))
