"""Actions screen: the list, decisions with their status, and who may decide."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from navigator.db import models as m
from navigator.db.session import session_scope
from tests.api.conftest import PERSONA
from tests.api.records import add_proposal, add_result_set, add_rule, add_run

pytestmark = pytest.mark.api

SUSTAINABILITY = {"X-Persona": "sustainability_specialist:S. Lead"}


def add_action(action_id: str) -> None:
    with session_scope() as session:
        session.add(
            m.ActionDefinition(
                action_id=action_id,
                name=f"Name of {action_id}",
                driver="heat at flowering",
                applies_at="project_yields",
                override={"type": "scale_feature"},
                scope={},
                cost={"eur_per_year": 1000},
                confidence="low",
                proposed_by="catalogue",
            )
        )


def add_option(result_set_id: str, run_id: str, option_id: str = "opt_1") -> None:
    with session_scope() as session:
        session.add(
            m.ActionOption(
                option_id=option_id,
                action_id="act_1",
                result_set_id=result_set_id,
                run_id=run_id,
                name="Irrigate pea",
                scenario="ssp585",
                cost_eur_per_yr=1000.0,
                risk_reduced_eur_per_yr=5000.0,
                assumption_ids=[],
            )
        )


def decision_count() -> int:
    with session_scope() as session:
        return session.scalar(select(func.count()).select_from(m.Decision)) or 0


def test_actions_list_status_follows_the_latest_decision(client: TestClient) -> None:
    add_action("act_1")
    add_action("act_2")
    listed = {a["action_id"]: a["status"] for a in client.get("/api/actions").json()}
    assert listed == {"act_1": "proposed", "act_2": "proposed"}

    url = "/api/actions/act_1/decisions"
    first = client.post(
        url, json={"decision": "approve", "comment": " Fits "}, headers=SUSTAINABILITY
    )
    assert first.status_code == 201
    assert first.json()["reviewer"] == "S. Lead"
    assert first.json()["comment"] == "Fits"
    assert client.get("/api/actions?status=approved_to_run").json()[0]["action_id"] == "act_1"

    client.post(url, json={"decision": "reject"}, headers=SUSTAINABILITY)
    listed = {a["action_id"]: a["status"] for a in client.get("/api/actions").json()}
    assert listed == {"act_1": "rejected", "act_2": "proposed"}
    assert decision_count() == 2


def test_action_decision_for_a_missing_action_is_404(client: TestClient) -> None:
    response = client.post(
        "/api/actions/act_9/decisions", json={"decision": "approve"}, headers=SUSTAINABILITY
    )
    assert response.status_code == 404


def test_action_options_carry_the_status_of_their_latest_decision(client: TestClient) -> None:
    add_action("act_1")
    run_id = add_run()
    result_set_id = add_result_set(run_id)
    add_option(result_set_id, run_id)
    url = f"/api/result-sets/{result_set_id}/action-options"
    [option] = client.get(url).json()
    assert option["status"] is None
    assert option["scenario"] == "ssp585"

    for decision in ("recommended", "rejected"):
        response = client.post(
            "/api/action-options/opt_1/decisions",
            json={"decision": decision},
            headers=SUSTAINABILITY,
        )
        assert response.status_code == 201
        assert response.json()["run_id"] == run_id
    assert client.get(url).json()[0]["status"] == "rejected"


def test_missing_result_set_and_option_are_404(client: TestClient) -> None:
    assert client.get("/api/result-sets/rs_9/action-options").status_code == 404
    response = client.post(
        "/api/action-options/opt_9/decisions",
        json={"decision": "considered"},
        headers=SUSTAINABILITY,
    )
    assert response.status_code == 404


def test_only_the_sustainability_specialist_decides_on_actions(client: TestClient) -> None:
    add_action("act_1")
    run_id = add_run()
    add_option(add_result_set(run_id), run_id)
    for url, body in [
        ("/api/actions/act_1/decisions", {"decision": "approve"}),
        ("/api/action-options/opt_1/decisions", {"decision": "recommended"}),
    ]:
        response = client.post(url, json=body, headers=PERSONA)
        assert response.status_code == 403
        assert "sustainability specialist" in response.json()["detail"]
    assert decision_count() == 0


def test_only_the_data_specialist_decides_on_fixes_and_rules(client: TestClient) -> None:
    proposal_id = add_proposal(add_run(), "R1", "FS1")
    add_rule("R9", "agent")
    attempts = [
        (f"/api/proposals/{proposal_id}/decisions", {"decision": "approve"}),
        ("/api/proposals/decisions", {"proposal_ids": [proposal_id], "decision": "approve"}),
        ("/api/rules/R9/decisions", {"decision": "approve"}),
    ]
    for url, body in attempts:
        response = client.post(url, json=body, headers=SUSTAINABILITY)
        assert response.status_code == 403
        assert "data specialist" in response.json()["detail"]
    assert decision_count() == 0
    for url, body in attempts:
        assert client.post(url, json=body, headers=PERSONA).status_code == 201
