"""Approved actions reach step 10, and the options it prices land with the result set."""

from typing import Any

import pandas as pd
import pytest
from sqlalchemy import func, select

from navigator import ids
from navigator.db import models as m
from navigator.db.session import session_scope
from navigator.recipes.core import (
    ACTION_OPTION_COLUMNS,
    ACTIONS_INPUT,
    STEPS,
    Artifact,
    AssumptionUse,
    Params,
    Recipe,
    RunContext,
    StepFunction,
    StepInfo,
    StepResult,
    StepSpec,
)
from navigator.worker import runner
from tests.api.records import add_run

pytestmark = pytest.mark.api

APPROVED = "A1-approved"
NEVER_DECIDED = "A2-never-decided"
APPROVED_THEN_REJECTED = "A3-approved-then-rejected"
REJECTED = "A4-rejected"
REAPPROVED = "A5-rejected-then-approved"


def add_action(action_id: str, *decisions: str) -> None:
    with session_scope() as session:
        session.add(
            m.ActionDefinition(
                action_id=action_id,
                name=f"Name of {action_id}",
                short_name=f"Short {action_id}",
                driver="heat at flowering, Finnish pea",
                applies_at="project_yields",
                override={"type": "scale_feature", "feature": "heat_days_27", "factor": 0.7},
                scope={"units": [["FI_SW", "pea"]]},
                cost={"eur_per_year": None, "source": "not in the package"},
                confidence="low",
                proposed_by="catalogue",
            )
        )
    for decision in decisions:
        with session_scope() as session:
            session.add(
                m.Decision(
                    decision_id=ids.new_id("decision"),
                    target_type="action",
                    target_id=action_id,
                    decision=decision,
                    reviewer="Catalogue policy",
                )
            )


def option_step(received: list[pd.DataFrame], option_action_ids: list[str]) -> StepFunction:
    def price_actions(ctx: RunContext, inputs: dict[str, Artifact], params: Params) -> StepResult:
        actions = inputs[ACTIONS_INPUT].frame
        received.append(actions)
        rows: list[dict[str, Any]] = []
        for action_id in option_action_ids or actions["action_id"].tolist():
            for scenario in ("baseline", "ssp585"):
                rows.append(
                    {
                        "key": f"{action_id}|{scenario}",
                        "action_id": action_id,
                        "name": f"Name of {action_id}",
                        "scenario": scenario,
                        "region": "FI_SW",
                        "crop": "pea",
                        "cost_eur_per_yr": None,
                        "risk_reduced_eur_per_yr": 36000.0,
                        "emissions_change_t": -76.0,
                        "assumptions": [f"compare_actions.action_cost.{action_id}"],
                        "confidence": "low",
                    }
                )
        return StepResult(
            tables=[Artifact("action_results", "result", pd.DataFrame({"x": [1]}))],
            action_options=pd.DataFrame(rows, columns=ACTION_OPTION_COLUMNS),
            assumptions=[
                AssumptionUse(
                    f"compare_actions.action_cost.{action_id}", "Cost", None, "€ per year", "x"
                )
                for action_id in actions["action_id"]
            ],
        )

    return price_actions


def run_with(
    monkeypatch: pytest.MonkeyPatch, received: list[pd.DataFrame], option_ids: list[str]
) -> str:
    info = StepInfo("price_actions", "model", "Prices actions.", option_step(received, option_ids))
    monkeypatch.setitem(STEPS, "price_actions", info)
    recipe = Recipe(
        "farm_climate_risk", 3, "Test", (StepSpec("price_actions", inputs=(ACTIONS_INPUT,)),)
    )
    monkeypatch.setattr(runner, "get_recipe", lambda _: recipe)
    run_id = add_run("running")
    runner.execute_run(run_id)
    return run_id


def add_actions() -> None:
    add_action(APPROVED, "approve")
    add_action(NEVER_DECIDED)
    add_action(APPROVED_THEN_REJECTED, "approve", "reject")
    add_action(REJECTED, "reject")
    add_action(REAPPROVED, "reject", "approve")


def test_only_actions_whose_latest_decision_is_an_approval_reach_the_step(
    monkeypatch: pytest.MonkeyPatch, storage: str
) -> None:
    add_actions()
    received: list[pd.DataFrame] = []
    run_with(monkeypatch, received, [])
    (actions,) = received
    assert actions["action_id"].tolist() == [APPROVED, REAPPROVED]
    assert list(actions.columns) == runner.ACTION_COLUMNS
    first = actions.iloc[0]
    assert first["override"] == {"type": "scale_feature", "feature": "heat_days_27", "factor": 0.7}
    assert first["scope"] == {"units": [["FI_SW", "pea"]]}
    assert first["cost"] == {"eur_per_year": None, "source": "not in the package"}
    assert first["proposed_by"] == "catalogue"


def test_a_run_with_no_approved_action_gives_the_step_an_empty_table(
    monkeypatch: pytest.MonkeyPatch, storage: str
) -> None:
    add_action(NEVER_DECIDED)
    received: list[pd.DataFrame] = []
    run_id = run_with(monkeypatch, received, [])
    assert received[0].empty
    with session_scope() as session:
        assert session.get_one(m.Run, run_id).status == "succeeded"
        assert session.scalar(select(func.count()).select_from(m.ActionOption)) == 0


def test_options_land_with_the_result_set(monkeypatch: pytest.MonkeyPatch, storage: str) -> None:
    add_actions()
    run_id = run_with(monkeypatch, [], [])
    with session_scope() as session:
        assert session.get_one(m.Run, run_id).status == "succeeded"
        result_set = session.scalars(select(m.ResultSet)).one()
        options = session.scalars(
            select(m.ActionOption).order_by(m.ActionOption.action_id, m.ActionOption.scenario)
        ).all()
        assumptions = {a.name: a.assumption_id for a in session.scalars(select(m.Assumption))}
        assert [(o.action_id, o.scenario) for o in options] == [
            (APPROVED, "baseline"),
            (APPROVED, "ssp585"),
            (REAPPROVED, "baseline"),
            (REAPPROVED, "ssp585"),
        ]
        for option in options:
            assert option.result_set_id == result_set.result_set_id
            assert option.run_id == run_id
            assert option.option_id.startswith("opt_")
            assert option.cost_eur_per_yr is None
            assert option.risk_reduced_eur_per_yr == 36000.0
            assert option.emissions_change_t == -76.0
            assert option.assumption_ids == [
                assumptions[f"compare_actions.action_cost.{option.action_id}"]
            ]


def test_an_option_for_an_unknown_action_stops_the_run_and_leaves_no_results(
    monkeypatch: pytest.MonkeyPatch, storage: str
) -> None:
    add_actions()
    run_id = run_with(monkeypatch, [], ["A9-not-in-the-catalogue"])
    with session_scope() as session:
        run = session.get_one(m.Run, run_id)
        assert run.status == "failed"
        assert "A9-not-in-the-catalogue" in (run.error or "")
        assert "not in the action catalogue" in (run.error or "")
        for table in (m.ResultSet, m.ActionOption):
            assert session.scalar(select(func.count()).select_from(table)) == 0
