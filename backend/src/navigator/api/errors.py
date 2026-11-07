"""Error responses shared by the routers, and their place in the OpenAPI contract."""

from typing import Any

from fastapi import HTTPException, status
from fastapi.exceptions import RequestValidationError

from navigator.api.schemas import ErrorMessage

NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorMessage, "description": "No record with that id."}
}
BAD_PERSONA: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorMessage, "description": "The X-Persona header is missing or malformed."}
}
WRONG_ROLE: dict[int | str, dict[str, Any]] = {
    403: {"model": ErrorMessage, "description": "This decision belongs to the other specialist."}
}


def invalid(location: tuple[str, ...], message: str) -> RequestValidationError:
    """A 422 in the same shape as FastAPI's own validation errors, so clients read one format.

    `location` names the input, such as ("body", "kind") or ("query", "filter").
    """
    return RequestValidationError([{"type": "value_error", "loc": location, "msg": message}])


def not_found(thing: str, record_id: str) -> HTTPException:
    """`thing` is the word the app uses, such as 'run' or 'table'."""
    return HTTPException(status.HTTP_404_NOT_FOUND, f"No {thing} with id {record_id}.")
