"""The HTTP API.

The only HTTP surface in the system (docs/architecture.md §4). Built with
django-ninja: Pydantic schemas in, OpenAPI out at ``/api/openapi.json``, which the SPA
uses to generate a typed client (ADR 0004).

Two credentials, one API (ADR 0006, docs/public-api.md §3): the SPA authenticates with a
session cookie and CSRF is enforced on its writes (ADR 0003); everything else — Python,
R, MATLAB, curl — authenticates with an ``X-API-Key`` header, which needs no CORS and no
CSRF work. django-ninja tries each in ``auth=`` in order and uses the first that
resolves, so every existing endpoint accepts either credential with no code changed:
``ApiKeyAuth.authenticate`` returns the key's owning ``User``, and ``api/auth.py``'s
``get_owned``/``owned_queryset`` keep working unmodified either way.
"""

import logging

from django.http import Http404
from ninja import NinjaAPI
from ninja.errors import AuthenticationError, ValidationError
from ninja.security import django_auth

from api.errors import ApiError, envelope
from api.routers.auth import router as auth_router
from api.routers.datasets import router as datasets_router
from api.routers.meta import router as meta_router
from api.routers.projects import router as projects_router
from api.routers.results import router as results_router
from api.routers.runs import router as runs_router
from api.security import ApiKeyAuth

logger = logging.getLogger(__name__)

api = NinjaAPI(
    title="CERNAL API",
    version="1",
    description="RNA logic circuit design platform.",
    # Key first: cheaper, and it has no CSRF path (api/security.py). django_auth is
    # SessionAuth, which carries csrf=True — in django-ninja 1.6 CSRF is a property of
    # the auth mechanism rather than an API-level flag.
    auth=[ApiKeyAuth(), django_auth],
    urls_namespace="api",
)

api.add_router("/auth", auth_router, tags=["auth"])
api.add_router("/projects", projects_router, tags=["projects"])
api.add_router("", datasets_router, tags=["datasets"])
api.add_router("", runs_router, tags=["runs"])
api.add_router("", results_router, tags=["results"])
api.add_router("", meta_router, tags=["meta"])


@api.exception_handler(ApiError)
def handle_api_error(request, exc: ApiError):
    return api.create_response(
        request, envelope(exc.code, exc.message, exc.detail), status=exc.status
    )


@api.exception_handler(Http404)
def handle_not_found(request, exc):
    return api.create_response(
        request, envelope("not_found", "That resource does not exist."), status=404
    )


@api.exception_handler(AuthenticationError)
def handle_unauthenticated(request, exc):
    return api.create_response(
        request, envelope("not_authenticated", "Authentication is required."), status=401
    )


@api.exception_handler(ValidationError)
def handle_validation_error(request, exc: ValidationError):
    return api.create_response(
        request,
        envelope("validation_failed", "The request body is invalid.", {"errors": exc.errors}),
        status=422,
    )


@api.exception_handler(Exception)
def handle_unexpected(request, exc):
    """Never leak internals to a client.

    The traceback goes to the log; the client gets a generic message
    (docs/architecture.md §7.2).
    """
    logger.exception("Unhandled API error at %s", request.path)
    return api.create_response(
        request,
        envelope("internal_error", "Something went wrong. The team has been notified."),
        status=500,
    )
