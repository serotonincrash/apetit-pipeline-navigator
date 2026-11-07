"""The report drafter: one call per paragraph, with numbers only as metric and insight tokens.

The caller gathers the facts from the database and passes them in as `ReportEvidence`; this module
only builds prompts, checks answers and returns the paragraphs. Drafting stops at the first
paragraph that fails its checks, so a draft is never partial.
"""

import json
import re
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from navigator.agents.schemas import ParagraphDraft
from navigator.llm import Llm, LlmResult
from navigator.llm.models import FAKE_RESPONSES

AGENT = "report-drafter"
PROMPT_VERSION = "report-drafter-v2"
MAX_WORDS = 120
INPUT_MARKER = "\nINPUT_JSON:\n"
RULES = (Path(__file__).parent / "prompts" / "report_drafter.txt").read_text()

SCENARIO_LABELS = {
    "historical": "Past weather",
    "baseline": "1991\u20132020 weather",
    "ssp126": "Low emissions (SSP1-2.6)",
    "ssp245": "Middle (SSP2-4.5)",
    "ssp585": "High emissions (SSP5-8.5)",
}
# Which figures a paragraph sees first when its facts are cut to the plan's limit: the future
# under the highest emissions, then today, so a paragraph can compare the two.
SCENARIO_ORDER = {"ssp585": 0, "baseline": 1, "ssp245": 2, "ssp126": 3}
NGFS_LABELS = {
    "today": "Today's premiums",
    "net_zero_2050": "Net Zero 2050",
    "below_2c": "Below 2°C",
    "low_demand": "Low Demand",
    "delayed_transition": "Delayed Transition",
    "fragmented_world": "Fragmented World",
    "ndcs": "Nationally Determined Contributions (NDCs)",
    "current_policies": "Current Policies",
}
REGION_LABELS = {"FI_SW": "South-west Finland", "SE_SKANE": "Skåne"}
METRIC_LABELS = {
    "fit_yield_model.production_error_pct": "Yield model error in production",
    "fit_yield_model.baseline_production_error_pct": "Farm-average error in production",
    "project_yields.yield_change_pct": "Yield change",
    "project_yields.bad_year_chance": "Chance of a bad year",
    "price_risk.expected_cost_eur": "Expected extra cost",
    "price_risk.one_in_ten_cost_eur": "Extra cost in a 1-in-10 bad year",
    "price_risk.expected_import_tco2e": "Extra emissions from replacement imports",
    "price_risk.climate_added_cost_eur": "Cost added by climate change",
    "price_risk.foodhills_cover_share": "Share of the shortfall the Foodhills hedge covers",
    "price_risk.foodhills_premium_avoided_eur": "Premium the Foodhills hedge avoids",
    "compare_actions.risk_removed_eur": "Risk removed",
    "compare_actions.import_tco2e_removed": "Import emissions removed",
    "compare_actions.break_even_cost_eur": "Break-even cost",
    "scope2_electricity.electricity_use_mwh": "Electricity use",
    "scope2_electricity.location_based_tco2e": "Location-based Scope 2",
    "scope2_electricity.market_based_tco2e": "Market-based Scope 2",
    "compare_inventory.location_based_difference_tco2e": (
        "Location-based Scope 2 minus the answer inventory"
    ),
    "compare_inventory.market_based_difference_tco2e": (
        "Market-based Scope 2 minus the answer inventory"
    ),
}


@dataclass(frozen=True)
class MetricFact:
    metric_id: str
    name: str
    unit: str
    value: float
    low: float | None
    high: float | None
    region: str | None
    crop: str | None
    scenario: str | None
    ngfs_scenario: str | None
    period: str | None
    action: str | None  # the action's name, for the action metrics
    site: str | None = None  # the site's id, for the Scope 2 metrics; None for a total


@dataclass(frozen=True)
class InsightFact:
    insight_id: str
    title: str
    text: str


@dataclass(frozen=True)
class OptionFact:
    name: str
    status: str | None  # recommended, considered, rejected, or None before a reviewer marks it
    confidence: str | None


@dataclass(frozen=True)
class DriverFact:
    unit: str
    scenario: str
    driver: str
    direction: str  # lowers or raises


@dataclass(frozen=True)
class AssumptionFact:
    label: str
    value: Any
    unit: str


@dataclass(frozen=True)
class ReportEvidence:
    metrics: list[MetricFact]
    insights: list[InsightFact]
    options: list[OptionFact]
    drivers: list[DriverFact]
    assumptions: list[AssumptionFact]
    recipe_id: str = "farm_climate_risk"


@dataclass(frozen=True)
class ParagraphPlan:
    section: str
    heading: str
    brief: str
    fake_text: str
    metric_names: tuple[str, ...]
    metric_limit: int
    uses: tuple[str, ...] = ()


