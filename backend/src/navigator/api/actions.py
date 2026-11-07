"""Actions screen: the catalogue and proposed actions, and the priced what-if results."""

from typing import Annotated

from fastapi import APIRouter, Query, status

from navigator.api import schemas
from navigator.api.dependencies import PersonaDep
from navigator.api.errors import BAD_PERSONA, NOT_BUILT, NOT_FOUND, not_built

router = APIRouter(prefix="/api", tags=["actions"])

MILESTONE_4 = "come in milestone 4, with actions and the report."


@router.get("/actions", operation_id="listActions", responses=NOT_BUILT)
def list_actions(
    action_status: Annotated[schemas.ActionStatus | None, Query(alias="status")] = None,
) -> list[schemas.Action]:
    """The action catalogue and the actions the action proposer suggested."""
    raise not_built(f"Actions {MILESTONE_4}")


@router.post(
    "/actions/{action_id}/decisions",
    operation_id="decideAction",
    status_code=status.HTTP_201_CREATED,
    responses={**BAD_PERSONA, **NOT_FOUND, **NOT_BUILT},
)
def decide_action(
    action_id: str, request: schemas.ActionDecisionRequest, persona: PersonaDep
) -> schemas.Decision:
    """Approve an action to run as a what-if, or reject it."""
    raise not_built(f"Decisions on actions {MILESTONE_4}")


@router.get(
    "/result-sets/{result_set_id}/action-options",
    operation_id="listActionOptions",
    responses={**NOT_FOUND, **NOT_BUILT},
)
def list_action_options(result_set_id: str) -> list[schemas.ActionOption]:
    """Priced what-if results for a result set, for comparing cost and risk removed."""
    raise not_built(f"Action options {MILESTONE_4}")


@router.post(
    "/action-options/{option_id}/decisions",
    operation_id="decideActionOption",
    status_code=status.HTTP_201_CREATED,
    responses={**BAD_PERSONA, **NOT_FOUND, **NOT_BUILT},
)
def decide_action_option(
    option_id: str, request: schemas.ActionOptionDecisionRequest, persona: PersonaDep
) -> schemas.Decision:
    """Mark a priced option as recommended, considered or rejected, with a comment."""
    raise not_built(f"Decisions on action options {MILESTONE_4}")
