"""Rule proposals: an agent's rule waits for a person; decisions apply to one version."""

import pytest
from fastapi.testclient import TestClient

from tests.api.conftest import PERSONA
from tests.api.records import add_rule

pytestmark = pytest.mark.api


def rule_statuses(client: TestClient) -> list[tuple[str, int, str]]:
    return [(r["rule_id"], r["version"], r["status"]) for r in client.get("/api/rules").json()]


def test_rule_status_follows_its_latest_decision(client: TestClient) -> None:
    add_rule("R1", author="Core team")
    add_rule("R9", author="agent:fix-proposer")
    add_rule("R9", author="agent:fix-proposer", version=2)
    assert rule_statuses(client) == [
        ("R1", 1, "approved"),
        ("R9", 2, "proposed"),
        ("R9", 1, "proposed"),
    ]

    response = client.post("/api/rules/R9/decisions", json={"decision": "approve"}, headers=PERSONA)
    assert response.status_code == 201, response.text
    assert response.json()["target_id"] == "R9:2"
    assert response.json()["reviewer"] == "A. Reviewer"

    client.post(
        "/api/rules/R9/decisions", json={"decision": "reject", "version": 1}, headers=PERSONA
    )
    assert rule_statuses(client) == [
        ("R1", 1, "approved"),
        ("R9", 2, "approved"),
        ("R9", 1, "rejected"),
    ]


def test_a_decision_on_an_unknown_rule_is_not_found(client: TestClient) -> None:
    add_rule("R1", author="Core team")
    missing_rule = client.post(
        "/api/rules/R7/decisions", json={"decision": "approve"}, headers=PERSONA
    )
    missing_version = client.post(
        "/api/rules/R1/decisions", json={"decision": "approve", "version": 4}, headers=PERSONA
    )
    assert (missing_rule.status_code, missing_version.status_code) == (404, 404)
    assert missing_version.json()["detail"] == "No data check with id R1 version 4."
