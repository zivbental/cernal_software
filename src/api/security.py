"""API-key authentication (ADR 0006).

A second credential on the ``/api/`` surface, tried before the session cookie: cheaper,
and it has no CSRF path. In django-ninja 1.6, CSRF is a property of ``APIKeyCookie.__init__
(csrf=True)`` — not of ``AuthBase`` and not of ``APIKeyHeader``. ``APIKeyHeader._get_key``
reads ``request.headers`` directly, so header-based key auth needs zero CSRF work and does
not weaken the SPA's CSRF protection by one bit (docs/public-api.md §2).
"""

from django.core.cache import cache
from django.utils import timezone
from ninja.security import APIKeyHeader

from api.errors import ApiError
from apps.accounts.models import ApiKey
from apps.accounts.services import authenticate_api_key

#: ``last_used_at`` is written at most this often per key, so a 3-second poll from a
#: script does not become a database write on every request — real cost under
#: Q_CLUSTER's workers: 1 / SQLite (docs/public-api.md §5).
_LAST_USED_THROTTLE_SECONDS = 300


class InvalidApiKey(ApiError):
    """One code for every reason a key fails: missing, malformed, unknown, revoked,
    expired, or its owner deactivated. Distinguishing them would let a client learn
    which keys exist — the same reasoning that makes a bad login one message and
    ownership failures 404 rather than 403 (docs/public-api.md §10)."""

    status = 401
    code = "invalid_api_key"


class InsufficientScope(ApiError):
    status = 403
    code = "insufficient_scope"


class ApiKeyAuth(APIKeyHeader):
    """Resolves ``X-API-Key`` to the key's owning user.

    Returns ``None`` — not an error — when no header is present at all, so the next
    auth mechanism in ``auth=[ApiKeyAuth(), django_auth]`` (the session cookie) gets a
    chance. A header that *is* present but does not resolve raises ``InvalidApiKey``
    instead of falling through silently: presenting a bad explicit credential should
    fail loudly, not be quietly ignored in favour of whatever cookie happens to be on
    the request.
    """

    param_name = "X-API-Key"

    def authenticate(self, request, key):
        if not key:
            return None

        api_key = authenticate_api_key(key)
        if api_key is None:
            raise InvalidApiKey("The API key is missing, unknown, revoked or expired.")

        request.user = api_key.owner  # a real User, so get_owned() needs no changes
        request.api_key = api_key  # scopes, quotas and throttling read this
        _touch_last_used(api_key)
        return api_key.owner


def _touch_last_used(api_key: ApiKey) -> None:
    cache_key = f"apikey-last-used:{api_key.id}"
    if cache.get(cache_key):
        return
    cache.set(cache_key, True, _LAST_USED_THROTTLE_SECONDS)
    ApiKey.objects.filter(pk=api_key.pk).update(last_used_at=timezone.now())


def require_scope(request, scope: str) -> None:
    """Enforce a scope on a write endpoint (docs/public-api.md §6).

    A session-authenticated request always has every scope — scoping is a key concept
    only. A key-authenticated request needs it explicitly; ``design`` implies ``read``
    (``ApiKey.has_scope``).
    """
    api_key = getattr(request, "api_key", None)
    if api_key is not None and not api_key.has_scope(scope):
        raise InsufficientScope(f"This key does not have the '{scope}' scope.")
