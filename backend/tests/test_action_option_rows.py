"""The runner's swap of names for ids for action options, and the action support check, tested
without a database or the challenge package."""

import pandas as pd
import pytest

from navigator.analysis import actions as ac
from navigator.recipes.core import ACTION_OPTION_COLUMNS
from navigator.worker.runner import build_action_option_rows

ASSUMPTIONS = {"compare_actions.action_cost.A1": "asm_1"}


def option(**changes: object) -> dict[str, object]:
    row: dict[str, object] = {
        "key": "A1|baseline",
        "action_id": "A1",
        "name": "Move area",
        "scenario": "baseline",
        "region": "FI_SW",
        "crop": None,
        "cost_eur_per_yr": float("nan"),
        "risk_reduced_eur_per_yr": 36000.0,
        "emissions_change_t": -76.0,
        "assumptions": ["compare_actions.action_cost.A1"],
        "confidence": "low",
    }
    return row | changes


def build(*rows: dict[str, object], known: set[str] | None = None):
    frame = pd.DataFrame(list(rows), columns=ACTION_OPTION_COLUMNS)
    return build_action_option_rows([frame], "rs_1", "run_1", ASSUMPTIONS, known or {"A1"})


def test_an_option_gets_the_result_set_run_and_assumption_ids() -> None:
    (row,) = build(option())
    assert (row.result_set_id, row.run_id, row.assumption_ids) == ("rs_1", "run_1", ["asm_1"])
    assert row.option_id.startswith("opt_")
    assert row.scenario == "baseline" and row.crop is None
    assert row.cost_eur_per_yr is None


def test_an_option_for_an_unknown_action_is_a_plain_error() -> None:
    with pytest.raises(ValueError, match="not in the action catalogue"):
        build(option(action_id="A2"))


def test_a_repeated_key_or_unknown_assumption_is_a_plain_error() -> None:
    with pytest.raises(ValueError, match="used twice"):
        build(option(), option())
    with pytest.raises(ValueError, match="no step recorded"):
        build(option(assumptions=["compare_actions.action_cost.A2"]))


def test_a_table_without_the_option_columns_is_refused() -> None:
    with pytest.raises(ValueError, match="no scenario column"):
        build_action_option_rows(
            [
                pd.DataFrame({"key": ["k"]}).reindex(
                    columns=[c for c in ACTION_OPTION_COLUMNS if c != "scenario"]
                )
            ],
            "rs_1",
            "run_1",
            ASSUMPTIONS,
            {"A1"},
        )


MODELS = {"FI_SW/pea": {"beta": {"heat_days_27": -0.1, "drought_x_irr": 0.0}}}


def spec(override: dict[str, object], units: list[list[str]] | None = None) -> dict[str, object]:
    return {"override": override, "scope": {"units": units or [["FI_SW", "pea"]]}}


def test_support_names_the_reason_for_each_refusal() -> None:
    runnable = {"relocate_area", "set_irrigated", "scale_feature"}
    ok, why = ac.support(spec({"type": "shift_sowing", "days": -7}), MODELS, runnable)
    assert (ok, why) == (False, "override type 'shift_sowing' is not implemented")
    assert ac.support(spec({"type": "shift_sowing", "days": -7}), MODELS) == (True, "")
    assert "no share" in ac.support(spec({"type": "relocate_area"}), MODELS)[1]
    assert (
        "no yield model for XX/pea"
        in ac.support(spec({"type": "relocate_area", "share": 0.2}, [["XX", "pea"]]), MODELS)[1]
    )
    assert "never irrigate" in ac.support(spec({"type": "set_irrigated", "value": 1.0}), MODELS)[1]
    scale = {"type": "scale_feature", "feature": "heat_days_27", "factor": 0.7}
    assert ac.support(spec(scale), MODELS) == (True, "")
