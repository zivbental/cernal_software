"""Exceptions raised by the cernal client.

Mapped from the shared error envelope (docs/public-api.md §10): every failure the
server returns is ``{"error": {"code", "message", "detail"}}``. These classes exist so
a caller can ``except cernal.ValidationError`` instead of parsing status codes.
"""

from __future__ import annotations


class CernalError(Exception):
    """Base for every error this client raises."""


class AuthError(CernalError):
    """401 ``invalid_api_key`` — missing, malformed, unknown, revoked or expired."""


class ValidationError(CernalError):
    """422 — ``validation_failed`` or ``unknown_parameter``.

    ``strict`` submissions (the default on ``POST /api/design``) carry ``did_you_mean``
    for a misspelled field name (docs/public-api.md §9.2).
    """

    def __init__(self, message: str, *, code: str = "", detail: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.detail = detail or {}

    @property
    def did_you_mean(self) -> str | None:
        return self.detail.get("did_you_mean")


class RateLimited(CernalError):
    """429 — ``rate_limited`` or ``too_many_active_runs``."""

    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message)
        #: Seconds to wait before retrying, when the server sent ``Retry-After``.
        self.retry_after = retry_after


class RunFailed(CernalError):
    """A run reached a terminal ``FAILED`` or ``CANCELLED`` state.

    ``error_summary`` is what the server reported — safe to show a researcher, no
    tracebacks or paths (docs/architecture.md §7.2).
    """

    def __init__(self, message: str, *, status: str = "", error_summary: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.error_summary = error_summary
