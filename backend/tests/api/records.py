"""Rows as the worker writes them, inserted straight into the test database."""

from typing import Any

from navigator import ids
from navigator.db import models as m
from navigator.db.session import session_scope


def add_run(status: str = "queued", recipe_id: str = "farm_climate_risk") -> str:
    run_id = ids.new_id("run")
    with session_scope() as session:
        session.add(
            m.Run(
                run_id=run_id,
                recipe_id=recipe_id,
                version=1,
                kind="full",
                params={"step_params": {}},
                params_hash="hash",
                status=status,
                triggered_by="Worker test",
            )
        )
    return run_id


def add_step_run(run_id: str, step: str, position: int, **fields: Any) -> str:
    step_run_id = ids.new_id("step_run")
    with session_scope() as session:
        session.add(
            m.StepRun(
                step_run_id=step_run_id,
                run_id=run_id,
                position=position,
                step=step,
                kind=fields.pop("kind", "transform"),
                summary=fields.pop("summary", f"Summary of {step}."),
                **fields,
            )
        )
    return step_run_id


def add_artifact(
    run_id: str,
    step_run_id: str,
    name: str,
    columns: list[str],
    uri: str = "s3://navigator-test/none.parquet",
    row_count: int = 0,
) -> str:
    artifact_id = ids.new_id("artifact")
    with session_scope() as session:
        session.add(
            m.Artifact(
                artifact_id=artifact_id,
                step_run_id=step_run_id,
                run_id=run_id,
                name=name,
                uri=uri,
                layer="raw",
                row_count=row_count,
                columns=columns,
                content_hash="hash",
            )
        )
    return artifact_id


def add_proposal(
    run_id: str,
    rule_id: str,
    record_key: str,
    field: str = "yield_t_ha",
    action: str = "fix",
    table: str = "farm_survey",
) -> str:
    proposal_id = ids.new_id("proposal")
    with session_scope() as session:
        session.add(
            m.Proposal(
                proposal_id=proposal_id,
                proposal_key=f"{rule_id}:{record_key}:{field}",
                run_id=run_id,
                rule_id=rule_id,
                issue_type="unit_error",
                proposer=f"rule:{rule_id}",
                table=table,
                record_key=record_key,
                field=field,
                old_value="5400",
                new_value="5.4" if action == "fix" else None,
                action=action,
                evidence="Yield is 1000 times the farm median.",
                explanation=None,
            )
        )
    return proposal_id


def add_events(run_id: str, events: list[tuple[str, dict[str, Any]]]) -> list[int]:
    """Store events in order and return their seq numbers."""
    rows = [
        m.RunEvent(
            event_id=ids.new_id("run_event"),
            run_id=run_id,
            step=payload.get("step"),
            type=type_,
            payload=payload,
        )
        for type_, payload in events
    ]
    with session_scope() as session:
        for row in rows:
            session.add(row)
            session.flush()
    return [row.seq for row in rows]


def add_rule(rule_id: str, author: str, version: int = 1) -> None:
    with session_scope() as session:
        session.add(
            m.Rule(
                rule_id=rule_id,
                version=version,
                description=f"Check {rule_id}.",
                author=author,
                backtest={"precision": 1.0, "recall": 0.9},
            )
        )
