"""The worker: claims queued runs from Postgres one at a time and executes them."""

import time
from datetime import UTC, datetime

from sqlalchemy import select, update

from navigator.db import models as m
from navigator.db.session import session_scope
from navigator.logs import configure, get_logger
from navigator.recipes.registry import RECIPES
from navigator.settings import get_settings
from navigator.worker.report_run import execute_report_run
from navigator.worker.runner import emit, execute_run

log = get_logger(__name__)


def register_recipes() -> None:
    """Record each recipe version with its ordered steps, so runs can point at it."""
    with session_scope() as session:
        for recipe in RECIPES.values():
            if session.get(m.Recipe, (recipe.recipe_id, recipe.version)) is None:
                session.add(
                    m.Recipe(
                        recipe_id=recipe.recipe_id,
                        version=recipe.version,
                        title=recipe.title,
                        steps=[s.name for s in recipe.steps],
                    )
                )


def fail_interrupted_runs() -> None:
    """A run still marked running at startup was cut off by a crash or restart."""
    with session_scope() as session:
        run_ids = session.scalars(
            update(m.Run)
            .where(m.Run.status == "running")
            .values(status="failed", error="interrupted", finished_at=datetime.now(UTC))
            .returning(m.Run.run_id)
        ).all()
    for run_id in run_ids:
        log.warning("marked interrupted run as failed", extra={"run_id": run_id})
        emit(run_id, "run.status", {"status": "failed"})


def claim_next_run() -> str | None:
    with session_scope() as session:
        run = session.scalars(
            select(m.Run)
            .where(m.Run.status == "queued")
            .order_by(m.Run.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        ).first()
        if run is None:
            return None
        run.status = "running"
        run.started_at = datetime.now(UTC)
        return run.run_id


def execute(run_id: str) -> None:
    """Report runs have no recipe steps, so they go to the report drafter."""
    with session_scope() as session:
        kind = session.get_one(m.Run, run_id).kind
    if kind == "report":
        execute_report_run(run_id)
    else:
        execute_run(run_id)


def main() -> None:
    settings = get_settings()
    configure(settings.log_level)
    register_recipes()
    fail_interrupted_runs()
    log.info("worker started")
    while True:
        run_id = claim_next_run()
        if run_id is None:
            time.sleep(settings.worker_poll_seconds)
            continue
        log.info("run claimed", extra={"run_id": run_id})
        execute(run_id)


if __name__ == "__main__":
    main()
