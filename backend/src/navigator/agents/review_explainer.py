"""The review explainer: one explanation per proposal, with numbers only as evidence tokens.

The prompt carries the proposal and the names and values of its evidence. The answer may cite a
value only as `{{ev:name}}` with a name from that evidence, and may type no figure at all.
"""

import re
from collections.abc import Collection, Mapping
from pathlib import Path
from typing import Any

from navigator.agents.schemas import Explanation
from navigator.llm import Llm, LlmResult
from navigator.llm.models import FAKE_RESPONSES

AGENT = "review-explainer"
PROMPT_VERSION = "review-explainer-v1"
MAX_WORDS = 80
TEMPLATE = (Path(__file__).parent / "prompts" / "review_explainer.txt").read_text()

TOKEN = re.compile(r"\{\{([^{}]*)\}\}")
NAMES_LINE = re.compile(r"^Evidence value names: (.*)$", re.MULTILINE)


def build_prompt(proposal: Mapping[str, Any]) -> str:
    """The prompt for one proposal: a row of the `proposals` input with its evidence."""
    evidence: Mapping[str, Any] = proposal["evidence"]
    values: Mapping[str, float] = evidence["values"]
    fields = {
        "rule_id": proposal["rule_id"],
        "issue_type": proposal["issue_type"],
        "action": proposal["action"],
        "table": proposal["table"],
        "field": proposal["field"],
        "old_value": proposal["old_value"] or "none",
        "new_value": proposal["new_value"] or "none",
        "summary": evidence["summary"],
        "values": ", ".join(f"{name} = {value:g}" for name, value in values.items()),
        "names": ", ".join(values),
    }
    return re.sub(r"\[\[(\w+)\]\]", lambda found: str(fields[found.group(1)]), TEMPLATE)


def check_tokens(text: str, value_names: Collection[str], *, allow_figures: bool = False) -> None:
    """Raise ValueError when a token names no evidence value or a figure is typed.

    The fix proposer may cite record keys, which hold digits, so it passes `allow_figures`.
    """
    for token in TOKEN.findall(text):
        name = token.removeprefix("ev:")
        if not token.startswith("ev:") or name not in value_names:
            raise ValueError(
                f"The token {{{{{token}}}}} names no evidence value. "
                f"Use one of: {', '.join(value_names) or 'none'}."
            )
    plain = TOKEN.sub(" ", text)
    if not allow_figures and re.search(r"\d", plain):
        raise ValueError(
            "The text types a figure. Write every number as an evidence token such as "
            "{{ev:name}}, and leave out record keys."
        )


def check_explanation(text: str, value_names: Collection[str]) -> None:
    check_tokens(text, value_names)
    if value_names and not TOKEN.search(text):
        raise ValueError(
            "The explanation cites no evidence value. Cite at least one as {{ev:name}}."
        )


def explain(llm: Llm, proposal: Mapping[str, Any]) -> LlmResult[Explanation]:
    names = list(proposal["evidence"]["values"])
    return llm.call(
        AGENT,
        PROMPT_VERSION,
        build_prompt(proposal),
        Explanation,
        item=proposal["proposal_key"],
        prose_fields=["explanation"],
        limits={"explanation": MAX_WORDS},
        check=lambda answer: check_explanation(answer.explanation, names),
    )


def fake_explanation(prompt: str) -> dict[str, Any]:
    """A valid answer for any proposal: it cites the first two values the prompt names."""
    found = NAMES_LINE.search(prompt)
    names = [n.strip() for n in found.group(1).split(",") if n.strip()] if found else []
    if len(names) >= 2:
        reason = f"The value {{{{ev:{names[0]}}}}} stands out against {{{{ev:{names[1]}}}}}."
    elif names:
        reason = f"The value {{{{ev:{names[0]}}}}} stands out from similar records."
    else:
        reason = "The record stands out from similar records."
    text = (
        f"A data check flagged this record. {reason} A person decides whether the record "
        "changes. If a person rejects the suggestion, the record keeps its current value."
    )
    return {"explanation": text}


FAKE_RESPONSES[Explanation] = fake_explanation
