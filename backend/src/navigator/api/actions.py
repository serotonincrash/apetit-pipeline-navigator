"""Actions screen: the catalogue and proposed actions, and the priced what-if results.

The actions a what-if run refused to price are not in the options list. They are the rows of
the run's `actions_not_run` table: read the run (`GET /api/runs/{run_id}`) for the table's id,
then `GET /api/artifacts/{id}/rows`.
"""

from typing import Annotated

from fastapi import APIRouter, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from navigator import ids
from navigator.api import schemas
from navigator.api.dependencies import PersonaDep, SessionDep, require_role
from navigator.api.errors import BAD_PERSONA, NOT_FOUND, not_found
from navigator.db import models as m
from navigator.db.decisions import action_status, latest_decisions, option_status

router = APIRouter(prefix="/api", tags=["actions"])


@router.get("/actions", operation_id="listActions")
def list_actions(
    session: SessionDep,
    action_status_filter: Annotated[schemas.ActionStatus | None, Query(alias="status")] = None,
) -> list[schemas.Action]:
    """The action catalogue and the actions the action proposer suggested."""
    definitions = session.scalars(
        select(m.ActionDefinition).order_by(m.ActionDefinition.action_id)
    ).all()
    latest = latest_decisions(session, "action", (a.action_id for a in definitions))
    actions = [_action_out(a, latest.get(a.action_id)) for a in definitions]
    if action_status_filter:
        actions = [a for a in actions if a.status == action_status_filter]
    return actions


@router.post(
    "/actions/{action_id}/decisions",
    operation_id="decideAction",
    status_code=status.HTTP_201_CREATED,
    responses={**BAD_PERSONA, **NOT_FOUND},
)
def decide_action(
    action_id: str,
    request: schemas.ActionDecisionRequest,
    session: SessionDep,
    persona: PersonaDep,
) -> schemas.Decision:
    """Approve an action to run as a what-if, or reject it."""
    require_role(persona, "sustainability_specialist", "decide on actions")
    if session.get(m.ActionDefinition, action_id) is None:
        raise not_found("action", action_id)
    return _record(session, "action", action_id, request.decision, request.comment, persona.name)


@router.get(
    "/result-sets/{result_set_id}/action-options",
    operation_id="listActionOptions",
    responses=NOT_FOUND,
)
def list_action_options(result_set_id: str, session: SessionDep) -> list[schemas.ActionOption]:
    """Priced what-if results for a result set, for comparing cost and risk removed."""
    if session.get(m.ResultSet, result_set_id) is None:
        raise not_found("results", result_set_id)
    options = session.scalars(
        select(m.ActionOption)
        .where(m.ActionOption.result_set_id == result_set_id)
        .order_by(
            m.ActionOption.action_id,
            m.ActionOption.scenario,
            m.ActionOption.region,
            m.ActionOption.crop,
            m.ActionOption.option_id,
        )
    ).all()
    latest = latest_decisions(session, "action_option", (o.option_id for o in options))
    return [
        schemas.ActionOption.model_validate(
            {
                **{
                    name: getattr(o, name)
                    for name in schemas.ActionOption.model_fields
                    if name != "status"
                },
                "status": option_status(latest.get(o.option_id)),
            }
        )
        for o in options
    ]


@router.post(
    "/action-options/{option_id}/decisions",
    operation_id="decideActionOption",
    status_code=status.HTTP_201_CREATED,
    responses={**BAD_PERSONA, **NOT_FOUND},
)
def decide_action_option(
    option_id: str,
    request: schemas.ActionOptionDecisionRequest,
    session: SessionDep,
    persona: PersonaDep,
) -> schemas.Decision:
    """Mark a priced option as recommended, considered or rejected, with a comment."""
    require_role(persona, "sustainability_specialist", "decide on priced options")
    option = session.get(m.ActionOption, option_id)
    if option is None:
        raise not_found("priced option", option_id)
    return _record(
        session,
        "action_option",
        option_id,
        request.decision,
        request.comment,
        persona.name,
        run_id=option.run_id,
    )


def _record(
    session: Session,
    target_type: str,
    target_id: str,
    decision: str,
    comment: str | None,
    reviewer: str,
    run_id: str | None = None,
) -> schemas.Decision:
    row = m.Decision(
        decision_id=ids.new_id("decision"),
        target_type=target_type,
        target_id=target_id,
        decision=decision,
        reviewer=reviewer,
        comment=(comment or "").strip() or None,
        run_id=run_id,
    )
    session.add(row)
    session.flush()
    return schemas.Decision.model_validate(row)


def _action_out(action: m.ActionDefinition, decision: m.Decision | None) -> schemas.Action:
    return schemas.Action.model_validate(
        {
            **{
                name: getattr(action, name)
                for name in schemas.Action.model_fields
                if name != "status"
            },
            "status": action_status(decision),
        }
    )
