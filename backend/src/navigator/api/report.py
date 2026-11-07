"""Report screen: draft, review and publish a result set's report, and export it."""

from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response, status

from navigator.api import schemas
from navigator.api.dependencies import PersonaDep
from navigator.api.errors import BAD_PERSONA, NOT_BUILT, NOT_FOUND, not_built

router = APIRouter(prefix="/api", tags=["report"])

MILESTONE_4 = "milestone 4, with actions and the report."


@router.post(
    "/result-sets/{result_set_id}/report",
    operation_id="requestReport",
    status_code=status.HTTP_202_ACCEPTED,
    responses={**BAD_PERSONA, **NOT_FOUND, **NOT_BUILT},
)
def request_report(result_set_id: str, persona: PersonaDep) -> schemas.Run:
    """Queue a report run: the report drafter writes a draft for results review."""
    raise not_built(f"Report drafts come in {MILESTONE_4}")


@router.get(
    "/result-sets/{result_set_id}/report",
    operation_id="getReport",
    responses={**NOT_FOUND, **NOT_BUILT},
)
def get_report(result_set_id: str) -> schemas.Report:
    """The draft or published report, with every cited metric."""
    raise not_built(f"Reports come in {MILESTONE_4}")


@router.post(
    "/result-sets/{result_set_id}/decisions",
    operation_id="decideResultSet",
    status_code=status.HTTP_201_CREATED,
    responses={**BAD_PERSONA, **NOT_FOUND, **NOT_BUILT},
)
def decide_result_set(
    result_set_id: str, request: schemas.ResultSetDecisionRequest, persona: PersonaDep
) -> schemas.Decision:
    """Move a result set to in review, approved or published."""
    raise not_built(f"Results review comes in {MILESTONE_4}")


@router.get(
    "/result-sets/{result_set_id}/report/export",
    operation_id="exportReport",
    response_class=Response,
    responses={
        200: {
            "content": {"application/pdf": {}, "text/markdown": {}},
            "description": "The published report as a file.",
        },
        **NOT_FOUND,
        **NOT_BUILT,
    },
)
def export_report(
    result_set_id: str,
    file_format: Annotated[Literal["pdf", "markdown"], Query(alias="format")] = "pdf",
) -> Response:
    """The published report as PDF or Markdown."""
    raise not_built(f"Report export comes in {MILESTONE_4}")
