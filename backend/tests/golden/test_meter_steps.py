"""Recipe 2 reproduces the labelled 2023-24 energy issues and the answer inventories.

The numbers pinned here come from the energy file, the registry statement and the A2 answer
inventories in the challenge package. A change in them means a check or a factor changed.
"""

from typing import Any

import numpy as np
import pandas as pd
import pytest

from navigator.evidence import Evidence, reproduces
from navigator.llm.client import Llm
from navigator.llm.models import FakeModel
from navigator.recipes.core import (
    METRIC_COLUMNS,
    PROPOSALS_INPUT,
    STEPS,
    Artifact,
    RunContext,
    StepResult,
)
from navigator.recipes.energy_meter_check import RECIPE
from navigator.steps.check_meters import reading_key
from navigator.steps.scope2_electricity import counted_origin_guarantees
from navigator.worker.runner import build_metric_rows

pytestmark = pytest.mark.golden

LABELLED = {"missing_record": 6, "unit_error": 6, "meter_spike": 4}


def run_step(ctx: RunContext, name: str, tables: dict[str, Artifact]) -> StepResult:
    spec = next(s for s in RECIPE.steps if s.name == name)
    return STEPS[name].func(ctx, {n: tables[n] for n in spec.inputs}, spec.params)


def proposals_input(proposals: pd.DataFrame, approved_rules: tuple[str, ...]) -> Artifact:
    """The `proposals` input after a reviewer approved the fixes of the named rules."""
    frame = proposals.copy()
    for column in ("old_value", "new_value"):
        frame[column] = [None if pd.isna(v) else str(v) for v in frame[column]]
    frame["status"] = np.where(
        frame["rule_id"].isin(approved_rules) & frame["action"].eq("fix"),
        "approved",
        np.where(frame["action"].eq("flag"), "flag", "open"),
    )
    return Artifact(PROPOSALS_INPUT, "result", frame)


@pytest.fixture(scope="module")
def ctx(package_root: Any) -> RunContext:
    from tests.golden.conftest import DiskPackage

    return RunContext("run_golden", "energy_meter_check", DiskPackage(package_root))


@pytest.fixture(scope="module")
def raw(ctx: RunContext) -> dict[str, Artifact]:
    return {t.name: t for t in run_step(ctx, "load_raw", {}).tables}


@pytest.fixture(scope="module")
def checked(ctx: RunContext, raw: dict[str, Artifact]) -> StepResult:
    return run_step(ctx, "check_meters", raw)


def downstream(
    ctx: RunContext,
    raw: dict[str, Artifact],
    checked: StepResult,
    approved_rules: tuple[str, ...],
) -> dict[str, Artifact]:
    """Every table steps 1 to 7 write, with the named rules' fixes approved."""
    assert checked.proposals is not None
    tables = dict(raw)
    tables.update({t.name: t for t in checked.tables})
    tables[PROPOSALS_INPUT] = proposals_input(checked.proposals, approved_rules)
    for name in (
        "backtest_meters",
        "apply_approved_meters",
        "scope2_electricity",
        "compare_inventory",
    ):
        tables.update({t.name: t for t in run_step(ctx, name, tables).tables})
    return tables


@pytest.fixture(scope="module")
def approved(ctx: RunContext, raw: dict[str, Artifact], checked: StepResult) -> dict[str, Artifact]:
    return downstream(ctx, raw, checked, ("M1", "M2", "M3"))


def row(frame: pd.DataFrame, **match: Any) -> dict[str, Any]:
    """The one row of `frame` whose columns equal `match`, as a dict."""
    keep = pd.Series(True, index=frame.index)
    for column, value in match.items():
        keep &= frame[column].eq(value)
    (found,) = frame[keep].to_dict("records")
    return {str(k): v for k, v in found.items()}


def test_the_package_has_the_labelled_issues(raw: dict[str, Artifact]) -> None:
    labels = raw["dev_issue_labels"].frame
    energy = labels[labels["table"].eq("energy_meter_readings")]
    assert energy["issue_type"].value_counts().to_dict() == LABELLED
    assert len(raw["energy_meter_readings"].frame) == 610


def test_proposal_counts_per_rule(checked: StepResult) -> None:
    assert checked.proposals is not None
    assert checked.proposals.groupby("rule_id").size().to_dict() == {"M1": 21, "M2": 21, "M3": 13}
    assert checked.decisions is None


def test_every_proposal_has_structured_evidence(checked: StepResult) -> None:
    assert checked.proposals is not None
    for rule_id, key, evidence in zip(
        checked.proposals["rule_id"],
        checked.proposals["record_key"],
        checked.proposals["evidence"],
        strict=True,
    ):
        Evidence.model_validate(evidence)
        assert key in evidence["record_keys"]
        assert evidence["query"] == {**evidence["query"], "kind": "rule", "rule_id": rule_id}
        assert evidence["values"]
        assert all(type(v) is float for v in evidence["values"].values())


