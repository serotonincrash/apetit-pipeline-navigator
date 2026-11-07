"""Executes one run: every step of its recipe in order, recording what each step did.

All reading and writing happens here. Steps get their input tables as DataFrames and return
a StepResult; the runner stores the tables as Parquet artifacts and writes the proposals,
decisions, rules and assumptions to Postgres. Events are committed as they happen, so the
app can follow a run live.

Steps name their metrics, lineage tables, assumptions and insight citations; the runner swaps
in the ids. It holds every step's metrics and insights in memory and writes them with the
result set in the same transaction that marks the run succeeded, so a failed run leaves no
partial results.
"""

import re
import time
from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from navigator import ids
from navigator.db import models as m
from navigator.db.decisions import latest_decisions, proposal_status, proposal_value
from navigator.db.session import session_scope
from navigator.logs import get_logger
from navigator.recipes.core import (
    INSIGHT_COLUMNS,
    METRIC_COLUMNS,
    PROPOSALS_INPUT,
    STEPS,
    Artifact,
    Params,
    Recipe,
    RunContext,
    SourceFile,
    StepResult,
    StepSpec,
    event_sink,
)
from navigator.recipes.registry import get_recipe
from navigator.settings import get_settings
from navigator.storage import objects

log = get_logger(__name__)


def _now() -> datetime:
    return datetime.now(UTC)


def emit(run_id: str, type_: str, payload: dict[str, Any], step: str | None = None) -> None:
    """Store one run event in its own transaction, so it is visible to the stream at once."""
    with session_scope() as session:
        session.add(
            m.RunEvent(
                event_id=ids.new_id("run_event"),
                run_id=run_id,
                step=step,
                type=type_,
                payload=payload,
            )
        )


class PackageSources(Mapping[str, SourceFile]):
    """The challenge package in object storage, read file by file when a step asks for one."""

    def __init__(self, files: dict[str, m.SourceFile]) -> None:
        self._files = files

    def __getitem__(self, path: str) -> SourceFile:
        row = self._files[path]
        return SourceFile(path=path, sha256=row.sha256, content=objects.get_bytes(row.uri))

    def __iter__(self) -> Iterator[str]:
        return iter(self._files)

    def __len__(self) -> int:
        return len(self._files)


def step_params(recipe_step: StepSpec, overrides: Mapping[str, Any]) -> Params:
    """The step's params from the recipe, with any overrides queued with the run."""
    return {**recipe_step.params, **overrides.get(recipe_step.name, {})}


def proposals_with_status(session: Session, run_id: str) -> pd.DataFrame:
    """This run's proposals, each with the status set by its latest decision."""
    proposals = session.scalars(select(m.Proposal).where(m.Proposal.run_id == run_id)).all()
    latest = latest_decisions(session, "proposal", (p.proposal_key for p in proposals))

    rows: list[dict[str, Any]] = []
    for p in proposals:
        decision = latest.get(p.proposal_key)
        rows.append(
            {
                "proposal_key": p.proposal_key,
                "rule_id": p.rule_id,
                "issue_type": p.issue_type,
                "table": p.table,
                "record_key": p.record_key,
                "field": p.field,
                "old_value": p.old_value,
                "new_value": proposal_value(p.new_value, decision),
                "action": p.action,
                "status": proposal_status(p.action, decision),
            }
        )
    columns = [
        "proposal_key",
        "rule_id",
        "issue_type",
        "table",
        "record_key",
        "field",
        "old_value",
        "new_value",
        "action",
        "status",
    ]
    return pd.DataFrame(rows, columns=columns)


METRIC_TOKEN = re.compile(r"\{\{metric:([^}]+)\}\}")
DIMENSIONS = ["region", "crop", "scenario", "ngfs_scenario", "period", "action_id"]


def _missing(value: Any) -> bool:
    return value is None or (isinstance(value, float) and pd.isna(value))


def _optional(value: Any) -> Any:
    return None if _missing(value) else value


def _optional_float(value: Any) -> float | None:
    return None if _missing(value) else float(value)


def _check_columns(frame: pd.DataFrame, columns: Sequence[str], what: str) -> None:
    absent = [c for c in columns if c not in frame.columns]
    if absent:
        raise ValueError(f"The {what} table has no {', '.join(absent)} column.")


