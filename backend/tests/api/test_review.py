"""Data review: a proposal's status follows its latest decision, here and in the runner."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from navigator.db import models as m
from navigator.db.session import session_scope
from navigator.worker.runner import proposals_with_status
from tests.api.conftest import PERSONA
from tests.api.records import EVIDENCE, add_proposal, add_run

pytestmark = pytest.mark.api


def statuses(client: TestClient, run_id: str) -> dict[str, str]:
    items = client.get("/api/proposals", params={"run_id": run_id}).json()["items"]
    return {p["proposal_id"]: p["status"] for p in items}


def runner_statuses(run_id: str) -> dict[str, str]:
    with session_scope() as session:
        frame = proposals_with_status(session, run_id)
    return dict(zip(frame["proposal_key"], frame["status"], strict=True))


def decide(client: TestClient, proposal_id: str, **body: object) -> dict[str, object]:
    response = client.post(f"/api/proposals/{proposal_id}/decisions", json=body, headers=PERSONA)
    assert response.status_code == 201, response.text
    return response.json()


def test_status_follows_the_latest_decision(client: TestClient) -> None:
    run_id = add_run("succeeded")
    fix = add_proposal(run_id, "R1", "farm_survey:FS02175")
    flag = add_proposal(run_id, "R4", "farm_survey:FS02176", action="flag")
    assert statuses(client, run_id) == {fix: "open", flag: "flag"}

    decision = decide(client, fix, decision="approve", comment="Unit is kg per hectare.")
    assert decision["reviewer"] == "A. Reviewer"
    assert decision["target_id"] == "R1:farm_survey:FS02175:yield_t_ha"
    assert statuses(client, run_id)[fix] == "approved"

    decide(client, fix, decision="reject")
    decide(client, flag, decision="reject")
    assert statuses(client, run_id) == {fix: "rejected", flag: "rejected"}

    decide(client, fix, decision="edit", edited_value="5.2")
    assert statuses(client, run_id)[fix] == "approved"
    assert runner_statuses(run_id) == {
        "R1:farm_survey:FS02175:yield_t_ha": "approved",
        "R4:farm_survey:FS02176:yield_t_ha": "rejected",
    }
    with session_scope() as session:
        frame = proposals_with_status(session, run_id)
    assert frame.set_index("rule_id").loc["R1", "new_value"] == "5.2"

    detail = client.get(f"/api/proposals/{fix}").json()
    assert [d["decision"] for d in detail["decisions"]] == ["approve", "reject", "edit"]
    assert detail["latest_decision"]["edited_value"] == "5.2"
    assert detail["evidence"] == EVIDENCE


def test_decisions_carry_over_to_the_next_run(client: TestClient) -> None:
    first = add_run("succeeded")
    old = add_proposal(first, "R1", "farm_survey:FS02175")
    decide(client, old, decision="approve")

    second = add_run("succeeded")
    new = add_proposal(second, "R1", "farm_survey:FS02175")
    listed = client.get("/api/proposals").json()
    assert listed["run_id"] == second
    assert [(p["proposal_id"], p["status"]) for p in listed["items"]] == [(new, "approved")]


def test_proposals_filter_by_rule_table_and_status(client: TestClient) -> None:
    run_id = add_run("succeeded")
    r1 = add_proposal(run_id, "R1", "farm_survey:FS1")
    r2 = add_proposal(run_id, "R2", "farm_survey:FS2")
    registry = add_proposal(
        run_id, "R3", "farm_registry:F1", field="area_ha", table="farm_registry"
    )
    decide(client, r2, decision="reject")

    def ids(**params: str) -> list[str]:
        response = client.get("/api/proposals", params={"run_id": run_id, **params})
        return [p["proposal_id"] for p in response.json()["items"]]

    assert ids(rule_id="R1") == [r1]
    assert ids(table="farm_registry") == [registry]
    assert ids(status="open") == [r1, registry]
    assert ids(status="rejected") == [r2]
    page = client.get("/api/proposals", params={"run_id": run_id, "limit": 1, "offset": 1})
    assert page.json()["total"] == 3
    assert [p["proposal_id"] for p in page.json()["items"]] == [r2]


def test_a_bulk_decision_writes_one_row_per_proposal(client: TestClient) -> None:
    run_id = add_run("succeeded")
    proposal_ids = [add_proposal(run_id, "R5", f"farm_survey:FS{i}") for i in range(3)]

    response = client.post(
        "/api/proposals/decisions",
        json={
            "proposal_ids": [*proposal_ids, proposal_ids[0]],
            "decision": "approve",
            "comment": "Every R5 fix checked against the registry.",
        },
        headers=PERSONA,
    )
    assert response.status_code == 201, response.text
    assert len(response.json()) == 3
    with session_scope() as session:
        rows = session.scalars(select(m.Decision)).all()
        assert sorted(d.target_id for d in rows) == [
            f"R5:farm_survey:FS{i}:yield_t_ha" for i in range(3)
        ]
        assert {(d.decision, d.reviewer, d.run_id) for d in rows} == {
            ("approve", "A. Reviewer", run_id)
        }
    assert set(statuses(client, run_id).values()) == {"approved"}


def test_a_bulk_decision_with_an_unknown_proposal_writes_nothing(client: TestClient) -> None:
    run_id = add_run("succeeded")
    known = add_proposal(run_id, "R5", "farm_survey:FS1")
    response = client.post(
        "/api/proposals/decisions",
        json={"proposal_ids": [known, "prop_missing"], "decision": "approve"},
        headers=PERSONA,
    )
    assert response.status_code == 404
    with session_scope() as session:
        assert session.query(m.Decision).count() == 0


@pytest.mark.parametrize(
    ("action", "body", "field"),
    [
        ("fix", {"decision": "edit"}, "edited_value"),
        ("fix", {"decision": "approve", "edited_value": "5.1"}, "edited_value"),
        ("flag", {"decision": "edit", "edited_value": "5.1"}, "decision"),
    ],
)
def test_only_an_edit_on_a_fix_carries_a_value(
    client: TestClient, action: str, body: dict[str, str], field: str
) -> None:
    proposal_id = add_proposal(add_run("succeeded"), "R1", "farm_survey:FS1", action=action)
    response = client.post(f"/api/proposals/{proposal_id}/decisions", json=body, headers=PERSONA)
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", field]


def test_decisions_need_a_persona(client: TestClient) -> None:
    proposal_id = add_proposal(add_run("succeeded"), "R1", "farm_survey:FS1")
    single = client.post(f"/api/proposals/{proposal_id}/decisions", json={"decision": "approve"})
    bulk = client.post(
        "/api/proposals/decisions", json={"proposal_ids": [proposal_id], "decision": "approve"}
    )
    assert (single.status_code, bulk.status_code) == (400, 400)


def test_no_proposals_yet(client: TestClient) -> None:
    assert client.get("/api/proposals").json() == {"run_id": None, "total": 0, "items": []}
    assert client.get("/api/proposals/prop_missing").status_code == 404
