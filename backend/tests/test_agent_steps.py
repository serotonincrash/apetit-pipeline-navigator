"""The two agent steps: explanations cite evidence tokens, fix proposals need evidence."""

import json
from typing import Any

import pandas as pd
import pytest
from pydantic import BaseModel

from navigator.agents.review_explainer import check_explanation, fake_explanation
from navigator.agents.schemas import FixProposals
from navigator.llm.client import CallRow, Llm
from navigator.llm.models import FakeModel
from navigator.recipes.core import (
    PROPOSAL_COLUMNS,
    PROPOSALS_INPUT,
    Artifact,
    RunContext,
    event_sink,
)
from navigator.recipes.farm_climate_risk import RULE_PARAMS
from navigator.steps.explain_proposals import explain_proposals
from navigator.steps.propose_fixes import propose_fixes

NAMES = ["ratio_to_median", "median"]


class CountingModel:
    """Answers every explanation like the fake model and counts the calls."""

    name = "counting"

    def __init__(self, answer: str | None = None) -> None:
        self.calls = 0
        self.answer = answer

    def generate(self, prompt: str, schema: type[BaseModel]) -> str:
        self.calls += 1
        return self.answer or json.dumps(fake_explanation(prompt))


def llm_with(model: Any, failures: list[tuple[str, str, str]] | None = None) -> Llm:
    rows: list[CallRow] = []
    return Llm(
        model,
        "run_1",
        record=rows.append,
        on_failure=lambda *args: (failures if failures is not None else []).append(args),
    )


def proposal(key: str, explanation: str = "") -> dict[str, Any]:
    return {
        "proposal_key": f"R1|{key}|yield_t_ha",
        "rule_id": "R1",
        "issue_type": "outlier_implausible",
        "table": "farm_survey",
        "record_key": key,
        "field": "yield_t_ha",
        "old_value": "54.0",
        "new_value": "5.4",
        "action": "fix",
        "status": "open",
        "evidence": {
            "summary": "54 t/ha is 10 times the median.",
            "record_keys": [key],
            "query": {"kind": "rule", "rule_id": "R1", "params": {}},
            "values": {"ratio_to_median": 10.0, "median": 5.4},
        },
        "explanation": explanation,
    }


def explain(llm: Llm | None, rows: list[dict[str, Any]], **params: Any) -> dict[str, str | None]:
    options = {"max_explanations": None, "concurrency": 2, **params}
    frame = pd.DataFrame(rows)
    ctx = RunContext("run_1", "farm_climate_risk", llm=llm)
    inputs = {PROPOSALS_INPUT: Artifact(PROPOSALS_INPUT, "result", frame)}
    result = explain_proposals(ctx, inputs, options)
    assert result.explanations is not None
    table = result.explanations
    return dict(zip(table["proposal_key"], table["explanation"], strict=True))


def test_explanation_guardrails() -> None:
    check_explanation("The ratio is {{ev:ratio_to_median}}.", NAMES)
    with pytest.raises(ValueError, match="names no evidence value"):
        check_explanation("The ratio is {{ev:ratio}}.", NAMES)
    with pytest.raises(ValueError, match="names no evidence value"):
        check_explanation("The cost is {{metric:met_1}}.", NAMES)
    with pytest.raises(ValueError, match="types a figure"):
        check_explanation("The ratio is {{ev:median}}, about 10 times more.", NAMES)
    with pytest.raises(ValueError, match="cites no evidence value"):
        check_explanation("The ratio is far too high.", NAMES)


def test_the_fake_explanation_passes_the_guardrail_for_any_evidence() -> None:
    model = CountingModel()
    for names in (["a", "b", "c"], ["a"]):
        row = proposal("farm_survey:FS1")
        row["evidence"]["values"] = dict.fromkeys(names, 1.0)
        assert explain(llm_with(model), [row])["R1|farm_survey:FS1|yield_t_ha"]
    assert model.calls == 2


def test_earlier_explanations_carry_over_and_make_no_calls() -> None:
    model = CountingModel()
    rows = [proposal("farm_survey:FS1", "Kept from an earlier run."), proposal("farm_survey:FS2")]
    written = explain(llm_with(model), rows)
    assert model.calls == 1
    assert written["R1|farm_survey:FS1|yield_t_ha"] == "Kept from an earlier run."
    assert "{{ev:" in (written["R1|farm_survey:FS2|yield_t_ha"] or "")

    rerun = [{**r, "explanation": written[r["proposal_key"]]} for r in rows]
    explain(llm_with(model), rerun)
    explain(None, rerun)
    assert model.calls == 1


def test_a_failed_explanation_is_marked_and_the_others_go_on() -> None:
    failures: list[tuple[str, str, str]] = []
    # The model types a figure on every attempt, so the check fails the call.
    bad = CountingModel(json.dumps({"explanation": "It is 10 times too high."}))
    written = explain(llm_with(bad, failures), [proposal("farm_survey:FS1")])
    assert written == {"R1|farm_survey:FS1|yield_t_ha": None}
    assert [(f[0], f[1]) for f in failures] == [
        ("review-explainer", "R1|farm_survey:FS1|yield_t_ha")
    ]
    assert bad.calls == 3


