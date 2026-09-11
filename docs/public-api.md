# The public API — external integration

**Status:** Proposal. Nothing here is built.
**Question it answers:** iGEM's *"How well can the software be integrated with external
tools/software applications? (APIs, packages, etc.)"*
**Companion documents:** [`api.md`](api.md) is the reference for the API that exists
today; [`architecture.md §3`](architecture.md) is the boundary rule this must not break;
[`ROADMAP.md`](ROADMAP.md) is where the tasks in §14 belong once this is agreed.

> **This is a design document, not a planning file.** [ROADMAP.md](ROADMAP.md) is the
> single place work is recorded — "*Found new work? Add it here… Not in a separate
> document — that is how the previous fourteen planning files happened.*" §14 gives the
> rows to paste into it. This file holds the *rationale and the spec*; the ROADMAP holds
> the *work*.

---

## 1. The short answer

**You are not building an API layer. You already have one.** `src/api/` is 34
django-ninja endpoints with an auto-generated OpenAPI document at `/api/openapi.json`
and interactive docs at `/api/docs`. The whole scientific workflow — dataset, submit,
poll, candidates, metric decomposition, artifacts, CSV export — is built, tested and
running against `MockEngine` today.

What is missing is not the API. It is **five specific things** that stand between that
API and a scientist at an R prompt:

| # | Gap | Size |
|---|---|---|
| 1 | **No credential a script can hold.** Auth is a session cookie plus CSRF ([ADR 0003](decisions/0003-same-origin-spa-session-auth.md)) | M |
| 2 | **No fast path.** A design costs 4 round trips and forces the caller to invent a dataset | S |
| 3 | **No client packages.** Every user hand-rolls HTTP, JSON and a polling loop | M |
| 4 | **No budget or concurrency ceiling.** One script can fill a 1-worker queue for hours | S |
| 5 | **`params` is free-form and silently ignores typos** — the same failure class as [CLAUDE.md §2](../CLAUDE.md) | S |

**Is it overkill?** The three-language ask is the only part that risks it, and only if
built the wrong way. Verdict, per piece:

| Piece | Verdict | Why |
|---|---|---|
| API keys | **Do it.** ~1 day | [ADR 0003](decisions/0003-same-origin-spa-session-auth.md) already names this exact trigger: *"Revisit when a client that is not a browser on this origin needs to authenticate."* |
| One-call `POST /api/design` | **Do it.** ~½ day | The single biggest usability win. Turns 5 calls into 1 |
| Python client | **Do it.** ~250 lines | Where most users are, and `to_dataframe()` is a real value-add |
| R client | **Do it.** ~180 lines | R users will not hand-roll `httr2` + polling. Cheap, and high judging value |
| MATLAB client | **Do it, thinnest possible.** ~150 lines | `webwrite`/`webread` are built in; a `+cernal` package folder is the whole deliverable |
| Three full SDKs mirroring 34 endpoints | **Overkill. Do not.** | §12 |
| OAuth, GraphQL, gRPC, streaming, a separate public-API service | **Overkill. Do not.** | §12 |

**The lever that makes this a week and not a month:** all three clients wrap the *same
five HTTP calls*, not 34. The REST API stays the product; the packages are thin,
idiomatic sugar over `design · status · results · artifact · capabilities`. Anyone
needing more drops to REST, which is documented and self-describing.

Realistic total: **~5–6 working days**, splittable across four people (§14).

---

## 2. What already exists — read this before writing anything

The most expensive mistake available here is building a second, parallel API. These are
built and tested; call them.

