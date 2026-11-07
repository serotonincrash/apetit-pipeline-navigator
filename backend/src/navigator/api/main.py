"""The FastAPI app. One router per screen; the OpenAPI contract is generated from them."""

from fastapi import FastAPI

from navigator.logs import configure
from navigator.settings import get_settings

configure(get_settings().log_level)

app = FastAPI(title="Climate and Nature Navigator", version="0.1.0")


@app.get("/api/health", tags=["all"])
def health() -> dict[str, str]:
    """Liveness check for Caddy and Compose."""
    return {"status": "ok"}
