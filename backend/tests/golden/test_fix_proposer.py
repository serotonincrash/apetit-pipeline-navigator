"""The fake fix proposer returns one real finding in the raw purchase lines, and it reproduces."""

from typing import Any, cast

import pytest

from navigator.llm.client import Llm
from navigator.llm.models import FakeModel
from navigator.recipes.core import PROPOSALS_INPUT, Artifact, RunContext, StepResult
from navigator.steps.propose_fixes import propose_fixes
from tests.golden.conftest import proposals_input, recipe_step

pytestmark = pytest.mark.golden


def run_proposer(
    ctx: RunContext, raw_tables: dict[str, Artifact], farm_checks: StepResult
) -> StepResult:
    spec = recipe_step("propose_fixes")
    inputs = {name: raw_tables[name] for name in spec.inputs if name in raw_tables}
    inputs["rule_validation"] = farm_checks.tables[0]
    inputs[PROPOSALS_INPUT] = Artifact(PROPOSALS_INPUT, "result", proposals_input(farm_checks))
    llm = Llm(FakeModel(), ctx.run_id, record=lambda row: None)
    fake_ctx = RunContext(ctx.run_id, ctx.recipe_id, ctx.sources, llm)
    return propose_fixes(fake_ctx, inputs, {**spec.params, "enabled": True})


def test_the_fake_proposer_finds_one_purchase_line_priced_a_thousand_times_too_high(
    ctx: RunContext, raw_tables: dict[str, Artifact], farm_checks: StepResult
) -> None:
    result = run_proposer(ctx, raw_tables, farm_checks)
    assert result.proposals is not None
    assert result.proposals["proposal_key"].tolist() == ["AG1|erp:4500006594:10|quantity"]
    assert result.tables[0].frame.empty
    evidence = cast(dict[str, Any], result.proposals["evidence"].iat[0])
    assert 900 < evidence["values"]["price_ratio"] < 1100


def test_the_proposals_are_the_same_on_a_rerun(
    ctx: RunContext, raw_tables: dict[str, Artifact], farm_checks: StepResult
) -> None:
    first = run_proposer(ctx, raw_tables, farm_checks)
    second = run_proposer(ctx, raw_tables, farm_checks)
    assert first.proposals is not None and second.proposals is not None
    assert first.proposals["proposal_key"].tolist() == second.proposals["proposal_key"].tolist()
