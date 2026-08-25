# HTTP API reference

The only HTTP surface in the system. Built with [django-ninja](https://django-ninja.dev)
(ADR 0004); the machine-readable schema is generated at **`/api/openapi.json`** and the
interactive docs at **`/api/docs`**.

Design rules for this layer are in [software-design.md §7](software-design.md).

---

## Authentication

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
| `POST /api/auth/login` | `{username, password}` → the user |
| `POST /api/auth/logout` | 204 |
| `GET /api/auth/me` | The current user, or 401 |

Login returns the same message for an unknown username and a wrong password, so the
endpoint cannot be used to enumerate accounts.

---

## Errors

Every failure has one shape:

```json
{"error": {"code": "not_found", "message": "No project with that id.", "detail": {}}}
```

| Status | `code` | When |
|---|---|---|
| 401 | `not_authenticated` · `invalid_credentials` | No session, or bad login |
| 403 | — | Missing/invalid CSRF token |
| 404 | `not_found` | Missing **or not yours** |
| 409 | `conflict` | Duplicate name; deleting something still referenced |
| 422 | `validation_failed` | Bad body, unknown gate family, unusable dataset |
| 500 | `internal_error` | Generic message; the traceback goes to the log |

> **404, never 403, for objects you do not own.** Returning 403 for an object that
> exists would confirm its existence to someone who should not know ([§7.2](software-design.md)).

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
| `GET /api/projects/{id}/runs` | |
| `POST /api/projects/{id}/runs` | **202 Accepted** |
| `GET /api/runs/{id}` | **The polling endpoint** |
| `GET /api/runs/{id}/detail` | Full record incl. the immutable snapshot |
| `POST /api/runs/{id}/cancel` | |

### Submitting

```json
{
  "dataset_id": "…",
  "gate_families": ["toehold"],
  "scoring_profile": "default",
  "seed": 42,
  "params": {"max_triggers": 2},
  "idempotency_key": "any-unique-string"
}
```

**202, not 201** — the work is accepted, not completed. Poll `GET /api/runs/{id}`.

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
  "gate_families": ["toehold"], "scoring_profiles": ["default"]
}
```

The frontend reads `gate_families` and `scoring_profiles` from here to populate its
configuration form. The Platform cannot import the engine's registries directly
([§3](software-design.md)), so the engine advertises them instead.

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
