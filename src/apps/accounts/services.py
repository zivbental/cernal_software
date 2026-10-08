"""Account registration and approval.

New accounts are created **inactive** and stay that way until a staff member approves
them in Django admin. No email is involved anywhere: at a few dozen users, a person on
the team is always reachable, and SMTP credentials would be one more thing to hold
correctly on the VPS (docs/architecture.md §2, rule 10).
"""

import hashlib
import hmac
import logging
import secrets

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import ApiKey, ApiKeyScope

logger = logging.getLogger(__name__)


class RegistrationError(Exception):
    """The account could not be created. The message is safe to show the applicant."""


@transaction.atomic
def register_user(*, username: str, email: str, password: str, full_name: str = ""):
    """Create a pending account.

    Returns the user with ``is_active=False``. They cannot sign in until a staff member
    approves them.
    """
    model = get_user_model()

    username = username.strip()
    email = email.strip().lower()

    if not username:
        raise RegistrationError("Choose a username.")
    if username.casefold() == REVIEWER_USERNAME.casefold():
        raise RegistrationError("That username is reserved for the reviewer account.")
    if len(username) > 150:
        raise RegistrationError("Usernames must be at most 150 characters.")
    if not email:
        raise RegistrationError("An email address is required, so we know who you are.")
    try:
        model._meta.get_field("username").run_validators(username)
        validate_email(email)
    except ValidationError as exc:
        raise RegistrationError(" ".join(exc.messages)) from None
    if len(username) < 3:
        raise RegistrationError("Usernames must be at least 3 characters.")
    if len(password) < 8:
        raise RegistrationError("Passwords must be at least 8 characters.")
    if not email:
        raise RegistrationError("An email address is required, so we know who you are.")

    # Usernames are unique and the applicant has to be told, so this necessarily
    # reveals that one is taken. Email is checked case-insensitively for the same reason.
    if model.objects.filter(username__iexact=username).exists():
        raise RegistrationError("That username is already taken.")
    if model.objects.filter(email__iexact=email).exists():
        raise RegistrationError("An account with that email address already exists.")

    first_name, _, last_name = full_name.strip().partition(" ")

    user = model(
        username=username,
        email=email,
        first_name=first_name[:150],
        last_name=last_name[:150],
        # The whole point: approval is a deliberate human act.
        is_active=False,
    )

    try:
        validate_password(password, user)
    except ValidationError as exc:
        raise RegistrationError(" ".join(exc.messages)) from None

    user.set_password(password)

    try:
        user.save()
    except IntegrityError:
        raise RegistrationError("That username is already taken.") from None

    logger.info("Registration request from %s (%s) awaiting approval", username, email)
    return user


def approve_user(user) -> bool:
    """Activate a pending account. Returns False if it was already active."""
    if user.is_active:
        return False

    user.is_active = True
    user.save(update_fields=["is_active"])
    logger.info("Account %s approved", user.username)
    return True


def pending_users():
    """Everyone waiting for approval, oldest request first."""
    return get_user_model().objects.filter(is_active=False).order_by("date_joined")


#: The one account the login page's reviewer button ever signs in as (settings
#: REVIEWER_LOGIN_ENABLED). Fixed, not minted per click, so repeated clicks are
#: idempotent and reviewers all land on the same browsable history.
REVIEWER_USERNAME = "reviewer"


def get_or_create_reviewer_account():
    """The shared, pre-approved, passwordless account behind the reviewer button.

    No usable password: `set_unusable_password` means this account can never be
    reached through the normal username/password form, only by `django_login` from the
    dedicated reviewer-login endpoint. Deliberately not staff and not superuser — a
    button anyone can click must never grant admin access.
    """
    model = get_user_model()
    user, created = model.objects.get_or_create(
        username=REVIEWER_USERNAME,
        defaults={
            "email": "reviewer@cernal.local",
            "first_name": "Reviewer",
            "is_active": True,
            "is_staff": False,
            "is_superuser": False,
        },
    )
    if not created and (
        user.is_staff
        or user.is_superuser
        or not user.is_active
        or user.has_usable_password()
        or user.email != "reviewer@cernal.local"
    ):
        raise RegistrationError("The dedicated reviewer identity is unavailable.")
    if created:
        user.set_unusable_password()
        user.save(update_fields=["password"])
    return user


# --- API keys (ADR 0006) -----------------------------------------------------------

#: A fixed, greppable prefix — matched by GitHub secret scanning, GitGuardian and
#: trufflehog. A random-looking blob is invisible to all three.
_KEY_PREFIX = "cern_live_"

#: The whole point of SHA-256 over bcrypt/argon2 here: verification runs on *every*
#: request. A 190-bit secrets.token_urlsafe token is not guessable, so there is nothing
#: for a slow hash to defend — but a ~100ms bcrypt round on every poll is a real cost.
#: Lookup is by indexed `prefix`, comparison by `hmac.compare_digest` (timing-safe).


