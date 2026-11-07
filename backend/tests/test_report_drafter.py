"""The report drafter's guardrails, with scripted models and the fake model."""

import json
import re
import time
from dataclasses import replace
from typing import Any

import pytest
from pydantic import BaseModel

from navigator.agents import report_drafter as drafter
from navigator.llm.client import CallRow, Llm
from navigator.llm.models import FakeModel

METRIC = "met_AAA"
OTHER = "met_BBB"
INSIGHT = "ins_AAA"


def evidence(status: str | None = None) -> drafter.ReportEvidence:
    def metric(metric_id: str, name: str, **fields: Any) -> drafter.MetricFact:
        values: dict[str, Any] = {
            "unit": "€ per year",
            "value": 36000.0,
            "low": None,
            "high": None,
            "region": "FI_SW",
            "crop": "pea",
            "scenario": "ssp585",
            "ngfs_scenario": "current_policies",
            "period": None,
            "action": None,
        }
        return drafter.MetricFact(metric_id, name, **(values | fields))

    return drafter.ReportEvidence(
        metrics=[
            metric(METRIC, "price_risk.expected_cost_eur"),
            metric(OTHER, "compare_actions.risk_removed_eur", action="Earlier sowing"),
        ],
        insights=[drafter.InsightFact(INSIGHT, "Foodhills hedge", "It covers {{metric:met_AAA}}.")],
        options=[drafter.OptionFact("Earlier sowing", status, "medium")],
        drivers=[drafter.DriverFact("Pea, Finland", "ssp585", "early drought", "lowers")],
        assumptions=[drafter.AssumptionFact("Price year", 2025, "year")],
    )


class Scripted:
    """Answers every paragraph with the text built by `write`, and keeps the prompts."""

    name = "scripted"

    def __init__(self, write: Any) -> None:
        self.write = write
        self.prompts: list[str] = []

    def generate(self, prompt: str, schema: type[BaseModel]) -> str:
        self.prompts.append(prompt)
        section = json.loads(prompt.split(drafter.INPUT_MARKER)[1].split("\n")[0])["section"]
        return json.dumps({"section": section, "heading": "", "text": self.write(section)})


def llm_for(model: Any, failures: list[tuple[str, str, str]] | None = None) -> Llm:
    return Llm(
        model,
        "run_1",
        on_failure=lambda *args: (failures if failures is not None else []).append(args),
        record=lambda row: None,
    )


def draft_with(text: str, status: str | None = None) -> list[drafter.Paragraph]:
    return drafter.draft_report(llm_for(Scripted(lambda _: text)), evidence(status))


def rejection(text: str, status: str | None = None) -> str:
    rows: list[CallRow] = []
    llm = Llm(Scripted(lambda _: text), "run_1", record=rows.append)
    with pytest.raises(drafter.DraftFailed):
        drafter.draft_report(llm, evidence(status))
    return rows[0].error or ""


def test_the_fake_model_drafts_seven_paragraphs_that_pass_every_guardrail() -> None:
    rows: list[CallRow] = []
    llm = Llm(FakeModel(), "run_1", record=rows.append)
    paragraphs = drafter.draft_report(llm, evidence())
    assert [p.section for p in paragraphs] == [
        "summary",
        "risk",
        "risk",
        "drivers",
        "options",
        "insights",
        "method",
    ]
    assert [p.heading for p in paragraphs] == [
        "Summary",
        "Risk by crop and region",
        None,
        "What drives the losses",
        "Options and what they buy",
        "Insights",
        "Method and limits",
    ]
    assert {r.status for r in rows} == {"ok"}
    assert {r.prompt_version for r in rows} == {drafter.PROMPT_VERSION}
    tokens = re.findall(r"\{\{(\w+):(\w+)\}\}", " ".join(p.text for p in paragraphs))
    assert {t for t in tokens} <= {("metric", METRIC), ("metric", OTHER), ("insight", INSIGHT)}
    assert ("insight", INSIGHT) in tokens
    assert "Earlier sowing would remove {{metric:met_BBB}}" in paragraphs[0].text


def test_a_paragraph_may_cite_known_tokens_years_and_scenario_names() -> None:
    text = (
        "Under High emissions (SSP5-8.5) the cost for 2041 to 2060 is {{metric:met_AAA}}, "
        "and one in a 1-in-10 bad year is {{metric:met_BBB}}. See {{insight:ins_AAA}}."
    )
    assert len(draft_with(text)) == 7


