"""The models behind the wrapper: OpenCode Go, Gemini and a fixed-answer fake."""

import json
import re
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable
from typing import Any, Protocol

from pydantic import BaseModel

from navigator.settings import get_settings


class ModelUnavailable(Exception):
    """The model cannot be used for the rest of the run: no key, a rejected key or no quota."""


class ModelError(Exception):
    """One call failed for another reason. The wrapper counts it as a failed attempt."""


class TextModel(Protocol):
    name: str

    def generate(self, prompt: str, schema: type[BaseModel]) -> str:
        """Return the model's answer as JSON text shaped like `schema`."""
        ...


# Filled in by the agents as they are written: one valid answer per output schema. An answer
# that depends on the prompt, such as one citing ids the prompt carries, is a function of it.
FakeResponse = dict[str, Any] | Callable[[str], dict[str, Any]]
FAKE_RESPONSES: dict[type[BaseModel], FakeResponse] = {}


class FakeModel:
    name = "fake"

    def __init__(self, responses: dict[type[BaseModel], FakeResponse] | None = None) -> None:
        self._responses = FAKE_RESPONSES if responses is None else responses

    def generate(self, prompt: str, schema: type[BaseModel]) -> str:
        if schema not in self._responses:
            raise LookupError(
                f"The fake model has no answer for {schema.__name__}. "
                "Add one to navigator.llm.models.FAKE_RESPONSES."
            )
        response = self._responses[schema]
        return json.dumps(response(prompt) if callable(response) else response)


class GeminiModel:
    """Builds its client on the first call, so fake mode needs no key and no SDK import."""

    def __init__(self, api_key: str, model: str) -> None:
        self.name = model
        self._api_key = api_key
        self._client: Any = None

    def generate(self, prompt: str, schema: type[BaseModel]) -> str:
        if not self._api_key:
            raise ModelUnavailable("GEMINI_API_KEY is not set.")
        if not self.name:
            raise ModelUnavailable("GEMINI_MODEL is not set.")
        from google import genai
        from google.genai import errors, types

        if self._client is None:
            self._client = genai.Client(api_key=self._api_key)
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema=schema.model_json_schema(),
        )
        try:
            response = self._client.models.generate_content(
                model=self.name, contents=prompt, config=config
            )
        except errors.APIError as exc:
            # 429 is the quota. A bad key comes back as 401, 403 or a 400 that says so.
            if exc.code in (401, 403, 429) or (exc.code == 400 and "API key" in str(exc)):
                raise ModelUnavailable(f"Gemini refused the call: {exc}") from exc
            raise ModelError(f"Gemini call failed: {exc}") from exc
        return response.text or ""


_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)


class OpenCodeModel:
    """OpenCode Go through its OpenAI-style chat endpoint, which serves every Go model.

    Go states no JSON mode, so the schema goes into the prompt and the wrapper's validation
    and retries catch answers that miss it.
    """

    def __init__(self, api_key: str, model: str, base_url: str, timeout: float = 120.0) -> None:
        self.name = model
        self._api_key = api_key
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._timeout = timeout
        # Go asks for one stable session id per conversation; one wrapper serves one run.
        self._session = uuid.uuid4().hex

    def generate(self, prompt: str, schema: type[BaseModel]) -> str:
        if not self._api_key:
            raise ModelUnavailable("OPENCODE_API_KEY is not set.")
        if not self.name:
            raise ModelUnavailable("OPENCODE_MODEL is not set.")
        instruction = (
            "Answer with one JSON object and nothing else, no code fence. It must match this "
            f"JSON schema:\n{json.dumps(schema.model_json_schema())}"
        )
        body = {
            "model": self.name,
            "messages": [
                {"role": "system", "content": instruction},
                {"role": "user", "content": prompt},
            ],
        }
        request = urllib.request.Request(
            self._url,
            data=json.dumps(body).encode(),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "User-Agent": "climate-nature-navigator/1.0",
                "x-opencode-session": self._session,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                answer = json.load(response)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:300]
            # 401 and 403 are the key, 402 and 429 the plan's allowance.
            if exc.code in (401, 402, 403, 429):
                raise ModelUnavailable(f"OpenCode refused the call ({exc.code}): {detail}") from exc
            raise ModelError(f"OpenCode call failed ({exc.code}): {detail}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ModelError(f"OpenCode could not be reached: {exc}") from exc
        try:
            text = answer["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise ModelError(f"OpenCode answer has no message: {str(answer)[:300]}") from exc
        fenced = _FENCE.match(text)
        return fenced.group(1) if fenced else text


def default_model() -> TextModel:
    settings = get_settings()
    if settings.llm_mode == "opencode":
        return OpenCodeModel(
            settings.opencode_api_key,
            settings.opencode_model,
            settings.opencode_base_url,
            timeout=settings.opencode_timeout_seconds,
        )
    if settings.llm_mode == "gemini":
        return GeminiModel(settings.gemini_api_key, settings.gemini_model)
    return FakeModel()
