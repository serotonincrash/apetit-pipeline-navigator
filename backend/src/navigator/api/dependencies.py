"""Request dependencies: the database session and the persona making a change."""

from dataclasses import dataclass
from typing import Annotated
from urllib.parse import unquote

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from navigator.api.schemas import PersonaRole
from navigator.db.session import get_session

# Function scope commits before the response goes out, so a client that writes and then
# reads straight away sees its own write.
SessionDep = Annotated[Session, Depends(get_session, scope="function")]

ROLE_LABELS: dict[PersonaRole, str] = {
    "data_specialist": "Data specialist",
    "sustainability_specialist": "Sustainability specialist",
}
ROLES: dict[str, PersonaRole] = {role: role for role in ROLE_LABELS}

# Approvals made automatically under a rule policy carry this name (see docs/glossary.md), so
# a person cannot use it.
RESERVED_NAME = "rule policy"


@dataclass(frozen=True)
class PersonaHeader:
    role: PersonaRole
    name: str


def current_persona(
    x_persona: Annotated[
        str | None,
        Header(
            description=(
                "Required on every write: `<role>:<name>`, for example "
                "`data_specialist:A. Reviewer`. The name may be percent-encoded."
            )
        ),
    ] = None,
) -> PersonaHeader:
    """The persona from the X-Persona header. Its name is recorded on decisions and runs."""
    if not x_persona:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Choose a persona before making changes. The app sends it as role:name.",
        )
    raw_role, _, raw_name = x_persona.partition(":")
    role = ROLES.get(raw_role)
    name = unquote(raw_name).strip()
    if role is None or not name:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "The persona must be role:name, with the role data_specialist or "
            "sustainability_specialist.",
        )
    if name.lower() == RESERVED_NAME:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "That name is kept for approvals by the data check policy. Choose another name.",
        )
    return PersonaHeader(role=role, name=name)


PersonaDep = Annotated[PersonaHeader, Depends(current_persona)]


def require_role(persona: PersonaHeader, role: PersonaRole, decision: str) -> None:
    """Each specialist decides only in their own review step. `decision` completes the sentence."""
    if persona.role != role:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Only the {ROLE_LABELS[role].lower()} can {decision}. Switch persona to go on.",
        )
