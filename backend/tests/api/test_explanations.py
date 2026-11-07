"""Explanations are stored on the run's proposals by the real runner, and carry over to the next."""

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from navigator.agents.schemas import Explanation
from navigator.db import models as m
from navigator.db.session import session_scope
from navigator.llm import models as llm_models
from navigator.recipes.core import (
    PROPOSAL_COLUMNS,
    PROPOSALS_INPUT,
    STEPS,
    Artifact,
    Params,
    Recipe,
    RunContext,
    StepInfo,
    StepResult,
    StepSpec,
)
from navigator.steps import explain_proposals as _explain_step  # noqa: F401  (registers the step)
from navigator.worker import runner
from tests.api.conftest import PERSONA
from tests.api.records import add_run

pytestmark = pytest.mark.api

KEYS = ["farm_survey:FS1", "farm_survey:FS2"]


def two_proposals(ctx: RunContext, inputs: dict[str, Artifact], params: Params) -> StepResult:
    rows = [
        {
            "proposal_key": f"R1|{key}|yield_t_ha",
            "rule_id": "R1",
            "issue_type": "outlier_implausible",
            "table": "farm_survey",
            "record_key": key,
            "field": "yield_t_ha",
            "old_value": "54.0",
            "new_value": "5.4",
            "action": "fix",
            "evidence": {
                "summary": "The yield is far above the median.",
                "record_keys": [key],
                "query": {"kind": "rule", "rule_id": "R1", "params": {}},
                "values": {"yield_t_ha": 54.0, "ratio_to_median": 10.0},
            },
            "explanation": "",
            "proposer": "rule R1",
        }
        for key in KEYS
    ]
    return StepResult(tables=[], proposals=pd.DataFrame(rows, columns=PROPOSAL_COLUMNS))


def run_recipe(monkeypatch: pytest.MonkeyPatch) -> str:
    info = StepInfo("two_proposals", "propose", "Writes two proposals.", two_proposals)
    monkeypatch.setitem(STEPS, "two_proposals", info)
    recipe = Recipe(
        "farm_climate_risk",
        4,
        "Test",
        (
            StepSpec("two_proposals", inputs=()),
            StepSpec(
                "explain_proposals",
                inputs=(PROPOSALS_INPUT,),
                params={"max_explanations": None, "concurrency": 2},
            ),
        ),
    )
    monkeypatch.setattr(runner, "get_recipe", lambda _: recipe)
    run_id = add_run("running")
    runner.execute_run(run_id)
    return run_id


def explanations(run_id: str) -> dict[str, str | None]:
    with session_scope() as session:
        assert session.get_one(m.Run, run_id).status == "succeeded"
        rows = session.scalars(select(m.Proposal).where(m.Proposal.run_id == run_id)).all()
        return {p.record_key: p.explanation for p in rows}


def explainer_calls() -> int:
    with session_scope() as session:
        query = select(func.count()).select_from(m.LlmCall)
        return session.scalar(query.where(m.LlmCall.agent == "review-explainer")) or 0


def test_the_runner_stores_an_explanation_with_evidence_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    written = explanations(run_recipe(monkeypatch))
    assert set(written) == set(KEYS)
    for text in written.values():
        assert text and "{{ev:yield_t_ha}}" in text
    assert explainer_calls() == 2


def test_a_later_run_carries_the_explanations_over_and_makes_no_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = explanations(run_recipe(monkeypatch))
    second = explanations(run_recipe(monkeypatch))
    assert second == first
    assert explainer_calls() == 2


def test_a_failed_explanation_is_stored_empty_and_the_run_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(llm_models.FAKE_RESPONSES, Explanation, {"explanation": "Costs 12 euros."})
    run_id = run_recipe(monkeypatch)
    assert explanations(run_id) == dict.fromkeys(KEYS)
    with session_scope() as session:
        failed = session.scalars(select(m.RunEvent).where(m.RunEvent.type == "call.failed")).all()
        assert {e.payload["item"] for e in failed} == {f"R1|{key}|yield_t_ha" for key in KEYS}


def test_a_run_queued_with_the_fix_proposer_turns_the_step_on(client: TestClient) -> None:
    body = {"recipe_id": "farm_climate_risk", "run_fix_proposer": True}
    response = client.post("/api/runs", json=body, headers=PERSONA)
    assert response.status_code == 201, response.text
    with session_scope() as session:
        stored = session.get_one(m.Run, response.json()["run_id"])
        assert stored.params == {"step_params": {"propose_fixes": {"enabled": True}}}
