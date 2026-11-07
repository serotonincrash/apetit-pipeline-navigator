"""The default recorder writes one llm_call row per attempt, committed as it happens."""

import json

import pytest
from pydantic import BaseModel
from sqlalchemy import select

from navigator.db import models as m
from navigator.db.session import session_scope
from navigator.llm.client import Llm
from navigator.llm.models import FakeModel
from tests.api.records import add_run

pytestmark = pytest.mark.api


class Explanation(BaseModel):
    explanation: str


class BadThenGood:
    name = "scripted"

    def __init__(self) -> None:
        self.answers = ["not json", json.dumps({"explanation": "Plain text."})]

    def generate(self, prompt: str, schema: type[BaseModel]) -> str:
        return self.answers.pop(0)


def test_default_recorder_writes_llm_call_rows() -> None:
    run_id = add_run()
    llm = Llm(BadThenGood(), run_id, fallback=FakeModel())
    result = llm.call(
        "explainer", "v1", "Explain.", Explanation, item="p", prose_fields=["explanation"]
    )
    with session_scope() as session:
        rows = session.scalars(
            select(m.LlmCall).where(m.LlmCall.run_id == run_id).order_by(m.LlmCall.attempt)
        ).all()
        assert [(r.attempt, r.status) for r in rows] == [(1, "retried"), (2, "ok")]
        assert rows[1].call_id == result.call_id
        assert rows[0].error
        assert rows[1].output_hash