| You need | It already exists | Where |
|---|---|---|
| An HTTP surface with generated OpenAPI | 34 endpoints, `/api/openapi.json`, `/api/docs` | [`src/api/`](../src/api/), [`docs/api.md`](api.md) |
| Submit a run, freeze its config, queue it | `submit_run(...) -> (run, created)` | [`apps/analyses/services.py:41`](../src/apps/analyses/services.py#L41) |
| Idempotent resubmission | `idempotency_key`, unique column, returns the existing run | same |
| Validate gate families / profiles against the engine | `_validate_against_capabilities` | [`apps/analyses/services.py:128`](../src/apps/analyses/services.py#L128) |
| Ownership scoping on every object | `get_owned`, `owned_queryset`, `_OWNER_PATHS` | [`src/api/auth.py:16`](../src/api/auth.py#L16) |
| One error envelope, 404-never-403 | `ApiError`, `envelope()` | [`src/api/errors.py`](../src/api/errors.py) |
| Capability advertisement without importing the engine | `EngineCapabilities`, `GET /api/version` | [`engine/contract.py:80`](../src/engine/contract.py#L80), [`api/routers/meta.py:28`](../src/api/routers/meta.py#L28) |
| Cooperative cancellation | `cancel_run`, `on_progress` returning `False` | [`apps/analyses/services.py`](../src/apps/analyses/services.py) |
| Rate limiting primitives | `ninja.throttling` — `BaseThrottle`, `SimpleRateThrottle`, `UserRateThrottle` | django-ninja 1.6.3, installed |
| API-key auth primitives | `ninja.security.APIKeyHeader` | same |
| Flat candidate × metric export | `GET /api/runs/{id}/export.csv` | [`api/routers/results.py`](../src/api/routers/results.py) |

**Verified, and it decides the whole design:** in django-ninja, CSRF is a property of
`APIKeyCookie.__init__(csrf=True)` — *not* of `AuthBase` and *not* of `APIKeyHeader`.
`APIKeyHeader._get_key` is three lines that read `request.headers`, with no CSRF path at
all. So **header-based key auth needs zero CSRF work**, and it does not weaken the SPA's
CSRF protection by one bit, because the two auth classes are independent objects.

---

## 3. The one architectural idea

> **One API, two credentials. Not a public API beside a private one.**

`django_auth` is set once, API-wide, at [`src/api/__init__.py:34`](../src/api/__init__.py#L34).
Change it to a list and every existing endpoint accepts either credential:

```python
# src/api/__init__.py
api = NinjaAPI(
    title="CERNAL API",
    version="1",
    auth=[ApiKeyAuth(), django_auth],  # key first: cheaper, and no CSRF path
    urls_namespace="api",
)
```

django-ninja tries each in order and uses the first that returns a principal. Because
`ApiKeyAuth.authenticate` returns **the key's owning `User`**, `request.user` is a real
user object — so `get_owned`, `owned_queryset` and every `_OWNER_PATHS` rule keep working
**unchanged**. No endpoint is rewritten. No permission logic is duplicated.

Three consequences worth stating out loud, because they are the selling points:

1. **Everything done through the API appears in the web UI**, owned by the same account,
   with the same candidates, artifacts and annotations. There is no second data model and
   no "API results" silo.
2. **The 34 existing endpoints become the advanced API for free.** §8's "fast path" is
   one *added* endpoint, not a replacement surface.
3. **The security review is small**, because the only new attack surface is
   *authentication*. Authorization, error shape, artifact serving and input validation
   are unchanged and already reviewed.

```
                    ┌── session cookie + CSRF ──►  the SPA (same origin)
   /api/…  ─────────┤
   34 endpoints     └── X-API-Key header ───────►  Python · R · MATLAB · curl · Galaxy · Snakemake
        │
        └──► get_owned(model, id, request.user)   ← unchanged, one code path
```

### The boundary rules this must not break

| Rule | Where | What it forbids here |
|---|---|---|
| `src/api/` and `src/apps/` may import **only** `engine.contract` and `engine.client` | [architecture.md §3](architecture.md) | The API must not build a `ScoringProfile`, must not import `engine.scoring`, must not touch `engine.gates`. §9.1 is designed around this |
| `src/engine/` must never import `django`, `apps`, `api`, `config` | same, machine-checked by [`tests/test_boundary.py`](../tests/test_boundary.py) | The engine must never learn what an API key is |
| Every status transition happens in `apps/analyses/services.py` | [architecture.md §6.2](architecture.md) | `POST /api/design` calls `submit_run`. It must not write `run.status` itself |
| 404, never 403, for objects you do not own | [architecture.md §7.2](architecture.md) | A valid key for the wrong user's run gets 404 |
| Responses never carry paths, tracebacks or settings | same | Includes anything a client library echoes back |

---

## 4. ADR 0006 — drop-in text

[ROADMAP §9](ROADMAP.md) requires a new ADR to revisit a settled decision. ADR 0003 is
settled; this extends rather than reverses it, and ADR 0003's own "Revisit when" clause is
the authority. Save as `docs/decisions/0006-api-keys-for-non-browser-clients.md`.

```markdown
# 0006 — API keys for non-browser clients

**Status:** Proposed
**Extends:** ADR 0003 (same-origin SPA, session cookies)

## Context

ADR 0003 chose session cookies and closed with: "Revisit when a client that is not a
browser on this origin needs to authenticate." That client now exists — Python, R and
MATLAB scripts run by researchers, and the iGEM integration requirement asks for exactly
this.

A session cookie cannot be held by a script: it requires a login round trip, a cookie
jar, and a CSRF token read from a second cookie and echoed in a header. Every scientific
HTTP client makes that awkward and MATLAB's `webwrite` makes it near-impossible.

## Decision

Add **long-lived API keys**, presented in an `X-API-Key` request header, as a *second*
credential on the *same* `/api/` surface. Session auth is unchanged and remains the
SPA's only mechanism.

A key belongs to exactly one user. Authenticating with it sets `request.user` to that
user, so all existing ownership checks apply without modification.

Keys are stored as SHA-256 digests. The secret is displayed once, at creation.

## Consequences

**Gained.** Scripts authenticate in one header. No CORS is needed, because these clients
are not browsers. No CSRF work is needed, because django-ninja attaches CSRF to
`APIKeyCookie`, not to `APIKeyHeader`. The SPA is untouched. Work submitted by a script
appears in the web UI, owned by the same account.

**Given up.** A second credential to revoke, expire and audit. A bearer secret that,
unlike an HttpOnly cookie, can be pasted into a notebook and committed to a repository —
mitigated by a `cern_live_` prefix that secret scanners recognise, single-display,
per-key revocation and expiry.

**Not chosen.** OAuth 2 / JWT: no third-party application needs delegated access, and
refresh-token handling in R and MATLAB would be the largest single piece of client code.
Reconsider only if a client must act *on behalf of* a user who is not its owner.

**Revisit when** a third party needs delegated access, or a browser-based tool on another
origin needs to call the API (that one needs CORS, not a new credential).
```

---

## 5. The key model

Lives in `apps/accounts/` — the app whose `User` is [deliberately empty
today](../src/apps/accounts/models.py) and whose `services.py` already owns registration.

```python
# src/apps/accounts/models.py


class ApiKey(UUIDModel, TimestampedModel):
    """A long-lived credential for a non-browser client (ADR 0006).

    The secret is never stored. Only its SHA-256 digest is, alongside a short public
    prefix used for lookup and display — so a key can be identified in a log or a UI
    without the log ever containing something that authenticates.
    """

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="api_keys"
    )
    label = models.CharField(max_length=100)  # "laptop", "snakemake-prod"
    prefix = models.CharField(max_length=16, db_index=True)  # "cern_live_7Kd2"
    key_hash = models.CharField(max_length=64, unique=True)  # sha256 hexdigest

    scopes = models.JSONField(default=list)  # ["read"] | ["read","design"]
    max_concurrent_runs = models.PositiveSmallIntegerField(default=2)
    rate_per_minute = models.PositiveSmallIntegerField(default=60)

    expires_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    @property
    def is_active(self) -> bool:
        now = timezone.now()
        return self.revoked_at is None and (self.expires_at is None or self.expires_at > now)
```

### Key format

```
cern_live_7Kd2mQ8vF3xR9wLbN4pT6yH1sJ0aZcVe
└───┬────┘└──────────────┬───────────────┘
  prefix          32 chars of base62 ≈ 190 bits from secrets.token_urlsafe
```

- `cern_live_` / `cern_test_` — a fixed, greppable prefix. GitHub, GitGuardian and
  `trufflehog` match on patterns like this; a random-looking blob is invisible to them.
- The first 4 secret characters join the prefix in the `prefix` column, so the UI and the
  logs can say *which* key without holding one that works.

### Why SHA-256 and not bcrypt/argon2

Deliberate, and reviewers always ask. Password hashes are slow because passwords are
low-entropy and guessable. A 190-bit random token is not guessable — there is nothing for
a slow hash to defend. What matters instead is that verification is **fast**, because it
runs on *every request*: a bcrypt round on each call would add ~100 ms to every poll. Look
the key up by `prefix` (indexed), then compare digests with `hmac.compare_digest`. This is
what GitHub, Stripe and AWS do with their tokens.

```python
# src/apps/accounts/services.py
def issue_api_key(*, owner, label, scopes=("read", "design"), expires_at=None):
    """Mint a key. Returns (ApiKey, secret) — the ONLY time the secret exists."""
    secret = f"cern_live_{secrets.token_urlsafe(24)}"
    key = ApiKey.objects.create(
        owner=owner,
        label=label,
        prefix=secret[:14],
        key_hash=hashlib.sha256(secret.encode()).hexdigest(),
        scopes=list(scopes),
        expires_at=expires_at,
    )
    return key, secret


def authenticate_api_key(secret: str) -> ApiKey | None:
    """Resolve a presented secret, or None. Never raises, never logs the secret."""
    if not secret or not secret.startswith(("cern_live_", "cern_test_")):
        return None
    digest = hashlib.sha256(secret.encode()).hexdigest()
    key = ApiKey.objects.select_related("owner").filter(prefix=secret[:14]).first()
    if key is None or not hmac.compare_digest(key.key_hash, digest):
        return None
    if not key.is_active or not key.owner.is_active:
        return None
    return key
```

### The authenticator

```python
# src/api/security.py
class ApiKeyAuth(APIKeyHeader):
    param_name = "X-API-Key"  # APIKeyHeader reads request.headers — no CSRF path

    def authenticate(self, request, key):
        api_key = authenticate_api_key(key or "")
        if api_key is None:
            return None
        request.api_key = api_key  # scopes, quotas and throttling read this
        _touch_last_used(api_key)  # throttled write, see below
        return api_key.owner  # ← a real User, so get_owned() is unchanged
```

`last_used_at` is written **at most once per 5 minutes per key**, guarded by the cache.
Writing it on every request turns a cheap 3-second poll into a database write on a SQLite
deployment with `workers: 1` ([ADR 0002](decisions/0002-sqlite-and-orm-task-queue.md)).

### Management endpoints

Session-authenticated only — you cannot mint a key with a key. That keeps a leaked key
from becoming a permanent foothold.

| Endpoint | Auth | Notes |
|---|---|---|
| `GET /api/auth/keys` | session | Yours. Label, prefix, scopes, `last_used_at`, expiry. **Never the secret** |
| `POST /api/auth/keys` | session | `{label, scopes, expires_in_days}` → **201, the only response containing `secret`** |
| `DELETE /api/auth/keys/{id}` | session | Revoke. Idempotent, 204 |
| `GET /api/auth/whoami` | **key** | Confirms a key works: user, scopes, quota, expiry. The first call every client makes |

Plus a Django admin registration and two `./do` commands mirroring `./do approve`:
`./do key <username> <label>` and `./do keys <username>`.

---

## 6. Scopes, quotas and rate limits

Deliberately small. Two scopes, because there are exactly two risk levels:

| Scope | Grants | For |
|---|---|---|
| `read` | Every `GET`. Projects, runs, candidates, artifacts, exports | Dashboards, a shared analysis notebook, CI that checks results |
| `design` | `POST /api/design`, run submission, cancellation, annotations | Anything that consumes compute |

`design` implies `read`. There is no `admin` scope and no `delete` scope — destructive
operations stay session-only, in the web UI, where a human is present.

### The quota that actually matters

`Q_CLUSTER` runs **one worker** with a **one-hour timeout**
([`settings/base.py:121`](../src/config/settings/base.py#L121)). A single script looping
`POST /api/design` can therefore park the lab's entire compute queue for hours, and the
team's own runs from the web UI sit behind it. Rate-limiting requests per minute does
**not** fix this — 60 accepted submissions in one minute is 60 hours of queue.

> **`max_concurrent_runs` per key is the load-bearing control, not the rate limit.**
> Enforce it at submission: count the key owner's runs in `QUEUED` or `RUNNING`, and
> return **429** with `Retry-After` when the ceiling is hit. Default 2.

```python
active = AnalysisRun.objects.filter(
    created_by=request.user, status__in=[RunStatus.QUEUED, RunStatus.RUNNING]
).count()
if active >= request.api_key.max_concurrent_runs:
    raise TooManyRequests(
        f"{active} runs already active; this key allows {request.api_key.max_concurrent_runs}.",
        retry_after=60,
    )
```

### Rate limits

`ninja.throttling` ships `SimpleRateThrottle`; subclass it so the cache key is the **key
id**, not the user id — otherwise `UserRateThrottle` pools every key a user owns together
and a shared CI key starves their laptop.

| Limit | Value | Applies to |
|---|---|---|
| Requests / minute / key | 60 (configurable per key) | Everything |
| Concurrent `QUEUED`+`RUNNING` runs / key | 2 | `POST /api/design`, `POST …/runs` |
| Designs per run | `budget.max_designs`, default 100 000 | §9.3 |
| Inline DGE table | `MAX_DATASET_MB` (100 MB), reusing the existing cap | §8 |

**One deployment note.** No `CACHES` is configured, so Django defaults to
`LocMemCache` — per-process, which means throttle counters split across gunicorn workers
and the true limit is `rate × workers`. Add `django.core.cache.backends.db.DatabaseCache`
with `manage.py createcachetable`: it is one table in the SQLite database that is already
the queue broker, and it needs no Redis, consistent with ADR 0002.

---

## 7. The extension `EngineCapabilities` needs

One contract change is required, and it is the same pattern §3 already established for
gate families.

The API must validate a caller's custom scoring weights (§9.1) and report what the nine
metrics *mean* — but [architecture.md §3](architecture.md) forbids `api/` importing
`engine.scoring`. Today `EngineCapabilities` advertises profile **names** only
([`contract.py:92`](../src/engine/contract.py#L92)), which is not enough to validate a
metric name or to document a unit.

```python
# src/engine/contract.py — additive, both fields defaulted


@dataclass(frozen=True, slots=True)
class MetricInfo:
    """One metric in a scoring profile, as the engine describes it.

    Mirrors MetricSpec, minus anything the Platform has no business knowing. Advertised
    so the API can reject an unknown metric name at submit time — the same reason
    GateFamilyInfo exists.
    """

    name: str
    direction: str  # HIGHER_BETTER | LOWER_BETTER
    weight: float
    valid_range: tuple[float, float]
    unit: str = ""  # "kcal/mol" · "percent 0-100" · "log2 fold" · "linear fold"
    description: str = ""


@dataclass(frozen=True, slots=True)
class EngineCapabilities:
    ...
    metrics: list[MetricInfo] = field(default_factory=list)
    hard_filters: list[dict] = field(default_factory=list)
```

Populated in `_installed_capabilities` from `DEFAULT_V1`, which already carries every
field except `unit`. **`unit` is worth adding for its own sake**: it is the one piece of
metadata that would have prevented [CLAUDE.md §6](../CLAUDE.md)'s documented traps —
`dynamic_range` being linear while `state_separation` directly above it is log2, and
`gc_content` being 0–100 while every neighbouring probability is 0–1.

Additive with defaults, so `SCHEMA_VERSION` stays `"1"` and no stored result is
invalidated. `GET /api/version` gains a `metrics` array and becomes self-documenting.

---

## 8. The fast path — one call

> **The design target: a scientist with a sequence gets ranked designs in four lines of
> R, having read nothing.**

```http
POST /api/design
X-API-Key: cern_live_7Kd2…
Content-Type: application/json

{"trigger_sequence": "AUGGCUAAGCUUAACGGAUCCAUGGCUAAGCUUAAC", "organism": "ecoli"}
```

```jsonc
// 202 Accepted
{
  "job_id": "6f1c…", "status": "QUEUED", "progress_pct": 0,
  "poll_url":    "/api/design/6f1c…",
  "results_url": "/api/design/6f1c…/results",
  "web_url":     "/runs/6f1c…",              // the same run in the SPA
  "estimate": {"designs": 240, "seconds": 4},
  "resolved": {                               // every default made explicit
    "input_mode": "direct", "gate_families": ["toehold"],
    "scoring_profile": "default-v1", "seed": null,
    "constraints": {"max_triggers": 2, "min_separation": 0.5, "max_p_adj": 0.05,
                    "trigger_lengths": [30, 36], "max_switch_length": 200,
                    "standard": "RFC10"}
  }
}
```

**`resolved` is not decoration.** It echoes every default the server chose, so a run is
reproducible from its response alone and a caller can diff two runs' configurations
without reading this document. It is the API-level equivalent of `params_snapshot`.

### What the endpoint does

Everything the SPA wizard does, in one transaction, using services that already exist:

1. **Resolve the input.** `trigger_sequence` → `direct`. `dataset_id` → `de`. Inline
   `dge_csv` → `create_dataset(...)` first, then `de`. Supplying two, or neither, is a
   422 that names the conflict.
2. **Resolve defaults** from `GET /api/version`, never from a hardcoded list — so a newly
   available gate family is picked up with no API change.
3. **Enforce the concurrency ceiling** (§6).
4. **Call `submit_run(...)`** — the existing service, unchanged. Status transitions stay
   where [architecture.md §6.2](architecture.md) puts them. `organism` is stored
   directly on the run — there is no project to resolve or create.
5. **Return 202**, or block if `wait` is set.

### `wait` — the "fast and dirty" mode

```http
POST /api/design?wait=120
```

Blocks up to 120 s (hard ceiling **300 s**) and returns the finished result inline —
`200` with candidates instead of `202` with a handle. On timeout it returns `202` and the
same handle, so **the client code path is identical either way**:

```python
r = post(...)  # 200 or 202, the client does not care
job = Job.from_response(r)  # holds results, or knows how to poll for them
df = job.wait().to_dataframe()  # returns immediately if already resolved
```

> **Be honest about `wait` in the docs.** [ROADMAP §3](ROADMAP.md) measures ~15 ms per
> design on one core: 12 000 designs ≈ 1 minute, but 13 M designs ≈ 55 hours. `wait` is
> for `direct` runs and small `de` runs. It must **never** be the documented default, and
> the ceiling must be below any reverse-proxy timeout — Caddy's default write timeout
> would otherwise cut the connection and leave the caller thinking the run failed when it
> is running fine.

### The five endpoints a client needs

| Endpoint | Purpose |
|---|---|
| `POST /api/design` | Submit. `?wait=` optional. `?dry_run=true` estimates without running |
| `GET /api/design/{id}` | Status. Thin alias of the existing polling endpoint |
| `GET /api/design/{id}/results` | Ranked candidates with metric decomposition, `?format=json\|csv` |
| `GET /api/artifacts/{id}/download` | **Exists already.** Unchanged |
| `GET /api/version` | Capabilities: gate families, profiles, metrics, units |

Only the first three are new, and they are thin wrappers over `submit_run`,
`get_run_status` and `list_candidates`.

---

## 9. The controlled path — every argument

The same endpoint, fully specified. **Nothing here is invented**: every field maps to a
real record. `constraints` is [`domain.Constraints`](../src/engine/domain.py#L287) field
for field; `organism` is `domain.Host`; `payload.outputs` is `domain.DesiredOutcome`;
`gate_families` is validated against the registry.

```jsonc
POST /api/design
{
  // ─── input (exactly one) ────────────────────────────────────────────────
  "trigger_sequence": "AUGGCU…",       // → input_mode "direct"
  "dataset_id":       "…",             // → input_mode "de"
  "dge_csv":          "gene_id,log2fc,p_adj\n…",   // inline, ≤ MAX_DATASET_MB

  // ─── biology ────────────────────────────────────────────────────────────
  "organism": "ecoli",                 // domain.Host
  "payload":  {"outputs": ["gfp", "ampr"], "custom_sequence": null},

  // ─── which chemistries may be used ──────────────────────────────────────
  "gate_families": ["toehold"],        // subset of GET /api/version → available
  "exclude_gate_families": ["crispr"], // alternative phrasing: allow all but these

  // ─── search constraints — domain.Constraints, field for field ───────────
  "constraints": {
    "max_triggers":      2,            // circuit arity ceiling
    "min_separation":    1.0,          // min |log2 fold change| for a usable gene
    "max_p_adj":         0.01,         // significance threshold
    "trigger_lengths":   [30, 36],     // window sizes to scan, nt
    "max_switch_length": 200,          // synthesis ceiling, nt
    "forbidden_motifs":  ["GGTCTC", "GAATTC"],
    "standard":          "RFC10"       // RFC10 | RFC1000 → which sites are banned
  },

  // ─── how candidates are compared (§9.1) ─────────────────────────────────
  "scoring": {
    "base": "default",
    "weights":      {"predicted_leakage": 4.0, "gc_content": 0.0},
    "hard_filters": [{"metric": "dynamic_range", "minimum": 10.0}],
    "tie_breakers": ["dynamic_range", "predicted_leakage"]
  },

  // ─── cost ceiling (§9.3) ────────────────────────────────────────────────
  "budget": {"max_designs": 50000, "max_runtime_seconds": 1800,
             "on_exceed": "return_best"},   // return_best | fail

  // ─── output shaping ─────────────────────────────────────────────────────
  "top_n": 25,
  "include_rejected": true,            // rejected candidates carry their reason
  "include_metrics": true,
  "include_artifacts": ["fasta", "structure_svg"],

  // ─── reproducibility & control ──────────────────────────────────────────
  "seed": 42,
  "idempotency_key": "study-A-run-003",
  "strict": true,                      // §9.2 — unknown keys are an error
  "callback_url": "https://lab.example.org/hooks/cernal",   // §9.4, optional
  "notes": "sweep 3 of 5"
}
```

### 9.1 Custom scoring — the standout feature, and the one with a trap

Letting a caller re-weight the nine metrics is the most scientifically interesting thing
this API can offer: *"rank these by leakage, I do not care about GC."* It is also the
fastest way to make every stored score uninterpretable, so it needs four rules.

| Rule | Why |
|---|---|
| **Only the nine names in `DEFAULT_V1` are accepted.** An unknown name → **422** listing all nine | [CLAUDE.md §2](../CLAUDE.md): `spec()` returns `None` for an unknown name and `build_metrics`/`weighted_score`/`failed_filter` all skip it *silently*. Sending `leakage` for `predicted_leakage` is a triple silent failure. **The API's job is to turn that silence into a 422.** This alone justifies §7 |
| **`weights`, `hard_filters` and `tie_breakers` are overridable. `direction` and `valid_range` are not** | Direction and range are physics and units, not preference. A caller who could widen `valid_range` could make their own numbers look better and quietly break comparability with every other run |
| **The derived profile gets a deterministic label**, `custom-<sha256(canonical_json)[:8]>`, recorded in `params_snapshot`, echoed on every candidate and returned in `resolved` | Design map 12: a score must stay interpretable after the fact. Two runs with identical weights get the same label, so they are comparable — and visibly so |
| **The engine builds the profile, not the API** | [architecture.md §3](architecture.md). The API validates *names* against advertised `EngineCapabilities.metrics` (§7) and passes the block through as `params["scoring"]`. `engine.scoring.profiles` constructs and `validate()`s it |

`"weights": {"gc_content": 0.0}` is the clean way to say *ignore this metric*: weight zero
rather than a deleted spec, so the raw value is still measured, still reported, and still
visible in the decomposition — it just stops moving the rank.

### 9.2 `strict` — turning silent typos into errors

`params` is free-form by contract, and that is right for the SPA: the wizard adds a field
without an engine release. For a script it is a hazard of exactly the kind this repo
documents everywhere else — a scientist who writes `max_trigger` instead of
`max_triggers` silently gets the default 2 and never learns.

> **`strict` defaults to `true` on `POST /api/design`, and stays `false` on the existing
> `POST /api/runs`.** New surface, safe default; old surface, unchanged behaviour and no
> SPA regression.

```jsonc
// 422
{"error": {"code": "unknown_parameter",
           "message": "Unknown constraint 'max_trigger'.",
           "detail": {"did_you_mean": "max_triggers",
                      "allowed": ["max_triggers", "min_separation", "max_p_adj",
                                  "trigger_lengths", "max_switch_length",
                                  "forbidden_motifs", "standard"]}}}
```

`difflib.get_close_matches` gives `did_you_mean` in one line and it is the difference
between a good API and a merely correct one.

### 9.3 `dry_run` and `budget` — because the search space is unbounded

[ROADMAP §3](ROADMAP.md) is blunt: top-50 genes in pairs is 12 000 designs and about a
minute; top-200 in triples is 13 M designs and ~55 hours. **A public API with no ceiling
is a denial-of-service you serve to yourself.**

```http
POST /api/design?dry_run=true
```

Returns **200 immediately**, queues nothing:

```jsonc
{"estimate": {"genes_surviving": 187, "trigger_candidates": 4210,
              "trigger_sets": 1225, "designs": 12250,
              "seconds_1_core": 184, "confidence": "rough"},
 "budget_ok": true,
 "resolved": {…}}
```

Two honest notes for whoever builds it. The arithmetic is `designs × 15 ms`, from
[ROADMAP §3](ROADMAP.md)'s measured ViennaRNA throughput — label it `"rough"` and never
present it as a guarantee. And under `de` mode a real estimate needs gene counts from the
dataset, so before the engine's stage 1 exists it can only be bounded from the table's row
count; say so in the response rather than inventing precision.

`budget` then enforces it. `max_runtime_seconds` rides the mechanism that already exists:
`on_progress` returns `False` and the pipeline raises `JobCancelled`, exactly as
cancellation does. `on_exceed: "return_best"` finishes with what has been evaluated and a
warning in `JobResult.warnings`; `"fail"` returns a failed run. **This is engine-side
work** (§14, X6) — the API-side cap is available immediately, the engine-side one lands
with the pipeline.

### 9.4 Webhooks — optional, and a genuine security decision

`callback_url` POSTs the terminal status once. Convenient for Snakemake and Nextflow,
which would otherwise hold a polling loop open for an hour.

It is also **server-side request forgery on a plate**, so if it is built:

- **https only.** Reject `http`, `file`, `gopher` and anything else.
- **Resolve the hostname and reject private ranges** — `127/8`, `10/8`, `172.16/12`,
  `192.168/16`, `169.254/16` (cloud metadata), `::1`, ULA. Re-check *after* DNS
  resolution, not just on the literal string, or DNS rebinding walks straight past it.
- **Never follow redirects.** A 302 to `169.254.169.254` is the whole attack.
- **Sign it**: `X-CERNAL-Signature: sha256=<hmac(key_secret_digest, body)>` so the
  receiver can verify origin.
- **3 attempts, exponential backoff, 5 s timeout, then give up.** Polling remains the
  contract; the webhook is an optimisation.

Given ~5 analyses/day, **polling is genuinely fine**. This belongs in phase 2, and the doc
should say so rather than shipping a half-guarded SSRF.

---

## 10. Errors, versioning and the compatibility promise

Errors keep the existing envelope, unchanged, with four new codes:

| Status | `code` | When |
|---|---|---|
| 401 | `invalid_api_key` | Missing, malformed, unknown, revoked or expired key |
| 403 | `insufficient_scope` | A `read`-scoped key attempted `POST /api/design` |
| 422 | `unknown_parameter` | `strict` mode, with `did_you_mean` |
| 429 | `rate_limited` · `too_many_active_runs` | With `Retry-After` |

401 says **`invalid_api_key`** for every one of missing, unknown, revoked and expired. A
client that learns *"this key was revoked"* versus *"no such key"* learns which keys exist
— the same reasoning that makes login return one message for a bad username and a bad
password ([`api/routers/auth.py`](../src/api/routers/auth.py)), and that makes ownership
failures 404 rather than 403.

### Versioning — do nothing, deliberately

The API already reports `api_schema_version: "1"` at `GET /api/version`. Do **not** add a
`/api/v1/` prefix now: it doubles the URL surface, and django-ninja's own answer to a
breaking change is a second `NinjaAPI(version="2", urls_namespace="api2")` mounted
alongside, which costs nothing until it is needed.

What external consumers actually need is a written promise, so put this in
[`api.md`](api.md):

> **Within `api_schema_version: "1"`, changes are additive only.** New optional request
> fields and new response fields may appear. An existing field will not be removed,
> renamed, or change type or units. A breaking change means a new
> `api_schema_version` and a `/api/v2/` mount, with `"1"` supported for at least the
> remainder of the competition season.
>
> **Clients must ignore unknown response fields.** All three reference clients do.

That last line is load-bearing: it is what lets you add `MetricInfo.unit` (§7) without
breaking someone's R script mid-season.

---

## 11. The three clients

**The design rule that keeps this from being overkill:** every client wraps the same five
calls and is a thin, idiomatic layer — not a generated mirror of 34 endpoints. Anyone
needing more uses REST directly against a documented, self-describing API.

Each client does exactly six things: hold a key, POST a design, poll with backoff,
return a data frame / table, download an artifact, raise a *readable* error.

### Layout

```
clients/
  python/   pyproject.toml · cernal/{__init__,client,job,errors}.py · tests/
  r/        DESCRIPTION · NAMESPACE · R/{client,design,results}.R · tests/
  matlab/   +cernal/{Client.m,Job.m,private/request.m} · README.md
  fixtures/ design_request.json · expected_columns.json    ← shared, §11.4
```

In-repo, not in three separate repositories. One PR changes the API and all three
clients, and the conformance test (§11.4) fails if one drifts.

### 11.1 Python — `pip install cernal`

```python
import os
from cernal import Client

c = Client(api_key=os.environ["CERNAL_API_KEY"])  # base_url defaults to the public host

# fast and dirty
job = c.design(trigger_sequence="AUGGCUAAGCUUAACGGAUCC", organism="ecoli")
df = job.wait().to_dataframe()  # blocks, polls with backoff
print(df.head())

# constrained
job = c.design(
    dge_csv=open("deseq2.csv").read(),
    organism="ecoli",
    gate_families=["toehold"],
    constraints=dict(
        max_triggers=2,
        min_separation=1.0,
        max_p_adj=0.01,
        trigger_lengths=[30, 36],
        standard="RFC10",
    ),
    scoring=dict(
        weights={"predicted_leakage": 4.0, "gc_content": 0.0},
        hard_filters=[{"metric": "dynamic_range", "minimum": 10.0}],
    ),
    budget=dict(max_designs=50_000, max_runtime_seconds=1800),
    seed=42,
    top_n=25,
)
print(job.estimate)  # from the 202, before waiting
best = job.wait().best()  # highest-ranked CandidateResult
job.artifact("fasta").save("best.fa")
```

- `requests` only. **pandas is optional** — `to_dataframe()` raises a message telling you
  to `pip install cernal[pandas]`, and `.to_dicts()` always works. A hard pandas
  dependency on a client library is a bad neighbour in a conda environment.
- `Job.wait()` polls at 2 s, backing off to 15 s, with an overall timeout.
- Errors map to exception classes — `AuthError`, `ValidationError` (carrying
  `did_you_mean`), `RateLimited` (carrying `retry_after`), `RunFailed` (carrying
  `error_summary`).
- `Client(dry_run=True)` returns estimates for every call — a whole parameter sweep can be
  costed before a single design is queued.
- ~250 lines.

### 11.2 R — `remotes::install_github("…", subdir = "clients/r")`

```r
library(cernal)

cl  <- cernal_client(Sys.getenv("CERNAL_API_KEY"))

job <- cernal_design(cl, trigger_sequence = "AUGGCUAAGCUUAACGGAUCC", organism = "ecoli")
df  <- cernal_results(cernal_wait(job))
head(df)

job <- cernal_design(
  cl,
  dge_csv       = readr::read_file("deseq2.csv"),
  organism      = "ecoli",
  gate_families = "toehold",
  constraints   = list(max_triggers = 2L, min_separation = 1.0, max_p_adj = 0.01),
  scoring       = list(weights = list(predicted_leakage = 4.0)),
  seed          = 42L
)
df <- cernal_results(cernal_wait(job))
```

- `httr2` + `jsonlite` + `tibble`. No Bioconductor dependency.
- Returns a **tibble**, one row per candidate, metrics as columns — which is what makes
  it worth writing at all: the output drops straight into `dplyr` and `ggplot2`.
- The natural next step is `DESeq2::results()` → `as.data.frame()` → `cernal_design()`,
  which is a genuinely compelling demo: **DESeq2 output to plasmid design in one script**,
  and precisely the "integrates with external tools" evidence iGEM asks for.
- Scalar coercion is the one real trap: R has no scalars, so `jsonlite::toJSON` turns
  `max_triggers = 2` into `[2]`. Use `auto_unbox = TRUE` and test it — this is the bug
  every hand-written R client ships with.
- ~180 lines.

### 11.3 MATLAB — a `+cernal` package folder

```matlab
addpath('/path/to/cernal/clients/matlab');

c   = cernal.Client(getenv('CERNAL_API_KEY'));

job = c.design('trigger_sequence', 'AUGGCUAAGCUUAACGGAUCC', 'organism', 'ecoli');
T   = job.wait().results();          % a MATLAB table
head(T)

job = c.design('dge_csv', fileread('deseq2.csv'), ...
               'organism', 'ecoli', ...
               'gate_families', {'toehold'}, ...
               'constraints', struct('max_triggers', 2, 'min_separation', 1.0), ...
               'seed', 42);
T = job.wait().results();
writetable(T, 'candidates.csv');
```

- `webwrite` / `webread` / `weboptions` — **built into base MATLAB**, no toolbox required.
  That constraint is the point: a client needing the Bioinformatics Toolbox is a client
  half the users cannot run.
- Name–value pairs, because that is how MATLAB reads; `struct` for nested blocks.
- Returns a `table`, so `writetable`, `sortrows` and `groupsummary` work immediately.
- Ship the folder, plus an optional `.mltbx` for one-click install. There is no package
  manager worth targeting; `addpath` is the idiom.
- `jsondecode` maps JSON objects to structs and **silently mangles field names that are
  not valid MATLAB identifiers**. The nine metric names are all safe — but assert that in
  the conformance test rather than discovering it on stage.
- ~150 lines.

### 11.4 The conformance test — what keeps three clients honest

Three clients drift. One fixture stops that:

```
clients/fixtures/design_request.json     # one canonical request, seed fixed
clients/fixtures/expected_columns.json   # the exact result columns, in order
```

Each client ships a test that submits the fixture against a `MockEngine` server and
asserts identical columns and identical values. `MockEngine` is deterministic and needs no
scientific dependencies, which is exactly why [ROADMAP P7](ROADMAP.md) keeps it as CI's
engine.

| Client | CI | Note |
|---|---|---|
| Python | **Every push.** Add to `.gitlab-ci.yml` beside the existing jobs | Free |
| R | **Every push**, `rocker/r-ver` image | ~2 min |
| MATLAB | **Manual, before a release.** Document the command | A licence in CI is not worth it for an iGEM team — say so plainly rather than pretending |

Add a fourth "client" that costs nothing: a **`curl` recipe** in `docs/api.md`. It is what
someone reaches for at 2 a.m., and it is the only one that never breaks.

---

## 12. What NOT to build

This section exists because the request said *"impressive"*, and the tempting things are
the wrong things.

| Do not build | Because |
|---|---|
| **Three SDKs mirroring all 34 endpoints** | ~2 000 lines to maintain in three languages for endpoints nobody calls from a script. Five functions each covers >95 % of use |
| **Generated clients (`openapi-generator`)** | The Python output is large and unidiomatic; the R and MATLAB generators are weak or absent. Generation wins at 200 endpoints, not at 5. Publish the OpenAPI doc so *others* can generate — that is the integration story, and it is free |
| **OAuth 2 / JWT** | Nothing needs delegated access. Refresh-token handling would be the single largest piece of R and MATLAB client code, for zero gain |
| **GraphQL or gRPC** | The result shape is fixed and small; there is no over-fetching problem to solve, and neither has a usable MATLAB story |
| **WebSockets / SSE progress streaming** | The run state machine already polls at 3 s ([architecture.md §7.1](architecture.md)) and runs take minutes. Streaming adds ASGI to a WSGI deployment for a nicer progress bar |
| **A separate public-API service** | Two surfaces means two authorization implementations, and the second one is where the bug lives. §3 |
| **CORS (`django-cors-headers`)** | Python, R and MATLAB are not browsers and do not send `Origin`. Add it the day a browser-based tool needs it, not before |
| **A `/api/v1/` prefix today** | §10. Cost now, no benefit until a breaking change exists |
| **Per-endpoint scope granularity** | Two scopes cover the two real risk levels. Ten scopes are ten things to get wrong |
| **Async/await in the Python client** | The workload is one submit and a slow poll. `requests` keeps the dependency tree flat |

---

## 13. Security review

New attack surface is **authentication only** — authorization, error shape, artifact
serving and upload limits are unchanged and already reviewed
([architecture.md §7.2](architecture.md)).

| Concern | Mitigation |
|---|---|
| Key leaked in a notebook or commit | `cern_live_` prefix is matched by GitHub secret scanning, GitGuardian and trufflehog. Single display. Per-key revoke. Optional expiry |
| Key in a URL query string | **Header only.** Query strings land in access logs, proxy logs and `Referer` headers. Reject a key presented any other way |
| Key in application logs | Log `key.prefix` (`cern_live_7Kd2`), never the secret. Add the field name to the logging filter |
| Timing attack on comparison | `hmac.compare_digest`; look up by indexed `prefix`, never by scanning |
| Key enumeration via error messages | One 401 code, `invalid_api_key`, for missing / unknown / revoked / expired |
| A key reading another user's data | Impossible without new code: `authenticate` returns the owning `User` and every endpoint already runs `get_owned` (§3). **Test it explicitly anyway** — key A, run owned by B, expect 404 |
| Queue exhaustion | `max_concurrent_runs` per key (§6). This is the real one, given `workers: 1` |
| Compute exhaustion in a single run | `budget.max_designs`, `budget.max_runtime_seconds` (§9.3) |
| Inline `dge_csv` as a memory bomb | Same `MAX_DATASET_MB` cap and the same `create_dataset` validation as the multipart path. No second code path |
| SSRF via `callback_url` | §9.4. If it cannot be guarded properly, **do not ship it** — polling is sufficient |
| Escalation from a leaked key | Key auth cannot mint keys, cannot delete projects or datasets, cannot change a password. Those stay session-only |

**Run `/security-review` on the branch before merging**, and add the
key-crosses-owner test to [`tests/api/test_auth_and_errors.py`](../tests/api/test_auth_and_errors.py),
which already covers the 404-not-403 rule.

---

## 14. The work — rows for ROADMAP.md

Paste into [ROADMAP.md](ROADMAP.md) as **"Phase X — External integration"**, in the format
§4 already uses. Sizes match that table's scale (S ≈ half a day, M ≈ 1–2 days).

| # | Task | Where | Size | Blocked on |
|---|---|---|---|---|
| **X1** | **ADR 0006 + `ApiKey` model, migration, `issue_api_key`/`authenticate_api_key`, admin, `./do key`** | `docs/decisions/`, `apps/accounts/` | M | — |
| **X2** | **`ApiKeyAuth`; `auth=[ApiKeyAuth(), django_auth]`; key management endpoints; `GET /api/auth/whoami`** | `api/security.py`, `api/__init__.py`, `api/routers/auth.py` | M | X1 |
| **X3** | **Scopes, per-key throttle, `max_concurrent_runs`, `DatabaseCache`** | `api/security.py`, `apps/analyses/services.py`, `config/settings/base.py` | S | X2 |
| **X4** | **`MetricInfo` on `EngineCapabilities`; `unit` on every metric; surface at `GET /api/version`** | `engine/contract.py`, `engine/client.py`, `engine/scoring/profiles.py`, `api/routers/meta.py` | S | — |
| **X5** | **`POST /api/design` + `GET /api/design/{id}[/results]`: defaults, auto-project, inline `dge_csv`, `resolved`, `wait`, `strict`, `top_n`** | `api/routers/design.py`, `apps/analyses/services.py` | M | X2, X4 |
| **X6** | **`budget` + `dry_run` estimate.** API-side cap now; engine-side enforcement via `on_progress`/`JobCancelled` with E-phase | `api/routers/design.py`, `engine/pipeline.py` | M | X5; engine half blocked on E2 |
| **X7** | **Custom scoring profile** — validate names against X4, deterministic `custom-<hash>` label, engine-side construction | `api/schemas.py`, `engine/scoring/profiles.py` | M | X4, X5 |
| **X8** | **Python client + PyPI + conformance test in CI** | `clients/python/`, `.gitlab-ci.yml` | M | X5 |
| **X9** | **R client + conformance test in CI** | `clients/r/`, `.gitlab-ci.yml` | M | X5 |
| **X10** | **MATLAB client + manual conformance run** | `clients/matlab/` | S | X5 |
| **X11** | **Docs: `api.md` key section, compatibility promise, three quickstarts, `curl` recipe** | `docs/api.md`, `docs/public-api.md` | S | X8–X10 |
| **X12** | *(optional, phase 2)* **Webhooks with full SSRF guarding** | `apps/analyses/services.py` | M | X5 |

### Suggested order and parallelism

```
X1 ─► X2 ─► X3
       │
       ├─► X5 ─┬─► X6      X4 ─┴─► X7
       │       ├─► X8 ─┐
       │       ├─► X9 ─┼─► X11
       │       └─► X10─┘
       └─► (X12, only if there is time)
```

**X4 has no blockers and is the smallest useful thing here** — it can start today, it
improves `GET /api/version` on its own, and it is what makes X7 legal under the boundary
rule. Start there.

X8, X9 and X10 are genuinely independent once X5 lands: three people, three languages,
one shared fixture. That is the parallelism that makes the whole plan fit in a week.

**Minimum viable, if time runs short:** X1 + X2 + X5 + X8 + X11. That is API keys, the
one-call endpoint, the Python client and the documentation — a complete, honest
integration story. X9 and X10 are what turn it into a *strong* one, and neither is more
than a day.

---

## 15. What this is worth to the iGEM requirement

The criterion is *"How well can the software be integrated with external tools/software
applications? (APIs, packages, etc.)"* Judges look for evidence, not claims. What this
plan produces, and where to point:

| Evidence | Where it comes from |
|---|---|
| A public, documented REST API | Already built. `/api/docs`, [`docs/api.md`](api.md) |
| A machine-readable spec anyone can generate a client from | Already built. `/api/openapi.json` — **link it directly on the wiki** |
| Installable packages in three scientific languages | X8, X9, X10 |
| A real interoperability demo | **DESeq2 → `cernal_design()` → ranked plasmid designs, in one R script.** The single most persuasive artefact here, and it costs one page |
| Reproducibility | `seed`, `idempotency_key`, `resolved`, and the profile label recorded on every run |
| Pipeline-friendliness | `dry_run` costing, `budget` ceilings, `--format csv`, artifact download by URL. A Snakemake/Nextflow rule is ~10 lines — **write one** |
| Honest limits | Rate limits, quotas, the compatibility promise, and a documented statement of what `wait` is *not* for |

Two things worth doing that are not code:

- **A sandbox key.** A public, `read`-scoped, rate-limited key against a `MockEngine`
  deployment, printed in the documentation. A judge who can paste one `curl` and get a
  ranked candidate back has evaluated your integration story in ten seconds. Nothing else
  on this list competes with that.
- **State what is mock and what is real.** The engine is stub-first
  ([ROADMAP §0](ROADMAP.md)): `MockEngine` is deterministic fake science. An API that
  returns plausible numbers without saying so is the one thing here that could damage
  credibility rather than build it. Put it in the response — `"engine": "MockEngine"` is
  already in `GET /api/version` — and put it in the documentation.
