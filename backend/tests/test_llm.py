"""The LLM wrapper retries bad answers, records every attempt and falls back to the fake model."""

import json
from typing import Any

import pytest
from pydantic import BaseModel

from navigator.llm.client import CallRow, Llm
from navigator.llm.models import FakeModel, GeminiModel, ModelError, ModelUnavailable


class Explanation(BaseModel):
    explanation: str


class Unregistered(BaseModel):
    text: str


GOOD = json.dumps({"explanation": "The area is 40 times the median for {{ev:ratio_to_median}}."})


class ScriptedModel:
    """Returns or raises the next scripted item on each call and keeps the prompts it saw."""

    name = "scripted"

    def __init__(self, *script: str | Exception) -> None:
        self.script = list(script)
        self.prompts: list[str] = []

    def generate(self, prompt: str, schema: type[BaseModel]) -> str:
        self.prompts.append(prompt)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class Setup:
    def __init__(self, model: Any, fallback: Any = None) -> None:
        self.rows: list[CallRow] = []
        self.failures: list[tuple[str, str, str]] = []
        self.llm = Llm(
            model,
            "run_1",
            on_failure=lambda *args: self.failures.append(args),
            record=self.rows.append,
            fallback=fallback or FakeModel({Explanation: json.loads(GOOD)}),
        )

    def ask(self, **kwargs: Any) -> Any:
        options: dict[str, Any] = {"item": "prop_1", "prose_fields": ["explanation"]}
        options.update(kwargs)
        return self.llm.call("explainer", "v1", "Explain.", Explanation, **options)


def test_valid_output_first_try() -> None:
    s = Setup(ScriptedModel(GOOD))
    result = s.ask(limits={"explanation": 80})
    assert result.ok
    assert result.value.explanation.startswith("The area")
    assert [r.status for r in s.rows] == ["ok"]
    assert result.call_id == s.rows[0].call_id
    assert s.failures == []


def test_bad_json_then_good() -> None:
    model = ScriptedModel("not json", GOOD)
    s = Setup(model)
    result = s.ask()
    assert result.ok
    assert [(r.attempt, r.status) for r in s.rows] == [(1, "retried"), (2, "ok")]
    assert result.call_id == s.rows[1].call_id
    assert s.rows[0].error


def test_schema_failure_is_retried_with_the_error() -> None:
    model = ScriptedModel('{"wrong": 1}', GOOD)
    s = Setup(model)
    assert s.ask().ok
    assert "explanation" in model.prompts[1]
    assert "Field required" in model.prompts[1]


def test_prose_failure_on_banned_word() -> None:
    bad = json.dumps({"explanation": "A robust fix."})
    model = ScriptedModel(bad, GOOD)
    s = Setup(model)
    assert s.ask().ok
    assert "robust" in model.prompts[1]


def test_prose_failure_on_word_limit() -> None:
    bad = json.dumps({"explanation": "one two three four"})
    s = Setup(ScriptedModel(bad, json.dumps({"explanation": "one two"})))
    assert s.ask(limits={"explanation": 3}).ok
    assert "over the limit of 3" in (s.rows[0].error or "")


def test_check_callback_failure_reason_reaches_the_prompt() -> None:
    def check(value: Explanation) -> None:
        if "ev:" not in value.explanation:
            raise ValueError("Token names no evidence value.")

    model = ScriptedModel(json.dumps({"explanation": "Plain text."}), GOOD)
    s = Setup(model)
    assert s.ask(check=check).ok
    assert "Token names no evidence value." in model.prompts[1]
    assert "Plain text." in model.prompts[1]


def test_failure_after_three_attempts() -> None:
    model = ScriptedModel("x", "y", "z")
    s = Setup(model)
    result = s.ask()
    assert not result.ok
    assert result.value is None
    assert result.reason
    assert result.call_id == s.rows[-1].call_id
    assert [(r.attempt, r.status) for r in s.rows] == [
        (1, "retried"),
        (2, "retried"),
        (3, "failed"),
    ]
    assert s.failures == [("explainer", "prop_1", result.reason)]


def test_rows_carry_hashes_and_ids() -> None:
    model = ScriptedModel("bad", GOOD)
    s = Setup(model)
    s.ask()
    first, second = s.rows
    assert first.run_id == "run_1"
    assert first.agent == "explainer"
    assert first.prompt_version == "v1"
    assert first.model == "scripted"
    assert first.call_id.startswith("call_")
    assert first.call_id != second.call_id
    assert len(first.input_hash) == 64
    assert first.input_hash != second.input_hash
    assert first.output_hash != second.output_hash


def test_other_model_errors_count_as_failed_attempts() -> None:
    s = Setup(ScriptedModel(ModelError("503"), GOOD))
    assert s.ask().ok
    assert s.rows[0].output_hash is None
    assert s.rows[0].status == "retried"


def test_quota_error_switches_to_fake_and_stays() -> None:
    model = ScriptedModel(ModelUnavailable("quota"))
    s = Setup(model)
    assert s.ask().ok
    assert s.ask().ok
    assert len(model.prompts) == 1
    assert [(r.model, r.status) for r in s.rows] == [("fake", "fake model")] * 2
    assert "quota" in (s.rows[0].error or "")


def test_missing_key_switches_to_fake() -> None:
    s = Setup(GeminiModel("", "gemini-test"))
    assert s.ask().ok
    assert s.rows[0].status == "fake model"
    assert "GEMINI_API_KEY" in (s.rows[0].error or "")


def test_unregistered_schema_raises_a_clear_error() -> None:
    with pytest.raises(LookupError, match="Unregistered"):
        FakeModel({}).generate("p", Unregistered)
