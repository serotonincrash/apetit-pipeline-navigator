"""Recipe 2 runs through the real runner, and screens can ask for one recipe's results."""

import hashlib
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from navigator.db import models as m
from navigator.db.session import session_scope
from navigator.recipes.energy_meter_check import RAW_FILES
from navigator.storage import objects
from navigator.worker import runner
from tests.api.conftest import PERSONA
from tests.api.records import add_metric, add_proposal, add_result_set, add_run

pytestmark = pytest.mark.api

RECIPE_ID = "energy_meter_check"


@pytest.fixture
def package(storage: str) -> None:
    """The six package files the recipe reads, in the test bucket and recorded as source files."""
    root = Path(os.environ.get("PACKAGE_DIR", "../APETIT_CLIMATE_NATURE_NAVIGATOR_2026")).resolve()
    if not (root / "data").exists():
        pytest.skip(f"challenge package not found at {root}; set PACKAGE_DIR")
    with session_scope() as session:
        for entry in RAW_FILES.values():
            path = entry["path"]
            content = (root / path).read_bytes()
            session.add(
                m.SourceFile(
                    file_id=f"file_{hashlib.sha256(path.encode()).hexdigest()[:12]}",
                    path=path,
                    sha256=hashlib.sha256(content).hexdigest(),
                    bytes=len(content),
                    rows=None,
                    uri=objects.put_bytes(storage, objects.package_key(path), content),
                )
            )


def start_run(client: TestClient, *, fix_proposer: bool = False) -> str:
    response = client.post(
        "/api/runs",
        json={"recipe_id": RECIPE_ID, "run_fix_proposer": fix_proposer},
        headers=PERSONA,
    )
    assert response.status_code == 201, response.text
    run_id: str = response.json()["run_id"]
    runner.execute_run(run_id)
    return run_id


def comparison(client: TestClient, run_id: str) -> dict[tuple[str, str], float]:
    (result_set,) = client.get("/api/result-sets", params={"run_id": run_id}).json()
    metrics = client.get(
        f"/api/result-sets/{result_set['result_set_id']}/metrics",
        params={"limit": 1000},
    ).json()["items"]
    return {
        (metric["name"], metric["period"]): metric["value"]
        for metric in metrics
        if metric["name"].startswith("compare_inventory.")
    }


def test_screens_without_a_recipe_show_the_first_recipe(client: TestClient) -> None:
    farm_run, energy_run = add_run("succeeded"), add_run("succeeded", recipe_id=RECIPE_ID)
    farm_proposal = add_proposal(farm_run, "R1", "farm_survey:FS1")
    energy_proposal = add_proposal(
        energy_run, "M2", "energy:S-HQ:2023-09:electricity", "value", table="energy_meter_readings"
    )
    farm_set, energy_set = add_result_set(farm_run), add_result_set(energy_run)

    def proposal_ids(**params: str) -> list[str]:
        items = client.get("/api/proposals", params=params).json()["items"]
        return [p["proposal_id"] for p in items]

    assert proposal_ids() == [farm_proposal]
    assert proposal_ids(recipe_id=RECIPE_ID) == [energy_proposal]
    assert proposal_ids(run_id=energy_run) == [energy_proposal]

    def result_set_ids(**params: str) -> list[str]:
        return [r["result_set_id"] for r in client.get("/api/result-sets", params=params).json()]

    assert result_set_ids() == [farm_set]
    assert result_set_ids(recipe_id=RECIPE_ID) == [energy_set]
    assert result_set_ids(run_id=energy_run) == [energy_set]


def test_metrics_filter_by_site_and_period(client: TestClient) -> None:
    result_set_id = add_result_set(add_run("succeeded", recipe_id=RECIPE_ID))
    add_metric(
        result_set_id, "scope2_electricity.location_based_tco2e", site="S-SAK", period="2023"
    )
    add_metric(
        result_set_id, "scope2_electricity.location_based_tco2e", site="S-SAK", period="2024"
    )
    add_metric(
        result_set_id, "scope2_electricity.location_based_tco2e", site="S-KAN", period="2023"
    )

    url = f"/api/result-sets/{result_set_id}/metrics"
    saekylae = client.get(url, params={"site": "S-SAK"}).json()
    assert [(i["site"], i["period"]) for i in saekylae["items"]] == [
        ("S-SAK", "2023"),
        ("S-SAK", "2024"),
    ]
    assert client.get(url, params={"site": "S-SAK", "period": "2024"}).json()["total"] == 1
    assert client.get(url, params={"period": "2023"}).json()["total"] == 2


def test_the_recipe_runs_and_approved_fixes_bring_scope2_to_the_answer(
    client: TestClient, package: None
) -> None:
    first = start_run(client, fix_proposer=True)
    with session_scope() as session:
        assert session.get_one(m.Run, first).status == "succeeded"
        rules = session.scalars(select(m.Proposal.rule_id).where(m.Proposal.run_id == first)).all()
        assert sorted(set(rules)) == ["AG1", "M1", "M2", "M3"]
        assert session.scalar(select(func.count()).select_from(m.Metric)) == 91

    # No approvals yet, so the readings are as delivered and the figures are far off.
    before = comparison(client, first)
    assert before[("compare_inventory.location_based_difference_tco2e", "2023")] > 10_000

    proposals = client.get("/api/proposals", params={"recipe_id": RECIPE_ID, "limit": 200}).json()[
        "items"
    ]
    fixes = [p["proposal_id"] for p in proposals if p["action"] == "fix" and p["rule_id"] != "AG1"]
    assert len(fixes) == 55
    response = client.post(
        "/api/proposals/decisions",
        json={"proposal_ids": fixes, "decision": "approve"},
        headers=PERSONA,
    )
    assert response.status_code == 201

    second = start_run(client)
    after = comparison(client, second)
    assert after[("compare_inventory.location_based_difference_tco2e", "2023")] == pytest.approx(
        -0.30, abs=0.01
    )
    assert after[("compare_inventory.market_based_difference_tco2e", "2023")] == pytest.approx(
        0.0, abs=0.01
    )

    (result_set,) = client.get("/api/result-sets", params={"run_id": second}).json()
    saekylae = client.get(
        f"/api/result-sets/{result_set['result_set_id']}/metrics",
        params={
            "site": "S-SAK",
            "period": "2023",
            "name": "scope2_electricity.location_based_tco2e",
        },
    ).json()["items"]
    (metric,) = saekylae
    sources = client.get(f"/api/metrics/{metric['metric_id']}/sources").json()
    assert [(s["artifact"]["name"], s["row_count"]) for s in sources["sources"]] == [
        ("scope2_site_year", 1),
        ("energy_clean", 12),
    ]
    assert [c["rule_id"] for c in sources["corrections"]] == ["M1"]
