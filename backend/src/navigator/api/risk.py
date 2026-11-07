"""Risk view: result sets, their metrics, where each number came from, and the assumptions."""

from typing import Annotated, Any, cast

from fastapi import APIRouter, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from navigator.api import schemas
from navigator.api.dependencies import SessionDep
from navigator.api.errors import NOT_FOUND, invalid, not_found
from navigator.api.review import DEFAULT_RECIPE, proposal_out
from navigator.api.runs import artifact_out, row_filter
from navigator.db import models as m
from navigator.db.decisions import latest_decisions, proposal_status
from navigator.storage.query import corrected_record_keys, read_rows

router = APIRouter(prefix="/api", tags=["risk"])


@router.get("/result-sets", operation_id="listResultSets")
def list_result_sets(
    session: SessionDep,
    run_id: str | None = None,
    recipe_id: Annotated[
        str | None,
        Query(description="Defaults to farm_climate_risk when no run id is given."),
    ] = None,
    result_set_status: Annotated[schemas.ResultSetStatus | None, Query(alias="status")] = None,
) -> list[schemas.ResultSet]:
    """Result sets, newest first, optionally those of one run or one recipe."""
    query = select(m.ResultSet)
    if run_id:
        query = query.where(m.ResultSet.run_id == run_id)
    elif recipe_id is None:
        recipe_id = DEFAULT_RECIPE
    if recipe_id:
        query = query.join(m.Run, m.Run.run_id == m.ResultSet.run_id).where(
            m.Run.recipe_id == recipe_id
        )
    if result_set_status:
        query = query.where(m.ResultSet.status == result_set_status)
    rows = session.scalars(
        query.order_by(m.ResultSet.created_at.desc(), m.ResultSet.result_set_id.desc())
    ).all()
    return [schemas.ResultSet.model_validate(r) for r in rows]