def build_metric_rows(
    frames: Sequence[pd.DataFrame],
    result_set_id: str,
    artifact_ids: Mapping[str, str],
    assumption_ids: Mapping[str, str],
) -> tuple[list[m.Metric], dict[str, str]]:
    """Turn the steps' metric tables into rows, swapping table and assumption names for ids.

    Also returns each metric key's new metric id, which the insights cite.
    """
    rows: list[m.Metric] = []
    metric_ids: dict[str, str] = {}
    for frame in frames:
        _check_columns(frame, METRIC_COLUMNS, "metric")
        for record in frame.to_dict("records"):
            key = str(record["key"])
            if key in metric_ids:
                raise ValueError(f"The metric key {key!r} is used twice.")
            if _missing(record["value"]):
                raise ValueError(f"The metric {key!r} has no value.")
            lineage: list[Any] = []
            for entry in record["lineage"]:
                table = entry["table"]
                if table not in artifact_ids:
                    raise ValueError(
                        f"The metric {key!r} names the table {table!r}, which no step wrote."
                    )
                lineage.append({"artifact": artifact_ids[table], "filter": entry["filter"]})
            assumption_refs: list[str] = []
            for name in record["assumptions"]:
                if name not in assumption_ids:
                    raise ValueError(
                        f"The metric {key!r} names the assumption {name!r}, which no step recorded."
                    )
                assumption_refs.append(assumption_ids[name])
            metric_id = ids.new_id("metric")
            metric_ids[key] = metric_id
            rows.append(
                m.Metric(
                    metric_id=metric_id,
                    result_set_id=result_set_id,
                    name=record["name"],
                    unit=record["unit"],
                    value=float(record["value"]),
                    low=_optional_float(record["low"]),
                    high=_optional_float(record["high"]),
                    **{d: _optional(record[d]) for d in DIMENSIONS},
                    lineage=lineage,
                    assumption_ids=assumption_refs,
                )
            )
    return rows, metric_ids


def build_insight_rows(
    held: Sequence[tuple[str, pd.DataFrame]],
    result_set_id: str,
    metric_ids: Mapping[str, str],
) -> list[m.Insight]:
    """Turn the steps' insight tables (each with its step name) into rows.

    Every `{{metric:<key>}}` in the text and every entry of `metric_keys` becomes the metric id.
    """

    def metric_id(key: str, title: str) -> str:
        if key not in metric_ids:
            raise ValueError(
                f"The insight {title!r} cites the metric {key!r}, which no step wrote."
            )
        return metric_ids[key]

    rows: list[m.Insight] = []
    for step_name, frame in held:
        _check_columns(frame, INSIGHT_COLUMNS, "insight")
        for record in frame.to_dict("records"):
            title = str(record["title"])
            text = METRIC_TOKEN.sub(
                lambda token, title=title: "{{metric:" + metric_id(token.group(1), title) + "}}",
                record["text"],
            )
            rows.append(
                m.Insight(
                    insight_id=ids.new_id("insight"),
                    result_set_id=result_set_id,
                    step=step_name,
                    title=title,
                    text=text,
                    metric_ids=[metric_id(key, title) for key in record["metric_keys"]],
                )
            )
    return rows


