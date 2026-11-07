"""The platform tables: what went in, what each step did, what people decided, what came out.

Data tables themselves are Parquet artifacts in object storage; these rows describe them.
`decision` is append-only: the current status of a proposal, rule, action or result set is
its latest decision.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    type_annotation_map = {  # noqa: RUF012
        dict[str, Any]: JSONB,
        list[Any]: JSONB,
    }


def _now() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class SourceFile(Base):
    __tablename__ = "source_file"
    file_id: Mapped[str] = mapped_column(String, primary_key=True)
    path: Mapped[str] = mapped_column(String, unique=True)
    sha256: Mapped[str] = mapped_column(String)
    bytes: Mapped[int] = mapped_column(BigInteger)
    rows: Mapped[int | None] = mapped_column(Integer)
    uri: Mapped[str] = mapped_column(String)
    loaded_at: Mapped[datetime] = _now()


class Recipe(Base):
    __tablename__ = "recipe"
    recipe_id: Mapped[str] = mapped_column(String, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String)
    steps: Mapped[list[Any]] = mapped_column()
    code_commit: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = _now()


class Run(Base):
    __tablename__ = "run"
    run_id: Mapped[str] = mapped_column(String, primary_key=True)
    recipe_id: Mapped[str] = mapped_column(String)
    version: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String, default="full")
    parent_run_id: Mapped[str | None] = mapped_column(ForeignKey("run.run_id"))
    action_id: Mapped[str | None] = mapped_column(String)
    params: Mapped[dict[str, Any]] = mapped_column(default=dict)
    params_hash: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="queued")
    error: Mapped[str | None] = mapped_column(Text)
    triggered_by: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = _now()
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_run_status_created", "status", "created_at"),)


class StepRun(Base):
    __tablename__ = "step_run"
    step_run_id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("run.run_id"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    step: Mapped[str] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String)
    summary: Mapped[str] = mapped_column(Text)
    params: Mapped[dict[str, Any]] = mapped_column(default=dict)
    input_artifacts: Mapped[list[Any]] = mapped_column(default=list)
    output_artifacts: Mapped[list[Any]] = mapped_column(default=list)
    status: Mapped[str] = mapped_column(String, default="pending")
    error: Mapped[str | None] = mapped_column(Text)
    seconds: Mapped[float | None] = mapped_column(Float)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RunEvent(Base):
    __tablename__ = "run_event"
    seq: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String, unique=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("run.run_id"), index=True)
    step: Mapped[str | None] = mapped_column(String)
    type: Mapped[str] = mapped_column(String)
    payload: Mapped[dict[str, Any]] = mapped_column(default=dict)
    created_at: Mapped[datetime] = _now()


class Artifact(Base):
    __tablename__ = "artifact"
    artifact_id: Mapped[str] = mapped_column(String, primary_key=True)
    step_run_id: Mapped[str] = mapped_column(ForeignKey("step_run.step_run_id"), index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("run.run_id"), index=True)
    name: Mapped[str] = mapped_column(String)
    uri: Mapped[str] = mapped_column(String)
    layer: Mapped[str] = mapped_column(String)
    row_count: Mapped[int] = mapped_column(BigInteger)
    columns: Mapped[list[Any]] = mapped_column(default=list)
    content_hash: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = _now()


class Assumption(Base):
    __tablename__ = "assumption"
    assumption_id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("run.run_id"), index=True)
    step: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(String)
    label: Mapped[str] = mapped_column(String)
    value: Mapped[Any] = mapped_column(JSONB)
    unit: Mapped[str] = mapped_column(String)
    source: Mapped[str] = mapped_column(Text)
    owner: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="in use")


class Proposal(Base):
    """One proposed fix or flag, as one run produced it.

    `proposal_key` (rule, record key and field) is the same for the same proposal in every
    run; decisions point at it, so they carry over to the next run.
    """

    __tablename__ = "proposal"
    proposal_id: Mapped[str] = mapped_column(String, primary_key=True)
    proposal_key: Mapped[str] = mapped_column(String, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("run.run_id"), index=True)
    rule_id: Mapped[str] = mapped_column(String)
    issue_type: Mapped[str] = mapped_column(String)
    proposer: Mapped[str] = mapped_column(String)
    table: Mapped[str] = mapped_column(String)
    record_key: Mapped[str] = mapped_column(String)
    field: Mapped[str] = mapped_column(String)
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    action: Mapped[str] = mapped_column(String)
    evidence: Mapped[dict[str, Any]] = mapped_column(default=dict)
    explanation: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _now()

    __table_args__ = (Index("ix_proposal_run_key", "run_id", "proposal_key", unique=True),)


class Rule(Base):
    __tablename__ = "rule"
    rule_id: Mapped[str] = mapped_column(String, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    description: Mapped[str] = mapped_column(Text)
    code: Mapped[str | None] = mapped_column(Text)
    author: Mapped[str] = mapped_column(String)
    backtest: Mapped[dict[str, Any]] = mapped_column(default=dict)
    last_run_id: Mapped[str | None] = mapped_column(ForeignKey("run.run_id"))
    created_at: Mapped[datetime] = _now()


class Decision(Base):
    __tablename__ = "decision"
    decision_id: Mapped[str] = mapped_column(String, primary_key=True)
    target_type: Mapped[str] = mapped_column(String)
    target_id: Mapped[str] = mapped_column(String)
    decision: Mapped[str] = mapped_column(String)
    edited_value: Mapped[str | None] = mapped_column(Text)
    reviewer: Mapped[str] = mapped_column(String)
    comment: Mapped[str | None] = mapped_column(Text)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("run.run_id"))
    decided_at: Mapped[datetime] = _now()

    __table_args__ = (Index("ix_decision_target", "target_type", "target_id", "decided_at"),)


class ResultSet(Base):
    __tablename__ = "result_set"
    result_set_id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("run.run_id"), unique=True)
    status: Mapped[str] = mapped_column(String, default="draft")
    approved_by: Mapped[str | None] = mapped_column(String)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _now()


class Metric(Base):
    __tablename__ = "metric"
    metric_id: Mapped[str] = mapped_column(String, primary_key=True)
    result_set_id: Mapped[str] = mapped_column(ForeignKey("result_set.result_set_id"), index=True)
    name: Mapped[str] = mapped_column(String)
    unit: Mapped[str] = mapped_column(String)
    value: Mapped[float] = mapped_column(Float)
    low: Mapped[float | None] = mapped_column(Float)
    high: Mapped[float | None] = mapped_column(Float)
    region: Mapped[str | None] = mapped_column(String)
    crop: Mapped[str | None] = mapped_column(String)
    scenario: Mapped[str | None] = mapped_column(String)
    ngfs_scenario: Mapped[str | None] = mapped_column(String)
    period: Mapped[str | None] = mapped_column(String)
    action_id: Mapped[str | None] = mapped_column(String)
    lineage: Mapped[list[Any]] = mapped_column(default=list)
    assumption_ids: Mapped[list[Any]] = mapped_column(default=list)


class ActionDefinition(Base):
    __tablename__ = "action_definition"
    action_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    short_name: Mapped[str | None] = mapped_column(String)
    driver: Mapped[str] = mapped_column(String)
    applies_at: Mapped[str] = mapped_column(String)
    override: Mapped[dict[str, Any]] = mapped_column(default=dict)
    scope: Mapped[dict[str, Any]] = mapped_column(default=dict)
    cost: Mapped[dict[str, Any]] = mapped_column(default=dict)
    confidence: Mapped[str] = mapped_column(String)
    proposed_by: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = _now()


class ActionOption(Base):
    __tablename__ = "action_option"
    option_id: Mapped[str] = mapped_column(String, primary_key=True)
    action_id: Mapped[str] = mapped_column(ForeignKey("action_definition.action_id"))
    result_set_id: Mapped[str] = mapped_column(ForeignKey("result_set.result_set_id"), index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("run.run_id"))
    name: Mapped[str] = mapped_column(String)
    scenario: Mapped[str | None] = mapped_column(String)
    region: Mapped[str | None] = mapped_column(String)
    crop: Mapped[str | None] = mapped_column(String)
    cost_eur_per_yr: Mapped[float | None] = mapped_column(Float)
    risk_reduced_eur_per_yr: Mapped[float | None] = mapped_column(Float)
    emissions_change_t: Mapped[float | None] = mapped_column(Float)
    assumption_ids: Mapped[list[Any]] = mapped_column(default=list)
    confidence: Mapped[str | None] = mapped_column(String)


class Insight(Base):
    """A finding that is not a priced metric. Its numbers are metric tokens in `text`."""

    __tablename__ = "insight"
    insight_id: Mapped[str] = mapped_column(String, primary_key=True)
    result_set_id: Mapped[str] = mapped_column(ForeignKey("result_set.result_set_id"), index=True)
    step: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String)
    text: Mapped[str] = mapped_column(Text)
    metric_ids: Mapped[list[Any]] = mapped_column(default=list)
    created_at: Mapped[datetime] = _now()


class Report(Base):
    """One draft of a result set's report. Each report run writes a new version."""

    __tablename__ = "report"
    report_id: Mapped[str] = mapped_column(String, primary_key=True)
    result_set_id: Mapped[str] = mapped_column(ForeignKey("result_set.result_set_id"), index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("run.run_id"))
    version: Mapped[int] = mapped_column(Integer)
    paragraphs: Mapped[list[Any]] = mapped_column(default=list)
    status: Mapped[str] = mapped_column(String, default="draft")
    created_at: Mapped[datetime] = _now()

    __table_args__ = (Index("ix_report_version", "result_set_id", "version", unique=True),)


class LlmCall(Base):
    """One call to the LLM, so every paragraph and explanation points to the call that wrote it."""

    __tablename__ = "llm_call"
    call_id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("run.run_id"), index=True)
    agent: Mapped[str] = mapped_column(String)
    model: Mapped[str] = mapped_column(String)
    prompt_version: Mapped[str] = mapped_column(String)
    input_hash: Mapped[str] = mapped_column(String)
    output_hash: Mapped[str | None] = mapped_column(String)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _now()
