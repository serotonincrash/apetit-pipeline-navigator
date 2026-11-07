"""The FastAPI app. One router per screen; the OpenAPI contract is generated from them."""

from typing import Any

from fastapi import FastAPI

from navigator.api import actions, health, personas, report, review, risk, rules, runs
from navigator.logs import configure
from navigator.settings import get_settings

configure(get_settings().log_level)

EVENT_STREAM_PATH = "/api/runs/{run_id}/events"


class NavigatorAPI(FastAPI):
    def openapi(self) -> dict[str, Any]:
        schema = super().openapi()
        # FastAPI types every non-JSON response as a string next to its model. For the event
        # stream that hides the RunEvent schema from client generators, so drop the string.
        content = schema["paths"][EVENT_STREAM_PATH]["get"]["responses"]["200"]["content"]
        content["text/event-stream"]["schema"].pop("type", None)
        return schema


app = NavigatorAPI(title="Climate and Nature Navigator", version="0.1.0")

for module in (health, personas, runs, review, rules, risk, actions, report):
    app.include_router(module.router)
