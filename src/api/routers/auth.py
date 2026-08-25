"""Session authentication.

Session cookies rather than tokens: the SPA is served from the same origin, so this
works with no CORS and nothing sensitive in browser storage (ADR 0003).
"""

from django.contrib.auth import authenticate
from django.contrib.auth import login as django_login
from django.contrib.auth import logout as django_logout
from django.middleware.csrf import get_token
from ninja import Router, Status

from api.errors import ApiError
from api.schemas import LoginIn, UserOut

router = Router()


class InvalidCredentials(ApiError):
    status = 401
    code = "invalid_credentials"


@router.get("/csrf", response={204: None}, auth=None, url_name="csrf")
def csrf(request):
    """Hand the browser a CSRF cookie.

    Session auth means writes are CSRF-protected. A single-page app has no server-rendered
    form to carry the token, so it calls this once at start-up and then sends the cookie
    value back in the ``X-CSRFToken`` header.

    ``get_token`` marks the request so CsrfViewMiddleware sets the cookie on the way out
    — the same thing ``@ensure_csrf_cookie`` does, but compatible with ninja's response
    pipeline, which returns a ``Status`` rather than an ``HttpResponse``.
    """
    get_token(request)
    return Status(204, None)


@router.post("/login", response=UserOut, auth=None, url_name="login")
def login(request, payload: LoginIn):
    user = authenticate(request, username=payload.username, password=payload.password)
    if user is None:
        # One message for both cases, so the endpoint cannot be used to enumerate users.
        raise InvalidCredentials("Incorrect username or password.")

    django_login(request, user)
    return user


@router.post("/logout", response={204: None})
def logout(request):
    django_logout(request)
    return Status(204, None)


@router.get("/me", response=UserOut)
def me(request):
    return request.user
