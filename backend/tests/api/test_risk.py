"""Result sets, metrics, metric sources, assumptions and the Excel export."""

import io

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from navigator import ids
from navigator.api import runs
from navigator.storage import objects
from tests.api.records import (
    add_artifact,
    add_assumption,
    add_decision,
    add_metric,
    add_proposal,
    add_result_set,
    add_run,
    add_step_run,
)

pytestmark = pytest.mark.api


def test_result_sets_newest_first_and_filtered(client: TestClient) -> None:
    first_run, second_run = add_run("succeeded"), add_run("succeeded")
    first = add_result_set(first_run, "published")
    second = add_result_set(second_run, "draft")

    listed = client.get("/api/result-sets").json()
    assert [r["result_set_id"] for r in listed] == [second, first]
    by_run = client.get("/api/result-sets", params={"run_id": first_run}).json()
    assert [r["result_set_id"] for r in by_run] == [first]
    by_status = client.get("/api/result-sets", params={"status": "draft"}).json()
    assert [r["result_set_id"] for r in by_status] == [second]


def test_metrics_filter_page_and_total(client: TestClient) -> None:
    result_set_id = add_result_set(add_run("succeeded"))
    other = add_result_set(add_run("succeeded"))
    add_metric(result_set_id, region="FI_SW", crop="pea", scenario="ssp585", low=-5.0, high=-2.0)
    add_metric(result_set_id, region="FI_SW", crop="carrot", scenario="ssp585")
    add_metric(result_set_id, region="SE_S", crop="pea", scenario="ssp245")
    add_metric(other, region="FI_SW", crop="pea")

    everything = client.get(f"/api/result-sets/{result_set_id}/metrics").json()
    assert everything["total"] == 3

    pea = client.get(
        f"/api/result-sets/{result_set_id}/metrics", params={"crop": "pea", "region": "FI_SW"}
    ).json()
    assert pea["total"] == 1
    assert (pea["items"][0]["low"], pea["items"][0]["high"]) == (-5.0, -2.0)
    assert pea["items"][0]["action_id"] is None

    page = client.get(f"/api/result-sets/{result_set_id}/metrics", params={"limit": 2, "offset": 2})
    assert page.json()["total"] == 3
    assert len(page.json()["items"]) == 1
    names = client.get(
        f"/api/result-sets/{result_set_id}/metrics", params={"name": "nothing.here"}
    ).json()
    assert names == {"total": 0, "items": []}


def test_metrics_of_a_missing_result_set(client: TestClient) -> None:
    response = client.get("/api/result-sets/rs_missing/metrics")
    assert response.status_code == 404
    assert response.json() == {"detail": "No results with id rs_missing."}


def test_missing_metric_sources(client: TestClient) -> None:
    assert client.get("/api/metrics/met_missing/sources").status_code == 404


def _clean_table(storage: str, run_id: str, step_run_id: str) -> str:
    frame = pd.DataFrame(
        {
            "record_key": [
                "farm_survey:FS1",
                "farm_survey:FS2",
                "farm_survey:FS3",
                "farm_survey:FS4",
            ],
            "crop": ["pea", "pea", "pea", "carrot"],
            "n_corrections": [1, 1, 0, 1],
        }
    )
    key = objects.artifact_key(run_id, ids.new_id("artifact"))
    uri = objects.put_bytes(storage, key, objects.frame_to_parquet(frame))
    return add_artifact(
        run_id, step_run_id, "farm_survey_clean", list(frame.columns), uri=uri, row_count=4
    )


def test_metric_sources_rows_corrections_and_assumptions(client: TestClient, storage: str) -> None:
    run_id = add_run("succeeded")
    step_run_id = add_step_run(run_id, "apply_approved", 1)
    artifact_id = _clean_table(storage, run_id, step_run_id)
    first = add_assumption(run_id, "tune_calendar", "tune_calendar.error_tolerance")
    second = add_assumption(run_id, "check_farm_data", "check_farm_data.max_ratio")
    result_set_id = add_result_set(run_id)
    metric_id = add_metric(
        result_set_id,
        lineage=[{"artifact": artifact_id, "filter": {"crop": ["pea"]}}],
        assumption_ids=[first, second],
    )
    approved = add_proposal(run_id, "R1", "farm_survey:FS1")
    add_decision(approved, "approve")
    add_proposal(run_id, "R1", "farm_survey:FS2")  # open
    rejected = add_proposal(run_id, "R1", "farm_survey:FS3")
    add_decision(rejected, "reject")
    elsewhere = add_proposal(run_id, "R1", "farm_survey:FS4")  # approved, but carrot
    add_decision(elsewhere, "approve")

    response = client.get(f"/api/metrics/{metric_id}/sources")
    assert response.status_code == 200, response.text
    body = response.json()
    (source,) = body["sources"]
    assert source["artifact"]["artifact_id"] == artifact_id
    assert source["filters"] == ["crop=pea"]
    assert source["row_count"] == 3
    assert [c["record_key"] for c in body["corrections"]] == ["farm_survey:FS1"]
    assert body["corrections"][0]["status"] == "approved"
    assert [a["assumption_id"] for a in body["assumptions"]] == [first, second]
    assert body["metric"]["metric_id"] == metric_id