def test_the_rules_find_every_labelled_issue_and_flag_no_correct_reading(
    checked: StepResult,
) -> None:
    assert checked.rules is not None
    backtests = dict(zip(checked.rules["rule_id"], checked.rules["backtest"], strict=True))
    assert sorted(backtests) == ["M1", "M2", "M3"]
    for rule_id, labelled in (("M1", 6), ("M2", 6), ("M3", 4)):
        found = backtests[rule_id]
        assert (found["dev_labels"], found["tp"], found["fp"], found["fn"]) == (
            labelled,
            labelled,
            0,
            0,
        )
        assert (found["precision"], found["recall"]) == (1.0, 1.0)


def test_seasonal_peaks_are_not_flagged(checked: StepResult) -> None:
    assert checked.proposals is not None
    spikes = checked.proposals[checked.proposals["rule_id"].eq("M3")]["record_key"]
    # Saekylae electricity is about twice as high from July to September every year.
    assert not spikes.str.match(r"energy:S-SAK:\d{4}-0[789]:electricity").any()
    # Pudasjaervi district heat follows a heating season, from 30 MWh in summer to 79 in winter.
    assert not spikes.str.match(r"energy:S-PUD:\d{4}-(0[1-5]|1[0-2]):district_heat").any()


def test_a_reading_in_kilowatt_hours_and_a_spike_is_proposed_by_both_rules(
    checked: StepResult,
) -> None:
    assert checked.proposals is not None
    both = checked.proposals[checked.proposals["record_key"].eq("energy:S-PUD:2024-11:electricity")]
    assert sorted(both["proposal_key"]) == [
        "M2|energy:S-PUD:2024-11:electricity|value",
        "M3|energy:S-PUD:2024-11:electricity|value",
    ]


def test_the_backtest_scores_all_sixteen_labels(approved: dict[str, Artifact]) -> None:
    table = approved["meter_backtest"].frame.set_index("rule_id")
    assert list(table.index) == ["M1", "M2", "M3", "all"]
    everything = row(approved["meter_backtest"].frame, rule_id="all")
    assert (everything["dev_labels"], everything["dev_flagged"]) == (16, 16)
    assert (everything["tp"], everything["fp"], everything["fn"]) == (16, 0, 0)
    # The compound reading S-PUD 2024-11 has a unit-error label in MWh and a spike label in kWh,
    # so neither rule's fix matches both labelled true values.
    assert table["fixed_value_matches_truth"].round(3).to_dict() == {
        "M1": 1.0,
        "M2": 0.833,
        "M3": 0.75,
        "all": 0.875,
    }


def test_nothing_is_filled_without_an_approved_fix(
    ctx: RunContext, raw: dict[str, Artifact], checked: StepResult
) -> None:
    tables = downstream(ctx, raw, checked, ())
    clean = tables["energy_clean"].frame
    assert len(clean) == 610
    assert clean["n_corrections"].sum() == 0
    assert clean["value"].isna().sum() == 0
    assert clean["value"].max() > 1_000_000


def test_gaps_are_filled_only_from_approved_fixes(
    ctx: RunContext, raw: dict[str, Artifact], checked: StepResult
) -> None:
    only_gaps = downstream(ctx, raw, checked, ("M1",))["energy_clean"].frame
    assert len(only_gaps) == 610 + 21
    assert only_gaps["n_corrections"].sum() == 21
    filled = row(only_gaps, record_key="energy:S-SAK:2023-05:electricity")
    assert filled["value"] == pytest.approx(1580.72, abs=0.01)
    assert pd.isna(filled["raw_value"])


def test_the_cleaned_readings_keep_the_delivered_value(approved: dict[str, Artifact]) -> None:
    frame = approved["energy_clean"].frame
    clean = frame
    assert len(clean) == 631
    assert clean["n_corrections"].sum() == 55
    compound = row(frame, record_key=reading_key("S-PUD", 2024, 11, "electricity"))
    assert compound["raw_value"] == pytest.approx(693108.523)
    assert compound["n_corrections"] == 2
    assert compound["value"] == pytest.approx(179.71, abs=0.01)


def test_scope2_matches_the_2023_answer_inventory(approved: dict[str, Artifact]) -> None:
    comparison = approved["scope2_vs_answer"].frame
    location = row(comparison, year=2023, basis="location_based")
    assert location["answer_tco2e"] == pytest.approx(1438.38)
    assert location["ours_tco2e"] == pytest.approx(1438.08, abs=0.01)
    market = row(comparison, year=2023, basis="market_based")
    assert market["answer_tco2e"] == pytest.approx(60.8)
    assert market["ours_tco2e"] == pytest.approx(60.8, abs=0.01)


