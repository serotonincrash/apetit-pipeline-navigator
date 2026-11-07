"""Executes a report run: the report drafter writes a numbered draft for an existing result set.

A report run has no steps and creates no result set. Its draft is stored only when every
paragraph passed its checks, in the same transaction that marks the run succeeded.
"""

import re
from collections import Counter
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from navigator import ids
from navigator.agents import report_drafter as drafter
from navigator.db import models as m
from navigator.db.decisions import latest_decisions, option_status
from navigator.db.session import session_scope
from navigator.llm import get_llm
from navigator.logs import get_logger
from navigator.storage.query import read_all_rows
from navigator.worker.runner import emit, failure_message

log = get_logger(__name__)

DRIVER_ROWS = 12


def execute_report_run(run_id: str) -> None:
    """Execute a claimed report run and record its outcome. Failures are recorded, not raised."""
    try:
        _draft_report(run_id)
    except Exception as error:
        log.exception("report run failed", extra={"run_id": run_id})
        message = failure_message(error)
        with session_scope() as session:
            run = session.get_one(m.Run, run_id)
            run.status = "failed"
            run.error = message
            run.finished_at = datetime.now(UTC)
        emit(run_id, "run.status", {"status": "failed"})
        emit(run_id, "run.finished", {"status": "failed", "result_set_id": None, "error": message})


def _draft_report(run_id: str) -> None:
    with session_scope() as session:
        result_set_id: str = session.get_one(m.Run, run_id).params["result_set_id"]
        evidence = gather_evidence(session, result_set_id)
    emit(run_id, "run.status", {"status": "running"})

    def call_failed(agent: str, item: str, reason: str) -> None:
        emit(run_id, "call.failed", {"step": None, "agent": agent, "item": item, "reason": reason})

    paragraphs = drafter.draft_report(get_llm(run_id, on_failure=call_failed), evidence)

    with session_scope() as session:
        rows: list[dict[str, Any]] = [
            {"section": p.section, "heading": p.heading, "text": p.text, "call_id": p.call_id}
            for p in paragraphs
        ]
        rows += method_paragraphs(session, result_set_id, run_id)
        latest = session.scalar(
            select(func.max(m.Report.version)).where(m.Report.result_set_id == result_set_id)
        )
        session.add(
            m.Report(
                report_id=ids.new_id("report"),
                result_set_id=result_set_id,
                run_id=run_id,
                version=(latest or 0) + 1,
                paragraphs=rows,
            )
        )
        run = session.get_one(m.Run, run_id)
        run.status = "succeeded"
        run.finished_at = datetime.now(UTC)
    emit(run_id, "run.status", {"status": "succeeded"})
    emit(run_id, "run.finished", {"status": "succeeded", "result_set_id": result_set_id})


def gather_evidence(session: Session, result_set_id: str) -> drafter.ReportEvidence:
    result_set = session.get_one(m.ResultSet, result_set_id)
    action_names = {
        a.action_id: a.short_name or a.name for a in session.scalars(select(m.ActionDefinition))
    }
    metrics = [
        drafter.MetricFact(
            metric_id=x.metric_id,
            name=x.name,
            unit=x.unit,
            value=x.value,
            low=x.low,
            high=x.high,
            region=x.region,
            crop=x.crop,
            scenario=x.scenario,
            ngfs_scenario=x.ngfs_scenario,
            period=x.period,
            action=action_names.get(x.action_id or ""),
        )
        for x in session.scalars(
            select(m.Metric)
            .where(m.Metric.result_set_id == result_set_id)
            .order_by(m.Metric.metric_id)
        )
    ]
    insights = [
        drafter.InsightFact(i.insight_id, i.title, i.text)
        for i in session.scalars(
            select(m.Insight)
            .where(m.Insight.result_set_id == result_set_id)
            .order_by(m.Insight.insight_id)
        )
    ]
    option_rows = session.scalars(
        select(m.ActionOption)
        .where(m.ActionOption.result_set_id == result_set_id)
        .order_by(m.ActionOption.option_id)
    ).all()
    marks = latest_decisions(session, "action_option", (o.option_id for o in option_rows))
    options = [
        drafter.OptionFact(o.name, option_status(marks.get(o.option_id)), o.confidence)
        for o in option_rows
    ]
    assumptions = [
        drafter.AssumptionFact(a.label, a.value, a.unit)
        for a in session.scalars(
            select(m.Assumption)
            .where(m.Assumption.run_id == result_set.run_id)
            .order_by(m.Assumption.step, m.Assumption.name)
        )
    ]
    return drafter.ReportEvidence(
        metrics, insights, options, loss_drivers(session, result_set.run_id), assumptions
    )