@router.get("/result-sets/{result_set_id}/metrics", operation_id="listMetrics", responses=NOT_FOUND)
def list_metrics(
    result_set_id: str,
    session: SessionDep,
    name: str | None = None,
    region: str | None = None,
    crop: str | None = None,
    site: str | None = None,
    scenario: str | None = None,
    ngfs_scenario: str | None = None,
    period: str | None = None,
    limit: Annotated[int, Query(ge=1, le=5000)] = 1000,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> schemas.MetricList:
    """Metrics of a result set, filtered by region, crop, site, scenarios and period."""
    if session.get(m.ResultSet, result_set_id) is None:
        raise not_found("results", result_set_id)
    query = select(m.Metric).where(m.Metric.result_set_id == result_set_id)
    for column, value in {
        m.Metric.name: name,
        m.Metric.region: region,
        m.Metric.crop: crop,
        m.Metric.site: site,
        m.Metric.scenario: scenario,
        m.Metric.ngfs_scenario: ngfs_scenario,
        m.Metric.period: period,
    }.items():
        if value:
            query = query.where(column == value)
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = session.scalars(
        query.order_by(
            m.Metric.name,
            m.Metric.region,
            m.Metric.crop,
            m.Metric.site,
            m.Metric.scenario,
            m.Metric.ngfs_scenario,
            m.Metric.period,
            m.Metric.action_id,
            m.Metric.metric_id,
        )
        .limit(limit)
        .offset(offset)
    ).all()
    return schemas.MetricList(total=total, items=[schemas.Metric.model_validate(r) for r in rows])


@router.get("/metrics/{metric_id}/sources", operation_id="getMetricSources", responses=NOT_FOUND)
def get_metric_sources(metric_id: str, session: SessionDep) -> schemas.MetricSources:
    """Where a number came from: source tables and filters, corrections and assumptions."""
    metric = session.get(m.Metric, metric_id)
    if metric is None:
        raise not_found("metric", metric_id)
    result_set = session.get(m.ResultSet, metric.result_set_id)
    run_id = result_set.run_id if result_set else None

    sources: list[schemas.MetricSource] = []
    corrected: set[str] = set()
    for entry in metric.lineage:
        row = session.execute(
            select(m.Artifact, m.StepRun.step)
            .join(m.StepRun, m.StepRun.step_run_id == m.Artifact.step_run_id)
            .where(m.Artifact.artifact_id == entry["artifact"])
        ).first()
        if row is None:
            raise not_found("table", entry["artifact"])
        artifact, step = row
        filters = lineage_filter_strings(entry.get("filter") or {})
        where, parameters = row_filter(artifact, filters)
        _, row_count = read_rows(artifact.uri, where, parameters, limit=0)
        sources.append(
            schemas.MetricSource(
                artifact=artifact_out(artifact, step), filters=filters, row_count=row_count
            )
        )
        if {"record_key", "n_corrections"} <= set(artifact.columns):
            corrected.update(corrected_record_keys(artifact.uri, where, parameters))

    return schemas.MetricSources(
        metric=schemas.Metric.model_validate(metric),
        sources=sources,
        corrections=_approved_corrections(session, run_id, corrected),
        assumptions=_assumptions_in_order(session, metric.assumption_ids),
    )


@router.get("/assumptions", operation_id="listAssumptions", responses=NOT_FOUND)
def list_assumptions(
    session: SessionDep, result_set_id: str | None = None, run_id: str | None = None
) -> list[schemas.Assumption]:
    """Assumptions behind a result set or run, by step and name. Give either id."""
    if result_set_id:
        result_set = session.get(m.ResultSet, result_set_id)
        if result_set is None:
            raise not_found("results", result_set_id)
        run_id = result_set.run_id
    if not run_id:
        raise invalid(("query", "run_id"), "Give a result set id or a run id.")
    rows = session.scalars(
        select(m.Assumption)
        .where(m.Assumption.run_id == run_id)
        .order_by(m.Assumption.step, m.Assumption.name)
    ).all()
    return [schemas.Assumption.model_validate(r) for r in rows]


def lineage_filter_strings(lineage_filter: dict[str, Any]) -> list[str]:
    """A lineage filter as `column=value` strings, the format the table rows endpoint takes.

    A list value gives one string per item. Metric lineage never holds ranges, so one is an error.
    """
    strings: list[str] = []
    for column, value in lineage_filter.items():
        if isinstance(value, dict):
            raise ValueError(
                f"The filter on {column} is a range. Metric sources take single values and lists."
            )
        items = cast("list[Any]", value) if isinstance(value, list) else [value]
        for item in items:
            strings.append(f"{column}={_filter_text(item)}")
    return strings


def _filter_text(value: Any) -> str:
    # Booleans compare as DuckDB writes them when cast to text.
    return str(value).lower() if isinstance(value, bool) else str(value)


def _approved_corrections(
    session: Session, run_id: str | None, record_keys: set[str]
) -> list[schemas.Proposal]:
    if run_id is None or not record_keys:
        return []
    proposals = session.scalars(
        select(m.Proposal)
        .where(m.Proposal.run_id == run_id, m.Proposal.record_key.in_(sorted(record_keys)))
        .order_by(m.Proposal.rule_id, m.Proposal.record_key, m.Proposal.field)
    ).all()
    latest = latest_decisions(session, "proposal", (p.proposal_key for p in proposals))
    return [
        proposal_out(p, latest.get(p.proposal_key))
        for p in proposals
        if proposal_status(p.action, latest.get(p.proposal_key)) == "approved"
    ]


def _assumptions_in_order(session: Session, assumption_ids: list[Any]) -> list[schemas.Assumption]:
    found = {
        a.assumption_id: a
        for a in session.scalars(
            select(m.Assumption).where(m.Assumption.assumption_id.in_(assumption_ids))
        ).all()
    }
    return [schemas.Assumption.model_validate(found[i]) for i in assumption_ids if i in found]
