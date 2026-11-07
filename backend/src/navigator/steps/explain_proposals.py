"""Step 2b: explain_proposals. The review explainer writes the text a reviewer reads.

Explanations carry over by proposal key, like decisions, so a rerun asks for none that exist. The
step returns an explanation for every proposal it has one for. A proposal whose call failed gets
None, which Data review shows as "Explanation failed"; a proposal left over by the limit on
explanations gets an empty text and is picked up by the next run.
"""

from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Any

import pandas as pd

from navigator.agents import review_explainer
from navigator.llm import Llm
from navigator.recipes.core import (
    EXPLANATION_COLUMNS,
    PROPOSALS_INPUT,
    Artifact,
    Params,
    RunContext,
    StepResult,
    section,
    step,
)


def explain_one(llm: Llm, proposal: Mapping[str, Any]) -> str | None:
    result = review_explainer.explain(llm, proposal)
    return result.value.explanation if result.value else None


@step(
    "explain_proposals",
    kind="llm",
    summary=(
        "Writes a plain explanation for each suggested fix or flag that has none yet, citing "
        "the evidence values by name. Earlier explanations carry over by proposal key, so a "
        "rerun asks for no new ones."
    ),
)
def explain_proposals(ctx: RunContext, inputs: dict[str, Artifact], params: Params) -> StepResult:
    proposals = inputs[PROPOSALS_INPUT].frame.sort_values("proposal_key")
    has_text = proposals["explanation"].fillna("").ne("")

    with section(
        "keep earlier explanations",
        "Keeps the explanation of every proposal that already has one, matched by proposal key "
        "across runs.",
    ):
        kept = proposals[has_text][EXPLANATION_COLUMNS]

    with section(
        "explain new proposals",
        "Asks the explainer for one explanation per proposal that has none, up to the limit on "
        "explanations set for this run.",
    ):
        waiting = proposals[~has_text]
        limit: int | None = params["max_explanations"]
        rows: list[dict[str, Any]] = [
            {str(name): value for name, value in record.items()}
            for record in (waiting if limit is None else waiting.head(limit)).to_dict("records")
        ]
        texts: list[str | None] = []
        if rows:
            llm = ctx.llm
            if llm is None:
                raise ValueError(
                    "The explainer needs the language model wrapper, which is missing."
                )
            with ThreadPoolExecutor(max_workers=params["concurrency"]) as pool:
                texts = list(pool.map(partial(explain_one, llm), rows))

    written = pd.DataFrame(
        {"proposal_key": [r["proposal_key"] for r in rows], "explanation": texts},
        columns=EXPLANATION_COLUMNS,
        dtype=object,
    )
    return StepResult(tables=[], explanations=pd.concat([kept, written], ignore_index=True))
