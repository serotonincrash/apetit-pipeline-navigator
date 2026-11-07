"""Golden tests for steps 5 and 6: the tuned crop calendar and the weather features reproduce
`notebooks/c1_weather_features.ipynb`."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from navigator.recipes.core import Artifact, RunContext
from navigator.recipes.farm_climate_risk import RECIPE
from navigator.steps.tune_calendar import tune_calendar
from navigator.steps.weather_features import weather_features
from tests.golden.fingerprint import as_read_from_csv, assert_matches

pytestmark = pytest.mark.golden

RESULTS = Path(__file__).parents[3] / "notebooks" / "results"


def recipe_params(name: str) -> dict:
    return dict(next(s for s in RECIPE.steps if s.name == name).params)


@pytest.fixture(scope="session")
def upstream(clean_tables: dict[str, Artifact]) -> dict[str, Artifact]:
    """The tables steps 5 and 6 read, as steps 1 to 4 wrote them."""
    names = (
        "weather_daily",
        "erp_purchase_lines",
        "c1_template",
        "training_table",
        "parcel_year_contract",
    )
    return {name: clean_tables[name] for name in names}


@pytest.fixture(scope="session")
def calendar(ctx: RunContext, upstream: dict[str, Artifact]) -> dict[str, pd.DataFrame]:
    names = ("weather_daily", "training_table", "parcel_year_contract", "erp_purchase_lines")
    result = tune_calendar(ctx, {n: upstream[n] for n in names}, recipe_params("tune_calendar"))
    return {t.name: t.frame for t in result.tables}


@pytest.fixture(scope="session")
def features(
    ctx: RunContext, upstream: dict[str, Artifact], calendar: dict[str, pd.DataFrame]
) -> dict[str, pd.DataFrame]:
    names = ("weather_daily", "training_table", "parcel_year_contract", "c1_template")
    inputs = {n: upstream[n] for n in names}
    inputs["crop_params"] = Artifact("crop_params", "feature", calendar["crop_params"])
    result = weather_features(ctx, inputs, recipe_params("weather_features"))
    return {t.name: t.frame for t in result.tables}


def test_calendar_choice(calendar: dict[str, pd.DataFrame]) -> None:
    # The notebook rounds the choice to 6 decimals before writing it.
    actual = as_read_from_csv(calendar["calendar_choice"].round(6))
    expected = pd.read_csv(RESULTS / "calendar_choice.csv")
    assert list(actual.columns) == list(expected.columns)
    assert len(actual) == len(expected)
    for column in expected.columns:
        if pd.api.types.is_float_dtype(expected[column]):
            np.testing.assert_allclose(actual[column], expected[column], rtol=1e-9, err_msg=column)
        else:
            assert actual[column].tolist() == expected[column].tolist(), column


def test_crop_params(calendar: dict[str, pd.DataFrame]) -> None:
    expected = json.loads((RESULTS / "crop_params.json").read_text())["crop_params"]
    actual = {}
    for row in calendar["crop_params"].to_dict("records"):
        fields = {k: v for k, v in row.items() if k != "region"}
        for window in ("flower", "sensitive"):
            fields[window] = [fields.pop(f"{window}_start"), fields.pop(f"{window}_end")]
        actual[f"{row['region']}/{row['crop']}"] = fields
    assert actual == expected


def test_calendar_tuning(calendar: dict[str, pd.DataFrame]) -> None:
    assert_matches("calendar_tuning", as_read_from_csv(calendar["calendar_tuning"]))


def test_weather_features_cell(features: dict[str, pd.DataFrame]) -> None:
    assert_matches("weather_features_cell", features["weather_features_cell"])


def test_parcel_year_features(features: dict[str, pd.DataFrame]) -> None:
    assert_matches("parcel_year_features", features["parcel_year_features"])


def test_model_table(features: dict[str, pd.DataFrame]) -> None:
    assert_matches("model_table", as_read_from_csv(features["model_table"]))