def test_the_fake_model_handles_action_names_that_hold_figures() -> None:
    name = "Relocate 20% of Finnish pea area (L24)"
    facts = evidence()
    facts.metrics[1] = replace(facts.metrics[1], action=name)
    facts.options[0] = replace(facts.options[0], name=name)
    assert any(name in p.text for p in drafter.draft_report(llm_for(FakeModel()), facts))


def test_a_figure_outside_an_action_name_still_fails() -> None:
    facts = evidence()
    facts.options[0] = replace(facts.options[0], name="Relocate 20% of Finnish pea area")
    with pytest.raises(drafter.DraftFailed):
        drafter.draft_report(
            llm_for(Scripted(lambda _: "Relocating 30% of Finnish pea area would help.")), facts
        )


def test_a_typed_number_fails() -> None:
    assert "types the figure 36" in rejection("The cost is 36 thousand euros.")


def test_a_typed_percentage_next_to_a_token_fails() -> None:
    assert "types the figure" in rejection("The cost is {{metric:met_AAA}}, up 12.5% on today.")


def test_a_token_that_names_no_metric_in_the_result_set_fails() -> None:
    assert "names no metric" in rejection("The cost is {{metric:met_ZZZ}}.")


def test_an_insight_token_must_exist_too() -> None:
    assert "names no insight" in rejection("See {{insight:ins_ZZZ}}.")


def test_an_evidence_token_is_not_allowed_in_a_report() -> None:
    assert "is not allowed" in rejection("The ratio is {{ev:ratio_to_median}}.")


def test_recommend_fails_unless_the_action_is_marked_recommended() -> None:
    assert "recommending" in rejection("Apetit recommends earlier sowing for {{metric:met_BBB}}.")
    assert "recommending" in rejection(
        "Apetit recommends earlier sowing for {{metric:met_BBB}}.", "considered"
    )
    assert len(
        draft_with("Apetit recommends earlier sowing for {{metric:met_BBB}}.", "recommended")
    )


def test_first_person_fails() -> None:
    assert "third person" in rejection("We see a cost of {{metric:met_AAA}}.")
    assert "third person" in rejection("I read a cost of {{metric:met_AAA}}.")


def test_more_than_120_words_fails() -> None:
    assert "over the limit of 120" in rejection("Cost rises. " * 61 + "{{metric:met_AAA}}")


def test_the_prose_check_still_applies() -> None:
    assert "banned" in rejection("The cost is robust at {{metric:met_AAA}}.")


def test_an_answer_for_another_section_fails() -> None:
    class AlwaysSummary:
        name = "scripted"

        def generate(self, prompt: str, schema: type[BaseModel]) -> str:
            return json.dumps({"section": "summary", "text": "Cost is {{metric:met_AAA}}."})

    rows: list[CallRow] = []
    with pytest.raises(drafter.DraftFailed):
        drafter.draft_report(Llm(AlwaysSummary(), "run_1", record=rows.append), evidence())
    # Paragraphs are drafted in parallel, so the failed calls are recorded in any order.
    errors = {row.error for row in rows if row.status == "failed"}
    assert "The section must be 'risk'." in errors


def test_a_failed_paragraph_gives_no_draft() -> None:
    failures: list[tuple[str, str, str]] = []
    model = Scripted(lambda section: "Cost is 36 euros." if section == "risk" else "Fine.")
    with pytest.raises(drafter.DraftFailed) as raised:
        drafter.draft_report(llm_for(model, failures), evidence(), concurrency=1)
    assert "Nothing was saved" in str(raised.value)
    assert [(f[0], f[1]) for f in failures] == [("report-drafter", "Risk by crop and region")]
    # With one worker the calls run in order: one for the summary, three for the failed paragraph.
    assert len(model.prompts) == 4


def test_the_prompt_carries_the_rules_and_the_facts_of_one_paragraph() -> None:
    prompt = drafter.build_prompt(0, evidence())
    assert "Never type a figure" in prompt
    facts = json.loads(prompt.split(drafter.INPUT_MARKER)[1])
    assert [m["id"] for m in facts["metrics"]] == [OTHER, METRIC]
    assert (
        facts["metrics"][0]["applies_to"]
        == "Pea, South-west Finland, High emissions (SSP5-8.5), Current Policies"
    )
    assert "insights" not in facts


