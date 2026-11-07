"""The fix proposer: looks for errors the rules miss in one raw table and proposes fixes.

It reads a table's statistics, sample and extreme rows, the rule library and the labelled errors
from 2023 and 2024, and answers with proposals whose evidence is a compute query. The step runs
each query again; this module builds the prompt, checks the writing and holds the fake answer.
"""

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import pandas as pd

from navigator import prose
from navigator.agents.review_explainer import check_tokens
from navigator.agents.schemas import FixProposals
from navigator.evidence import ComputeQuery
from navigator.llm import Llm, LlmResult
from navigator.llm.models import FAKE_RESPONSES

AGENT = "fix-proposer"
PROMPT_VERSION = "fix-proposer-v1"
MAX_WORDS = 60
TEMPLATE = (Path(__file__).parent / "prompts" / "fix_proposer.txt").read_text()

# How a record is named in a proposal, by raw table. Same as the rules and the answer key.
RECORD_KEY_FORMATS = {
    "farm_survey": "farm_survey:{survey_id}",
    "farm_registry": "farm:{farm_id}",
    "parcels": "parcel:{parcel_id}",
    "crop_history": "crop_history:{parcel_id}:{year}",
    "erp_purchase_lines": "erp:{doc_no}:{line_no}",
}
SAMPLE_ROWS = 8
EXTREME_ROWS = 3
LABELS_PER_ISSUE = 2


def record_key_of(table: str, row: Mapping[Any, Any]) -> str:
    return RECORD_KEY_FORMATS[table].format_map({str(name): value for name, value in row.items()})


def _named(table: str, frame: pd.DataFrame, column: str, index: pd.Index) -> str:
    return "; ".join(
        f"{record_key_of(table, cast(Mapping[Any, Any], frame.loc[i]))} = {frame.at[i, column]:g}"
        for i in index
    )


def _extremes(table: str, frame: pd.DataFrame) -> str:
    lines: list[str] = []
    for column in frame.select_dtypes("number").columns:
        values = frame[column].dropna()
        if values.nunique() < 3 or column in RECORD_KEY_FORMATS[table]:
            continue
        smallest = _named(table, frame, str(column), values.nsmallest(EXTREME_ROWS).index)
        largest = _named(table, frame, str(column), values.nlargest(EXTREME_ROWS).index)
        lines.append(f"{column}: smallest {smallest}. Largest {largest}.")
    return "\n".join(lines) or "None."


def _labels(table: str, labels: pd.DataFrame) -> str:
    own = labels[labels["table"].eq(table)]
    if own.empty:
        return "No labelled examples for this table."
    shown = own.groupby("issue_type").head(LABELS_PER_ISSUE)
    columns = ["record_key", "issue_type", "field", "observed_value", "true_value", "note"]
    return shown[columns].to_string(index=False)


def build_prompt(
    table: str,
    frame: pd.DataFrame,
    rule_text: str,
    rule_proposals: pd.DataFrame,
    labels: pd.DataFrame,
) -> str:
    """The prompt for one raw table. `rule_proposals` are the rules' proposals on that table."""
    covered = rule_proposals.groupby("rule_id").head(5)
    fields = {
        "key_formats": "\n".join(f"{name}: {fmt}" for name, fmt in RECORD_KEY_FORMATS.items()),
        "table": table,
        "rows": len(frame),
        "statistics": frame.describe(include="all").T.to_string(),
        "samples": frame.sample(min(SAMPLE_ROWS, len(frame)), random_state=0).to_string(),
        "extremes": _extremes(table, frame),
        "rules": rule_text,
        "rule_proposals": (
            "\n".join(f"{r.rule_id} {r.record_key} {r.field}" for r in covered.itertuples())
            or "None."
        ),
        "labels": _labels(table, labels),
    }
    return re.sub(r"\[\[(\w+)\]\]", lambda found: str(fields[found.group(1)]), TEMPLATE)


def check_answer(answer: FixProposals) -> None:
    """Writing and structure checks that send the answer back to the model."""
    for proposal in answer.proposals:
        problems = prose.check(proposal.explanation, MAX_WORDS)
        if problems:
            raise ValueError(f"Explanation of {proposal.record_key}: {' '.join(problems)}")
        if not isinstance(proposal.evidence.query, ComputeQuery):
            raise ValueError(f"The evidence of {proposal.record_key} must use a compute query.")
        check_tokens(proposal.explanation, list(proposal.evidence.values), allow_figures=True)


def propose(llm: Llm, table: str, prompt: str) -> LlmResult[FixProposals]:
    return llm.call(AGENT, PROMPT_VERSION, prompt, FixProposals, item=table, check=check_answer)


# The one finding the fake returns. Line 10 of purchase document 4500006594 is priced at about a
# thousand times the usual price per kilogram of chickpeas, so its quantity was keyed in tonnes
# under the unit kilogram. The answer key covers 2023 and 2024 only; this line is from 2025.
FAKE_FINDING: dict[str, Any] = {
    "table": "erp_purchase_lines",
    "record_key": "erp:4500006594:10",
    "field": "quantity",
    "issue_type": "unit_error",
    "action": "fix",
    "old_value": "6.7476",
    "new_value": "6747.6",
    "evidence": {
        "summary": "The line is priced at about a thousand times the usual price per kilogram.",
        "record_keys": ["erp:4500006594:10"],
        "query": {
            "kind": "compute",
            "table": "erp_purchase_lines",
            "group_by": ["material_id"],
            "compute": {
                "median_quantity": {"op": "median", "column": "quantity"},
                "unit_price": {"op": "divide", "left": "net_amount", "right": "quantity"},
                "typical_unit_price": {"op": "median", "column": "unit_price"},
                "price_ratio": {
                    "op": "divide",
                    "left": "unit_price",
                    "right": "typical_unit_price",
                },
            },
            "where": {"doc_no": 4500006594, "line_no": 10},
        },
        "values": {
            "quantity": 6.7476,
            "median_quantity": 3001.0,
            "unit_price": 1218.4139545912622,
            "typical_unit_price": 1.2582156658193628,
            "price_ratio": 968.3665429470063,
        },
    },
    "explanation": (
        "Line erp:4500006594:10 holds {{ev:quantity}} kilograms of chickpeas, against a usual "
        "{{ev:median_quantity}}, and is priced at {{ev:price_ratio}} times the usual price per "
        "kilogram. The quantity was likely keyed in tonnes. The fix would multiply it by one "
        "thousand. If a person rejects it, the line keeps its quantity."
    ),
}


def fake_proposals(prompt: str) -> dict[str, Any]:
    """The finding for the purchase lines, and nothing for the other tables."""
    found = re.search(r"^Table: (\S+)$", prompt, re.MULTILINE)
    table = found.group(1) if found else ""
    return {"proposals": [FAKE_FINDING] if table == FAKE_FINDING["table"] else []}


FAKE_RESPONSES[FixProposals] = fake_proposals
