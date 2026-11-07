"""The models behind the wrapper: Gemini through google-genai, and a fixed-answer fake."""

import json
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


# Filled in by the agents as they are written: one valid answer per output schema.
FAKE_RESPONSES: dict[type[BaseModel], dict[str, Any]] = {}


class FakeModel:
    name = "fake"

    def __init__(self, responses: dict[type[BaseModel], dict[str, Any]] | None = None) -> None:
        self._responses = FAKE_RESPONSES if responses is None else responses

    def generate(self, prompt: str, schema: type[BaseModel]) -> str:
        if schema not in self._responses:
            raise LookupError(
                f"The fake model has no answer for {schema.__name__}. "
                "Add one to navigator.llm.models.FAKE_RESPONSES."
            )
        return json.dumps(self._responses[schema])


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


def default_model() -> TextModel:
    settings = get_settings()
    if settings.llm_mode == "gemini":
        return GeminiModel(settings.gemini_api_key, settings.gemini_model)
    return FakeModel()
