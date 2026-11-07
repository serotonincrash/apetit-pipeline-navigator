"""Request and response models: the API contract the frontend client is generated from.

Model names become the type names in the generated client, so they name the domain thing
(`Run`, `Proposal`, `Metric`) rather than the transport.
"""

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel

from navigator.db.decisions import ProposalStatus, RuleStatus
from navigator.evidence import Evidence
from navigator.recipes.core import Layer, StepKind

PersonaRole = Literal["data_specialist", "sustainability_specialist"]
RunKind = Literal["full", "what_if", "report"]
RunStatus = Literal["queued", "running", "succeeded", "failed"]
StepStatus = Literal["pending", "running", "succeeded", "failed", "reused"]
ResultSetStatus = Literal["draft", "in_review", "approved", "published", "superseded"]
ActionStatus = Literal["proposed", "approved_to_run", "rejected"]
ActionOptionStatus = Literal["recommended", "considered", "rejected"]


class ApiModel(BaseModel):
    # Every field of a response is always present, so the generated client marks it required.
    model_config = ConfigDict(
        from_attributes=True, json_schema_serialization_defaults_required=True
    )


class ErrorMessage(ApiModel):
    detail: str


# Shared


class Health(ApiModel):
    status: Literal["ok"]


class Persona(ApiModel):
    role: PersonaRole
    label: str = Field(description="How the app shows the role, for example 'Data specialist'.")


# Runs


class RunRequest(ApiModel):
    recipe_id: str = Field(examples=["farm_climate_risk"])
    kind: Literal["full", "what_if"] = "full"
    parent_run_id: str | None = Field(
        default=None, description="The approved run a what-if starts from."
    )
    action_id: str | None = Field(default=None, description="The action a what-if applies.")
    step_params: dict[str, dict[str, Any]] = Field(
        default_factory=dict[str, dict[str, Any]],
        description="Overrides of step params, by step name and then param name.",
        examples=[{"check_farm_data": {"r1_yield_max_ratio_to_median": 4.0}}],
    )


class Run(ApiModel):
    run_id: str
    recipe_id: str
    version: int
    kind: RunKind
    parent_run_id: str | None
    action_id: str | None
    status: RunStatus
    error: str | None
    triggered_by: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    result_set_id: str | None = Field(default=None, description="Set once the run has succeeded.")


class RunList(ApiModel):
    total: int
    items: list[Run]


class StepRun(ApiModel):
    step_run_id: str
    position: int
    step: str
    kind: StepKind
    summary: str = Field(description="The step's annotation, shown beside it in the timeline.")
    params: dict[str, Any]
    status: StepStatus
    error: str | None = Field(description="The last line of the error, when the step failed.")
    seconds: float | None
    started_at: datetime | None
    finished_at: datetime | None
    input_artifacts: list[str]
    output_artifacts: list[str]


class Artifact(ApiModel):
    artifact_id: str
    run_id: str
    step_run_id: str
    step: str
    name: str
    layer: Layer
    row_count: int
    columns: list[str]
    content_hash: str
    created_at: datetime


class RunDetail(Run):
    params: dict[str, Any]
    params_hash: str
    steps: list[StepRun]
    artifacts: list[Artifact]


class ArtifactRows(ApiModel):
    artifact_id: str
    columns: list[str]
    total: int = Field(description="Rows matching the filters, before paging.")
    limit: int
    offset: int
    rows: list[dict[str, Any]]


# Run events, as sent in the `data` field of the event stream.


class RunStatusPayload(ApiModel):
    status: RunStatus


class StepStartedPayload(ApiModel):
    step: str
    annotation: str


class StepFinishedPayload(ApiModel):
    step: str
    annotation: str
    status: StepStatus
    seconds: float
    error: str | None = Field(default=None, description="Why the step stopped, in plain words.")


class SectionStartedPayload(ApiModel):
    step: str
    section: str
    annotation: str


class SectionFinishedPayload(ApiModel):
    step: str
    section: str
    annotation: str
    seconds: float


class ProposalsCreatedPayload(ApiModel):
    step: str
    count_per_rule: dict[str, int]


class RunFinishedPayload(ApiModel):
    status: RunStatus
    result_set_id: str | None
    error: str | None = Field(default=None, description="Why the run stopped, in plain words.")


class RunEventFields(ApiModel):
    seq: int = Field(description="Order of the event in the run; also the stream's event id.")
    event_id: str
    run_id: str
    step: str | None
    created_at: datetime


class RunStatusEvent(RunEventFields):
    type: Literal["run.status"]
    payload: RunStatusPayload


class StepStartedEvent(RunEventFields):
    type: Literal["step.started"]
    payload: StepStartedPayload


class StepFinishedEvent(RunEventFields):
    type: Literal["step.finished"]
    payload: StepFinishedPayload


class SectionStartedEvent(RunEventFields):
    type: Literal["section.started"]
    payload: SectionStartedPayload


class SectionFinishedEvent(RunEventFields):
    type: Literal["section.finished"]
    payload: SectionFinishedPayload


class ProposalsCreatedEvent(RunEventFields):
    type: Literal["proposal.created"]
    payload: ProposalsCreatedPayload


class RunFinishedEvent(RunEventFields):
    type: Literal["run.finished"]
    payload: RunFinishedPayload