def energy_evidence() -> drafter.ReportEvidence:
    def metric(metric_id: str, name: str, unit: str, site: str | None, period: str):
        return drafter.MetricFact(
            metric_id, name, unit, 1580.7, None, None, None, None, None, None, period, None, site
        )

    return drafter.ReportEvidence(
        metrics=[
            metric("met_USE", "scope2_electricity.electricity_use_mwh", "MWh", "S-HQ", "2023"),
            metric("met_USE_ALL", "scope2_electricity.electricity_use_mwh", "MWh", None, "2023"),
            metric("met_LOC", "scope2_electricity.location_based_tco2e", "t CO2e", "S-HQ", "2023"),
            metric(
                "met_LOC_ALL", "scope2_electricity.location_based_tco2e", "t CO2e", None, "2023"
            ),
            metric("met_MKT", "scope2_electricity.market_based_tco2e", "t CO2e", "S-HQ", "2023"),
            metric("met_MKT_ALL", "scope2_electricity.market_based_tco2e", "t CO2e", None, "2023"),
            metric(
                "met_DIFF",
                "compare_inventory.location_based_difference_tco2e",
                "t CO2e",
                None,
                "2023",
            ),
        ],
        insights=[],
        options=[],
        drivers=[],
        assumptions=[drafter.AssumptionFact("Grid factor", 0.038, "t CO2e per MWh")],
        recipe_id="energy_meter_check",
    )


def test_recipe_2_has_a_three_section_outline_that_needs_no_insights() -> None:
    rows: list[CallRow] = []
    paragraphs = drafter.draft_report(
        Llm(FakeModel(), "run_1", record=rows.append), energy_evidence()
    )
    assert [p.section for p in paragraphs] == ["summary", "scope2", "scope2", "method"]
    assert [p.heading for p in paragraphs] == [
        "Summary",
        "Scope 2 by site and year",
        None,
        "Method and limits",
    ]
    text = " ".join(p.text for p in paragraphs)
    assert "{{insight:" not in text
    assert "{{metric:met_LOC_ALL}}" in paragraphs[0].text
    assert "{{metric:met_DIFF}}" in paragraphs[0].text
    assert "{{metric:met_USE_ALL}}" in paragraphs[1].text


def test_recipe_2_prompts_show_totals_before_site_rows() -> None:
    prompt = drafter.build_prompt(1, energy_evidence())
    facts = json.loads(prompt.split(drafter.INPUT_MARKER)[1])
    assert facts["recipe"] == "energy_meter_check"
    assert [m["id"] for m in facts["metrics"]] == [
        "met_USE_ALL",
        "met_LOC_ALL",
        "met_USE",
        "met_LOC",
    ]
    assert facts["metrics"][2]["applies_to"] == "S-HQ, 2023"


def test_scope_2_in_words_is_not_a_typed_figure() -> None:
    text = "The Scope 2 of 2023 is {{metric:met_LOC_ALL}} in CO2e."
    llm = llm_for(Scripted(lambda _: text))
    assert len(drafter.draft_report(llm, energy_evidence())) == 4


def test_paragraphs_keep_outline_order_when_the_model_answers_out_of_order() -> None:
    class Slow(FakeModel):
        """Answers the early paragraphs last."""

        def generate(self, prompt: str, schema: type[BaseModel]) -> str:
            position = json.loads(prompt.split(drafter.INPUT_MARKER)[1])["plan"]
            time.sleep(0.05 * (6 - position))
            return super().generate(prompt, schema)

    paragraphs = drafter.draft_report(llm_for(Slow()), evidence(), concurrency=7)
    assert [p.section for p in paragraphs] == [
        "summary",
        "risk",
        "risk",
        "drivers",
        "options",
        "insights",
        "method",
    ]
    assert len({p.call_id for p in paragraphs}) == 7


def test_a_failure_in_a_parallel_draft_still_gives_no_draft() -> None:
    model = Scripted(lambda section: "Cost is 36 euros." if section == "drivers" else "Fine.")
    with pytest.raises(drafter.DraftFailed, match="What drives the losses"):
        drafter.draft_report(llm_for(model), evidence(), concurrency=3)
