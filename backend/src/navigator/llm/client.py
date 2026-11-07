"""The wrapper steps call through ctx.llm: prompt in, validated object out, every attempt logged."""

import hashlib
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from pydantic import BaseModel, ValidationError

from navigator import ids, prose
from navigator.db import models as m
from navigator.db.session import session_scope
from navigator.llm.models import FakeModel, ModelError, ModelUnavailable, TextModel, default_model
from navigator.logs import get_logger

log = get_logger(__name__)

MAX_ATTEMPTS = 3


@dataclass(frozen=True)
class LlmResult[T: BaseModel]:
    """`value` is set when the call succeeded. A failed call has a `reason` and a `call_id`."""

    call_id: str
    value: T | None
    reason: str = ""

    @property
    def ok(self) -> bool:
        return self.value is not None


@dataclass(frozen=True)
class CallRow:
    call_id: str
    run_id: str | None
    agent: str
    model: str
    prompt_version: str
    input_hash: str
    output_hash: str | None
    attempt: int
    status: str
    error: str | None


Recorder = Callable[[CallRow], None]
FailureHandler = Callable[[str, str, str], None]


def record_to_database(row: CallRow) -> None:
    """Store one call in its own transaction, so it is visible at once."""
    with session_scope() as session:
        session.add(m.LlmCall(**vars(row)))


def _ignore_failure(agent: str, item: str, reason: str) -> None:
    return None


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


class Llm:
    def __init__(
        self,
        model: TextModel,
        run_id: str | None,
        *,
        on_failure: FailureHandler | None = None,
        record: Recorder = record_to_database,
        fallback: TextModel | None = None,
    ) -> None:
        self._model = model
        self._fallback = fallback or FakeModel()
        self._run_id = run_id
        self._on_failure: FailureHandler = on_failure or _ignore_failure
        self._record = record
        self._switch_reason = ""
        self._switch_lock = threading.Lock()

    def call[T: BaseModel](
        self,
        agent: str,
        prompt_version: str,
        prompt: str,
        schema: type[T],
        *,
        item: str,
        prose_fields: Sequence[str] = (),
        limits: Mapping[str, int] | None = None,
        check: Callable[[T], None] | None = None,
    ) -> LlmResult[T]:
        """Ask the model, check the answer and retry with the error up to twice.

        `item` names what the call is for, such as a proposal key, and goes to `on_failure`.
        `check` raises ValueError with a reason when the answer breaks an agent guardrail.
        """
        sent = prompt
        call_id = ""
        reason = ""
        for attempt in range(1, MAX_ATTEMPTS + 1):
            call_id = ids.new_id("llm_call")
            output: str | None = None
            value: T | None = None
            try:
                output = self._generate(sent, schema)
                value = self._validate(output, schema, prose_fields, limits or {}, check)
            except (ModelError, ValueError) as exc:
                reason = str(exc)[:600]
            if value is not None:
                status = "fake model" if self._switch_reason else "ok"
                self._write(call_id, agent, prompt_version, sent, output, attempt, status, None)
                return LlmResult(call_id, value)
            last = attempt == MAX_ATTEMPTS
            status = "failed" if last else "retried"
            self._write(call_id, agent, prompt_version, sent, output, attempt, status, reason)
            sent = (
                f"{prompt}\n\nYour previous answer was rejected.\nAnswer: {output}\n"
                f"Problem: {reason}\nReturn corrected JSON only."
            )
        log.warning("llm call failed", extra={"agent": agent, "item": item, "reason": reason})
        self._on_failure(agent, item, reason)
        return LlmResult(call_id, None, reason)

    def _generate(self, prompt: str, schema: type[BaseModel]) -> str:
        try:
            return self._model.generate(prompt, schema)
        except ModelUnavailable as exc:
            # Calls overlap in threads: the first to fail switches, the others find it switched.
            with self._switch_lock:
                if not self._switch_reason:
                    self._switch_reason = f"Switched to the fake model: {exc}"
                    log.warning("llm switched to fake model", extra={"reason": str(exc)})
                self._model = self._fallback
            return self._fallback.generate(prompt, schema)

    def _validate[T: BaseModel](
        self,
        output: str,
        schema: type[T],
        prose_fields: Sequence[str],
        limits: Mapping[str, int],
        check: Callable[[T], None] | None,
    ) -> T:
        try:
            value = schema.model_validate_json(output)
        except ValidationError as exc:
            raise ValueError(f"Output does not match the schema: {exc}") from exc
        problems = [
            f"{field}: {problem}"
            for field in prose_fields
            for problem in prose.check(str(getattr(value, field)), limits.get(field))
        ]
        if problems:
            raise ValueError("Writing check failed. " + " ".join(problems))
        if check is not None:
            check(value)
        return value

    def _write(
        self,
        call_id: str,
        agent: str,
        prompt_version: str,
        prompt: str,
        output: str | None,
        attempt: int,
        status: str,
        error: str | None,
    ) -> None:
        if self._switch_reason:
            error = error or self._switch_reason
        self._record(
            CallRow(
                call_id=call_id,
                run_id=self._run_id,
                agent=agent,
                model=self._model.name,
                prompt_version=prompt_version,
                input_hash=_sha256(prompt),
                output_hash=None if output is None else _sha256(output),
                attempt=attempt,
                status=status,
                error=error,
            )
        )


def get_llm(run_id: str | None, on_failure: FailureHandler | None = None) -> Llm:
    """The wrapper for one run, with the model chosen by LLM_MODE."""
    return Llm(default_model(), run_id, on_failure=on_failure)
