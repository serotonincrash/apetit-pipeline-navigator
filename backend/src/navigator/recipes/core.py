"""The contract every recipe step follows.

A step is a plain function decorated with `@step`. It reads only from its arguments and
returns a `StepResult`; the runner does all reading and writing of files and the database.

    @step("tune_calendar", kind="model", summary="Picks the sowing temperature ...")
    def tune_calendar(ctx: RunContext, inputs: dict[str, Artifact], params: Params) -> StepResult:
        with section("score settings", "Tries every setting in the grid and scores ..."):
            ...

Annotations are static text shown in the app next to each step and section, written to the
writing standards in AGENTS.md.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Generator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, Protocol

import pandas as pd

if TYPE_CHECKING:
    from navigator.llm import Llm

Layer = Literal["raw", "clean", "feature", "result"]
StepKind = Literal["load", "propose", "transform", "model", "llm"]
Params = Mapping[str, Any]

# Columns of StepResult.proposals. `proposal_key` (rule, record key and field) is stable across
# runs, so a decision made on one run's proposal still applies to the same proposal next run.
PROPOSAL_COLUMNS = [
    "proposal_key",
    "rule_id",
    "issue_type",
    "table",
    "record_key",
    "field",
    "old_value",
    "new_value",
    "action",
    "evidence",
    "explanation",
    "proposer",
]

# Columns of StepResult.explanations: the text for one proposal, or None when the explainer failed.
EXPLANATION_COLUMNS = ["proposal_key", "explanation"]

# Columns of StepResult.decisions: approvals a step makes under a written rule policy.
DECISION_COLUMNS = ["proposal_key", "decision", "reviewer", "comment"]

# Columns of StepResult.rules: one row per rule, with its backtest on labelled history.
RULE_COLUMNS = ["rule_id", "version", "description", "author", "backtest"]

# Columns of StepResult.metrics: one result number per row. The step names its tables and
# assumptions; the runner swaps in artifact ids and assumption ids when it stores them.
METRIC_COLUMNS = [
    "key",
    "name",
    "unit",
    "value",
    "low",
    "high",
    "region",
    "crop",
    "site",
    "scenario",
    "ngfs_scenario",
    "period",
    "action_id",
    "lineage",
    "assumptions",
]

# Columns of StepResult.insights: a finding whose numbers are `{{metric:<key>}}` tokens in
# `text`, and the keys of the metrics it cites.
INSIGHT_COLUMNS = ["title", "text", "metric_keys"]

# Columns of StepResult.action_options: one priced action in one climate scenario per row. The
# step names its assumptions; the runner swaps in assumption ids when it stores the rows.
ACTION_OPTION_COLUMNS = [
    "key",
    "action_id",
    "name",
    "scenario",
    "region",
    "crop",
    "cost_eur_per_yr",
    "risk_reduced_eur_per_yr",
    "emissions_change_t",
    "assumptions",
    "confidence",
]

# The runner passes this run's proposals to later steps under this input name, with a `status`
# column: open, approved, rejected or flag.
PROPOSALS_INPUT = "proposals"

# The runner passes the approved actions to later steps under this input name, one row per action
# whose latest decision is an approval, with the columns of an action spec.
ACTIONS_INPUT = "actions"


@dataclass(frozen=True)
class Artifact:
    """One table, as a step receives it or returns it."""

    name: str
    layer: Layer
    frame: pd.DataFrame
    artifact_id: str | None = None


@dataclass(frozen=True)
class SourceFile:
    """One file from the challenge package, as delivered."""

    path: str
    sha256: str
    content: bytes


@dataclass(frozen=True)
class RunContext:
    run_id: str
    recipe_id: str
    sources: Mapping[str, SourceFile] = field(default_factory=dict[str, SourceFile])
    llm: Llm | None = None


@dataclass(frozen=True)
class AssumptionUse:
    """An input value a person can question, as a step used it.

    `name` is `<step>.<param>`; `label` is the plain words the app shows instead.
    """

    name: str
    label: str
    value: Any
    unit: str
    source: str


@dataclass
class StepResult:
    tables: list[Artifact]
    proposals: pd.DataFrame | None = None
    decisions: pd.DataFrame | None = None
    rules: pd.DataFrame | None = None
    metrics: pd.DataFrame | None = None
    insights: pd.DataFrame | None = None
    action_options: pd.DataFrame | None = None
    explanations: pd.DataFrame | None = None
    assumptions: list[AssumptionUse] = field(default_factory=list[AssumptionUse])


class StepFunction(Protocol):
    def __call__(
        self, ctx: RunContext, inputs: dict[str, Artifact], params: Params
    ) -> StepResult: ...


@dataclass(frozen=True)
class StepInfo:
    name: str
    kind: StepKind
    summary: str
    func: StepFunction


STEPS: dict[str, StepInfo] = {}


def step(name: str, *, kind: StepKind, summary: str) -> Callable[[StepFunction], StepFunction]:
    """Register a step function under `name`, with the summary the app shows beside it."""

    def register(func: StepFunction) -> StepFunction:
        if name in STEPS:
            raise ValueError(f"step {name!r} is registered twice")
        STEPS[name] = StepInfo(name=name, kind=kind, summary=summary, func=func)
        return func

    return register


EventSink = Callable[[str, dict[str, Any]], None]
_event_sink: ContextVar[EventSink | None] = ContextVar("event_sink", default=None)


@contextmanager
def event_sink(sink: EventSink) -> Generator[None]:
    """Send section events raised inside this block to `sink`. Used by the runner."""
    token = _event_sink.set(sink)
    try:
        yield
    finally:
        _event_sink.reset(token)


@contextmanager
def section(name: str, annotation: str) -> Generator[None]:
    """A named part of a step, reported to the app as it starts and finishes."""
    sink = _event_sink.get()
    started = time.monotonic()
    if sink:
        sink("section.started", {"section": name, "annotation": annotation})
    yield
    if sink:
        sink(
            "section.finished",
            {
                "section": name,
                "annotation": annotation,
                "seconds": round(time.monotonic() - started, 3),
            },
        )


@dataclass(frozen=True)
class StepSpec:
    """One step in a recipe: which registered step, which tables it reads, its params."""

    name: str
    inputs: tuple[str, ...]
    params: Params = field(default_factory=dict[str, Any])


@dataclass(frozen=True)
class Recipe:
    recipe_id: str
    version: int
    title: str
    steps: tuple[StepSpec, ...]
