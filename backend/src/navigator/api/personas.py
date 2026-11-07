"""Personas for the switcher in the app header. There is no sign-in for the hackathon."""

from fastapi import APIRouter

from navigator.api.dependencies import ROLE_LABELS
from navigator.api.schemas import Persona

router = APIRouter(prefix="/api", tags=["shared"])


@router.get("/personas", operation_id="listPersonas")
def list_personas() -> list[Persona]:
    """The roles a person can act as. The person types the name recorded on their decisions."""
    return [Persona(role=role, label=label) for role, label in ROLE_LABELS.items()]