def test_metric_sources_name_a_missing_table(client: TestClient) -> None:
    result_set_id = add_result_set(add_run("succeeded"))
    metric_id = add_metric(result_set_id, lineage=[{"artifact": "art_gone", "filter": {}}])
    response = client.get(f"/api/metrics/{metric_id}/sources")
    assert response.status_code == 404
    assert response.json() == {"detail": "No table with id art_gone."}


def test_assumptions_by_run_and_by_result_set(client: TestClient) -> None:
    run_id = add_run("succeeded")
    other_run = add_run("succeeded")
    result_set_id = add_result_set(run_id)
    add_assumption(run_id, "tune_calendar", "tune_calendar.b")
    add_assumption(run_id, "check_farm_data", "check_farm_data.z")
    add_assumption(run_id, "tune_calendar", "tune_calendar.a")
    add_assumption(other_run, "tune_calendar", "tune_calendar.a")

    expected = ["check_farm_data.z", "tune_calendar.a", "tune_calendar.b"]
    by_run = client.get("/api/assumptions", params={"run_id": run_id}).json()
    assert [a["name"] for a in by_run] == expected
    by_result_set = client.get("/api/assumptions", params={"result_set_id": result_set_id}).json()
    assert [a["name"] for a in by_result_set] == expected
    assert client.get("/api/assumptions", params={"result_set_id": "rs_missing"}).status_code == 404


def test_assumptions_need_a_result_set_or_a_run(client: TestClient) -> None:
    response = client.get("/api/assumptions")
    assert response.status_code == 422
    assert response.json()["detail"][0]["msg"] == "Give a result set id or a run id."


def _survey_artifact(storage: str) -> str:
    run_id = add_run("succeeded")
    step_run_id = add_step_run(run_id, "load_raw", 1, kind="load")
    frame = pd.DataFrame(
        {"farm_id": ["FS1", "FS2", "FS3"], "crop": ["pea", "pea", "carrot"], "y": [3.1, None, 41.0]}
    )
    key = objects.artifact_key(run_id, ids.new_id("artifact"))
    uri = objects.put_bytes(storage, key, objects.frame_to_parquet(frame))
    return add_artifact(
        run_id, step_run_id, "farm_survey", list(frame.columns), uri=uri, row_count=3
    )


def test_export_gives_the_filtered_rows_as_xlsx(client: TestClient, storage: str) -> None:
    artifact_id = _survey_artifact(storage)
    response = client.get(f"/api/artifacts/{artifact_id}/export", params={"filter": "crop=pea"})
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == runs.XLSX
    assert response.headers["content-disposition"] == 'attachment; filename="farm_survey.xlsx"'
    sheet = load_workbook(io.BytesIO(response.content)).active
    assert sheet is not None
    assert [[c.value for c in row] for row in sheet.iter_rows()] == [
        ["farm_id", "crop", "y"],
        ["FS1", "pea", 3.1],
        ["FS2", "pea", None],
    ]


def test_export_refuses_more_rows_than_the_cap(
    client: TestClient, storage: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact_id = _survey_artifact(storage)
    monkeypatch.setattr(runs, "EXPORT_MAX_ROWS", 2)
    response = client.get(f"/api/artifacts/{artifact_id}/export")
    assert response.status_code == 422
    message = response.json()["detail"][0]["msg"]
    assert "3 rows match" in message
    assert "Add filters" in message
    narrowed = client.get(f"/api/artifacts/{artifact_id}/export", params={"filter": "crop=pea"})
    assert narrowed.status_code == 200


def test_export_of_a_missing_table(client: TestClient) -> None:
    assert client.get("/api/artifacts/art_missing/export").status_code == 404
