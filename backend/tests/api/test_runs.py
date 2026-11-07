"""Queueing runs and reading them back, and the persona every write needs."""

import pytest
from fastapi.testclient import TestClient

from navigator.db import models as m
from navigator.db.session import session_scope
from tests.api.conftest import PERSONA
from tests.api.records import add_artifact, add_run, add_step_run

pytestmark = pytest.mark.api


def test_health_and_personas(client: TestClient) -> None:
    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/api/personas").json() == [
        {"role": "data_specialist", "label": "Data specialist"},
        {"role": "sustainability_specialist", "label": "Sustainability specialist"},
    ]


def test_queue_a_run_and_read_it_back(client: TestClient) -> None:
    overrides = {"check_farm_data": {"r1_yield_max_ratio_to_median": 4.0}}
    response = client.post(
        "/api/runs",
        json={"recipe_id": "farm_climate_risk", "step_params": overrides},
        headers=PERSONA,
    )
    assert response.status_code == 201, response.text
    run = response.json()
    assert run["status"] == "queued"
    assert run["kind"] == "full"
    assert run["triggered_by"] == "A. Reviewer"
    assert run["result_set_id"] is None

    with session_scope() as session:
        stored = session.get_one(m.Run, run["run_id"])
        assert stored.params == {"step_params": overrides}
        assert stored.version == 1

    listed = client.get("/api/runs").json()
    assert listed["total"] == 1
    assert [r["run_id"] for r in listed["items"]] == [run["run_id"]]
    assert client.get("/api/runs", params={"status": "succeeded"}).json()["total"] == 0

    detail = client.get(f"/api/runs/{run['run_id']}").json()
    assert detail["params"] == {"step_params": overrides}
    assert detail["steps"] == []


def test_run_detail_lists_steps_in_order_with_their_tables(client: TestClient) -> None:
    run_id = add_run("running")
    load = add_step_run(
        run_id,
        "load_raw",
        1,
        kind="load",
        status="succeeded",
        seconds=1.5,
        error=None,
    )
    raw = add_artifact(run_id, load, "farm_survey", ["farm_id", "yield_t_ha"], row_count=12)
    with session_scope() as session:
        session.get_one(m.StepRun, load).output_artifacts = [raw]
    add_step_run(
        run_id,
        "check_farm_data",
        2,
        kind="propose",
        status="failed",
        input_artifacts=[raw],
        error="Traceback (most recent call last):\n  File ...\nKeyError: 'yield_t_ha'\n",
    )

    detail = client.get(f"/api/runs/{run_id}").json()
    steps = detail["steps"]
    assert [s["step"] for s in steps] == ["load_raw", "check_farm_data"]
    assert steps[0]["summary"] == "Summary of load_raw."
    assert steps[0]["seconds"] == 1.5
    assert steps[0]["output_artifacts"] == [raw]
    assert steps[1]["input_artifacts"] == [raw]
    assert steps[1]["error"] == "KeyError: 'yield_t_ha'"
    assert [(a["artifact_id"], a["step"], a["row_count"]) for a in detail["artifacts"]] == [
        (raw, "load_raw", 12)
    ]


def test_a_what_if_run_is_refused_for_now(client: TestClient) -> None:
    response = client.post(
        "/api/runs",
        json={"recipe_id": "farm_climate_risk", "kind": "what_if", "parent_run_id": "run_x"},
        headers=PERSONA,
    )
    assert response.status_code == 422
    assert response.json()["detail"][0]["msg"] == "What-if runs come in a later milestone."


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"recipe_id": "no_such_recipe"}, "No recipe no_such_recipe. Recipes: farm_climate_risk."),
        (
            {"recipe_id": "farm_climate_risk", "step_params": {"no_step": {}}},
            "Recipe farm_climate_risk has no step no_step.",
        ),
        (
            {"recipe_id": "farm_climate_risk", "step_params": {"load_raw": {"nope": 1}}},
            "Step load_raw has no param nope.",
        ),
    ],
)
def test_a_run_must_name_a_recipe_and_its_params(
    client: TestClient, body: dict[str, object], message: str
) -> None:
    response = client.post("/api/runs", json=body, headers=PERSONA)
    assert response.status_code == 422
    assert response.json()["detail"][0]["msg"] == message
    with session_scope() as session:
        assert session.query(m.Run).count() == 0


@pytest.mark.parametrize(
    "header",
    [None, "", "A. Reviewer", "data_specialist:", "data_specialist:  ", "manager:A. Reviewer"],
)
def test_writes_need_a_persona(client: TestClient, header: str | None) -> None:
    headers = {} if header is None else {"X-Persona": header}
    response = client.post("/api/runs", json={"recipe_id": "farm_climate_risk"}, headers=headers)
    assert response.status_code == 400
    assert response.json()["detail"]
    with session_scope() as session:
        assert session.query(m.Run).count() == 0


def test_the_persona_name_may_be_percent_encoded(client: TestClient) -> None:
    response = client.post(
        "/api/runs",
        json={"recipe_id": "farm_climate_risk"},
        headers={"X-Persona": "sustainability_specialist:%C3%84.%20Virtanen"},
    )
    assert response.status_code == 201
    assert response.json()["triggered_by"] == "Ä. Virtanen"


def test_the_rule_policy_name_is_reserved(client: TestClient) -> None:
    response = client.post(
        "/api/runs",
        json={"recipe_id": "farm_climate_risk"},
        headers={"X-Persona": "data_specialist:Rule policy"},
    )
    assert response.status_code == 400


def test_an_unknown_run_is_not_found(client: TestClient) -> None:
    response = client.get("/api/runs/run_missing")
    assert response.status_code == 404
    assert response.json() == {"detail": "No run with id run_missing."}
