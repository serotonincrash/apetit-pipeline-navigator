"""Steps 1 to 4 reproduce notebooks/c1_clean.ipynb: the corrections log, the rule backtest and
the cleaned and joined tables."""

import json

import numpy as np
import pytest

from navigator.evidence import Evidence, reproduces
from navigator.recipes.core import PROPOSALS_INPUT, Artifact, RunContext, StepResult
from navigator.steps.apply_approved import apply_approved
from navigator.steps.spatial_join import spatial_join
from tests.golden.conftest import proposals_input, run_step
from tests.golden.fingerprint import as_read_from_csv, assert_matches

pytestmark = pytest.mark.golden

# Columns of the notebook's corrections log that the platform keeps elsewhere: who proposed,
# when, and the review status and comments live in the decision table, not on the proposal.
LOG_ONLY_COLUMNS = ("proposed_by", "proposed_at", "status", "approved_by", "review_comment")
# Columns of a proposal that the notebook's log does not have.
PROPOSAL_ONLY_COLUMNS = ("explanation", "proposer")


def test_proposal_counts_per_rule(farm_checks: StepResult) -> None:
    assert farm_checks.proposals is not None
    counts = farm_checks.proposals.groupby("rule_id").size().to_dict()
    assert counts == {"R1": 18, "R2": 44, "R3": 85, "R4": 195, "R5": 6}


def test_step_writes_no_decisions(farm_checks: StepResult) -> None:
    assert farm_checks.decisions is None


def test_every_proposal_has_structured_evidence(farm_checks: StepResult) -> None:
    assert farm_checks.proposals is not None
    proposals = farm_checks.proposals
    for rule_id, record_key, evidence in zip(
        proposals["rule_id"], proposals["record_key"], proposals["evidence"], strict=True
    ):
        assert set(evidence) == {"summary", "record_keys", "query", "values"}
        assert isinstance(evidence["summary"], str) and evidence["summary"]
        assert record_key in evidence["record_keys"]
        assert evidence["query"]["kind"] == "rule" and evidence["query"]["rule_id"] == rule_id
        Evidence.model_validate(evidence)
        assert evidence["values"]
        assert all(type(v) is float for v in evidence["values"].values())
        assert json.loads(json.dumps(evidence)) == evidence


def test_rules_carry_their_backtest(farm_checks: StepResult) -> None:
    assert farm_checks.rules is not None
    backtests = dict(zip(farm_checks.rules["rule_id"], farm_checks.rules["backtest"], strict=True))
    assert sorted(backtests) == ["R1", "R2", "R3", "R4", "R5"]
    assert backtests["R4"]["tp"] == 23 and backtests["R4"]["fixed_value_matches_truth"] is None
    assert backtests["R5"] == {
        "dev_labels": None,
        "dev_flagged": None,
        "tp": None,
        "fp": None,
        "fn": None,
        "precision": None,
        "recall": None,
        "fixed_value_matches_truth": None,
        "flagged_all_years": 3,
    }


def test_proposals_match_corrections_log(farm_checks: StepResult) -> None:
    assert farm_checks.proposals is not None
    proposals = farm_checks.proposals.rename(columns={"proposal_key": "correction_id"})
    proposals["evidence"] = [e["summary"] for e in proposals["evidence"]]
    assert_matches(
        "corrections_log",
        as_read_from_csv(proposals),
        ignore=LOG_ONLY_COLUMNS + PROPOSAL_ONLY_COLUMNS,
    )


@pytest.mark.parametrize(
    "name",
    [
        "rule_validation",
        "farm_survey_clean",
        "foodhills_clean",
        "farm_registry_clean",
        "parcel_features",
        "parcel_year_contract",
        "training_table",
    ],
)
def test_table_matches_notebook(clean_tables: dict[str, Artifact], name: str) -> None:
    assert_matches(name, as_read_from_csv(clean_tables[name].frame))


def test_unreviewed_fixes_stop_step_4_with_a_clear_message(
    ctx: RunContext, raw_tables: dict[str, Artifact], farm_checks: StepResult
) -> None:
    """On fresh data nobody has reviewed anything, so step 4 stops and names the open fixes."""
    tables = dict(raw_tables)
    open_proposals = proposals_input(farm_checks)
    open_proposals["status"] = np.where(open_proposals["action"].eq("flag"), "flag", "open")
    tables[PROPOSALS_INPUT] = Artifact(PROPOSALS_INPUT, "result", open_proposals)
    tables.update(
        {t.name: t for t in run_step(ctx, apply_approved, "apply_approved", tables).tables}
    )
    with pytest.raises(ValueError, match="6 coordinate fixes from rule R5 are waiting for review"):
        run_step(ctx, spatial_join, "spatial_join", tables)


def test_unreviewed_yield_fixes_are_named_once_coordinates_are_fixed(
    ctx: RunContext, raw_tables: dict[str, Artifact], farm_checks: StepResult
) -> None:
    tables = dict(raw_tables)
    proposals = proposals_input(farm_checks)
    approved = proposals["rule_id"].eq("R5")
    proposals["status"] = np.where(
        proposals["action"].eq("flag"), "flag", np.where(approved, "approved", "open")
    )
    tables[PROPOSALS_INPUT] = Artifact(PROPOSALS_INPUT, "result", proposals)
    tables.update(
        {t.name: t for t in run_step(ctx, apply_approved, "apply_approved", tables).tables}
    )
    with pytest.raises(ValueError, match="18 yield fixes from rule R1 are waiting for review"):
        run_step(ctx, spatial_join, "spatial_join", tables)


def test_an_r1_proposal_recomputes_from_the_raw_survey(
    raw_tables: dict[str, Artifact], farm_checks: StepResult
) -> None:
    """The compute form an agent would use reproduces a real R1 proposal's numbers."""
    assert farm_checks.proposals is not None
    r1 = farm_checks.proposals[farm_checks.proposals["rule_id"].eq("R1")].iloc[0]
    rule_values = r1["evidence"]["values"]
    survey = raw_tables["farm_survey"].frame.assign(
        record_key="farm_survey:" + raw_tables["farm_survey"].frame["survey_id"]
    )
    agent_evidence = Evidence.model_validate(
        {
            "summary": r1["evidence"]["summary"],
            "record_keys": [r1["record_key"]],
            "query": {
                "kind": "compute",
                "table": "farm_survey",
                "group_by": ["crop", "year"],
                "compute": {
                    "median": {"op": "median", "column": "yield_t_ha"},
                    "ratio_to_median": {"op": "divide", "left": "yield_t_ha", "right": "median"},
                },
                "where": {"record_key": r1["record_key"]},
            },
            "values": {
                k: v
                for k, v in rule_values.items()
                if k in ("yield_t_ha", "median", "ratio_to_median")
            },
        }
    )
    ok, reason = reproduces(agent_evidence, {"farm_survey": survey})
    assert ok, reason
