"""Endpoints from later milestones answer 501 and name the milestone that brings them."""

import pytest
from fastapi.testclient import TestClient

from tests.api.conftest import PERSONA

pytestmark = pytest.mark.api

NOT_BUILT = [
    ("GET", "/api/actions", None, 4),
    ("POST", "/api/actions/act_1/decisions", {"decision": "approve"}, 4),
    ("GET", "/api/result-sets/rs_1/action-options", None, 4),
    ("POST", "/api/action-options/opt_1/decisions", {"decision": "recommended"}, 4),
    ("POST", "/api/result-sets/rs_1/report", None, 4),
    ("GET", "/api/result-sets/rs_1/report", None, 4),
    ("POST", "/api/result-sets/rs_1/decisions", {"status": "approved"}, 4),
    ("GET", "/api/result-sets/rs_1/report/export", None, 4),
]


@pytest.mark.parametrize(("method", "path", "body", "milestone"), NOT_BUILT)
def test_later_endpoints_say_which_milestone_brings_them(
    client: TestClient, method: str, path: str, body: dict[str, str] | None, milestone: int
) -> None:
    response = client.request(method, path, json=body, headers=PERSONA)
    assert response.status_code == 501
    assert f"milestone {milestone}" in response.json()["detail"]


def test_every_endpoint_is_in_the_contract(client: TestClient) -> None:
    operations = [
        op["operationId"]
        for path in client.get("/openapi.json").json()["paths"].values()
        for op in path.values()
    ]
    assert len(operations) == len(set(operations)) == 27
