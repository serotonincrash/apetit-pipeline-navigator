"""The report path: request a draft, run it on the worker, review, publish and export."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from navigator import ids
from navigator.agents.schemas import ParagraphDraft
from navigator.db import models as m
from navigator.db.session import session_scope
from navigator.llm import models as llm_models
from navigator.worker import main as worker
from tests.api.records import (
    add_assumption,
    add_decision,
    add_metric,
    add_proposal,
    add_result_set,
    add_run,
)

pytestmark = pytest.mark.api

LEAD = {"X-Persona": "sustainability_specialist:S. Lead"}
DATA = {"X-Persona": "data_specialist:A. Reviewer"}


def results(recipe_id: str = "farm_climate_risk", status: str = "succeeded") -> tuple[str, str]:
    """A run with a result set holding two metrics, one insight, an assumption and a fix."""
    run_id = add_run(status, recipe_id)
    result_set_id = add_result_set(run_id)
    cost = add_metric(
        result_set_id,
        "price_risk.expected_cost_eur",
        unit="€ per year",
        value=36000.0,
        scenario="ssp585",
        ngfs_scenario="current_policies",
    )
    add_metric(
        result_set_id,
        "project_yields.bad_year_chance",
        unit="share",
        value=0.123,
        scenario="ssp585",
        period="2041\u20132060",
    )
    with session_scope() as session:
        session.add(
            m.Insight(
                insight_id=ids.new_id("insight"),
                result_set_id=result_set_id,
                step="price_risk",
                title="Foodhills hedge",
                text="The hedge avoids {{metric:" + cost + "}}.",
                metric_ids=[cost],
            )
        )
    add_assumption(run_id, "price_risk", "price_risk.price_year", 2025)
    add_decision(add_proposal(run_id, "R1", "farm_survey:FS1"))
    return run_id, result_set_id


def draft(client: TestClient, result_set_id: str) -> str:
    """Request a draft and run it on the worker the way its main loop does."""
    response = client.post(f"/api/result-sets/{result_set_id}/report", headers=LEAD)
    assert response.status_code == 202, response.text
    run_id = worker.claim_next_run()
    assert run_id is not None
    assert run_id == response.json()["run_id"]
    worker.execute(run_id)
    return run_id


def move(client: TestClient, result_set_id: str, target: str, headers: dict[str, str] = LEAD):
    return client.post(
        f"/api/result-sets/{result_set_id}/decisions", json={"status": target}, headers=headers
    )


def publish(client: TestClient, result_set_id: str) -> None:
    draft(client, result_set_id)
    for target in ("in_review", "approved", "published"):
        assert move(client, result_set_id, target).status_code == 201


def test_a_draft_is_requested_written_by_the_worker_and_read_back(client: TestClient) -> None:
    run_id, result_set_id = results()
    assert client.get(f"/api/result-sets/{result_set_id}/report").status_code == 404
    report_run_id = draft(client, result_set_id)

    run = client.get(f"/api/runs/{report_run_id}").json()
    assert (run["kind"], run["status"], run["recipe_id"], run["steps"]) == (
        "report",
        "succeeded",
        "farm_climate_risk",
        [],
    )
    assert run["parent_run_id"] == run_id
    with session_scope() as session:
        assert len(session.scalars(select(m.ResultSet)).all()) == 1
        events = session.scalars(
            select(m.RunEvent).where(m.RunEvent.run_id == report_run_id).order_by(m.RunEvent.seq)
        ).all()
        assert [(e.type, e.payload["status"]) for e in events] == [
            ("run.status", "queued"),
            ("run.status", "running"),
            ("run.status", "succeeded"),
            ("run.finished", "succeeded"),
        ]
        assert events[-1].payload["result_set_id"] == result_set_id

    report = client.get(f"/api/result-sets/{result_set_id}/report").json()
    assert (report["version"], report["status"], report["run_id"]) == (1, "draft", report_run_id)
    assert [p["section"] for p in report["paragraphs"]][:7] == [
        "summary",
        "risk",
        "risk",
        "drivers",
        "options",
        "insights",
        "method",
    ]
    drafted = [p for p in report["paragraphs"] if p["call_id"]]
    built = [p for p in report["paragraphs"] if not p["call_id"]]
    assert len(drafted) == 7
    assert [p["heading"] for p in built] == [
        "Data sources",
        "Corrections approved",
        "Assumptions used",
        "Models and prompt versions",
    ]
    assert "Data check R1: 1 fixes approved by A. Reviewer" in built[1]["text"]
    assert "report-drafter: model fake" in built[3]["text"]
    assert "{{metric:met_" in " ".join(p["text"] for p in drafted)
    assert set(report["metrics"]) >= {i["metric_ids"][0] for i in report["insights"]}
    with session_scope() as session:
        calls = session.scalars(select(m.LlmCall).where(m.LlmCall.run_id == report_run_id)).all()
        assert {c.call_id for c in calls} == {p["call_id"] for p in drafted}


def test_only_the_sustainability_specialist_asks_for_a_draft(client: TestClient) -> None:
    _, result_set_id = results()
    response = client.post(f"/api/result-sets/{result_set_id}/report", headers=DATA)
    assert response.status_code == 403
    assert client.post("/api/result-sets/rs_none/report", headers=LEAD).status_code == 404


def test_a_run_that_has_not_succeeded_cannot_be_drafted(client: TestClient) -> None:
    _, result_set_id = results(status="failed")
    response = client.post(f"/api/result-sets/{result_set_id}/report", headers=LEAD)
    assert response.status_code == 422
    assert "has not succeeded" in response.text


def test_a_second_request_waits_for_the_first_draft(client: TestClient) -> None:
    _, result_set_id = results()
    assert client.post(f"/api/result-sets/{result_set_id}/report", headers=LEAD).status_code == 202
    again = client.post(f"/api/result-sets/{result_set_id}/report", headers=LEAD)
    assert again.status_code == 422
    assert "already being written" in again.text


def test_each_report_run_writes_a_new_numbered_draft(client: TestClient) -> None:
    _, result_set_id = results()
    draft(client, result_set_id)
    draft(client, result_set_id)
    assert client.get(f"/api/result-sets/{result_set_id}/report").json()["version"] == 2
    with session_scope() as session:
        versions = session.scalars(select(m.Report.version).order_by(m.Report.version)).all()
        assert list(versions) == [1, 2]
        assert len(session.scalars(select(m.ResultSet)).all()) == 1


def test_a_failed_paragraph_gives_no_draft(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, result_set_id = results()
    monkeypatch.setitem(
        llm_models.FAKE_RESPONSES,
        ParagraphDraft,
        lambda _: {"section": "summary", "heading": "", "text": "The cost is 36 thousand euros."},
    )
    report_run_id = draft(client, result_set_id)
    run = client.get(f"/api/runs/{report_run_id}").json()
    assert run["status"] == "failed"
    assert "Nothing was saved" in run["error"]
    assert client.get(f"/api/result-sets/{result_set_id}/report").status_code == 404
    with session_scope() as session:
        failed = session.scalars(select(m.RunEvent).where(m.RunEvent.type == "call.failed")).all()
        assert [(e.payload["agent"], e.payload["item"]) for e in failed] == [
            ("report-drafter", "Summary")
        ]
        statuses = [
            c.status for c in session.scalars(select(m.LlmCall).order_by(m.LlmCall.attempt))
        ]
        assert statuses == ["retried", "retried", "failed"]


def test_results_move_one_step_at_a_time_and_publishing_needs_a_draft(client: TestClient) -> None:
    _, result_set_id = results()
    assert move(client, result_set_id, "approved").status_code == 422
    assert move(client, result_set_id, "in_review", DATA).status_code == 403
    assert move(client, result_set_id, "in_review").status_code == 201
    assert move(client, result_set_id, "in_review").status_code == 422
    approved = move(client, result_set_id, "approved")
    assert approved.status_code == 201
    assert approved.json()["reviewer"] == "S. Lead"
    refused = move(client, result_set_id, "published")
    assert refused.status_code == 422
    assert "Draft a report first" in refused.text
    with session_scope() as session:
        result_set = session.get_one(m.ResultSet, result_set_id)
        assert (result_set.status, result_set.approved_by) == ("approved", "S. Lead")
        decisions = session.scalars(select(m.Decision.decision).order_by(m.Decision.decision_id))
        assert list(decisions)[-2:] == ["in_review", "approved"]


def test_the_text_is_fixed_once_the_results_are_approved(client: TestClient) -> None:
    _, result_set_id = results()
    draft(client, result_set_id)
    move(client, result_set_id, "in_review")
    move(client, result_set_id, "approved")
    assert client.post(f"/api/result-sets/{result_set_id}/report", headers=LEAD).status_code == 422


def test_publishing_publishes_the_latest_draft_and_supersedes_the_earlier_ones(
    client: TestClient,
) -> None:
    _, result_set_id = results()
    draft(client, result_set_id)
    draft(client, result_set_id)
    for target in ("in_review", "approved", "published"):
        assert move(client, result_set_id, target).status_code == 201
    assert move(client, result_set_id, "published").status_code == 422
    report = client.get(f"/api/result-sets/{result_set_id}/report").json()
    assert (report["status"], report["version"]) == ("published", 2)
    assert report["published_at"] is not None
    with session_scope() as session:
        reports = session.scalars(select(m.Report).order_by(m.Report.version)).all()
        assert [r.status for r in reports] == ["superseded", "published"]


def test_export_is_markdown_for_a_published_report_only(client: TestClient) -> None:
    _, result_set_id = results()
    draft(client, result_set_id)
    early = client.get(f"/api/result-sets/{result_set_id}/report/export")
    assert early.status_code == 422
    assert "Publish the report first" in early.text
    for target in ("in_review", "approved", "published"):
        move(client, result_set_id, target)
    response = client.get(f"/api/result-sets/{result_set_id}/report/export")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    body = response.text
    assert "{{" not in body
    assert "€36k per year" in body
    assert "12.3%" in body
    assert "approved by S. Lead" in body
    assert "## Summary" in body
    assert "## Data sources" in body
    assert client.get("/api/result-sets/rs_none/report/export").status_code == 404


def test_publishing_supersedes_the_earlier_result_set_of_the_same_recipe_only(
    client: TestClient,
) -> None:
    _, first = results("farm_climate_risk")
    _, other_recipe = results("another_recipe")
    _, second = results("farm_climate_risk")
    publish(client, first)
    publish(client, other_recipe)
    publish(client, second)
    with session_scope() as session:
        status = {r.result_set_id: r.status for r in session.scalars(select(m.ResultSet))}
    assert status == {first: "superseded", other_recipe: "published", second: "published"}
    # The superseded result set keeps its report readable.
    assert client.get(f"/api/result-sets/{first}/report").json()["status"] == "superseded"
