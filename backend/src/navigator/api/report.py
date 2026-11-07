"""Report screen: draft, review and publish a result set's report, and export it."""

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from navigator import ids
from navigator.api import schemas
from navigator.api.dependencies import PersonaDep, SessionDep, require_role
from navigator.api.errors import BAD_PERSONA, NOT_FOUND, WRONG_ROLE, invalid, not_found
from navigator.db import models as m

router = APIRouter(prefix="/api", tags=["report"])

# Results move one step at a time. Publishing is the last move.
NEXT_STATUS = {"draft": "in_review", "in_review": "approved", "approved": "published"}
STATUS_WORDS = {
    "draft": "draft",
    "in_review": "in review",
    "approved": "approved",
    "published": "published",
    "superseded": "superseded",
}
TOKEN = re.compile(r"\{\{(metric|insight):(\w+)\}\}")
NOT_ALLOWED = {
    403: {"model": schemas.ErrorMessage, "description": "The persona cannot do this."},
}


def _result_set(session: Session, result_set_id: str) -> m.ResultSet:
    result_set = session.get(m.ResultSet, result_set_id)
    if result_set is None:
        raise not_found("results", result_set_id)
    return result_set


def _shown_report(session: Session, result_set_id: str) -> m.Report:
    """The published report when there is one, otherwise the latest draft."""
    reports = session.scalars(
        select(m.Report)
        .where(m.Report.result_set_id == result_set_id)
        .order_by(m.Report.version.desc())
    ).all()
    if not reports:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "This result set has no report yet. Draft one first.",
        )
    return next((r for r in reports if r.status == "published"), reports[0])


