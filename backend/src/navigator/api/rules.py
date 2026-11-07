"""Data checks with their backtest, shown in Data review, and decisions on agents' checks."""

from fastapi import APIRouter, status
from sqlalchemy import select

from navigator import ids
from navigator.api import schemas
from navigator.api.dependencies import PersonaDep, SessionDep, require_role
from navigator.api.errors import BAD_PERSONA, NOT_FOUND, WRONG_ROLE, not_found
from navigator.db import models as m
from navigator.db.decisions import latest_decisions, rule_status, rule_target_id

router = APIRouter(prefix="/api", tags=["rules"])


@router.get("/rules", operation_id="listRules")
def list_rules(session: SessionDep) -> list[schemas.Rule]:
    """Every version of every rule, newest version first within a rule."""
    rules = session.scalars(select(m.Rule).order_by(m.Rule.rule_id, m.Rule.version.desc())).all()
    latest = latest_decisions(
        session, "rule", (rule_target_id(r.rule_id, r.version) for r in rules)
    )
    return [_rule_out(r, latest.get(rule_target_id(r.rule_id, r.version))) for r in rules]


@router.post(
    "/rules/{rule_id}/decisions",
    operation_id="decideRule",
    status_code=status.HTTP_201_CREATED,
    responses={**BAD_PERSONA, **WRONG_ROLE, **NOT_FOUND},
)
def decide_rule(
    rule_id: str, request: schemas.RuleDecisionRequest, session: SessionDep, persona: PersonaDep
) -> schemas.Decision:
    """Approve or reject one version of a rule. Only approved rules run in recipes."""
    require_role(persona, "data_specialist", "decide on data checks")
    query = select(m.Rule).where(m.Rule.rule_id == rule_id)
    if request.version is not None:
        query = query.where(m.Rule.version == request.version)
    rule = session.scalars(query.order_by(m.Rule.version.desc()).limit(1)).first()
    if rule is None:
        version = f" version {request.version}" if request.version is not None else ""
        raise not_found("data check", f"{rule_id}{version}")
    decision = m.Decision(
        decision_id=ids.new_id("decision"),
        target_type="rule",
        target_id=rule_target_id(rule.rule_id, rule.version),
        decision=request.decision,
        reviewer=persona.name,
        comment=(request.comment or "").strip() or None,
        run_id=rule.last_run_id,
    )
    session.add(decision)
    session.flush()
    return schemas.Decision.model_validate(decision)


def _rule_out(rule: m.Rule, decision: m.Decision | None) -> schemas.Rule:
    return schemas.Rule.model_validate(
        {
            "rule_id": rule.rule_id,
            "version": rule.version,
            "description": rule.description,
            "code": rule.code,
            "author": rule.author,
            "backtest": rule.backtest,
            "last_run_id": rule.last_run_id,
            "created_at": rule.created_at,
            "status": rule_status(rule.author, decision),
            "latest_decision": schemas.Decision.model_validate(decision) if decision else None,
        }
    )
