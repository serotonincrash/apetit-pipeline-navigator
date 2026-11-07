"""What each agent returns, checked before anything is stored."""

from typing import Literal

from pydantic import BaseModel, Field

from navigator.evidence import Evidence


class ParagraphDraft(BaseModel):
    """The report drafter's answer: one paragraph, with numbers only as tokens."""

    section: str
    heading: str = ""
    text: str


class Explanation(BaseModel):
    """The review explainer's answer: numbers only as `{{ev:name}}` tokens."""

    explanation: str


class AgentProposal(BaseModel):
    """One finding of the fix proposer. `new_value` is empty for a flag."""

    table: str
    record_key: str
    field: str
    issue_type: str
    action: Literal["fix", "flag"]
    old_value: str
    new_value: str = ""
    evidence: Evidence = Field(description="Its query must be a compute query on a raw table.")
    explanation: str


class FixProposals(BaseModel):
    """The fix proposer's answer for one raw table."""

    proposals: list[AgentProposal]
