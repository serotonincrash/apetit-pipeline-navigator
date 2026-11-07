"""Recipe steps, one module per step. Importing this package registers them all."""

from navigator.steps import (
    apply_approved,
    check_farm_data,
    compare_actions,
    explain_proposals,
    fit_yield_model,
    load_raw,
    price_risk,
    project_yields,
    propose_fixes,
    spatial_join,
    tune_calendar,
    weather_features,
)

__all__ = [
    "apply_approved",
    "check_farm_data",
    "compare_actions",
    "explain_proposals",
    "fit_yield_model",
    "load_raw",
    "price_risk",
    "project_yields",
    "propose_fixes",
    "spatial_join",
    "tune_calendar",
    "weather_features",
]