# The six outline sections in order, with the number of paragraphs each gets (one call each).
PLANS = (
    ParagraphPlan(
        "summary",
        "Summary",
        "State the headline cost of climate risk today and in 2041 to 2060, and what the "
        "priced options would remove.",
        "This report shows what climate change could add to the cost of covering Apetit's "
        "contracted crop volumes, and what the priced options would remove.",
        (
            "price_risk.climate_added_cost_eur",
            "price_risk.expected_cost_eur",
            "compare_actions.risk_removed_eur",
        ),
        12,
    ),
    ParagraphPlan(
        "risk",
        "Risk by crop and region",
        "Give the expected cost and the cost in a 1-in-10 bad year by crop and region under "
        "each climate scenario.",
        "The figures below give the expected cost and the cost in a 1-in-10 bad year.",
        ("price_risk.expected_cost_eur", "price_risk.one_in_ten_cost_eur"),
        40,
    ),
    ParagraphPlan(
        "risk",
        "Risk by crop and region",
        "Give the chance of a bad year, the yield change and the extra emissions from "
        "replacement imports under each climate scenario.",
        "The figures below give the chance of a bad year, the yield change and the extra "
        "emissions from replacement imports.",
        (
            "project_yields.bad_year_chance",
            "project_yields.yield_change_pct",
            "price_risk.expected_import_tco2e",
        ),
        40,
    ),
    ParagraphPlan(
        "drivers",
        "What drives the losses",
        "Name the weather drivers behind the yield change per crop and region. Use the "
        "direction and rank of each driver, and cite the yield change metrics for the size.",
        "Yield changes under each climate scenario come from weather drivers. The strongest "
        "driver for each crop and region is listed below.",
        ("project_yields.yield_change_pct",),
        12,
        ("drivers",),
    ),
    ParagraphPlan(
        "options",
        "Options and what they buy",
        "Describe each priced action with the risk it would remove, its break-even cost and its "
        "confidence.",
        "Each option is priced against the same contracted volume as the cost of doing nothing.",
        (
            "compare_actions.risk_removed_eur",
            "compare_actions.break_even_cost_eur",
            "compare_actions.import_tco2e_removed",
        ),
        30,
        ("options",),
    ),
    ParagraphPlan(
        "insights",
        "Insights",
        "Introduce each insight in one sentence and cite it with its insight token.",
        "The run found these insights.",
        (),
        0,
        ("insights",),
    ),
    ParagraphPlan(
        "method",
        "Method and limits",
        "Open the method section: say what the figures rest on and where they are uncertain. "
        "The lists of files, corrections, assumptions and models follow in code.",
        "Every number in this report opens its sources. The lists below name the files, "
        "corrections, assumptions and models behind the figures.",
        (),
        0,
        ("assumptions",),
    ),
)


# Recipe 2 has no insights, loss drivers or options, so its outline is three sections. The
# summary sees the yearly totals and the differences from the answer inventories first.
ENERGY_PLANS = (
    ParagraphPlan(
        "summary",
        "Summary",
        "State the Scope 2 emissions from purchased electricity per year, location-based and "
        "market-based, and how far they sit from the 2023 and 2024 answer inventories.",
        "This report gives the Scope 2 emissions from purchased electricity at Apetit's sites, "
        "location-based and market-based, and compares them with the answer inventories.",
        (
            "compare_inventory.location_based_difference_tco2e",
            "compare_inventory.market_based_difference_tco2e",
            "scope2_electricity.location_based_tco2e",
            "scope2_electricity.market_based_tco2e",
        ),
        16,
    ),
    ParagraphPlan(
        "scope2",
        "Scope 2 by site and year",
        "Give the electricity use and the location-based Scope 2 of each site and year, after "
        "the total for the year.",
        "The figures below give the electricity use and the location-based Scope 2 of each site.",
        (
            "scope2_electricity.electricity_use_mwh",
            "scope2_electricity.location_based_tco2e",
        ),
        40,
    ),
    ParagraphPlan(
        "scope2",
        "Scope 2 by site and year",
        "Give the market-based Scope 2 of each site and year, and the difference between the "
        "totals and the 2023 and 2024 answer inventories.",
        "The figures below give the market-based Scope 2 of each site and how the totals "
        "compare with the answer inventories.",
        (
            "scope2_electricity.market_based_tco2e",
            "compare_inventory.location_based_difference_tco2e",
            "compare_inventory.market_based_difference_tco2e",
        ),
        40,
    ),
    ParagraphPlan(
        "method",
        "Method and limits",
        "Open the method section: say that the figures rest on the cleaned readings with the "
        "approved corrections, the grid factors and the residual mix, and that guarantees of "
        "origin count only for their own year. Name where the figures are uncertain. The lists "
        "of files, corrections, assumptions and models follow in code.",
        "Every number in this report opens its sources. The lists below name the files, "
        "corrections, assumptions and models behind the figures.",
        (),
        0,
        ("assumptions",),
    ),
)
OUTLINES = {"energy_meter_check": ENERGY_PLANS}


