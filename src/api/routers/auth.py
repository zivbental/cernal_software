"""Session authentication.

Session cookies rather than tokens: the SPA is served from the same origin, so this
works with no CORS and nothing sensitive in browser storage (ADR 0003).
"""

from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth import login as django_login
from django.contrib.auth import logout as django_logout
from django.middleware.csrf import get_token
from ninja import Router, Status

from api.errors import ApiError, ValidationFailed
from api.schemas import LoginIn, RegisterIn, RegistrationOut, UserOut
from apps.accounts.services import RegistrationError, register_user

router = Router()


class InvalidCredentials(ApiError):
    status = 401
    code = "invalid_credentials"


class AccountPendingApproval(ApiError):
    """Correct credentials, but a staff member has not approved the account yet."""

    status = 403
    code = "pending_approval"


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


@router.post("/register", response={201: RegistrationOut}, auth=None)
def register(request, payload: RegisterIn):
    """Request an account.

    Creates it inactive; a staff member approves it in Django admin. No session is
    established and no email is sent.
    """
    try:
        user = register_user(
            username=payload.username,
            email=payload.email,
            password=payload.password,
            full_name=payload.full_name,
        )
    except RegistrationError as exc:
        raise ValidationFailed(str(exc)) from None

    return Status(
        201,
        RegistrationOut(
            username=user.username,
            email=user.email,
            pending_approval=True,
            message=(
                "Your account has been created and is waiting for a team administrator "
                "to approve it. You will be able to sign in once they do."
            ),
        ),
    )


@router.post("/login", response=UserOut, auth=None, url_name="login")
def login(request, payload: LoginIn):
    user = authenticate(request, username=payload.username, password=payload.password)

    if user is None:
        # authenticate() also returns None for a correct password on an inactive
        # account, so distinguish that here — otherwise someone waiting for approval is
        # told their password is wrong and tries to register again.
        #
        # This only reveals "pending" to someone who already knows the password, so it
        # is not a way to enumerate accounts.
        if _is_pending(payload.username, payload.password):
            raise AccountPendingApproval(
                "Your account is waiting for a team administrator to approve it."
            )
        # One message for both cases, so the endpoint cannot be used to enumerate users.
        raise InvalidCredentials("Incorrect username or password.")

    django_login(request, user)
    return user


def _is_pending(username: str, password: str) -> bool:
    candidate = get_user_model().objects.filter(username__iexact=username.strip()).first()
    return bool(candidate and not candidate.is_active and candidate.check_password(password))


@router.post("/logout", response={204: None})
def logout(request):
    django_logout(request)
    return Status(204, None)


@router.get("/me", response=UserOut)
def me(request):
    return request.user
