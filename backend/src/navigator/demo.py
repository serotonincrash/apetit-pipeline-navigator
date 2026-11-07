"""Put the demo VM back in its prepared state after people have used it.

    python -m navigator.demo reset --reviewer "A. Reviewer"

Empties the database and the bucket, reseeds the package and the action catalogue, then goes
through the review loop once for each recipe through the API, as a person would: queue a full
run, approve the fixes of the rules whose fixes match the 2023-24 known issues, and run again.
Recipe 2's Scope 2 figures are 28 to 6,000 times too high until its unit fixes are approved.
Needs the API and the worker running; `scripts/reset_demo.sh` calls it inside the API container.
"""

import argparse
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from sqlalchemy import text

from navigator.db.models import Base
from navigator.db.session import session_scope
from navigator.logs import configure, get_logger
from navigator.seed import load_catalogue, seed_from_disk
from navigator.settings import get_settings
from navigator.storage import objects

log = get_logger(__name__)

# The rules whose fixes match the 2023-24 known issues, by recipe.
CHECKED_RULES = {
    "farm_climate_risk": ["R1", "R2", "R3", "R5"],
    "energy_meter_check": ["M1", "M2", "M3"],
}


class Api:
    def __init__(self, base: str, reviewer: str) -> None:
        self.base = base.rstrip("/")
        self.persona = urllib.parse.quote(f"data_specialist:{reviewer}", safe=":")

    def call(self, path: str, body: dict[str, Any] | None = None) -> Any:
        request = urllib.request.Request(
            self.base + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json", "X-Persona": self.persona},
            method="POST" if body is not None else "GET",
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)

    def run_until_finished(self, recipe_id: str, timeout_s: float) -> dict[str, Any]:
        run = self.call("/api/runs", {"recipe_id": recipe_id, "kind": "full"})
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            detail = self.call(f"/api/runs/{run['run_id']}")
            if detail["status"] in ("succeeded", "failed"):
                return detail
            time.sleep(3)
        raise TimeoutError(f"Run {run['run_id']} did not finish within {timeout_s:.0f} seconds.")

    def approve_fixes(self, recipe_id: str, rule_id: str, comment: str) -> int:
        query = urllib.parse.urlencode({"recipe_id": recipe_id, "rule_id": rule_id, "limit": 2000})
        proposals = self.call(f"/api/proposals?{query}")["items"]
        ids = [
            p["proposal_id"] for p in proposals if p["action"] == "fix" and p["status"] == "open"
        ]
        if ids:
            self.call(
                "/api/proposals/decisions",
                {"proposal_ids": ids, "decision": "approve", "comment": comment},
            )
        return len(ids)


def empty_bucket(bucket: str) -> None:
    client = objects.get_client()
    if not client.bucket_exists(bucket):
        return
    for item in client.list_objects(bucket, recursive=True):
        if item.object_name is not None:
            client.remove_object(bucket, item.object_name)


def empty_tables() -> None:
    """Delete every row of the platform tables. The tables stay, so a running worker and API
    carry on without errors."""
    names = ", ".join(f'"{table.name}"' for table in Base.metadata.sorted_tables)
    with session_scope() as session:
        session.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))


def reset(api_url: str, reviewer: str, timeout_s: float) -> None:
    settings = get_settings()
    empty_tables()
    empty_bucket(settings.s3_bucket)
    files = seed_from_disk(Path(settings.package_dir), settings.s3_bucket)
    actions = load_catalogue(Path(settings.catalogue_path))
    log.info("demo reseeded", extra={"files": files, "actions": actions})

    api = Api(api_url, reviewer)
    for recipe_id, rule_ids in CHECKED_RULES.items():
        first = api.run_until_finished(recipe_id, timeout_s)
        log.info(
            "first run finished",
            extra={"recipe_id": recipe_id, "status": first["status"], "error": first["error"]},
        )
        for rule_id in rule_ids:
            approved = api.approve_fixes(
                recipe_id, rule_id, "Checked against the 2023-24 known issues."
            )
            log.info("fixes approved", extra={"rule_id": rule_id, "approved": approved})
            if approved == 0:
                raise RuntimeError(f"Data check {rule_id} of {recipe_id} had no open fixes.")
        second = api.run_until_finished(recipe_id, timeout_s)
        if second["status"] != "succeeded":
            raise RuntimeError(f"The {recipe_id} demo run did not succeed: {second['error']}")
        log.info("demo ready", extra={"recipe_id": recipe_id, "run_id": second["run_id"]})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    reset_parser = sub.add_parser("reset", help="return the demo to its prepared state")
    reset_parser.add_argument("--reviewer", required=True, help="the name recorded on approvals")
    reset_parser.add_argument("--api", default="http://localhost:8000")
    reset_parser.add_argument("--timeout", type=float, default=900.0, help="seconds per run")
    args = parser.parse_args()
    configure(get_settings().log_level)
    reset(args.api, args.reviewer, args.timeout)


if __name__ == "__main__":
    main()
