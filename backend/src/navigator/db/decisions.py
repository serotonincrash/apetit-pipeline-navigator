"""Current status of proposals and rules, read from their latest decision.

`decision` is append-only, so a status is never stored: it is whatever the latest decision on
the target says. The runner and the API both read statuses through these functions, so the
cleaned tables and the review screens always agree.
"""

from collections.abc import Iterable
from typing import Literal, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from navigator.db import models as m

ProposalStatus = Literal["open", "approved", "rejected", "flag"]
RuleStatus = Literal["proposed", "approved", "rejected"]
ActionState = Literal["proposed", "approved_to_run", "rejected"]
OptionState = Literal["recommended", "considered", "rejected"]
TargetType = Literal["proposal", "rule", "action", "action_option", "result_set"]


def latest_decisions(
    session: Session, target_type: TargetType, target_ids: Iterable[str]
) -> dict[str, m.Decision]:
    """The latest decision on each target that has one, keyed by target id.

    Decisions made in one transaction share a timestamp, so the time-sortable decision id
    breaks the tie.
    """
    ids = list(set(target_ids))
    if not ids:
        return {}
    decisions = session.scalars(
        select(m.Decision)
        .where(m.Decision.target_type == target_type, m.Decision.target_id.in_(ids))
        .order_by(m.Decision.decided_at, m.Decision.decision_id)
    ).all()
    return {d.target_id: d for d in decisions}


def decision_history(session: Session, target_type: TargetType, target_id: str) -> list[m.Decision]:
    """Every decision on one target, oldest first."""
    return list(
        session.scalars(
            select(m.Decision)
            .where(m.Decision.target_type == target_type, m.Decision.target_id == target_id)
            .order_by(m.Decision.decided_at, m.Decision.decision_id)
        ).all()
    )


def proposal_status(action: str, decision: m.Decision | None) -> ProposalStatus:
    """A fix is open until decided; a flag stays a flag unless a reviewer rejects it."""
    if action == "flag":
        return "rejected" if decision and decision.decision == "reject" else "flag"
    if decision is None:
        return "open"
    return "rejected" if decision.decision == "reject" else "approved"


def proposal_value(new_value: str | None, decision: m.Decision | None) -> str | None:
    """The value the cleaned table gets: the reviewer's edit when there is one."""
    if decision and decision.edited_value:
        return decision.edited_value
    return new_value


def rule_target_id(rule_id: str, version: int) -> str:
    """Decisions on a rule apply to one version, so changed rule code is reviewed again."""
    return f"{rule_id}:{version}"


def rule_status(author: str, decision: m.Decision | None) -> RuleStatus:
    """A rule an agent wrote waits for a person; a rule a person wrote is approved."""
    if decision is not None:
        return "rejected" if decision.decision == "reject" else "approved"
    return "proposed" if author.startswith("agent") else "approved"


def action_status(decision: m.Decision | None) -> ActionState:
    """An action waits for a person until decided; the latest decision then says run or not."""
    if decision is None:
        return "proposed"
    return "approved_to_run" if decision.decision == "approve" else "rejected"


def option_status(decision: m.Decision | None) -> OptionState | None:
    """A priced option has no status until a reviewer marks it."""
    if decision is None:
        return None
    return cast("OptionState", decision.decision)