def test_the_limit_leaves_the_rest_empty_and_unmarked() -> None:
    model = CountingModel()
    rows = [proposal(f"farm_survey:FS{i}") for i in range(4)]
    written = explain(llm_with(model), rows, max_explanations=2)
    assert sorted(written) == ["R1|farm_survey:FS0|yield_t_ha", "R1|farm_survey:FS1|yield_t_ha"]
    assert model.calls == 2


# The fix proposer, on a small survey where record FS3 has an implausible yield.
SURVEY = pd.DataFrame(
    {
        "survey_id": ["FS1", "FS2", "FS3", "FS4"],
        "crop": ["pea"] * 4,
        "year": [2020] * 4,
        "yield_t_ha": [4.0, 5.0, 50.0, 6.0],
    }
)
RATIO = 50.0 / 5.5


def finding(record: str = "FS3", ratio: float = RATIO, **changes: Any) -> dict[str, Any]:
    values = {"yield_t_ha": 50.0, "median": 5.5, "ratio_to_median": ratio}
    found: dict[str, Any] = {
        "table": "farm_survey",
        "record_key": f"farm_survey:{record}",
        "field": "yield_t_ha",
        "issue_type": "outlier_implausible",
        "action": "fix",
        "old_value": "50.0",
        "new_value": "5.0",
        "evidence": {
            "summary": "The yield is far above the median.",
            "record_keys": [f"farm_survey:{record}", "farm_survey:FS3"],
            "query": {
                "kind": "compute",
                "table": "farm_survey",
                "group_by": ["crop", "year"],
                "compute": {
                    "median": {"op": "median", "column": "yield_t_ha"},
                    "ratio_to_median": {"op": "divide", "left": "yield_t_ha", "right": "median"},
                },
                "where": {"survey_id": "FS3"},
            },
            "values": values,
        },
        "explanation": "Record farm_survey:FS3 has {{ev:ratio_to_median}} times the median yield.",
    }
    return {**found, **changes}


def covered_by_rules() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "proposal_key": ["R1|farm_survey:FS9|yield_t_ha"],
            "rule_id": ["R1"],
            "table": ["farm_survey"],
            "record_key": ["farm_survey:FS9"],
            "field": ["yield_t_ha"],
        }
    )


def propose(
    findings: list[dict[str, Any]], enabled: bool = True
) -> tuple[Any, list[tuple[str, str]]]:
    notes: list[tuple[str, str]] = []
    model = FakeModel({FixProposals: {"proposals": findings}})
    llm = Llm(model, "run_1", record=lambda row: None)
    ctx = RunContext("run_1", "farm_climate_risk", llm=llm)
    inputs = {
        "farm_survey": Artifact("farm_survey", "raw", SURVEY),
        "dev_issue_labels": Artifact(
            "dev_issue_labels",
            "raw",
            pd.DataFrame(columns=["table", "record_key", "issue_type", "field"]),
        ),
        "rule_validation": Artifact(
            "rule_validation", "result", pd.DataFrame(columns=["rule_id", "precision", "recall"])
        ),
        PROPOSALS_INPUT: Artifact(PROPOSALS_INPUT, "result", covered_by_rules()),
    }
    params = {
        "enabled": enabled,
        "tables": ["farm_survey"],
        "rule_params": RULE_PARAMS,
        "concurrency": 1,
    }
    with event_sink(lambda type_, payload: notes.append((type_, payload["annotation"]))):
        result = propose_fixes(ctx, inputs, params)
    return result, notes


def test_the_fix_proposer_keeps_a_proposal_whose_evidence_runs_again() -> None:
    result, _ = propose([finding()])
    assert result.proposals is not None
    assert list(result.proposals.columns) == PROPOSAL_COLUMNS
    row = result.proposals.iloc[0]
    assert row["proposal_key"] == "AG1|farm_survey:FS3|yield_t_ha"
    assert row["rule_id"] == "AG1"
    assert row["proposer"].startswith("agent:fix-proposer call_")
    assert row["evidence"]["query"]["kind"] == "compute"


def test_a_proposal_whose_evidence_does_not_match_is_rejected_and_counted() -> None:
    wrong_values = finding(ratio=99.0)
    wrong_record = finding("FS2")
    text_fix = finding(new_value="five")
    already_covered = finding("FS9")
    already_covered["evidence"]["query"]["where"] = {"survey_id": "FS9"}
    result, notes = propose([wrong_values, wrong_record, text_fix, already_covered, finding()])
    assert result.proposals is not None
    assert len(result.proposals) == 1
    rejections = result.tables[0].frame
    assert [r.rstrip(".") for r in rejections["reason"]] == [
        "ratio_to_median comes out as 9.09091, not the claimed 99",
        "The query selects a different record than the one proposed",
        "The new value of a fix is not a number",
        "A rule or an earlier proposal already covers this record and field",
    ]
    finished = [text for type_, text in notes if "Rejected" in text]
    assert finished and finished[0].startswith("Rejected 4 of 5 findings")


def test_proposal_keys_are_the_same_on_a_rerun() -> None:
    first, _ = propose([finding()])
    second, _ = propose([finding()])
    assert first.proposals["proposal_key"].tolist() == second.proposals["proposal_key"].tolist()
    assert first.proposals["proposer"].iat[0] != second.proposals["proposer"].iat[0]


def test_the_fix_proposer_does_nothing_unless_the_run_asks_for_it() -> None:
    result, notes = propose([finding()], enabled=False)
    assert result.proposals is None
    assert result.tables == []
    assert [type_ for type_, _ in notes] == ["section.started", "section.finished"]
