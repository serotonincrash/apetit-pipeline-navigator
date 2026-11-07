"""A run's metrics and insights reach the database with its result set, or not at all."""

import pandas as pd
import pytest
from sqlalchemy import func, select

from navigator.db import models as m
from navigator.db.session import session_scope
from navigator.recipes.core import (
    METRIC_COLUMNS,
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

KEY = "price_risk.expected_cost_eur|FI_SW|pea"


def metric_step(cited_key: str) -> StepFunction:
    def result_step(ctx: RunContext, inputs: dict[str, Artifact], params: Params) -> StepResult:
        metric = {
            "key": KEY,
            "name": "price_risk.expected_cost_eur",
            "unit": "€ per year",
            "value": 36000.0,
            "low": None,
            "high": None,
            "region": "FI_SW",
            "crop": "pea",
            "scenario": None,
            "ngfs_scenario": None,
            "period": None,
            "action_id": None,
            "lineage": [{"table": "climate_risk", "filter": {"crop": "pea"}}],
            "assumptions": ["price_risk.price_year"],
        }
        insight = {
            "title": "Cost of Finnish pea",
            "text": "It costs {{metric:" + cited_key + "}} a year.",
            "metric_keys": [cited_key],
        }
        return StepResult(
            tables=[Artifact("climate_risk", "result", pd.DataFrame({"crop": ["pea"]}))],
            metrics=pd.DataFrame([metric], columns=METRIC_COLUMNS),
            insights=pd.DataFrame([insight]),
            assumptions=[AssumptionUse("price_risk.price_year", "Price year", 2025, "year", "x")],
        )

    return result_step


def run_with(monkeypatch: pytest.MonkeyPatch, cited_key: str) -> str:
    info = StepInfo("result_step", "transform", "Writes one metric.", metric_step(cited_key))
    monkeypatch.setitem(STEPS, "result_step", info)
    recipe = Recipe("farm_climate_risk", 2, "Test", (StepSpec("result_step", inputs=()),))
    monkeypatch.setattr(runner, "get_recipe", lambda _: recipe)
    run_id = add_run("running")
    runner.execute_run(run_id)
    return run_id


def test_a_succeeded_run_writes_its_result_set_metrics_and_insights(
    monkeypatch: pytest.MonkeyPatch, storage: str
) -> None:
    run_id = run_with(monkeypatch, KEY)
    with session_scope() as session:
        assert session.get_one(m.Run, run_id).status == "succeeded"
        result_set = session.scalars(select(m.ResultSet).where(m.ResultSet.run_id == run_id)).one()
        metric = session.scalars(select(m.Metric)).one()
        insight = session.scalars(select(m.Insight)).one()
        artifact = session.scalars(select(m.Artifact)).one()
        assumption = session.scalars(select(m.Assumption)).one()
        assert metric.result_set_id == result_set.result_set_id
        assert metric.lineage == [{"artifact": artifact.artifact_id, "filter": {"crop": "pea"}}]
        assert metric.assumption_ids == [assumption.assumption_id]
        assert insight.step == "result_step"
        assert insight.text == "It costs {{metric:" + metric.metric_id + "}} a year."
        assert insight.metric_ids == [metric.metric_id]


def test_a_run_that_cannot_store_its_results_leaves_none(
    monkeypatch: pytest.MonkeyPatch, storage: str
) -> None:
    run_id = run_with(monkeypatch, "no_such_metric")
    with session_scope() as session:
        run = session.get_one(m.Run, run_id)
        assert run.status == "failed"
        assert "no_such_metric" in (run.error or "")
        for table in (m.ResultSet, m.Metric, m.Insight):
            assert session.scalar(select(func.count()).select_from(table)) == 0
