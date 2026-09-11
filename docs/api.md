# HTTP API reference

The only HTTP surface in the system — **39 endpoints**. Built with
[django-ninja](https://django-ninja.dev) (ADR 0004); the machine-readable schema is
generated at **`/api/openapi.json`** and the interactive docs at **`/api/docs`**.

Design rules for this layer are in [architecture.md §7](architecture.md). The vocabularies
a submission carries — input modes, organisms, gate families, payloads — are explained in
[modalities.md](modalities.md). External, non-browser integration — API keys, the
one-call `POST /api/design` fast path, and the Python/R/MATLAB clients — is the subject
of [public-api.md](public-api.md); this page covers the whole surface, that one covers
the rationale for the slice of it built for scripts.

**Compatibility promise.** Within `api_schema_version: "1"`, changes are additive only:
new optional request fields and new response fields may appear; an existing field will
not be removed, renamed, or change type or units. **Clients must ignore unknown response
fields.** A breaking change means a new `api_schema_version` and a `/api/v2/` mount, with
`"1"` supported for at least the remainder of the competition season.

---

## Authentication

**Two credentials, one API (ADR 0006).** The SPA authenticates with a session cookie,
same as always; everything else — a script, `curl`, Snakemake, Nextflow — authenticates
with an `X-API-Key` header. Both reach the same 39 endpoints with the same ownership
rules; there is no separate "public API" surface and no second data model. `auth=` tries
the header first (cheaper, no CSRF path), then the session cookie.

```bash
curl https://your-cernal-host/api/version \
  -H "X-API-Key: cern_live_7Kd2mQ8vF3xR9wLbN4pT6yH1sJ0aZcVe"
```

### Session cookies (the SPA)

Session cookies, not tokens. The SPA is served from the same origin as `/api/`, so this
needs no CORS configuration and puts nothing sensitive in browser storage (ADR 0003).

Writes are CSRF-protected. A single-page app has no server-rendered form to carry the
token, so the sequence is:

```js
await fetch("/api/auth/csrf");                       // sets the csrftoken cookie
await fetch("/api/auth/login", {
  method: "POST",
  headers: { "Content-Type": "application/json",
             "X-CSRFToken": getCookie("csrftoken") },
  body: JSON.stringify({ username, password }),
});
```

Every subsequent write must send the `X-CSRFToken` header. Omitting it returns **403**.

| Endpoint | Purpose |
|---|---|
| `GET /api/auth/csrf` | 204; sets the `csrftoken` cookie |
| `POST /api/auth/register` | Request an account → 201, **pending approval** |
| `POST /api/auth/login` | `{username, password}` → the user |
| `POST /api/auth/logout` | 204 |
| `GET /api/auth/me` | The current user, or 401 |

Login returns the same message for an unknown username and a wrong password, so the
endpoint cannot be used to enumerate accounts.

### Registration and approval

Accounts are created **inactive**. A staff member approves them; no email is sent
anywhere.

```jsonc
// POST /api/auth/register
{"username": "maya", "email": "maya@example.org",
 "password": "…", "full_name": "Maya Cohen"}

// 201 — note there is no session: the account is not usable yet
{"username": "maya", "email": "maya@example.org", "pending_approval": true,
 "message": "Your account has been created and is waiting for…"}
```

Signing in before approval returns **403 `pending_approval`**, distinct from 401
`invalid_credentials`, so the applicant is told to wait rather than assuming their
password is wrong. That distinction is only made when the password is *correct*, so it
is not a way to discover which accounts exist.

Approve accounts either in Django admin (**Accounts → Users → Approval → Waiting for
approval**, then the *Approve selected accounts* action — the changelist also warns when
anyone is waiting) or from a terminal:

```bash
./do pending              # who is waiting
./do approve maya bob     # approve them
```

**Forgotten passwords** are reset by a staff member in Django admin. There is no
email-based reset flow, and therefore no SMTP configuration to hold correctly on the
VPS.

### API keys (scripts, notebooks, pipelines)

Session-authenticated only, on every one of these — you cannot mint, list or revoke a
key with a key, so a leaked key can never become a permanent foothold.

| Endpoint | Notes |
|---|---|
| `GET /api/auth/keys` | Yours. Label, prefix, scopes, `last_used_at`, expiry. **Never the secret** |
| `POST /api/auth/keys` | `{label, scopes, expires_in_days}` → 201, **the only response containing `secret`** |
| `DELETE /api/auth/keys/{id}` | Revoke. Idempotent, 204 |
| `GET /api/auth/whoami` | **Key-authenticated**, not session. The first call every client makes |

```jsonc
// POST /api/auth/keys  {"label": "laptop", "scopes": ["read", "design"]}
// 201 — the secret is shown exactly once and is not recoverable afterwards
{"id": "…", "label": "laptop", "prefix": "cern_live_7Kd2", "scopes": ["read", "design"],
 "max_concurrent_runs": 2, "rate_per_minute": 60, "expires_at": null,
 "secret": "cern_live_7Kd2mQ8vF3xR9wLbN4pT6yH1sJ0aZcVe"}
```

Store it now — the server never displays it again and cannot recover it (only its
SHA-256 digest is stored). From the terminal, before a browser session is convenient:

```bash
./do key alice laptop            # mint
./do keys alice                  # list — prefix, scopes, status; never the secret
```

**Scopes.** `read` — every `GET`. `design` — submission, cancellation, annotations;
implies `read`. There is no `admin` or `delete` scope: destructive operations stay
session-only, in the web UI, where a human is present.

**Quotas.** `max_concurrent_runs` (default 2) is the control that actually matters — the
worker runs one job at a time with a one-hour timeout, so a script that loops
`POST /api/design` can park the whole queue for hours. `rate_per_minute` (default 60) is
enforced separately, per key (not per user — a shared CI key cannot starve your laptop).
Both return **429**, with `Retry-After`.

Also usable wherever a session works, except the four endpoints above:

```bash
curl https://your-cernal-host/api/projects \
  -H "X-API-Key: cern_live_7Kd2mQ8vF3xR9wLbN4pT6yH1sJ0aZcVe"
```

---

## Errors

Every failure has one shape:

```json
{"error": {"code": "not_found", "message": "No project with that id.", "detail": {}}}
```

| Status | `code` | When |
|---|---|---|
| 401 | `not_authenticated` · `invalid_credentials` · `invalid_api_key` | No session/bad login (browser); missing, unknown, revoked or expired key (script) |
| 403 | `insufficient_scope` (or nothing, for a CSRF failure) | A `read`-scoped key attempted a `design`-only endpoint; missing/invalid CSRF token |
| 404 | `not_found` | Missing **or not yours** |
| 409 | `conflict` | Duplicate name; deleting something still referenced |
| 422 | `validation_failed` · `unknown_parameter` | Bad body, unknown gate family, unusable dataset; a `strict`-mode typo (carries `did_you_mean`) |
| 429 | `rate_limited` · `too_many_active_runs` | Per-key requests/minute; the concurrency ceiling — both carry `Retry-After` |
| 500 | `internal_error` | Generic message; the traceback goes to the log |

`invalid_api_key` covers every failure reason — missing, malformed, unknown, revoked,
expired — with one message. Telling a client *which* reason would let it learn which
keys exist, the same reasoning behind 404-not-403 above and one login message for both a
bad username and a bad password.

> **404, never 403, for objects you do not own.** Returning 403 for an object that
> exists would confirm its existence to someone who should not know
> ([architecture.md §7.2](architecture.md)).

Responses never contain filesystem paths, storage internals, engine tracebacks or
settings.

---

## Projects

| Endpoint | Notes |
|---|---|
| `GET /api/projects` | Yours only; includes `dataset_count`, `run_count` |
| `POST /api/projects` | 201. 409 if you already have that name |
| `GET /api/projects/{id}` | |
| `PATCH /api/projects/{id}` | Only the fields you send |
| `DELETE /api/projects/{id}` | 204. **409** if the project has runs |

## Datasets

| Endpoint | Notes |
|---|---|
| `GET /api/projects/{id}/datasets` | |
| `POST /api/projects/{id}/datasets` | `multipart/form-data`, field `file`. 201 |
| `GET /api/example-datasets` | The bundled examples, so the wizard is usable with no data of your own |
| `POST /api/projects/{id}/datasets/example` | Copy one of them into the project. 201 |
| `GET /api/datasets/{id}` | |
| `DELETE /api/datasets/{id}` | 204. **409** if any run used it |

Upload is **synchronous**: the file is checksummed and validated before the response
returns, so the researcher learns immediately whether it is usable.

```json
{
  "id": "…", "name": "expression.csv", "validation_status": "VALID",
  "checksum_sha256": "4139ba32…", "size_bytes": 271,
  "validation_report": {"rows": 5, "columns": ["gene_id", "log2fc", …],
                        "errors": [], "warnings": []}
}
```

`validation_status` is `VALID` · `INVALID` · `PENDING`. An `INVALID` dataset uploads
successfully (so the researcher can read the report) but **cannot be submitted for
analysis**. Validation is deliberately shallow — readable file, expected columns, sane
row count, parseable numerics. Scientific validation belongs to the engine.

## Runs

| Endpoint | Notes |
|---|---|
| `GET /api/runs` | Every run you own, newest first |
| `GET /api/projects/{id}/runs` | |
| `POST /api/projects/{id}/runs` | **202 Accepted** |
| `GET /api/runs/{id}` | **The polling endpoint** |
| `GET /api/runs/{id}/detail` | Full record incl. the immutable snapshot |
| `POST /api/runs/{id}/cancel` | |

### Submitting

```json
{
  "input_mode": "de",
  "dataset_id": "…",
  "gate_families": ["toehold"],
  "scoring_profile": "default",
  "seed": 42,
  "params": {"organism": "ecoli", "payload": {"outputs": ["gfp"]}},
  "idempotency_key": "any-unique-string"
}
```

**202, not 201** — the work is accepted, not completed. Poll `GET /api/runs/{id}`.

**Exactly one input source.** `input_mode` is `de` or `direct`
([modalities.md §1](modalities.md)):

| `input_mode` | Send | Must not send |
|---|---|---|
| `de` | `dataset_id` — a `VALID` dataset in this project | `trigger_sequence` |
| `direct` | `trigger_sequence` — the mRNA, pasted | `dataset_id` |

A mismatch returns **422**. The rule is also a database constraint, so it cannot be
bypassed by any other write path.

**`params` is free-form by contract.** It is frozen verbatim into `params_snapshot`, and
the engine reads what it recognises and ignores the rest — which is what lets the wizard
add a field without an engine release. Its v1 shape is in
[modalities.md §7](modalities.md).

`gate_families` and `scoring_profile` are validated against what the engine advertises at
`GET /api/version`; an unknown value returns 422 listing the available ones.

**Idempotency.** Resubmitting with the same `idempotency_key` returns the existing run
rather than launching a second computation. Generate one key per user-initiated
submission and reuse it across network retries.

The configuration is snapshotted at submission. Editing the project afterwards affects
future runs only.

### Polling

`GET /api/runs/{id}` is called every ~3 seconds while a run is active. Kept cheap — no
joins across candidates.

```json
{
  "id": "…", "status": "RUNNING", "stage": "Evaluating gate designs",
  "progress_pct": 78, "error_summary": null, "warnings": [],
  "submitted_at": "…", "started_at": "…", "finished_at": null,
  "counts": {"candidates": 0, "artifacts": 0}
}
```

`status` is `DRAFT` · `QUEUED` · `RUNNING` · `COMPLETED` · `FAILED` · `CANCELLED`. The
last three are terminal — stop polling. `stage` is human-readable and meant to be shown
directly. On `FAILED`, `error_summary` is safe to display verbatim.

### Cancelling

Cooperative — nothing is killed. A running analysis is flagged and stops at the next
stage boundary.

```json
{"id": "…", "status": "RUNNING", "outcome": "cancellation_requested"}
```

`outcome` is `cancelled` (it had not started), `cancellation_requested` (it was running),
or `already_terminal`.

---

## Design — the one-call fast path

The five calls above, collapsed into one for a script: `POST /api/design` resolves the
project (creating one if you don't name one), the dataset (inline `dge_csv` creates one),
the gate families and the scoring profile, then submits through the same `submit_run` the
wizard uses — no new science, no new status transitions.

| Endpoint | Notes |
|---|---|
| `POST /api/design` | `?dry_run=true` estimates without submitting. `?wait=<seconds>` (ceiling 300) blocks for a finished result |
| `GET /api/design/{id}` | Thin alias of `GET /api/runs/{id}` |
| `GET /api/design/{id}/results` | Ranked candidates + metric decomposition. `?format=csv` delegates to `export.csv` |

```bash
curl https://your-cernal-host/api/design \
  -H "X-API-Key: cern_live_…" -H "Content-Type: application/json" \
  -d '{"trigger_sequence": "AUGGCUAAGCUUAACGGAUCCAUGGCUAAGCUUAAC", "organism": "ecoli"}'
```

```jsonc
// 202 Accepted
{
  "job_id": "6f1c…", "status": "QUEUED", "progress_pct": 0,
  "poll_url": "/api/design/6f1c…", "results_url": "/api/design/6f1c…/results",
  "web_url": "/runs/6f1c…",
  "estimate": {"designs": 14, "seconds": 0.2, "confidence": "very rough"},
  "resolved": {"input_mode": "direct", "gate_families": ["toehold", …],
               "scoring_profile": "default", "seed": null, "constraints": {}}
}
```

`resolved` echoes every default the server chose — a run is reproducible from the
response alone. `estimate` is deliberately rough and labelled as such: `direct` mode
counts trigger lengths × gate families; `de` mode bounds the search space from the
dataset's row count, since gene selection (stage 1) doesn't compute the real one yet.

**Exactly one input**: `trigger_sequence`, `dataset_id`, or inline `dge_csv` — two or
none is 422 naming the conflict. **`strict` defaults to `true`** here (unlike
`POST /api/projects/{id}/runs`, where `params` stays intentionally free-form): an unknown
key anywhere in `constraints`, `scoring`, `budget` or `payload` is 422 with
`did_you_mean`, instead of the silent "unrecognised field, quietly ignored" failure the
free-form endpoint accepts on purpose.

**Custom scoring** — re-weight the nine metrics, or add a hard filter, per run:

```jsonc
"scoring": {
  "weights": {"predicted_leakage": 4.0, "gc_content": 0.0},
  "hard_filters": [{"metric": "dynamic_range", "minimum": 10.0}]
}
```

Only the nine names `GET /api/version`'s `metrics` array advertises are accepted — an
unknown one is 422 listing all nine, not a metric that silently scores as the worst
possible value. `direction` and `valid_range` are not overridable: those are physics and
units, not preference. The derived profile gets a deterministic label,
`custom-<hash8>` — recorded in `resolved.scoring_profile`, so two runs with identical
weights are visibly comparable.

**`wait=`** blocks and returns the finished result inline (`200` with candidates,
instead of `202` with a handle) — the client code path is identical either way, since a
timeout still returns `202` with the same handle. Never rely on it as the documented
default for a large `de` run: 12,000 designs is about a minute, but a search space of
millions is hours, and the ceiling (300s) is set below any reverse-proxy write timeout on
purpose.

---

## Results

| Endpoint | Notes |
|---|---|
| `GET /api/runs/{id}/candidates` | Paginated |
| `GET /api/candidates/{id}` | Full detail incl. metric decomposition |
| `GET /api/runs/{id}/artifacts` | |
| `GET /api/artifacts/{id}/download` | Authorized file serve |
| `GET /api/runs/{id}/export.csv` | Flat candidate × metric table |

### Listing candidates

`?limit=` `&offset=` — `{"items": [...], "count": n}`.

| Parameter | Default | Notes |
|---|---|---|
| `sort` | `rank` | `rank`, `overall_score`, `gate_family`, `logic_type`, `engine_ref`; prefix `-` for descending. Anything else → 422 with the allowed list |
| `gate_family` | — | Exact match |
| `include_rejected` | `false` | |

NULLs sort last in both directions, so unranked candidates never lead the list.

**Rejected candidates are kept, not deleted.** They are hidden by default, and every one
carries a non-empty `rejection_reason` — guaranteed by a database constraint, not by
convention.

### Candidate detail

Returns `triggers`, `design` (sequences, structure, logic graph) and the full `metrics`
list. Each metric carries `raw_value`, `normalized_value`, `weight` and `direction`: the
researcher is shown the decomposition, never a single opaque score (design map 12).

### Artifacts

`download_url` is always an API path, never a storage location. Artifacts are served
through an authorized view that checks run ownership — a static handler would make every
artifact readable by anyone who guessed the path.

## Annotations

| Endpoint | Notes |
|---|---|
| `GET /api/candidates/{id}/annotations` | |
| `POST /api/candidates/{id}/annotations` | `{text, decision_tag}` → 201 |
| `DELETE /api/annotations/{id}` | 204 |

`decision_tag` ∈ `NONE` · `PINNED` · `SHORTLISTED` · `REJECTED` · `SYNTHESIZE`. Anything
else → 422 with the allowed set. Annotations are product-owned and survive re-runs.

## Meta

| Endpoint | Auth | Notes |
|---|---|---|
| `GET /api/health` | none | `{"status": "ok"}` |
| `GET /api/version` | none | App, API and engine versions **plus engine capabilities** |

```json
{
  "app_version": "0.1.0", "api_schema_version": "1",
  "engine": "MockEngine", "engine_version": "mock-1.0.0",
  "engine_schema_version": "1",
  "gate_families": [
    {"name": "toehold", "label": "Toehold Riboswitch",
     "description": "Translational control · pre-mRNA", "available": true},
    {"name": "crispr", "label": "CRISPR-Cas sgRNA Gate",
     "description": "Transcriptional control · iSBH", "available": false}
  ],
  "scoring_profiles": ["default"],
  "metrics": [
    {"name": "predicted_leakage", "direction": "LOWER_BETTER", "weight": 2.5,
     "valid_range": [0.0, 1.0], "unit": "fraction 0-1",
     "description": "Proxy for OFF-state activation."}
  ],
  "hard_filters": [
    {"metric": "predicted_leakage", "minimum": null, "maximum": 0.85,
     "reason": "Predicted OFF-state leakage above the acceptable threshold."}
  ]
}
```

The frontend reads `gate_families` and `scoring_profiles` from here to populate its
configuration form. The Platform cannot import the engine's registries directly
([architecture.md §3](architecture.md)), so the engine advertises them instead.

`metrics` (nine entries; one shown above) is the vocabulary `POST /api/design`'s
`scoring.weights` accepts — including `unit`, the one piece of metadata that
distinguishes `dynamic_range` (linear fold) from `state_separation` directly above it
(log2 fold), and `gc_content` (0–100) from every neighbouring probability (0–1).

**Planned families are listed with `available: false`**, so the wizard renders them greyed
out with their real label — flipping the flag on the class changes the UI with no frontend
release.

> **Not yet host-aware.** CRISPR is eukaryotic only, but this endpoint reports
> availability without an organism, so the wizard cannot grey it out for *E. coli*
> specifically. Task **P2** in [ROADMAP.md](ROADMAP.md).

---

## Worked example

The full workflow, verified against a live server and worker:

```bash
./do dev        # terminal 1
./do worker     # terminal 2 — without this, runs sit in QUEUED forever
```

1. `GET  /api/auth/csrf` → cookie
2. `POST /api/auth/login`
3. `GET  /api/version` → available gate families
4. `POST /api/projects`
5. `POST /api/projects/{id}/datasets` (multipart) → `VALID`
6. `POST /api/projects/{id}/runs` → **202**, `QUEUED`
7. `GET  /api/runs/{id}` every 3s → `RUNNING 30% Discovering candidate features` → … → `COMPLETED 100%`
8. `GET  /api/runs/{id}/candidates` → ranked, best first
9. `GET  /api/candidates/{id}` → metric decomposition
10. `GET  /api/artifacts/{id}/download` → the FASTA
11. `POST /api/candidates/{id}/annotations`
12. `GET  /api/runs/{id}/export.csv`

Steps 3–10 collapse into one `POST /api/design` call from a script — see
[Design — the one-call fast path](#design--the-one-call-fast-path) above.

---

## Client libraries

Every client — including `curl` — wraps the same five calls:
`POST /api/design` · `GET /api/design/{id}` · `GET /api/design/{id}/results` ·
`GET /api/artifacts/{id}/download` · `GET /api/version`. Anyone needing more talks to
this reference or `/api/docs` directly; that is the integration story, and it costs
nothing extra to keep working, since it is the same surface the SPA uses.

### `curl` — the client that never breaks

```bash
KEY=cern_live_7Kd2mQ8vF3xR9wLbN4pT6yH1sJ0aZcVe
HOST=https://your-cernal-host

# submit and wait
curl -s "$HOST/api/design?wait=60" -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"trigger_sequence": "AUGGCUAAGCUUAACGGAUCCAUGGCUAAGCUUAAC", "organism": "ecoli"}' \
  | tee response.json

# or poll by hand
JOB=$(jq -r .job_id response.json)
curl -s "$HOST/api/design/$JOB" -H "X-API-Key: $KEY"
curl -s "$HOST/api/design/$JOB/results?top_n=10" -H "X-API-Key: $KEY" | jq '.candidates[0]'
curl -s "$HOST/api/design/$JOB/results?format=csv" -H "X-API-Key: $KEY" -o candidates.csv
```

### Python — `pip install cernal`

```python
import os
from cernal import Client

c = Client(api_key=os.environ["CERNAL_API_KEY"], base_url="https://your-cernal-host")
job = c.design(trigger_sequence="AUGGCUAAGCUUAACGGAUCC", organism="ecoli")
df = job.wait().to_dataframe()
```

`clients/python/` in this repo. `requests` only; pandas is optional
(`pip install cernal[pandas]`, or use `.to_dicts()`). Genuinely tested end to end
against a live server — see `clients/python/tests/test_conformance.py`.

### R — `remotes::install_github(..., subdir = "clients/r")`

```r
library(cernal)
cl  <- cernal_client(Sys.getenv("CERNAL_API_KEY"), base_url = "https://your-cernal-host")
job <- cernal_design(cl, trigger_sequence = "AUGGCUAAGCUUAACGGAUCC", organism = "ecoli")
df  <- cernal_results(cernal_wait(job))
```

`clients/r/`. `httr2` + `tibble`. The natural next step —
`DESeq2::results() |> as.data.frame() |> cernal_design(...)` — is DESeq2 output to
plasmid design in one script.

### MATLAB — a `+cernal` package folder

```matlab
c = cernal.Client(getenv('CERNAL_API_KEY'), 'BaseURL', 'https://your-cernal-host');
job = c.design('trigger_sequence', 'AUGGCUAAGCUUAACGGAUCC', 'organism', 'ecoli');
T = job.wait().results();
```

`clients/matlab/`. `webwrite`/`webread` only — no toolbox. `addpath` the folder; there
is no package manager worth targeting here.

> **R and MATLAB have not been run against a live server** — no interpreter was
> available while building them. Both are written directly from this reference and the
> engine's actual, tested responses, and both ship a conformance test against
> `clients/fixtures/`, but treat them as a first draft until someone with the runtime
> confirms they pass. The Python client has been; its conformance suite is in CI.