@router.post(
    "/result-sets/{result_set_id}/report",
    operation_id="requestReport",
    status_code=status.HTTP_202_ACCEPTED,
    responses={**BAD_PERSONA, **WRONG_ROLE, **NOT_ALLOWED, **NOT_FOUND},
)
def request_report(result_set_id: str, session: SessionDep, persona: PersonaDep) -> schemas.Run:
    """Queue a report run: the report drafter writes a draft for results review."""
    require_role(persona, "sustainability_specialist", "ask for a report draft")
    result_set = _result_set(session, result_set_id)
    analysis_run = session.get_one(m.Run, result_set.run_id)
    where = ("path", "result_set_id")
    if analysis_run.status != "succeeded":
        raise invalid(
            where,
            "The run behind these results has not succeeded, so there is nothing to draft from.",
        )
    if result_set.status in ("approved", "published", "superseded"):
        raise invalid(
            where,
            f"These results are {STATUS_WORDS[result_set.status]}, so the report text is fixed. "
            "Draft a report before approving the results.",
        )
    waiting = session.scalars(
        select(m.Run.run_id).where(
            m.Run.kind == "report",
            m.Run.status.in_(["queued", "running"]),
            m.Run.params["result_set_id"].astext == result_set_id,
        )
    ).first()
    if waiting:
        raise invalid(
            where, f"A draft is already being written (run {waiting}). Wait for it to finish."
        )

    params = {"result_set_id": result_set_id}
    run = m.Run(
        run_id=ids.new_id("run"),
        recipe_id=analysis_run.recipe_id,
        version=analysis_run.version,
        kind="report",
        parent_run_id=analysis_run.run_id,
        params=params,
        params_hash=hashlib.sha256(
            json.dumps(params, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        status="queued",
        triggered_by=persona.name,
    )
    session.add(run)
    session.add(
        m.RunEvent(
            event_id=ids.new_id("run_event"),
            run_id=run.run_id,
            type="run.status",
            payload={"status": "queued"},
        )
    )
    session.flush()
    session.refresh(run)
    return schemas.Run.model_validate(run)


@router.get(
    "/result-sets/{result_set_id}/report",
    operation_id="getReport",
    responses=NOT_FOUND,
)
def get_report(result_set_id: str, session: SessionDep) -> schemas.Report:
    """The draft or published report, with every cited metric."""
    result_set = _result_set(session, result_set_id)
    report = _shown_report(session, result_set_id)
    insights = session.scalars(
        select(m.Insight)
        .where(m.Insight.result_set_id == result_set_id)
        .order_by(m.Insight.created_at, m.Insight.insight_id)
    ).all()
    cited = {
        metric_id
        for text in [*(p["text"] for p in report.paragraphs), *(i.text for i in insights)]
        for kind, metric_id in TOKEN.findall(text)
        if kind == "metric"
    }
    cited.update(metric_id for i in insights for metric_id in i.metric_ids)
    metrics = session.scalars(
        select(m.Metric).where(
            m.Metric.result_set_id == result_set_id, m.Metric.metric_id.in_(sorted(cited))
        )
    ).all()
    return schemas.Report(
        report_id=report.report_id,
        result_set_id=result_set_id,
        version=report.version,
        status=schemas.ResultSet.model_validate(result_set).status,
        run_id=report.run_id,
        drafted_at=report.created_at,
        published_at=result_set.published_at,
        paragraphs=[schemas.ReportParagraph.model_validate(p) for p in report.paragraphs],
        metrics={x.metric_id: schemas.Metric.model_validate(x) for x in metrics},
        insights=[schemas.Insight.model_validate(i) for i in insights],
    )


@router.post(
    "/result-sets/{result_set_id}/decisions",
    operation_id="decideResultSet",
    status_code=status.HTTP_201_CREATED,
    responses={**BAD_PERSONA, **WRONG_ROLE, **NOT_ALLOWED, **NOT_FOUND},
)
def decide_result_set(
    result_set_id: str,
    request: schemas.ResultSetDecisionRequest,
    session: SessionDep,
    persona: PersonaDep,
) -> schemas.Decision:
    """Move a result set to in review, approved or published."""
    require_role(persona, "sustainability_specialist", "review and publish results")
    result_set = session.get(m.ResultSet, result_set_id, with_for_update=True)
    if result_set is None:
        raise not_found("results", result_set_id)
    where = ("body", "status")
    if NEXT_STATUS.get(result_set.status) != request.status:
        allowed = NEXT_STATUS.get(result_set.status)
        raise invalid(
            where,
            f"These results are {STATUS_WORDS[result_set.status]}. "
            + (
                f"The next move is to {STATUS_WORDS[allowed]}."
                if allowed
                else "They cannot move any further."
            ),
        )
    now = datetime.now(UTC)
    if request.status == "approved":
        result_set.approved_by = persona.name
    if request.status == "published":
        _publish(session, result_set, now)
    result_set.status = request.status
    decision = m.Decision(
        decision_id=ids.new_id("decision"),
        target_type="result_set",
        target_id=result_set_id,
        decision=request.status,
        reviewer=persona.name,
        comment=request.comment,
        run_id=result_set.run_id,
    )
    session.add(decision)
    session.flush()
    session.refresh(decision)
    return schemas.Decision.model_validate(decision)


def _publish(session: Session, result_set: m.ResultSet, now: datetime) -> None:
    drafts = session.scalars(
        select(m.Report)
        .where(m.Report.result_set_id == result_set.result_set_id, m.Report.status == "draft")
        .order_by(m.Report.version.desc())
    ).all()
    if not drafts:
        raise invalid(
            ("body", "status"), "These results have no report draft. Draft a report first."
        )
    drafts[0].status = "published"
    for older in drafts[1:]:
        older.status = "superseded"
    result_set.published_at = now
    # Only the same recipe: a published result set of another recipe stays published.
    earlier = select(m.Run.run_id).where(
        m.Run.recipe_id == session.get_one(m.Run, result_set.run_id).recipe_id
    )
    session.execute(
        update(m.ResultSet)
        .where(
            m.ResultSet.status == "published",
            m.ResultSet.result_set_id != result_set.result_set_id,
            m.ResultSet.run_id.in_(earlier),
        )
        .values(status="superseded")
    )


def format_metric(unit: str, value: float) -> str:
    """A metric as the report shows it: two significant figures for euros, one decimal for %."""
    if unit == "%":
        return f"{value:.1f}%"
    if unit == "share":
        return f"{100 * value:.1f}%"
    sign = "-" if value < 0 else ""
    rounded = abs(float(f"{value:.2g}"))
    if rounded >= 1e6:
        number = f"{rounded / 1e6:g}M"
    elif rounded >= 1e3:
        number = f"{rounded / 1e3:g}k"
    else:
        number = f"{rounded:g}"
    if unit.startswith("€"):
        return f"{sign}€{number}{unit[1:]}"
    return f"{sign}{number} {unit}"


def _resolve(text: str, metrics: dict[str, m.Metric], insights: dict[str, m.Insight]) -> str:
    def metric_text(found: re.Match[str]) -> str:
        metric = metrics.get(found.group(2))
        return found.group(0) if metric is None else format_metric(metric.unit, metric.value)

    def replace(found: re.Match[str]) -> str:
        if found.group(1) == "metric":
            return metric_text(found)
        insight = insights.get(found.group(2))
        return found.group(0) if insight is None else TOKEN.sub(metric_text, insight.text)

    return TOKEN.sub(replace, text)


@router.get(
    "/result-sets/{result_set_id}/report/export",
    operation_id="exportReport",
    response_class=Response,
    responses={
        200: {"content": {"text/markdown": {}}, "description": "The published report as Markdown."},
        **NOT_FOUND,
    },
)
def export_report(result_set_id: str, session: SessionDep) -> Response:
    """The published report as Markdown, with every token replaced by its number and unit."""
    result_set = _result_set(session, result_set_id)
    if result_set.status != "published":
        raise invalid(
            ("path", "result_set_id"),
            "Only a published report can be exported. Publish the report first.",
        )
    report = _shown_report(session, result_set_id)
    metrics = {
        x.metric_id: x
        for x in session.scalars(select(m.Metric).where(m.Metric.result_set_id == result_set_id))
    }
    insights = {
        x.insight_id: x
        for x in session.scalars(select(m.Insight).where(m.Insight.result_set_id == result_set_id))
    }
    published = result_set.published_at or datetime.now(UTC)
    lines = [
        "# Climate risk report",
        "",
        f"Published {published:%-d %B %Y}"
        + (f", approved by {result_set.approved_by}." if result_set.approved_by else "."),
    ]
    paragraphs: list[dict[str, Any]] = report.paragraphs
    for paragraph in paragraphs:
        if paragraph.get("heading"):
            lines += ["", f"## {paragraph['heading']}"]
        lines += ["", _resolve(paragraph["text"], metrics, insights)]
    return Response(
        "\n".join(lines) + "\n",
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="report-{result_set_id}.md"'},
    )