def issue_api_key(
    *,
    owner,
    label: str,
    scopes: tuple[str, ...] = (ApiKeyScope.READ, ApiKeyScope.DESIGN),
    expires_in_days: int | None = None,
    max_concurrent_runs: int = 2,
    rate_per_minute: int = 60,
) -> tuple[ApiKey, str]:
    """Mint a key. Returns ``(ApiKey, secret)`` — the ONLY time the secret exists.

    Session-authenticated callers only (docs/public-api.md §5): you cannot mint a key
    with a key, which keeps a leaked key from becoming a permanent foothold.
    """
    if not scopes:
        raise RegistrationError("Select at least one API-key scope.")
    for name, value, maximum in (
        ("expires_in_days", expires_in_days, 3650),
        ("max_concurrent_runs", max_concurrent_runs, 100),
        ("rate_per_minute", rate_per_minute, 10000),
    ):
        if value is not None and (type(value) is not int or not 1 <= value <= maximum):
            raise RegistrationError(f"{name} must be an integer between 1 and {maximum}.")
    unknown = set(scopes) - set(ApiKeyScope.values)
    if unknown:
        raise RegistrationError(f"Unknown scope(s): {', '.join(sorted(unknown))}.")

    expires_at = (
        timezone.now() + timezone.timedelta(days=expires_in_days)
        if expires_in_days is not None
        else None
    )
    for _attempt in range(10):
        secret = f"{_KEY_PREFIX}{secrets.token_urlsafe(24)}"
        try:
            with transaction.atomic():
                key = ApiKey.objects.create(
                    owner=owner,
                    label=label,
                    prefix=secret[:14],
                    key_hash=hashlib.sha256(secret.encode()).hexdigest(),
                    scopes=list(scopes),
                    expires_at=expires_at,
                    max_concurrent_runs=max_concurrent_runs,
                    rate_per_minute=rate_per_minute,
                )
        except IntegrityError:
            continue
        break
    else:
        raise RegistrationError("A unique API key could not be issued. Please retry.")
    logger.info("API key '%s' issued to %s (%s)", label, owner.username, key.prefix)
    return key, secret


def authenticate_api_key(secret: str) -> ApiKey | None:
    """Resolve a presented secret to its key, or ``None``. Never raises, never logs the
    secret.

    One code path for every failure reason (missing, malformed, unknown, revoked,
    expired, inactive owner) — the caller maps all of them to the same 401
    ``invalid_api_key``, deliberately (docs/public-api.md §10: telling a client *which*
    reason leaks which keys exist).
    """
    if not secret or not secret.startswith(_KEY_PREFIX):
        return None

    digest = hashlib.sha256(secret.encode()).hexdigest()
    key = ApiKey.objects.select_related("owner").filter(prefix=secret[:14]).first()
    if key is None or not hmac.compare_digest(key.key_hash, digest):
        return None
    if not key.is_active or not key.owner.is_active:
        return None
    return key


def revoke_api_key(key: ApiKey) -> bool:
    """Revoke a key. Idempotent: returns ``False`` if it was already revoked."""
    if key.revoked_at is not None:
        return False
    key.revoked_at = timezone.now()
    key.save(update_fields=["revoked_at"])
    logger.info("API key %s (%s) revoked", key.id, key.prefix)
    return True


def regenerate_api_key(key: ApiKey) -> tuple[ApiKey, str]:
    """Issue a fresh secret for an existing key, keeping its identity — label, scopes,
    quotas, `id` all unchanged. Returns ``(key, secret)``, the same as
    :func:`issue_api_key`: the secret exists only in this return value.

    The old secret stops authenticating the instant this returns — there is no overlap
    window, and a previously revoked key becomes active again (regenerating is the "I
    lost/leaked this, give me a working one back" action, not a second credential
    alongside the old one).
    """
    if key.expires_at is not None and key.expires_at <= timezone.now():
        raise RegistrationError("This key has expired. Create a new key with a new expiry.")
    for _attempt in range(10):
        secret = f"{_KEY_PREFIX}{secrets.token_urlsafe(24)}"
        key.prefix = secret[:14]
        key.key_hash = hashlib.sha256(secret.encode()).hexdigest()
        key.revoked_at = None
        try:
            with transaction.atomic():
                key.save(update_fields=["prefix", "key_hash", "revoked_at", "updated_at"])
        except IntegrityError:
            continue
        break
    else:
        key.refresh_from_db()
        raise RegistrationError("A unique API key could not be issued. Please retry.")
    logger.info("API key '%s' (%s) regenerated for %s", key.label, key.prefix, key.owner.username)
    return key, secret