def loss_drivers(session: Session, run_id: str) -> list[drafter.DriverFact]:
    """The strongest weather driver of each crop and region under each climate scenario."""
    artifact = session.scalars(
        select(m.Artifact).where(m.Artifact.run_id == run_id, m.Artifact.name == "loss_drivers")
    ).first()
    if artifact is None:
        return []
    table = read_all_rows(artifact.uri)
    table = table[
        ~table["scenario"].isin(["baseline", "historical"]) & (table["yield_effect_pct"] != 0)
    ]
    strongest = table.loc[
        table["yield_effect_pct"].abs().groupby([table["unit"], table["scenario"]]).idxmax()
    ]
    strongest = strongest.reindex(
        strongest["yield_effect_pct"].abs().sort_values(ascending=False).index
    )
    return [
        drafter.DriverFact(
            str(row["unit"]),
            str(row["scenario"]),
            str(row["driver"]),
            "lowers" if row["yield_effect_pct"] < 0 else "raises",
        )
        for _, row in strongest.head(DRIVER_ROWS).iterrows()
    ]


_RECIPE_SETTING = re.compile(r"^recipe \w+, \w+ params$")


def _value_text(value: Any) -> str:
    """An assumption value in words: rounded numbers, pairs as "name value", none as not known."""
    if value is None:
        return "not known"
    if isinstance(value, bool | int):
        return str(value)
    if isinstance(value, float):
        return f"{value:,.0f}" if abs(value) >= 100 else f"{value:.3g}"
    if isinstance(value, dict):
        pairs = cast(dict[str, Any], value)
        return ", ".join(f"{k.replace('_', ' ')} {_value_text(v)}" for k, v in pairs.items())
    if isinstance(value, list):
        return ", ".join(_value_text(v) for v in cast(list[Any], value))
    return str(value)


def _agent_name(agent: str) -> str:
    return agent.replace("-", " ").replace("_", " ").capitalize()


def _assumption_line(label: str, value: Any, unit: str, source: str) -> str:
    source = "a recipe setting" if _RECIPE_SETTING.match(source) else source
    amount = "not known" if value is None else f"{_value_text(value)} {unit}".strip()
    return f"- {label}: {amount}, from {source}"


def method_paragraphs(
    session: Session, result_set_id: str, report_run_id: str
) -> list[dict[str, Any]]:
    """The rest of 'Method and limits', written from the run's records, not by the assistant."""
    result_set = session.get_one(m.ResultSet, result_set_id)
    run_id = result_set.run_id

    load_params = session.scalars(
        select(m.StepRun.params).where(m.StepRun.run_id == run_id, m.StepRun.step == "load_raw")
    ).first()
    paths = [entry["path"] for entry in (load_params or {}).get("files", {}).values()]
    files = session.scalars(
        select(m.SourceFile).where(m.SourceFile.path.in_(paths)).order_by(m.SourceFile.path)
    ).all()
    sources = "\n".join(f"- {f.path}, SHA-256 {f.sha256}" for f in files) or "No source files."

    proposals = session.scalars(
        select(m.Proposal).where(m.Proposal.run_id == run_id, m.Proposal.action == "fix")
    ).all()
    latest = latest_decisions(session, "proposal", (p.proposal_key for p in proposals))
    approved: Counter[tuple[str, str]] = Counter(
        (p.rule_id, d.reviewer)
        for p in proposals
        if (d := latest.get(p.proposal_key)) is not None and d.decision != "reject"
    )
    corrections = (
        "\n".join(
            f"- Data check {rule}: {count} fixes approved by {reviewer}"
            for (rule, reviewer), count in sorted(approved.items())
        )
        or "No fixes were approved for this run."
    )

    assumptions = (
        "\n".join(
            _assumption_line(a.label, a.value, a.unit, a.source)
            for a in session.scalars(
                select(m.Assumption)
                .where(m.Assumption.run_id == run_id)
                .order_by(m.Assumption.step, m.Assumption.name)
            )
        )
        or "No assumptions were recorded."
    )

    calls = Counter(
        tuple(row)
        for row in session.execute(
            select(m.LlmCall.agent, m.LlmCall.prompt_version).where(
                m.LlmCall.run_id.in_([run_id, report_run_id]),
                m.LlmCall.status.in_(["ok", "fake model"]),
            )
        ).all()
    )
    # The model's name stays in the call log; the report names only the agent and prompt.
    models = (
        "\n".join(
            f"- {_agent_name(agent)}: prompt version {version}, {count} texts"
            for (agent, version), count in sorted(calls.items())
        )
        or "No text was written by the assistant."
    )

    return [
        {"section": "method", "heading": heading, "text": text, "call_id": None}
        for heading, text in [
            ("Data sources", sources),
            ("Corrections approved", corrections),
            ("Assumptions used", assumptions),
            ("Assistant prompts", models),
        ]
    ]
