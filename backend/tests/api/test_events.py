"""The run's event stream: stored events replay in order and a reconnect resumes."""

import json
import threading
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from navigator.api import runs
from navigator.api.schemas import RunEvent
from navigator.db import models as m
from navigator.db.session import session_scope
from tests.api.records import add_events, add_run

pytestmark = pytest.mark.api

ANNOTATION = "Reads every package file."
EVENTS: list[tuple[str, dict[str, Any]]] = [
    ("run.status", {"status": "queued"}),
    ("run.status", {"status": "running"}),
    ("step.started", {"step": "load_raw", "annotation": ANNOTATION}),
    (
        "section.started",
        {"step": "load_raw", "section": "read files", "annotation": "Reads the files."},
    ),
    (
        "section.finished",
        {
            "step": "load_raw",
            "section": "read files",
            "annotation": "Reads the files.",
            "seconds": 0.2,
        },
    ),
    (
        "step.finished",
        {"step": "load_raw", "annotation": ANNOTATION, "status": "succeeded", "seconds": 0.4},
    ),
    ("proposal.created", {"step": "check_farm_data", "count_per_rule": {"R1": 18, "R5": 6}}),
    ("run.status", {"status": "succeeded"}),
    ("run.finished", {"status": "succeeded", "result_set_id": "rs_1"}),
]


def parse_stream(body: str) -> list[tuple[int, dict[str, Any]]]:
    """(id, data) for each event in a server-sent event body; comments are skipped."""
    events: list[tuple[int, dict[str, Any]]] = []
    for block in body.split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        if "data" in fields:
            events.append((int(fields["id"]), json.loads(fields["data"])))
    return events


@pytest.fixture
def fast_polling(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runs, "POLL_SECONDS", 0.05)


def test_the_stream_replays_stored_events_in_order(client: TestClient) -> None:
    run_id = add_run("succeeded")
    seqs = add_events(run_id, EVENTS)

    response = client.get(f"/api/runs/{run_id}/events")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = parse_stream(response.text)
    assert [event_id for event_id, _ in events] == seqs
    assert [data["type"] for _, data in events] == [type_ for type_, _ in EVENTS]
    for event_id, data in events:
        assert data["seq"] == event_id
        assert data["run_id"] == run_id
        RunEvent.model_validate(data)


def test_a_reconnect_resumes_after_the_last_event_id(client: TestClient) -> None:
    run_id = add_run("succeeded")
    seqs = add_events(run_id, EVENTS)

    response = client.get(f"/api/runs/{run_id}/events", headers={"Last-Event-ID": str(seqs[1])})
    assert [event_id for event_id, _ in parse_stream(response.text)] == seqs[2:]


def test_a_client_that_saw_the_end_is_told_to_stop(client: TestClient) -> None:
    run_id = add_run("succeeded")
    seqs = add_events(run_id, EVENTS)

    response = client.get(f"/api/runs/{run_id}/events", headers={"Last-Event-ID": str(seqs[-1])})
    assert response.status_code == 204


def test_the_stream_follows_a_live_run_until_it_finishes(
    client: TestClient, fast_polling: None
) -> None:
    run_id = add_run("running")
    add_events(run_id, EVENTS[:3])

    def finish() -> None:
        time.sleep(0.3)
        add_events(run_id, EVENTS[3:])
        with session_scope() as session:
            session.get_one(m.Run, run_id).status = "succeeded"

    writer = threading.Thread(target=finish)
    writer.start()
    response = client.get(f"/api/runs/{run_id}/events")
    writer.join()
    assert [data["type"] for _, data in parse_stream(response.text)] == [t for t, _ in EVENTS]


def test_the_stream_ends_for_a_run_cut_off_without_a_finished_event(
    client: TestClient, fast_polling: None
) -> None:
    run_id = add_run("failed")
    add_events(
        run_id, [("run.status", {"status": "running"}), ("run.status", {"status": "failed"})]
    )

    events = parse_stream(client.get(f"/api/runs/{run_id}/events").text)
    assert [data["payload"]["status"] for _, data in events] == ["running", "failed"]


def test_the_stream_of_an_unknown_run_is_not_found(client: TestClient) -> None:
    assert client.get("/api/runs/run_missing/events").status_code == 404
