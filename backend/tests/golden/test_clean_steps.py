"""Steps 1 to 4 reproduce notebooks/c1_clean.ipynb: the corrections log, the rule backtest and
the cleaned and joined tables."""

import pytest

from navigator.recipes.core import Artifact, StepResult
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


def test_policy_approves_exactly_the_passing_fixes(farm_checks: StepResult) -> None:
    assert farm_checks.proposals is not None and farm_checks.decisions is not None
    proposals = farm_checks.proposals
    expected = proposals.loc[
        proposals["rule_id"].isin(["R1", "R2", "R3", "R5"]) & proposals["action"].eq("fix"),
        "proposal_key",
    ]
    decisions = farm_checks.decisions
    assert sorted(decisions["proposal_key"]) == sorted(expected)
    assert set(decisions["decision"]) == {"approve"}
    assert set(decisions["reviewer"]) == {"Rule policy"}


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
