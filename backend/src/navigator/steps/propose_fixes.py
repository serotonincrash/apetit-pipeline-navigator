"""Step 2a: propose_fixes. The fix proposer looks for errors the rules miss in the raw tables.

It runs only when the run was queued with the fix proposer on. Every proposal must carry a
compute query that the step runs again on the raw table; a proposal whose query does not find its
record and values is rejected here, and the rejection is reported in the step's last section.
"""

import math
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pandas as pd

from navigator.agents import fix_proposer
from navigator.agents.schemas import AgentProposal, FixProposals
from navigator.evidence import ComputeQuery, evaluate, reproduces
from navigator.llm import LlmResult
from navigator.recipes.core import (
    PROPOSAL_COLUMNS,
    PROPOSALS_INPUT,
    Artifact,
    Params,
    RunContext,
    StepResult,
    section,
    step,
)
from navigator.steps.check_farm_data import rule_descriptions

RULE_ID = "AG1"
# apply_approved writes approved fixes to these tables as numbers.
APPLIED_TABLES = ("farm_survey", "farm_registry", "energy_meter_readings")
REJECTION_COLUMNS = ["table", "record_key", "field", "reason"]


def rule_library(
    rules: pd.DataFrame, validation: pd.DataFrame, descriptions: Mapping[str, str]
) -> str:
    """Each rule in plain words, with the field it checks and its score on the answer key."""
    scores = {str(row["rule_id"]): row for row in validation.to_dict("records")}
    lines: list[str] = []
    for rule_id, description in descriptions.items():
        own = rules[rules["rule_id"].eq(rule_id)]
        where = f"{own['table'].iat[0]}.{own['field'].iat[0]}" if len(own) else "no table"
        score = ""
        precision = scores.get(rule_id, {}).get("precision")
        if isinstance(precision, float) and math.isfinite(precision):
            score = f" Precision {precision:.2f}, recall {scores[rule_id]['recall']:.2f}."
        lines.append(f"{rule_id} on {where}: {description}{score}")
    return "\n".join(lines)


def rejection_reason(proposal: AgentProposal, table: str, raw: dict[str, pd.DataFrame]) -> str:
    """Why the proposal is rejected, or an empty string when its evidence reproduces."""
    query = proposal.evidence.query
    if not isinstance(query, ComputeQuery):
        return "The evidence has no compute query."
    if proposal.table != table or query.table != table:
        return f"The proposal is not about the table {table}."
    if proposal.field not in raw[table].columns:
        return f"The table has no column {proposal.field}."
    if proposal.record_key not in proposal.evidence.record_keys:
        return "The evidence does not list the proposed record."
    try:
        matches, reason = reproduces(proposal.evidence, raw)
        if not matches:
            return reason
        row = evaluate(query, raw).to_dict("records")[0]
        if fix_proposer.record_key_of(table, row) != proposal.record_key:
            return "The query selects a different record than the one proposed."
    except (ValueError, KeyError) as error:
        return f"The query cannot run: {error}"
    if proposal.action == "fix" and table in APPLIED_TABLES:
        if not pd.api.types.is_numeric_dtype(raw[table][proposal.field]):
            return "A fix can only change a number in this table."
        try:
            float(proposal.new_value)
        except ValueError:
            return "The new value of a fix is not a number."
    return ""


def proposal_row(proposal: AgentProposal, call_id: str) -> dict[str, Any]:
    return {
        "proposal_key": f"{RULE_ID}|{proposal.record_key}|{proposal.field}",
        "rule_id": RULE_ID,
        "issue_type": proposal.issue_type,
        "table": proposal.table,
        "record_key": proposal.record_key,
        "field": proposal.field,
        "old_value": proposal.old_value,
        "new_value": proposal.new_value or None,
        "action": proposal.action,
        "evidence": proposal.evidence.model_dump(mode="json"),
        "explanation": proposal.explanation,
        "proposer": f"agent:fix-proposer {call_id}",
    }


@step(
    "propose_fixes",
    kind="llm",
    summary=(
        "Asks the fix proposer for errors the rules miss in the raw tables, and keeps only "
        "proposals whose evidence runs again on the raw data. A person decides each one. Runs "
        "only when queued with the fix proposer."
    ),
)
def propose_fixes(ctx: RunContext, inputs: dict[str, Artifact], params: Params) -> StepResult:
    if not params["enabled"]:
        with section(
            "skip fix proposer",
            "Adds no proposals because this run was queued without the fix proposer.",
        ):
            return StepResult(tables=[])
    llm = ctx.llm
    if llm is None:
        raise ValueError("The fix proposer needs the language model wrapper, which this run lacks.")

    raw = {name: inputs[name].frame for name in params["tables"]}
    by_rules = inputs[PROPOSALS_INPUT].frame
    labels = inputs["dev_issue_labels"].frame
    validation = inputs["rule_validation"].frame
    # A recipe whose check step describes its own rules puts the text in the validation table.
    descriptions = (
        dict(zip(validation["rule_id"], validation["description"], strict=True))
        if "description" in validation.columns
        else rule_descriptions(params["rule_params"])
    )
    library = rule_library(by_rules, validation, descriptions)

    with section(
        "ask for findings",
        "Sends every raw table at once, each with its statistics, sample rows, the rules and the "
        "labelled errors, to the fix proposer.",
    ):
        prompts = {
            table: fix_proposer.build_prompt(
                table, frame, library, by_rules[by_rules["table"].eq(table)], labels
            )
            for table, frame in raw.items()
        }

        def ask(table: str) -> LlmResult[FixProposals]:
            return fix_proposer.propose(llm, table, prompts[table])

        with ThreadPoolExecutor(max_workers=params["concurrency"]) as pool:
            replies = list(pool.map(ask, prompts))
        answers: dict[str, LlmResult[FixProposals]] = dict(zip(prompts, replies, strict=True))

    covered = set(zip(by_rules["record_key"], by_rules["field"], strict=True))
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, str]] = []
    with section(
        "run the evidence again",
        "Runs every proposal's query again on the raw table and rejects those whose record or "
        "values do not match, or that repeat a rule's proposal.",
    ):
        for table, answer in answers.items():
            if answer.value is None:
                continue
            for proposal in answer.value.proposals:
                key = (proposal.record_key, proposal.field)
                reason = (
                    "A rule or an earlier proposal already covers this record and field."
                    if key in covered
                    else rejection_reason(proposal, table, raw)
                )
                if reason:
                    rejected.append(
                        {
                            "table": proposal.table,
                            "record_key": proposal.record_key,
                            "field": proposal.field,
                            "reason": reason,
                        }
                    )
                    continue
                covered.add(key)
                accepted.append(proposal_row(proposal, answer.call_id))

    failed = sum(1 for answer in answers.values() if answer.value is None)
    proposals = len(accepted) + len(rejected)
    with section(
        "report rejections",
        f"Rejected {len(rejected)} of {proposals} findings: the evidence did not run again on the "
        f"raw data, or a rule already covers the record. {failed} of {len(answers)} requests "
        "failed.",
    ):
        pass

    return StepResult(
        tables=[
            Artifact(
                "fix_proposer_rejections",
                "result",
                pd.DataFrame(rejected, columns=REJECTION_COLUMNS),
            )
        ],
        proposals=pd.DataFrame(accepted, columns=PROPOSAL_COLUMNS),
    )
