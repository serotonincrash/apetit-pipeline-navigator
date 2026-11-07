"""Liveness check for Caddy and Compose."""

from fastapi import APIRouter

from navigator.api.schemas import Health

router = APIRouter(prefix="/api", tags=["shared"])


@router.get("/health", operation_id="getHealth")
def get_health() -> Health:
    """Liveness check for Caddy and Compose."""
    return Health(status="ok")