def test_scope2_differs_from_the_2024_answer_by_the_estimates(
    approved: dict[str, Artifact],
) -> None:
    comparison = approved["scope2_vs_answer"].frame
    location = row(comparison, year=2024, basis="location_based")
    assert location["answer_tco2e"] == pytest.approx(1123.05)
    assert location["difference_tco2e"] == pytest.approx(0.67, abs=0.01)
    # The Kantvik estimate for July 2024 is 23 MWh above the true reading. The registry covers
    # exactly the true consumption, so those megawatt hours count as uncovered.
    market = row(comparison, year=2024, basis="market_based")
    assert market["answer_tco2e"] == pytest.approx(62.93)
    assert market["difference_tco2e"] == pytest.approx(9.10, abs=0.01)


def test_without_approved_fixes_scope2_is_far_from_the_answer(
    ctx: RunContext, raw: dict[str, Artifact], checked: StepResult
) -> None:
    comparison = downstream(ctx, raw, checked, ())["scope2_vs_answer"].frame
    assert (comparison["difference_pct"] > 1000).all()


def test_guarantees_count_only_for_their_own_year_up_to_consumption() -> None:
    registry = pd.DataFrame(
        {
            "consumption_year": [2023, 2023, 2023],
            "beneficiary_site": ["S-X", "S-X", "S-X"],
            "mwh": [100.0, 50.0, 25.0],
            "production_period_start": ["2023-01-01", "2022-10-01", "2023-07-01"],
            "production_period_end": ["2023-03-28", "2022-12-28", "2023-09-28"],
        }
    )
    table = counted_origin_guarantees(registry).iloc[0]
    assert (table["goo_listed_mwh"], table["goo_valid_mwh"]) == (175.0, 125.0)


@pytest.fixture(scope="module")
def metric_steps(approved: dict[str, Artifact]) -> list[StepResult]:
    ctx = RunContext("run_golden", "energy_meter_check")
    return [run_step(ctx, name, approved) for name in ("scope2_electricity", "compare_inventory")]


def test_site_metrics_carry_their_site_and_trace_to_tables(
    approved: dict[str, Artifact], metric_steps: list[StepResult]
) -> None:
    frames = [r.metrics for r in metric_steps if r.metrics is not None]
    metrics = pd.concat(frames, ignore_index=True)
    assert len(metrics) == 3 * len(approved["scope2_site_year"].frame) + 4
    for frame in frames:
        assert list(frame.columns) == METRIC_COLUMNS
    per_site = metrics[metrics["name"].str.startswith("scope2_electricity.")]
    assert set(per_site["site"]) == {"S-BJU", "S-HQ", "S-KAN", "S-PUD", "S-SAK"}
    for lineage in metrics["lineage"]:
        assert {entry["table"] for entry in lineage} <= set(approved)


def test_metrics_reach_the_runner(
    approved: dict[str, Artifact], metric_steps: list[StepResult]
) -> None:
    names = [a.name for r in metric_steps for a in r.assumptions]
    rows, _ = build_metric_rows(
        [r.metrics for r in metric_steps if r.metrics is not None],
        "rs_1",
        {name: f"art_{name}" for name in approved},
        {name: f"asm_{name}" for name in names},
    )
    assert len(rows) == 3 * len(approved["scope2_site_year"].frame) + 4
    assert {r.site for r in rows if r.name.startswith("scope2_")} >= {"S-SAK", "S-KAN"}


def test_the_fake_proposer_flags_the_zero_readings_of_bjuv(
    ctx: RunContext, raw: dict[str, Artifact], checked: StepResult
) -> None:
    assert checked.proposals is not None
    spec = next(s for s in RECIPE.steps if s.name == "propose_fixes")
    inputs = {name: raw[name] for name in spec.inputs if name in raw}
    inputs["rule_validation"] = checked.tables[0]
    inputs[PROPOSALS_INPUT] = proposals_input(checked.proposals, ())
    llm = Llm(FakeModel(), ctx.run_id, record=lambda row: None)
    fake_ctx = RunContext(ctx.run_id, ctx.recipe_id, ctx.sources, llm)

    result = STEPS["propose_fixes"].func(fake_ctx, inputs, {**spec.params, "enabled": True})

    assert result.proposals is not None
    assert result.proposals["proposal_key"].tolist() == [
        "AG1|energy:S-BJU:2025-01:electricity|value"
    ]
    assert result.proposals["action"].tolist() == ["flag"]
    assert result.tables[0].frame.empty
    evidence = Evidence.model_validate(result.proposals["evidence"].iat[0])
    assert reproduces(evidence, {"energy_meter_readings": raw["energy_meter_readings"].frame})[0]