class RunEvent(
    RootModel[
        Annotated[
            RunStatusEvent
            | StepStartedEvent
            | StepFinishedEvent
            | SectionStartedEvent
            | SectionFinishedEvent
            | ProposalsCreatedEvent
            | RunFinishedEvent,
            Field(discriminator="type"),
        ]
    ]
):
    pass


# Data review


class Decision(ApiModel):
    decision_id: str
    target_type: str
    target_id: str = Field(description="For a proposal, its proposal key, so it carries over.")
    decision: str
    edited_value: str | None
    reviewer: str
    comment: str | None
    run_id: str | None
    decided_at: datetime


class Proposal(ApiModel):
    proposal_id: str
    proposal_key: str = Field(description="Rule, record key and field; the same in every run.")
    run_id: str
    rule_id: str
    issue_type: str
    proposer: str
    table: str
    record_key: str
    field: str
    old_value: str | None
    new_value: str | None = Field(description="The value proposed, before any edit.")
    action: Literal["fix", "flag"]
    status: ProposalStatus
    latest_decision: Decision | None


class ProposalDetail(Proposal):
    evidence: Evidence
    explanation: str | None
    decisions: list[Decision] = Field(description="Every decision on this proposal, oldest first.")


class ProposalList(ApiModel):
    run_id: str | None = Field(description="The run these proposals come from.")
    total: int
    items: list[Proposal]


class ProposalDecisionRequest(ApiModel):
    decision: Literal["approve", "edit", "reject"]
    edited_value: str | None = Field(default=None, description="Required when editing.")
    comment: str | None = None


class BulkProposalDecisionRequest(ApiModel):
    proposal_ids: list[str] = Field(min_length=1, max_length=2000)
    decision: Literal["approve", "reject"]
    comment: str | None = None


# Rule proposals


class Rule(ApiModel):
    rule_id: str
    version: int
    description: str
    code: str | None
    author: str
    backtest: dict[str, Any] = Field(description="Precision and recall on labelled history.")
    last_run_id: str | None
    created_at: datetime
    status: RuleStatus
    latest_decision: Decision | None


class RuleDecisionRequest(ApiModel):
    decision: Literal["approve", "reject"]
    version: int | None = Field(default=None, description="Defaults to the latest version.")
    comment: str | None = None


# Risk view


class ResultSet(ApiModel):
    result_set_id: str
    run_id: str
    status: ResultSetStatus
    approved_by: str | None
    published_at: datetime | None
    created_at: datetime


class Metric(ApiModel):
    metric_id: str
    result_set_id: str
    name: str
    unit: str
    value: float
    region: str | None
    crop: str | None
    scenario: str | None
    ngfs_scenario: str | None
    period: str | None
    assumption_ids: list[str]


class MetricList(ApiModel):
    total: int
    items: list[Metric]


class Assumption(ApiModel):
    assumption_id: str
    run_id: str
    step: str
    name: str
    value: Any
    unit: str
    source: str
    owner: str | None
    status: str


class MetricSource(ApiModel):
    artifact: Artifact
    filters: list[str] = Field(
        description="The lineage filter, in the format GET /api/artifacts/{id}/rows takes."
    )
    row_count: int = Field(description="Contributing rows in this artifact.")


class MetricSources(ApiModel):
    metric: Metric
    sources: list[MetricSource]
    corrections: list[Proposal] = Field(description="Approved fixes on the contributing rows.")
    assumptions: list[Assumption]


# Actions


class Action(ApiModel):
    action_id: str
    name: str
    short_name: str | None
    driver: str
    applies_at: str = Field(description="The step the action's override applies at.")
    override: dict[str, Any]
    scope: dict[str, Any]
    cost: dict[str, Any]
    confidence: str
    proposed_by: str
    status: ActionStatus
    created_at: datetime


class ActionDecisionRequest(ApiModel):
    decision: Literal["approve", "reject"]
    comment: str | None = None


class ActionOption(ApiModel):
    option_id: str
    action_id: str
    result_set_id: str
    run_id: str = Field(description="The what-if run that priced this option.")
    name: str
    region: str | None
    crop: str | None
    cost_eur_per_yr: float | None
    risk_reduced_eur_per_yr: float | None
    emissions_change_t: float | None
    assumption_ids: list[str]
    confidence: str | None
    status: ActionOptionStatus | None = Field(description="Empty until a reviewer marks it.")


class ActionOptionDecisionRequest(ApiModel):
    decision: ActionOptionStatus
    comment: str | None = None


# Report


class ReportParagraph(ApiModel):
    heading: str | None
    text: str = Field(
        description="Numbers appear only as tokens, {{metric:met_...}} or {{insight:ins_...}}."
    )
    call_id: str = Field(description="The logged LLM call that wrote this paragraph.")


class Insight(ApiModel):
    insight_id: str
    step: str = Field(description="The step that found it.")
    title: str
    text: str = Field(description="Numbers appear only as metric tokens.")
    metric_ids: list[str]


class Report(ApiModel):
    result_set_id: str
    status: ResultSetStatus
    run_id: str = Field(description="The report run that wrote the draft.")
    drafted_at: datetime
    published_at: datetime | None
    paragraphs: list[ReportParagraph]
    metrics: dict[str, Metric] = Field(description="Every cited metric, by metric id.")
    insights: list[Insight] = Field(description="The result set's insights, for the dashboard.")


class ResultSetDecisionRequest(ApiModel):
    status: Literal["in_review", "approved", "published"]
    comment: str | None = None