class RunExecution:
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.tables: dict[str, Artifact] = {}
        self.metrics: list[pd.DataFrame] = []
        self.insights: list[tuple[str, pd.DataFrame]] = []
        self.assumption_ids: dict[str, str] = {}

    def execute(self) -> None:
        with session_scope() as session:
            run = session.get_one(m.Run, self.run_id)
            recipe = get_recipe(run.recipe_id)
            overrides: dict[str, Any] = run.params.get("step_params", {})
            files = {f.path: f for f in session.scalars(select(m.SourceFile)).all()}
            step_runs = self._create_step_runs(session, recipe, overrides)
        emit(self.run_id, "run.status", {"status": "running"})
        ctx = RunContext(
            run_id=self.run_id, recipe_id=recipe.recipe_id, sources=PackageSources(files)
        )

        for spec, step_run_id in zip(recipe.steps, step_runs, strict=True):
            self._execute_step(ctx, spec, step_run_id, step_params(spec, overrides))

        with session_scope() as session:
            result_set = m.ResultSet(result_set_id=ids.new_id("result_set"), run_id=self.run_id)
            session.add(result_set)
            # The models declare no relationships, so nothing else orders this insert first.
            session.flush()
            artifact_ids = {
                name: table.artifact_id
                for name, table in self.tables.items()
                if table.artifact_id is not None
            }
            metric_rows, metric_ids = build_metric_rows(
                self.metrics, result_set.result_set_id, artifact_ids, self.assumption_ids
            )
            session.add_all(metric_rows)
            session.add_all(build_insight_rows(self.insights, result_set.result_set_id, metric_ids))
            run = session.get_one(m.Run, self.run_id)
            run.status = "succeeded"
            run.finished_at = _now()
        emit(self.run_id, "run.status", {"status": "succeeded"})
        emit(
            self.run_id,
            "run.finished",
            {"status": "succeeded", "result_set_id": result_set.result_set_id},
        )

    def _create_step_runs(
        self, session: Session, recipe: Recipe, overrides: Mapping[str, Any]
    ) -> list[str]:
        step_run_ids: list[str] = []
        for position, spec in enumerate(recipe.steps, start=1):
            info = STEPS[spec.name]
            step_run = m.StepRun(
                step_run_id=ids.new_id("step_run"),
                run_id=self.run_id,
                position=position,
                step=spec.name,
                kind=info.kind,
                summary=info.summary,
                params=dict(step_params(spec, overrides)),
            )
            session.add(step_run)
            step_run_ids.append(step_run.step_run_id)
        return step_run_ids

    def _execute_step(
        self, ctx: RunContext, spec: StepSpec, step_run_id: str, params: Params
    ) -> None:
        info = STEPS[spec.name]
        started = time.monotonic()
        with session_scope() as session:
            step_run = session.get_one(m.StepRun, step_run_id)
            step_run.status = "running"
            step_run.started_at = _now()
            inputs = self._load_inputs(session, spec)
            step_run.input_artifacts = [
                a.artifact_id for a in inputs.values() if a.artifact_id is not None
            ]
        emit(
            self.run_id, "step.started", {"step": spec.name, "annotation": info.summary}, spec.name
        )
        log.info("step started", extra={"run_id": self.run_id, "step": spec.name})

        def sink(type_: str, payload: dict[str, Any]) -> None:
            emit(self.run_id, type_, {"step": spec.name, **payload}, spec.name)

        try:
            with event_sink(sink):
                result = info.func(ctx, inputs, params)
            with session_scope() as session:
                self._store_result(session, spec.name, step_run_id, result)
        except Exception as error:
            seconds = round(time.monotonic() - started, 3)
            with session_scope() as session:
                step_run = session.get_one(m.StepRun, step_run_id)
                step_run.status = "failed"
                step_run.error = failure_message(error)
                step_run.seconds = seconds
                step_run.finished_at = _now()
            emit(
                self.run_id,
                "step.finished",
                {
                    "step": spec.name,
                    "annotation": info.summary,
                    "status": "failed",
                    "seconds": seconds,
                    "error": failure_message(error),
                },
                spec.name,
            )
            raise StepFailed(spec.name, failure_message(error)) from error

        seconds = round(time.monotonic() - started, 3)
        with session_scope() as session:
            step_run = session.get_one(m.StepRun, step_run_id)
            step_run.status = "succeeded"
            step_run.seconds = seconds
            step_run.finished_at = _now()
        if result.proposals is not None and len(result.proposals):
            counts = result.proposals.groupby("rule_id").size().astype(int).to_dict()
            emit(self.run_id, "proposal.created", {"step": spec.name, "count_per_rule": counts})
        emit(
            self.run_id,
            "step.finished",
            {
                "step": spec.name,
                "annotation": info.summary,
                "status": "succeeded",
                "seconds": seconds,
            },
            spec.name,
        )
        log.info(
            "step finished", extra={"run_id": self.run_id, "step": spec.name, "seconds": seconds}
        )

    def _load_inputs(self, session: Session, spec: StepSpec) -> dict[str, Artifact]:
        inputs: dict[str, Artifact] = {}
        for name in spec.inputs:
            if name == PROPOSALS_INPUT:
                frame = proposals_with_status(session, self.run_id)
                inputs[name] = Artifact(name=name, layer="result", frame=frame)
            elif name in self.tables:
                inputs[name] = self.tables[name]
            else:
                raise KeyError(f"step {spec.name} reads {name!r}, which no earlier step wrote")
        return inputs

    def _store_result(
        self, session: Session, step: str, step_run_id: str, result: StepResult
    ) -> None:
        bucket = get_settings().s3_bucket
        output_ids: list[str] = []
        for table in result.tables:
            artifact_id = ids.new_id("artifact")
            content = objects.frame_to_parquet(table.frame)
            uri = objects.put_bytes(bucket, objects.artifact_key(self.run_id, artifact_id), content)
            session.add(
                m.Artifact(
                    artifact_id=artifact_id,
                    step_run_id=step_run_id,
                    run_id=self.run_id,
                    name=table.name,
                    uri=uri,
                    layer=table.layer,
                    row_count=len(table.frame),
                    columns=[str(c) for c in table.frame.columns],
                    content_hash=objects.content_hash(content),
                )
            )
            self.tables[table.name] = Artifact(
                name=table.name, layer=table.layer, frame=table.frame, artifact_id=artifact_id
            )
            output_ids.append(artifact_id)
        session.get_one(m.StepRun, step_run_id).output_artifacts = output_ids

        if result.proposals is not None:
            for row in result.proposals.to_dict("records"):
                session.add(
                    m.Proposal(
                        proposal_id=ids.new_id("proposal"),
                        run_id=self.run_id,
                        **{str(k): v if k == "evidence" else _text(v) for k, v in row.items()},
                    )
                )
        session.flush()

        if result.decisions is not None and len(result.decisions):
            self._store_policy_decisions(session, result.decisions)

        if result.rules is not None:
            for row in result.rules.to_dict("records"):
                existing = session.get(m.Rule, (row["rule_id"], row["version"]))
                rule = existing or m.Rule(rule_id=row["rule_id"], version=row["version"])
                rule.description = row["description"]
                rule.author = row["author"]
                rule.backtest = row["backtest"]
                rule.last_run_id = self.run_id
                session.add(rule)

        if result.metrics is not None and len(result.metrics):
            self.metrics.append(result.metrics)
        if result.insights is not None and len(result.insights):
            self.insights.append((step, result.insights))

        for use in result.assumptions:
            if use.name in self.assumption_ids:
                raise ValueError(f"The assumption {use.name!r} is recorded twice in this run.")
            assumption_id = ids.new_id("assumption")
            self.assumption_ids[use.name] = assumption_id
            session.add(
                m.Assumption(
                    assumption_id=assumption_id,
                    run_id=self.run_id,
                    step=step,
                    name=use.name,
                    label=use.label,
                    value=use.value,
                    unit=use.unit,
                    source=use.source,
                )
            )

    def _store_policy_decisions(self, session: Session, decisions: pd.DataFrame) -> None:
        """Approvals under a rule policy apply only to proposals nobody has decided yet.

        A person's earlier decision, including a rejection, always stands.
        """
        keys = decisions["proposal_key"].tolist()
        decided = set(
            session.scalars(
                select(m.Decision.target_id).where(
                    m.Decision.target_type == "proposal", m.Decision.target_id.in_(keys)
                )
            ).all()
        )
        for row in decisions.to_dict("records"):
            if row["proposal_key"] in decided:
                continue
            session.add(
                m.Decision(
                    decision_id=ids.new_id("decision"),
                    target_type="proposal",
                    target_id=row["proposal_key"],
                    decision=row["decision"],
                    reviewer=row["reviewer"],
                    comment=row["comment"],
                    run_id=self.run_id,
                )
            )


class StepFailed(Exception):
    def __init__(self, step: str, message: str) -> None:
        super().__init__(message)
        self.step = step


def failure_message(error: Exception) -> str:
    """What a person reads when a step stops. A step's own checks raise ValueError with a plain
    message; anything else is unexpected, so its type is named for the data specialist."""
    if isinstance(error, ValueError):
        return str(error)
    return f"Unexpected {type(error).__name__}: {error}"


def _text(value: Any) -> Any:
    """Proposal values are stored as text; missing values stay empty."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return value if isinstance(value, str) else str(value)


def execute_run(run_id: str) -> None:
    """Execute a claimed run and record its outcome. Failures are recorded, not raised."""
    try:
        RunExecution(run_id).execute()
    except Exception as error:
        log.exception("run failed", extra={"run_id": run_id})  # the traceback stays in the logs
        with session_scope() as session:
            run = session.get_one(m.Run, run_id)
            run.status = "failed"
            run.error = str(error)
            run.finished_at = _now()
        emit(run_id, "run.status", {"status": "failed"})
        emit(
            run_id,
            "run.finished",
            {"status": "failed", "result_set_id": None, "error": str(error)},
        )
