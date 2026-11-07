"""Artifact metadata, and rows read from object storage with filters and paging."""

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from navigator import ids
from navigator.storage import objects
from tests.api.records import add_artifact, add_run, add_step_run

pytestmark = pytest.mark.api

COLUMNS = ["farm_id", "crop", "yield_t_ha"]


def test_artifact_metadata(client: TestClient) -> None:
    run_id = add_run("succeeded")
    step_run_id = add_step_run(run_id, "load_raw", 1, kind="load")
    artifact_id = add_artifact(run_id, step_run_id, "farm_survey", COLUMNS, row_count=4)

    artifact = client.get(f"/api/artifacts/{artifact_id}").json()
    assert artifact["name"] == "farm_survey"
    assert artifact["step"] == "load_raw"
    assert artifact["columns"] == COLUMNS
    assert artifact["row_count"] == 4
    assert "uri" not in artifact
    assert client.get("/api/artifacts/art_missing").json() == {
        "detail": "No table with id art_missing."
    }


@pytest.mark.parametrize(
    ("filters", "message"),
    [
        (["parcel_id=P1"], "Table farm_survey has no column parcel_id."),
        (
            ["farm_id"],
            "Write each filter as column=value, for example farm_id=FS02175, not farm_id.",
        ),
    ],
)
def test_rows_filter_only_on_the_artifacts_columns(
    client: TestClient, filters: list[str], message: str
) -> None:
    run_id = add_run("succeeded")
    step_run_id = add_step_run(run_id, "load_raw", 1, kind="load")
    artifact_id = add_artifact(run_id, step_run_id, "farm_survey", COLUMNS)

    response = client.get(f"/api/artifacts/{artifact_id}/rows", params={"filter": filters})
    assert response.status_code == 422
    assert response.json()["detail"][0]["msg"] == message


def test_rows_are_filtered_and_paged(client: TestClient, storage: str) -> None:
    run_id = add_run("succeeded")
    step_run_id = add_step_run(run_id, "load_raw", 1, kind="load")
    frame = pd.DataFrame(
        {
            "farm_id": ["FS1", "FS2", "FS3", "FS4"],
            "crop": ["pea", "pea", "carrot", "pea"],
            "yield_t_ha": [3.1, 2.8, 41.0, None],
        }
    )
    key = objects.artifact_key(run_id, ids.new_id("artifact"))
    uri = objects.put_bytes(storage, key, objects.frame_to_parquet(frame))
    artifact_id = add_artifact(run_id, step_run_id, "farm_survey", COLUMNS, uri=uri, row_count=4)

    response = client.get(
        f"/api/artifacts/{artifact_id}/rows",
        params={"filter": ["crop=pea", "farm_id=FS2", "farm_id=FS4"], "limit": 1, "offset": 1},
    )
    assert response.status_code == 200, response.text
    page = response.json()
    assert page["total"] == 2
    assert page["columns"] == COLUMNS
    assert page["rows"] == [{"farm_id": "FS4", "crop": "pea", "yield_t_ha": None}]

    numeric = client.get(f"/api/artifacts/{artifact_id}/rows", params={"filter": "yield_t_ha=41.0"})
    assert [r["farm_id"] for r in numeric.json()["rows"]] == ["FS3"]
