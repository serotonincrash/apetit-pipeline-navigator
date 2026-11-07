"""Every endpoint is built and in the OpenAPI contract."""

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.api


def test_every_endpoint_is_in_the_contract(client: TestClient) -> None:
    operations = [
        op["operationId"]
        for path in client.get("/openapi.json").json()["paths"].values()
        for op in path.values()
    ]
    assert len(operations) == len(set(operations)) == 27
