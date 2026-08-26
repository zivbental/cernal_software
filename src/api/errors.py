"""One error shape for the whole API.

Every failure the client sees looks like::

    {"error": {"code": "not_found", "message": "...", "detail": {...}}}

Responses never carry filesystem paths, storage internals, engine tracebacks or settings
(docs/architecture.md §7.2). Detail goes to the log, keyed by the object id.
"""

from typing import Any


class ApiError(Exception):
    """Base for errors that map to a clean HTTP response."""

    status = 400
    code = "bad_request"

    def __init__(self, message: str, *, detail: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail or {}


class NotFound(ApiError):
    status = 404
    code = "not_found"


class PermissionDenied(ApiError):
    status = 403
    code = "permission_denied"


class Conflict(ApiError):
    """The request is well-formed but conflicts with the resource's current state."""

    status = 409
    code = "conflict"


class ValidationFailed(ApiError):
    status = 422
    code = "validation_failed"


def envelope(code: str, message: str, detail: dict[str, Any] | None = None) -> dict:
    return {"error": {"code": code, "message": message, "detail": detail or {}}}
