"""Runs screen: queue runs, follow them live, and open the tables their steps wrote."""

import asyncio
import hashlib
import io
import json
import math
import re
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, time
from typing import Annotated, Any, cast

import numpy as np
import pandas as pd
from fastapi import APIRouter, Header, Query, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from navigator import ids
from navigator.api import schemas
from navigator.api.dependencies import PersonaDep, SessionDep
from navigator.api.errors import (
    BAD_PERSONA,
    NOT_FOUND,
    invalid,
    not_found,
)
from navigator.api.schemas import ErrorMessage
from navigator.db import models as m
from navigator.db.session import session_scope
from navigator.recipes.registry import RECIPES
from navigator.storage.query import read_all_rows, read_rows

router = APIRouter(prefix="/api", tags=["runs"])

FINISHED = {"succeeded", "failed"}
# The stream reads new events from the table at this interval. Tests shorten it.
POLL_SECONDS = 1.0
# A comment line after this many quiet polls keeps proxies from closing the stream.
KEEPALIVE_POLLS = 15
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
# Above this an export is refused, so one request cannot read a whole large table into memory.
EXPORT_MAX_ROWS = 200_000
_ILLEGAL_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_ILLEGAL_SHEET = re.compile(r"[\[\]:*?/\\]")


class EventStreamResponse(StreamingResponse):
    media_type = "text/event-stream"