def outline(recipe_id: str) -> tuple[ParagraphPlan, ...]:
    return OUTLINES.get(recipe_id, PLANS)


@dataclass(frozen=True)
class Paragraph:
    section: str
    heading: str | None
    text: str
    call_id: str


class DraftFailed(ValueError):
    """A paragraph failed its checks after the retries. The message is for the run's error."""


def draft_report(llm: Llm, evidence: ReportEvidence, concurrency: int = 8) -> list[Paragraph]:
    """Write the drafted paragraphs in outline order, a few calls at a time.

    Each paragraph has its own checks and retries. Raises DraftFailed for the first paragraph in
    outline order that fails, and starts no new calls once one has failed.
    """
    metric_ids = {m.metric_id for m in evidence.metrics}
    insight_ids = {i.insight_id for i in evidence.insights}
    recommended = any(o.status == "recommended" for o in evidence.options)
    action_names = {m.action for m in evidence.metrics if m.action}
    action_names |= {o.name for o in evidence.options}
    plans = outline(evidence.recipe_id)
    failed = threading.Event()

    def write(position: int) -> LlmResult[ParagraphDraft] | None:
        if failed.is_set():
            return None
        plan = plans[position]
        result = llm.call(
            AGENT,
            PROMPT_VERSION,
            build_prompt(position, evidence),
            ParagraphDraft,
            item=plan.heading,
            prose_fields=["text"],
            limits={"text": MAX_WORDS},
            check=guardrails(plan.section, metric_ids, insight_ids, recommended, action_names),
        )
        if result.value is None:
            failed.set()
        return result

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        results = list(pool.map(write, range(len(plans))))
    paragraphs: list[Paragraph] = []
    for plan, result in zip(plans, results, strict=True):
        if result is None or result.value is None:
            raise DraftFailed(
                f"The report draft failed: the assistant could not write the paragraph for "
                f"{plan.heading!r} so that it passes the checks. Nothing was saved. "
                "Start the draft again."
            )
        first = all(p.section != plan.section for p in paragraphs)
        paragraphs.append(
            Paragraph(
                plan.section, plan.heading if first else None, result.value.text, result.call_id
            )
        )
    return paragraphs


def build_prompt(position: int, evidence: ReportEvidence) -> str:
    plan = outline(evidence.recipe_id)[position]
    names = set(plan.metric_names)
    metrics = sorted(
        (m for m in evidence.metrics if m.name in names),
        key=lambda m: (
            m.region is not None,
            m.crop is not None,
            m.site is not None,
            m.name,
            m.region or "",
            m.crop or "",
            SCENARIO_ORDER.get(m.scenario or "", len(SCENARIO_ORDER)),
            m.ngfs_scenario or "",
            m.site or "",
            m.period or "",
            m.metric_id,
        ),
    )[: plan.metric_limit]
    facts: dict[str, Any] = {
        "recipe": evidence.recipe_id,
        "plan": position,
        "section": plan.section,
        "brief": plan.brief,
        "metrics": [metric_json(m) for m in metrics],
    }
    if "insights" in plan.uses:
        facts["insights"] = [
            {"id": i.insight_id, "title": i.title, "text": i.text} for i in evidence.insights
        ]
    if "options" in plan.uses:
        facts["actions"] = [
            {"name": o.name, "status": o.status or "not marked", "confidence": o.confidence}
            for o in evidence.options
        ]
    if "drivers" in plan.uses:
        facts["loss_drivers"] = [vars(d) for d in evidence.drivers]
    if "assumptions" in plan.uses:
        facts["assumptions"] = [vars(a) for a in evidence.assumptions]
    return f"{RULES}{INPUT_MARKER}{json.dumps(facts, ensure_ascii=False)}\n"


def applies_to(
    crop: str | None,
    region: str | None,
    scenario: str | None,
    ngfs: str | None,
    period: str | None,
    site: str | None = None,
) -> str:
    """The dimensions of a number in the words the app uses."""
    parts = [
        crop.replace("_", " ").capitalize() if crop else None,
        site,
        REGION_LABELS.get(region or "", region),
        SCENARIO_LABELS.get(scenario or "", scenario),
        NGFS_LABELS.get(ngfs or "", ngfs),
        None if scenario == "baseline" else period,
    ]
    return ", ".join(p for p in parts if p)


def metric_json(metric: MetricFact) -> dict[str, Any]:
    label = METRIC_LABELS.get(metric.name, metric.name.split(".")[-1].replace("_", " "))
    return {
        "id": metric.metric_id,
        "label": label,
        "name": metric.name,
        "value": metric.value,
        "low": metric.low,
        "high": metric.high,
        "unit": metric.unit,
        "applies_to": applies_to(
            metric.crop,
            metric.region,
            metric.scenario,
            metric.ngfs_scenario,
            metric.period,
            metric.site,
        ),
        "action": metric.action,
    }


