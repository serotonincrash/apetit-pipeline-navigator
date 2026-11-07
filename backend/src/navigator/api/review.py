"""Data review screen: suggested fixes and flags, and the decisions people make on them.

Decisions point at the stable proposal key, so a decision on one run's proposal carries over
to the same proposal in later runs.
"""

from typing import Annotated

from fastapi import APIRouter, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from navigator import ids
from navigator.api import schemas
from navigator.api.dependencies import PersonaDep, SessionDep, require_role
from navigator.api.errors import BAD_PERSONA, NOT_FOUND, invalid, not_found
from navigator.db import models as m
from navigator.db.decisions import (
    ProposalStatus,
    decision_history,
    latest_decisions,
    proposal_status,
)

router = APIRouter(prefix="/api", tags=["review"])


@router.get("/proposals", operation_id="listProposals")
def list_proposals(
    session: SessionDep,
    run_id: Annotated[
        str | None, Query(description="Defaults to the latest run that wrote proposals.")
    ] = None,
    rule_id: str | None = None,
    table: str | None = None,
    proposal_status: Annotated[ProposalStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=2000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> schemas.ProposalList:
    """One run's proposals, filtered by rule, table and status, ordered by rule and record."""
    if run_id is None:
        run_id = session.scalar(
            select(m.Proposal.run_id)
            .join(m.Run, m.Run.run_id == m.Proposal.run_id)
            .order_by(m.Run.created_at.desc(), m.Run.run_id.desc())
            .limit(1)
        )
        if run_id is None:
            return schemas.ProposalList(run_id=None, total=0, items=[])

    query = select(m.Proposal).where(m.Proposal.run_id == run_id)
    if rule_id:
        query = query.where(m.Proposal.rule_id == rule_id)
    if table:
        query = query.where(m.Proposal.table == table)
    proposals = session.scalars(
        query.order_by(m.Proposal.rule_id, m.Proposal.record_key, m.Proposal.field)
    ).all()
    latest = latest_decisions(session, "proposal", (p.proposal_key for p in proposals))
    items = [proposal_out(p, latest.get(p.proposal_key)) for p in proposals]
    if proposal_status:
        items = [p for p in items if p.status == proposal_status]
    return schemas.ProposalList(
        run_id=run_id, total=len(items), items=items[offset : offset + limit]
    )


@router.get("/proposals/{proposal_id}", operation_id="getProposal", responses=NOT_FOUND)
def get_proposal(proposal_id: str, session: SessionDep) -> schemas.ProposalDetail:
    """One proposal with its evidence, its explanation and every decision on it."""
    proposal = _find_proposal(session, proposal_id)
    history = decision_history(session, "proposal", proposal.proposal_key)
    latest = history[-1] if history else None
    return schemas.ProposalDetail.model_validate(
        {
            **proposal_out(proposal, latest).model_dump(),
            "evidence": proposal.evidence,
            "explanation": proposal.explanation,
            "decisions": [schemas.Decision.model_validate(d) for d in history],
        }
    )


@router.post(
    "/proposals/decisions",
    operation_id="decideProposals",
    status_code=status.HTTP_201_CREATED,
    responses={**BAD_PERSONA, **NOT_FOUND},
)
def decide_proposals(
    request: schemas.BulkProposalDecisionRequest, session: SessionDep, persona: PersonaDep
) -> list[schemas.Decision]:
    """Apply one decision to many proposals, such as all of one rule. Each gets its own row."""
    require_role(persona, "data_specialist", "decide on proposed fixes")
    proposal_ids = list(dict.fromkeys(request.proposal_ids))
    found = {
        p.proposal_id: p
        for p in session.scalars(
            select(m.Proposal).where(m.Proposal.proposal_id.in_(proposal_ids))
        ).all()
    }
    missing = [i for i in proposal_ids if i not in found]
    if missing:
        raise not_found("suggested fix or flag", ", ".join(missing[:5]))
    decisions = [
        _decision(found[i], request.decision, None, request.comment, persona.name)
        for i in proposal_ids
    ]
    session.add_all(decisions)
    session.flush()
    return [schemas.Decision.model_validate(d) for d in decisions]


@router.post(
    "/proposals/{proposal_id}/decisions",
    operation_id="decideProposal",
    status_code=status.HTTP_201_CREATED,
    responses={**BAD_PERSONA, **NOT_FOUND},
)
def decide_proposal(
    proposal_id: str,
    request: schemas.ProposalDecisionRequest,
    session: SessionDep,
    persona: PersonaDep,
) -> schemas.Decision:
    """Approve, edit or reject one proposal, with an optional comment."""
    require_role(persona, "data_specialist", "decide on proposed fixes")
    proposal = _find_proposal(session, proposal_id)
    edited_value = (request.edited_value or "").strip() or None
    if request.decision == "edit":
        if proposal.action == "flag":
            raise invalid(
                ("body", "decision"), "A flag has no value to edit. Approve or reject it."
            )
        if edited_value is None:
            raise invalid(("body", "edited_value"), "An edit needs the corrected value.")
    elif edited_value is not None:
        raise invalid(
            ("body", "edited_value"),
            "Only an edit carries a corrected value. Choose edit, or leave the value out.",
        )
    decision = _decision(proposal, request.decision, edited_value, request.comment, persona.name)
    session.add(decision)
    session.flush()
    return schemas.Decision.model_validate(decision)


def _find_proposal(session: Session, proposal_id: str) -> m.Proposal:
    proposal = session.get(m.Proposal, proposal_id)
    if proposal is None:
        raise not_found("suggested fix or flag", proposal_id)
    return proposal


def _decision(
    proposal: m.Proposal,
    decision: str,
    edited_value: str | None,
    comment: str | None,
    reviewer: str,
) -> m.Decision:
    return m.Decision(
        decision_id=ids.new_id("decision"),
        target_type="proposal",
        target_id=proposal.proposal_key,
        decision=decision,
        edited_value=edited_value,
        reviewer=reviewer,
        comment=(comment or "").strip() or None,
        run_id=proposal.run_id,
    )


def proposal_out(proposal: m.Proposal, decision: m.Decision | None) -> schemas.Proposal:
    return schemas.Proposal.model_validate(
        {
            "proposal_id": proposal.proposal_id,
            "proposal_key": proposal.proposal_key,
            "run_id": proposal.run_id,
            "rule_id": proposal.rule_id,
            "issue_type": proposal.issue_type,
            "proposer": proposal.proposer,
            "table": proposal.table,
            "record_key": proposal.record_key,
            "field": proposal.field,
            "old_value": proposal.old_value,
            "new_value": proposal.new_value,
            "action": proposal.action,
            "status": proposal_status(proposal.action, decision),
            "latest_decision": schemas.Decision.model_validate(decision) if decision else None,
        }
    )
