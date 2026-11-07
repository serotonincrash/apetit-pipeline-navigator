"""Rows as the worker writes them, inserted straight into the test database."""

from typing import Any

from navigator import ids
from navigator.db import models as m
from navigator.db.session import session_scope

EVIDENCE: dict[str, Any] = {
    "summary": "Yield is 1000 times the farm median.",
    "record_keys": ["farm_survey:FS02175"],
    "query": {
        "kind": "rule",
        "rule_id": "R1",
        "params": {"r1_yield_max_ratio_to_median": 5.0},
        "group": None,
    },
    "values": {"yield_t_ha": 5400.0, "median": 5.4, "ratio_to_median": 1000.0},
}


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
                evidence=EVIDENCE,
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


def add_result_set(run_id: str, status: str = "draft") -> str:
    result_set_id = ids.new_id("result_set")
    with session_scope() as session:
        session.add(m.ResultSet(result_set_id=result_set_id, run_id=run_id, status=status))
    return result_set_id


def add_metric(
    result_set_id: str, name: str = "project_yields.yield_change_pct", **fields: Any
) -> str:
    metric_id = ids.new_id("metric")
    values: dict[str, Any] = {"unit": "%", "value": -3.5, "lineage": [], "assumption_ids": []}
    with session_scope() as session:
        session.add(
            m.Metric(
                metric_id=metric_id,
                result_set_id=result_set_id,
                name=name,
                **(values | fields),
            )
        )
    return metric_id


def add_assumption(run_id: str, step: str, name: str, value: Any = 1.0) -> str:
    assumption_id = ids.new_id("assumption")
    with session_scope() as session:
        session.add(
            m.Assumption(
                assumption_id=assumption_id,
                run_id=run_id,
                step=step,
                name=name,
                label=f"Label of {name}",
                value=value,
                unit="share",
                source="Test source.",
            )
        )
    return assumption_id


def add_decision(proposal_id: str, decision: str = "approve") -> None:
    with session_scope() as session:
        proposal = session.get(m.Proposal, proposal_id)
        assert proposal is not None
        session.add(
            m.Decision(
                decision_id=ids.new_id("decision"),
                target_type="proposal",
                target_id=proposal.proposal_key,
                decision=decision,
                reviewer="A. Reviewer",
                run_id=proposal.run_id,
            )
        )