# Guardrails, enforced in code.

_TOKEN = re.compile(r"\{\{.*?\}\}", re.DOTALL)
_TOKEN_BODY = re.compile(r"\{\{(metric|insight):(\w+)\}\}")
_FIRST_PERSON = re.compile(r"(?i:\b(?:we|our|ours|us|my|you|your)\b)|\bI\b")
_RECOMMEND = re.compile(r"\brecommend\w*", re.IGNORECASE)
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
_SCENARIO_CODE = re.compile(r"SSP\d-\d\.\d")
_ALLOWED_PHRASES = [
    "1-in-10",
    "CO2e",
    "Scope 2",
    *SCENARIO_LABELS.values(),
    *NGFS_LABELS.values(),
]


def guardrails(
    section: str,
    metric_ids: set[str],
    insight_ids: set[str],
    recommended: bool,
    action_names: set[str],
) -> Callable[[ParagraphDraft], None]:
    def check(draft: ParagraphDraft) -> None:
        if draft.section != section:
            raise ValueError(f"The section must be {section!r}.")
        if not draft.text.strip():
            raise ValueError("The text is empty.")
        for token in _TOKEN.findall(draft.text):
            found = _TOKEN_BODY.fullmatch(token)
            if found is None:
                raise ValueError(
                    f"The token {token} is not allowed. Use {{{{metric:met_...}}}} or "
                    "{{insight:ins_...}} with an id from the input."
                )
            kind, record_id = found.groups()
            known = metric_ids if kind == "metric" else insight_ids
            if record_id not in known:
                raise ValueError(f"The token {token} names no {kind} in this result set.")
        plain = _TOKEN.sub(" ", draft.text)
        # Action names can hold figures of their own, such as "Relocate 20% of Finnish pea area".
        for phrase in sorted([*_ALLOWED_PHRASES, *action_names], key=len, reverse=True):
            plain = plain.replace(phrase, " ")
        plain = _YEAR.sub(" ", _SCENARIO_CODE.sub(" ", plain))
        typed = re.search(r"\d[\d.,]*", plain)
        if typed:
            raise ValueError(
                f"The text types the figure {typed.group()}. Cite numbers as metric or insight "
                "tokens only."
            )
        if _FIRST_PERSON.search(plain):
            raise ValueError("Write in the third person. Do not use I, we, our or you.")
        if not recommended and _RECOMMEND.search(plain):
            raise ValueError(
                "No action is marked recommended. Say what an action would remove, "
                "without recommending it."
            )

    return check


# The fake model: one plain templated paragraph per call, citing ids read from the prompt.


def _fake_sentence(metric: dict[str, Any]) -> str:
    token = "{{metric:" + metric["id"] + "}}"
    where = f" under {metric['applies_to']}" if metric["applies_to"] else ""
    action, label = metric["action"], metric["label"].lower()
    if action and metric["name"].endswith("risk_removed_eur"):
        return f"{action} would remove {token}{where}."
    if action:
        return f"The {label} of {action}{where} is {token}."
    scope = f" for {metric['applies_to']}" if metric["applies_to"] else " across all farms"
    return f"{metric['label']}{scope} is {token}."


def fake_paragraph(prompt: str) -> dict[str, Any]:
    start = prompt.rindex(INPUT_MARKER) + len(INPUT_MARKER)
    facts: dict[str, Any] = json.JSONDecoder().raw_decode(prompt[start:])[0]
    plan = outline(facts["recipe"])[int(facts["plan"])]
    sentences: list[str] = [plan.fake_text]
    first_of_each_name: dict[str, dict[str, Any]] = {}
    # The highest climate scenario first, so an action reads as what it removes in the future.
    for metric in sorted(facts["metrics"], key=lambda m: "High emissions" not in m["applies_to"]):
        first_of_each_name.setdefault(metric["name"], metric)
    sentences += [_fake_sentence(m) for m in list(first_of_each_name.values())[:3]]
    for driver in facts.get("loss_drivers", [])[:3]:
        scenario = SCENARIO_LABELS.get(driver["scenario"], driver["scenario"])
        sentences.append(
            f"For {driver['unit']} under {scenario}, {driver['driver']} "
            f"{driver['direction']} yield the most."
        )
    for insight in facts.get("insights", [])[:3]:
        title = "" if re.search(r"\d", insight["title"]) else insight["title"].rstrip(".") + ". "
        sentences.append(f"{title}{{{{insight:{insight['id']}}}}}")
    return {"section": facts["section"], "heading": "", "text": " ".join(sentences)}


FAKE_RESPONSES[ParagraphDraft] = fake_paragraph