@router.post(
    "/runs",
    operation_id="createRun",
    status_code=status.HTTP_201_CREATED,
    responses=BAD_PERSONA,
)
def create_run(
    request: schemas.RunRequest, session: SessionDep, persona: PersonaDep
) -> schemas.Run:
    """Queue a full run of a recipe, with optional overrides of its step params."""
    if request.kind == "what_if" or request.parent_run_id or request.action_id:
        raise invalid(("body", "kind"), "What-if runs come in a later milestone.")
    recipe = RECIPES.get(request.recipe_id)
    if recipe is None:
        raise invalid(
            ("body", "recipe_id"),
            f"No recipe {request.recipe_id}. Recipes: {', '.join(sorted(RECIPES))}.",
        )
    steps = {spec.name: spec for spec in recipe.steps}
    for step_name, overrides in request.step_params.items():
        spec = steps.get(step_name)
        if spec is None:
            raise invalid(
                ("body", "step_params", step_name),
                f"Recipe {recipe.recipe_id} has no step {step_name}.",
            )
        unknown = sorted(set(overrides) - set(spec.params))
        if unknown:
            raise invalid(
                ("body", "step_params", step_name),
                f"Step {step_name} has no param {', '.join(unknown)}.",
            )

    params: dict[str, Any] = {"step_params": request.step_params}
    run = m.Run(
        run_id=ids.new_id("run"),
        recipe_id=recipe.recipe_id,
        version=recipe.version,
        kind="full",
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
    return _run_out(run, None)


@router.get("/runs", operation_id="listRuns")
def list_runs(
    session: SessionDep,
    recipe_id: str | None = None,
    run_status: Annotated[schemas.RunStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> schemas.RunList:
    """Runs, newest first."""
    query = select(m.Run, m.ResultSet.result_set_id).outerjoin(
        m.ResultSet, m.ResultSet.run_id == m.Run.run_id
    )
    if recipe_id:
        query = query.where(m.Run.recipe_id == recipe_id)
    if run_status:
        query = query.where(m.Run.status == run_status)
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = session.execute(
        query.order_by(m.Run.created_at.desc(), m.Run.run_id.desc()).limit(limit).offset(offset)
    ).all()
    return schemas.RunList(
        total=total, items=[_run_out(run, result_set_id) for run, result_set_id in rows]
    )


@router.get("/runs/{run_id}", operation_id="getRun", responses=NOT_FOUND)
def get_run(run_id: str, session: SessionDep) -> schemas.RunDetail:
    """One run with its steps in order, their annotations and the tables they wrote."""
    run = session.get(m.Run, run_id)
    if run is None:
        raise not_found("run", run_id)
    result_set_id = session.scalar(
        select(m.ResultSet.result_set_id).where(m.ResultSet.run_id == run_id)
    )
    step_runs = session.scalars(
        select(m.StepRun).where(m.StepRun.run_id == run_id).order_by(m.StepRun.position)
    ).all()
    step_names = {s.step_run_id: s.step for s in step_runs}
    artifacts = session.scalars(
        select(m.Artifact).where(m.Artifact.run_id == run_id).order_by(m.Artifact.artifact_id)
    ).all()
    return schemas.RunDetail.model_validate(
        {
            **_run_out(run, result_set_id).model_dump(),
            "params": run.params,
            "params_hash": run.params_hash,
            "steps": [_step_run_out(s) for s in step_runs],
            "artifacts": [artifact_out(a, step_names[a.step_run_id]) for a in artifacts],
        }
    )


@router.get(
    "/runs/{run_id}/events",
    operation_id="streamRunEvents",
    response_class=EventStreamResponse,
    responses={
        200: {
            "model": schemas.RunEvent,
            "description": (
                "Server-sent events. Each event's `id` is its seq and its `data` is one "
                "RunEvent as JSON. The stream ends after `run.finished`."
            ),
        },
        204: {"description": "The run has finished and the client has seen every event."},
        **NOT_FOUND,
    },
)
def stream_run_events(
    run_id: str,
    session: SessionDep,
    last_event_id: Annotated[
        int | None,
        Header(description="The seq of the last event received; the stream resumes after it."),
    ] = None,
) -> Response:
    """The run's progress events in order, the stored ones first, then new ones as they happen.

    Answering 204 once the client has seen the end stops the browser reconnecting.
    """
    run = session.get(m.Run, run_id)
    if run is None:
        raise not_found("run", run_id)
    after = last_event_id or 0
    if run.status in FINISHED and _read_events(run_id, after)[0] == []:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return EventStreamResponse(
        _event_stream(run_id, after),
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _event_stream(run_id: str, after: int) -> AsyncIterator[str]:
    quiet_polls = 0
    quiet_polls_finished = 0
    while True:
        events, run_status = await run_in_threadpool(_read_events, run_id, after)
        for event in events:
            yield _format_event(event)
            after = event.seq
            if event.type == "run.finished":
                return
        if events:
            quiet_polls = quiet_polls_finished = 0
        else:
            quiet_polls += 1
            quiet_polls_finished = quiet_polls_finished + 1 if run_status in FINISHED else 0
        # A run cut off by a restart has no run.finished event. Its status is final, but the
        # runner writes the status before its last events, so the stream waits one more poll.
        if quiet_polls_finished >= 2:
            return
        if quiet_polls and quiet_polls % KEEPALIVE_POLLS == 0:
            yield ": keepalive\n\n"
        await asyncio.sleep(POLL_SECONDS)


def _read_events(run_id: str, after: int) -> tuple[list[m.RunEvent], str]:
    with session_scope() as session:
        run_status = session.get_one(m.Run, run_id).status
        events = session.scalars(
            select(m.RunEvent)
            .where(m.RunEvent.run_id == run_id, m.RunEvent.seq > after)
            .order_by(m.RunEvent.seq)
        ).all()
        return list(events), run_status


def _format_event(event: m.RunEvent) -> str:
    data = {
        "seq": event.seq,
        "event_id": event.event_id,
        "run_id": event.run_id,
        "step": event.step,
        "type": event.type,
        "payload": event.payload,
        "created_at": event.created_at.isoformat(),
    }
    return f"id: {event.seq}\ndata: {json.dumps(data)}\n\n"


@router.get("/artifacts/{artifact_id}", operation_id="getArtifact", responses=NOT_FOUND)
def get_artifact(artifact_id: str, session: SessionDep) -> schemas.Artifact:
    """A table's metadata: the step that wrote it, its layer, row count and content hash."""
    artifact, step = find_artifact(session, artifact_id)
    return artifact_out(artifact, step)


FilterQuery = Annotated[
    list[str] | None,
    Query(
        alias="filter",
        description=(
            "column=value, repeatable. Filters on different columns all apply; repeating a "
            "column matches any of its values. Values compare as text."
        ),
        examples=["farm_id=FS02175"],
    ),
]


@router.get(
    "/artifacts/{artifact_id}/rows",
    operation_id="listArtifactRows",
    responses=NOT_FOUND,
)
def list_artifact_rows(
    artifact_id: str,
    session: SessionDep,
    filters: FilterQuery = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> schemas.ArtifactRows:
    """Rows of a table, filtered and paged, in the order the step wrote them."""
    artifact, _ = find_artifact(session, artifact_id)
    where, parameters = row_filter(artifact, filters or [])
    frame, total = read_rows(artifact.uri, where, parameters, limit=limit, offset=offset)
    rows: list[dict[str, Any]] = json.loads(frame.to_json(orient="records", date_format="iso"))
    return schemas.ArtifactRows(
        artifact_id=artifact_id,
        columns=[str(c) for c in frame.columns],
        total=total,
        limit=limit,
        offset=offset,
        rows=rows,
    )


@router.get(
    "/artifacts/{artifact_id}/export",
    operation_id="exportArtifact",
    response_class=Response,
    responses={
        200: {"content": {XLSX: {}}, "description": "The filtered rows as an Excel file."},
        **NOT_FOUND,
        422: {"model": ErrorMessage, "description": "Too many rows match. Add filters."},
    },
)
def export_artifact(artifact_id: str, session: SessionDep, filters: FilterQuery = None) -> Response:
    """The filtered rows of a table as an Excel file, up to 200000 rows."""
    artifact, _ = find_artifact(session, artifact_id)
    where, parameters = row_filter(artifact, filters or [])
    _, total = read_rows(artifact.uri, where, parameters, limit=0)
    if total > EXPORT_MAX_ROWS:
        raise invalid(
            ("query", "filter"),
            f"{total} rows match, and an export holds at most {EXPORT_MAX_ROWS}. "
            "Add filters to narrow the table down.",
        )
    frame = read_all_rows(artifact.uri, where, parameters)
    return Response(
        build_workbook(artifact.name, frame),
        media_type=XLSX,
        headers={"Content-Disposition": f'attachment; filename="{export_filename(artifact.name)}"'},
    )


def export_filename(name: str) -> str:
    """A safe file name for the download, from the table's name."""
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("._") or "table"
    return f"{stem}.xlsx"


def xlsx_cell(value: Any) -> Any:
    """A value openpyxl can write.

    numpy types become Python ones, missing values become empty, and times lose their time zone
    (written as UTC), because Excel has none.
    """
    if isinstance(value, np.generic):
        value = cast(Any, value.item())
    if value is None or value is pd.NaT:
        return None
    if isinstance(value, float):
        return None if math.isnan(value) or math.isinf(value) else value
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(UTC).replace(tzinfo=None)
        return value.to_pydatetime() if isinstance(value, pd.Timestamp) else value
    if isinstance(value, bool | int | date | time):
        return value
    return _ILLEGAL_XML.sub("", value if isinstance(value, str) else str(value))


def build_workbook(name: str, frame: pd.DataFrame) -> bytes:
    """An .xlsx with one sheet: a header row of the column names, then the rows."""
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet(_ILLEGAL_SHEET.sub("_", name)[:31] or "table")
    sheet.append([_ILLEGAL_XML.sub("", str(c)) for c in frame.columns])
    for row in frame.itertuples(index=False, name=None):
        sheet.append([xlsx_cell(v) for v in row])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def find_artifact(session: Session, artifact_id: str) -> tuple[m.Artifact, str]:
    row = session.execute(
        select(m.Artifact, m.StepRun.step)
        .join(m.StepRun, m.StepRun.step_run_id == m.Artifact.step_run_id)
        .where(m.Artifact.artifact_id == artifact_id)
    ).first()
    if row is None:
        raise not_found("table", artifact_id)
    return row[0], row[1]


def row_filter(artifact: m.Artifact, filters: list[str]) -> tuple[str, list[Any]]:
    """A DuckDB condition over the artifact's own columns, with the values as parameters."""
    values: dict[str, list[str]] = {}
    for item in filters:
        column, sep, value = item.partition("=")
        if not sep:
            raise invalid(
                ("query", "filter"),
                f"Write each filter as column=value, for example farm_id=FS02175, not {item}.",
            )
        if column not in artifact.columns:
            raise invalid(("query", "filter"), f"Table {artifact.name} has no column {column}.")
        values.setdefault(column, []).append(value)
    conditions: list[str] = []
    for column, vals in values.items():
        quoted = '"' + column.replace('"', '""') + '"'
        conditions.append(f"CAST({quoted} AS VARCHAR) IN ({', '.join('?' for _ in vals)})")
    return " AND ".join(conditions), [v for vals in values.values() for v in vals]


def _run_out(run: m.Run, result_set_id: str | None) -> schemas.Run:
    out = schemas.Run.model_validate(run)
    out.result_set_id = result_set_id
    return out


def _step_run_out(step_run: m.StepRun) -> schemas.StepRun:
    out = schemas.StepRun.model_validate(step_run)
    # The stored error is the full traceback; the app shows only what went wrong.
    lines = [line for line in (step_run.error or "").splitlines() if line.strip()]
    out.error = lines[-1].strip() if lines else None
    return out


def artifact_out(artifact: m.Artifact, step: str) -> schemas.Artifact:
    return schemas.Artifact.model_validate(
        {
            "artifact_id": artifact.artifact_id,
            "run_id": artifact.run_id,
            "step_run_id": artifact.step_run_id,
            "step": step,
            "name": artifact.name,
            "layer": artifact.layer,
            "row_count": artifact.row_count,
            "columns": artifact.columns,
            "content_hash": artifact.content_hash,
            "created_at": artifact.created_at,
        }
    )
