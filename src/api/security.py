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
from ninja.throttling import SimpleRateThrottle

from api.errors import ApiError
from apps.accounts.models import ApiKey
from apps.accounts.services import authenticate_api_key
from apps.analyses.models import AnalysisRun, RunStatus

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


class ApiKeyRateThrottle(SimpleRateThrottle):
    """Requests/minute, keyed by the API key's id — not the owning user's.

    ``UserRateThrottle`` would key on ``request.user``, which pools every key a user
    owns together: a shared CI key would then starve their laptop (docs/public-api.md
    §6). Each key configures its own ``rate_per_minute``, which the base class cannot
    express — it reads a fixed rate once at construction via ``get_rate()`` — so this
    reimplements ``allow_request`` to read the limit from ``request.api_key`` on every
    call instead. A session-authenticated request (no ``request.api_key``) is not this
    mechanism's concern and always passes.
    """

    scope = "api_key"

    def get_rate(self):
        # A per-instance default is meaningless here — the real limit is read fresh in
        # allow_request(). None keeps the base constructor's parse_rate(None) happy.
        return None

    def get_cache_key(self, request) -> str | None:
        api_key = getattr(request, "api_key", None)
        if api_key is None:
            return None
        return self.cache_format % {"scope": self.scope, "ident": api_key.id}

    def allow_request(self, request) -> bool:
        api_key = getattr(request, "api_key", None)
        if api_key is None:
            return True

        self.num_requests = api_key.rate_per_minute
        self.duration = 60
        self.key = self.get_cache_key(request)
        self.history = self.cache.get(self.key, [])
        self.now = self.timer()

        while self.history and self.history[-1] <= self.now - self.duration:
            self.history.pop()
        if len(self.history) >= self.num_requests:
            return self.throttle_failure()
        return self.throttle_success()


class TooManyActiveRuns(ApiError):
    status = 429
    code = "too_many_active_runs"


def enforce_concurrency_ceiling(request) -> None:
    """The load-bearing control, not the rate limit above (docs/public-api.md §6):
    ``Q_CLUSTER`` runs one worker with a one-hour timeout, so 60 accepted submissions in
    one minute is 60 hours of queue. A session-authenticated request is exempt — these
    go through the SPA's own UX, not a loop.

    Counts the *owner's* active runs, not just this key's: the ceiling protects the
    shared queue from the account as a whole, using whichever key's configured limit
    this request happens to carry.
    """
    api_key = getattr(request, "api_key", None)
    if api_key is None:
        return

    active = AnalysisRun.objects.filter(
        created_by=request.user, status__in=[RunStatus.QUEUED, RunStatus.RUNNING]
    ).count()
    if active >= api_key.max_concurrent_runs:
        raise TooManyActiveRuns(
            f"{active} run(s) already active; this key allows {api_key.max_concurrent_runs}.",
            headers={"Retry-After": "60"},
        )
