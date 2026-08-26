# CERNAL — Software Design & Build Plan (v1)

> **Read this first.** This is the authoritative reference for how the CERNAL software
> product is structured and in what order it gets built. It exists so that any developer
> or AI agent joining the project can act without re-deriving the architecture or
> re-litigating decisions already made.
>
> - **Audience:** developers and AI coding agents working in this repository.
> - **Supersedes:** the `Design Maps/` Obsidian vault, for implementation purposes.
>   The maps remain the long-term north star; this document is what we actually build.
> - **Scope of v1:** the **software product**. The scientific engine is stubbed.

---

## 0. Current status

| Step | State | Notes |
|---|---|---|
| `Design Maps/` vault | Complete | 21 canvases; the long-term target architecture |
| This document | Complete | |
| **Step 0 — Scaffold** | **Complete** | Django 5.2 on Python 3.13; boots, migrates, admin reachable |
| **Step 1 — Engine contract + MockEngine** | **Complete** | Contract, MockEngine, gate/scoring layers, boundary test. No Django code touched. |
| **Step 2 — Domain model** | **Complete** | 8 models, migrations, admin back-office, `seed_demo`. |
| **Step 3 — API + orchestration** | **Complete** | 24 endpoints, run state machine, django-q2 worker. Verified live: full workflow + cancellation over HTTP. 291 tests pass. |
| **Step 4 — Frontend integration** | **Complete (4a–4g)** | React SPA served same-origin; login, wizard, progress, results, static pages. Plan: [step-4-frontend-plan.md](step-4-frontend-plan.md) |
| Step 5 — Real science | Not started | Planned in [step-5-engine-plan.md](step-5-engine-plan.md) |
| Step 6 — Deployment | Not started | [gcp-deployment.md](gcp-deployment.md) · rationale in [engine-deployment.md](engine-deployment.md) |

Update this table as steps complete. It is the fastest way for a new agent to orient.

**Deviations from this document so far**

- **`./do` replaces the `Makefile`** (§4, §13 Step 0). `make` is not present on a default
  WSL Ubuntu image and installing it needs root. A dependency-free shell script keeps
  "clone and run" true. ADR not required — this removes a dependency rather than adding one.
- **`load_engine(dotted_path)` replaces `get_engine()`** (§13 Step 1). §13 described it as
  "resolving `CERNAL_ENGINE`", but reading Django settings from inside `engine/` would
  violate §3 outright. The function takes the path as an argument; the Platform passes
  `settings.CERNAL_ENGINE` in.
- **`engine/pipeline/stages.py` holds all thirteen stage signatures**, rather than one module
  per stage (§13 Step 1). Thirteen near-empty modules is noise for a rotating team (rule 12);
  the stage ordering is just as visible in one file.
- **`EngineCapabilities` added to the engine contract** (§10). The Platform must validate
  a submission's gate families and scoring profile, but §3 forbids it importing
  `engine.gates.registry` or `engine.scoring.profiles`. So `EngineClient` grew a
  `capabilities()` method and the engine advertises them — the in-process form of design
  map 08's `GET /version` capability document. Surfaced at `GET /api/version`.
- **`GET /api/auth/csrf` added to §7.** Session auth means writes are CSRF-protected, and
  an SPA has no server-rendered form to carry the token. Django's test client bypasses CSRF,
  so this gap only appeared when driving the API over real HTTP.
- **`Annotation` now has a UUID primary key.** It was the one API-exposed model left with a
  sequential integer id, which both broke its `DELETE` route and leaked how many decisions
  had been recorded.
- **`Candidate.engine_ref` added to §5.** The engine's local candidate id is stored so a
  database row can be traced back to the result manifest that produced it, and so a
  manifest cannot be imported twice into one run (`unique_engine_ref_per_run`).
- **`apps/results/services.py::import_job_result` pulled forward from Step 3** (§13 Step 2).
  Step 2's "Done when" requires `seed_demo` to produce a browsable run, which needs result
  persistence. Writing it once in the right place beats writing it twice. Step 3 still owns
  the run *lifecycle* — this function deliberately does not touch `run.status` (rule 5).
- **`engine/scoring/` is implemented, not stubbed** (§13 Step 1). Normalization, weighting,
  hard filters and ranking are ~150 lines of generic, science-free machinery that `MockEngine`
  needs in order to produce meaningful score decompositions. Implementing it now makes the
  mock genuinely representative and shrinks Step 5. The *metric set* in `default-v1` remains
  provisional and is owned by the scientific team.

---

## 1. Context and goal

CERNAL is a research tool for an **iGEM** team. A researcher uploads transcriptomic
differential-expression data, defines a biological objective, configures an analysis, and
receives a ranked list of candidate RNA logic circuits (toehold gates, AND-toehold gates,
and later CRISPR-derived designs) with scores, metrics, sequences and downloadable artifacts.

**Expected load: a few dozen users, roughly 5 analyses per day.** This number drives every
decision in this document. It is not a placeholder — it is the reason the architecture below
looks the way it does.

### 1.1 What the Design Maps describe

The vault specifies two independently deployed systems:

- **CERNAL Platform** — React frontend, Django backend, PostgreSQL, Redis, Celery workers,
  object storage, gateway/TLS.
- **CERNAL Engine** — a separate FastAPI service owning the scientific pipeline, gate
  families, scoring, and a `ComputeProvider` abstraction over Slurm (TAU PowerSlurm) and
  future cloud batch providers.

They communicate over a versioned, asynchronous, idempotent REST contract, with a published
OpenAPI document, contract tests, service-to-service authentication and signed storage
references. The vault lists 15 domain entities, 14 platform run states and an 11-phase
roadmap.

### 1.2 Why we are not building that yet

That design is correct for a mature product with a dedicated ops owner. At 5 analyses/day it
costs far more than it returns: two repositories, two deployment units, two authentication
systems, a network boundary to version and test, and four long-running background services —
before a single researcher can run an analysis.

**The goal of v1 is to reach a working end-to-end product on one small VPS, with the
architectural seams placed exactly where the maps say they belong, so that growing into the
full design is a series of local substitutions rather than a rewrite.**

### 1.3 The one idea we preserve at full strength

The **Platform / Engine boundary**. In v1 it is a *module* boundary rather than a *network*
boundary, but it is enforced just as strictly (see §3). The Platform never calls scientific
code directly; it goes through an `EngineClient` interface. The day one machine is no longer
enough, `engine/` is wrapped in a thin HTTP service and `LocalEngine` is swapped for
`HttpEngine`. Nothing else in the codebase changes.

---

## 2. Simplification ledger

Every row is a deliberate decision, with the condition that should make us revisit it.

| Concern | Design Maps | v1 | Rationale | Re-add when |
|---|---|---|---|---|
| Repositories | 2 (`cernal-platform`, `cernal-engine`) | 1 | Two repos need two CI pipelines, two release cadences, a shared contract package | Two teams are genuinely blocking each other |
| Deploy units | Platform + Engine services | 1 web process + 1 worker process | One `systemd` unit each on one VPS | Engine needs to scale or move to HPC-adjacent hosting |
| Engine transport | Versioned REST + OpenAPI + contract tests | Python `Protocol` + frozen dataclasses | Same field-for-field payload shape, checked by the type system instead of serialised | Engine moves off-box |
| Task queue | Redis + Celery | `django-q2`, ORM broker | No broker service to run or back up; tasks and failures are visible in Django admin | Sustained queue depth, or need for multi-machine workers |
| Database | PostgreSQL | SQLite in WAL mode | At this volume SQLite is genuinely sufficient; backup is copying one file | Concurrent writers cause lock contention, or full-text/JSON querying becomes central |
| File storage | Object storage + signed URLs | `FileField` into `var/media/` | Identical `storage_ref` + `checksum` model, local backend | Disk pressure, or multi-host serving |
| Compute | `ComputeProvider` adapter → Slurm | Runs inline in the worker process | No Slurm access is needed to build the product | Analyses exceed the VPS's memory/time budget |
| Domain entities | 15 | 8 | See §5 | Multi-tenancy or dataset lineage becomes real |
| Run states | 14 | 6 | See §6 | Users need finer-grained failure recovery |
| Auth | Identity service, workspaces, roles, object-level permissions | Django auth + per-object ownership check | An iGEM team is one trusted group | External collaborators get accounts |
| Frontend | React SPA + typed API client | **Kept** — existing Lovable app, served same-origin by Django | Already built; same-origin removes CORS and token handling | — |
| Notifications / audit / export services | Separate services | Model fields, Django admin, CSV endpoints | Services with one caller are not services | Real audit requirements appear |
| Observability | Structured logs, metrics, alerting | Django logging to file + `qcluster` admin views | — | The VPS has users depending on uptime |

### 2.1 Explicitly kept from the maps

These cost almost nothing now and are expensive to retrofit:

1. **Immutable run submissions.** An `AnalysisRun` snapshots its full parameter set as JSON
   at submit time. Editing a project never mutates a submitted run.
2. **Idempotency keys.** Every run submission carries one. Re-submitting the same key returns
   the existing run instead of launching a second expensive computation.
3. **Checksums** on every dataset input and every produced artifact.
4. **Versioned scoring profiles** recorded on the run, so a score is always interpretable.
5. **`GateFamily` plugin interface** — the core scientific extensibility seam.
6. **Explicit rejection reasons** on candidates. Rejected candidates are stored, not silently
   dropped.
7. **A deterministic mock engine**, so product work never waits on scientific work.
8. **Product-facing status vocabulary** distinct from engine-internal stages.

---

## 3. The boundary rule

> **`src/engine/` must never import Django, and must never import from `src/apps/`,
> `src/api/` or `src/config/`.**

This is the single invariant that keeps v1 upgradeable into the full design. It is enforced
by an automated test (`tests/test_boundary.py`, §11.2), not by convention.

Consequences that follow from it, and which agents must respect:

- `engine/` receives **plain paths and dataclasses**, never Django model instances, `QuerySet`s,
  `Request` objects or `settings`.
- `engine/` never writes to the database. It returns a `JobResult`; the Platform persists it.
- `engine/` never reads Django settings. Configuration arrives inside `JobRequest`.
- Conversely, `apps/` and `api/` never import from `engine.pipeline`, `engine.gates` or
  `engine.scoring`. They may import only `engine.contract` and `engine.client`.

```
     ┌───────────────────────── PLATFORM (Django) ──────────────────────────┐
     │                                                                      │
     │   api/  ──►  apps/{projects,datasets,analyses,results}  ──►  DB      │
     │                              │                                       │
     │                              │  JobRequest (dataclass, plain paths)  │
     │                              ▼                                       │
     │                   engine.client.EngineClient   ◄── the seam          │
     └──────────────────────────────┬───────────────────────────────────────┘
                                    │  JobResult (dataclass)
     ┌──────────────────────────────▼───────────── ENGINE (pure Python) ────┐
     │   engine/{contract,client,pipeline,gates,scoring,artifacts}          │
     │   no django · no db · no settings · no http                          │
     └──────────────────────────────────────────────────────────────────────┘
```

**Swapping in the real architecture later:** add `engine/service.py` (FastAPI) exposing
`POST /v1/jobs`, `GET /v1/jobs/{id}`, `GET /v1/jobs/{id}/result`, `POST /v1/jobs/{id}/cancel`,
serialising the same dataclasses. Add `HttpEngineClient` implementing the same `Protocol`.
Change one setting. The Platform is untouched.

---

## 4. Repository layout

```
cernal/
├── README.md                     Quickstart only; design lives in docs/
├── pyproject.toml                Deps, ruff, pytest config
├── do                            Task runner: ./do dev | test | lint | migrate …
├── manage.py                     At root; inserts src/ onto sys.path
├── .env.example                  Every env var, documented, with safe defaults
├── .gitignore
│
├── docs/
│   ├── software-design.md        ← this file, the entry point
│   ├── domain-model.md           Field-level model reference (generated from §5)
│   ├── engine-contract.md        The dataclass contract + future HTTP mapping
│   ├── api.md                    Endpoint reference (generated from django-ninja OpenAPI)
│   ├── development.md            WSL setup, common tasks, troubleshooting
│   ├── deployment.md             VPS runbook
│   └── decisions/                Short ADRs, one file per decision
│       ├── 0001-single-repo-in-process-engine.md
│       ├── 0002-sqlite-and-orm-task-queue.md
│       ├── 0003-same-origin-spa-session-auth.md
│       └── 0004-django-ninja-over-drf.md
│
├── src/
│   ├── config/                   Django project
│   │   ├── settings/
│   │   │   ├── base.py           Everything shared
│   │   │   ├── dev.py            DEBUG, SQLite, MockEngine, console email
│   │   │   └── prod.py           Env-driven, security headers, file logging
│   │   ├── urls.py               /api/ → ninja, /admin/, SPA catch-all
│   │   ├── wsgi.py
│   │   └── asgi.py
│   │
│   ├── apps/                     Django apps — product logic only
│   │   ├── accounts/             Custom User (empty AbstractUser)
│   │   ├── common/               Shared base models, mixins, checksum helpers
│   │   ├── projects/             Project
│   │   ├── datasets/             Dataset + upload validation
│   │   ├── analyses/             AnalysisRun, orchestration, the queue task
│   │   └── results/              Candidate, CandidateMetric, Artifact, Annotation
│   │
│   ├── api/                      The ONLY HTTP surface
│   │   ├── __init__.py           NinjaAPI instance
│   │   ├── schemas.py            Pydantic request/response models
│   │   ├── auth.py               Session auth helper + permission checks
│   │   └── routers/              projects.py datasets.py runs.py results.py meta.py
│   │
│   ├── engine/                   ★ NO DJANGO. See §3.
│   │   ├── contract.py           JobRequest, JobResult, CandidateResult, MetricValue, ArtifactRef
│   │   ├── client.py             EngineClient Protocol · MockEngine · LocalEngine
│   │   ├── errors.py             EngineError hierarchy
│   │   ├── pipeline/             stages.py — 13 stage signatures (stubs until Step 5)
│   │   ├── gates/                base.py (GateFamily ABC) · toehold.py (stub) · registry.py
│   │   ├── scoring/              profiles.py, normalize.py — implemented
│   │   └── artifacts.py          Writes result files to a given output dir
│   │
│   └── static/
│       └── app/                  Vite build output of frontend/ (gitignored)
│
├── frontend/                     The existing Lovable / React application
│
├── tests/
│   ├── conftest.py
│   ├── test_boundary.py          ★ Enforces §3
│   ├── engine/                   Contract + MockEngine determinism tests
│   ├── api/                      Endpoint tests
│   └── e2e/                      Full workflow against MockEngine
│
├── var/                          gitignored — all mutable state
│   ├── cernal.db
│   ├── media/datasets/
│   ├── media/artifacts/
│   └── logs/
│
└── deploy/
    ├── Caddyfile
    ├── cernal-web.service
    ├── cernal-worker.service
    └── backup.sh
```

### 4.1 Layout notes for agents

- **`manage.py` sits at the repo root**, not in `src/`. It inserts `src/` onto `sys.path`
  before delegating to Django. This keeps `python manage.py …`, `pytest`, `ruff` and editors
  all rooted at the repo root while preserving a clean src layout.
- Django apps are addressed as **`apps.projects`**, not `projects`. `INSTALLED_APPS` uses the
  dotted path, and each app's `AppConfig.name` must match.
- **Never create a package named `platform`** — it shadows a Python standard library module.
- `var/` holds every piece of mutable state. Deleting `var/` and re-running migrations must
  produce a clean working system. Nothing outside `var/` is written at runtime.

---

## 5. Domain model

Eight models, down from fifteen. UUID primary keys throughout for external identifiers.

### `accounts.User`

```python
class User(AbstractUser):
    pass  # Intentionally empty.
```

Defined at scaffold time with `AUTH_USER_MODEL = "accounts.User"` **before the first
migration**. Swapping the user model after migrations exist is a painful, well-documented
Django trap. This is free insurance.

Accounts are **self-service but admin-approved**: anyone can request one at
`/register`, and it stays `is_active=False` until a staff member approves it in Django
admin or with `./do approve <username>`. No email is involved — at this scale a person on
the team is always reachable, and SMTP credentials would be one more secret to hold
correctly on the VPS (rule 10). Forgotten passwords are reset by staff in admin.

*Dropped from the maps:* `Workspace`, `WorkspaceMembership`. An iGEM team is one trusted
group; authorization is "is this object mine, or am I staff". Re-add when external
collaborators need scoped access.

### `projects.Project`

| Field | Type | Notes |
|---|---|---|
| `id` | UUID, pk | |
| `owner` | FK → User | `on_delete=PROTECT` |
| `name` | CharField(200) | Unique per owner |
| `organism` | CharField(100) | e.g. `E. coli` |
| `biological_objective` | TextField | Free text: base state → target state, desired logic |
| `created_at` / `updated_at` | DateTime | auto |

### `datasets.Dataset`

**Immutable.** Re-uploading creates a new row; there is no `DatasetVersion` table because the
Dataset *is* the version.

| Field | Type | Notes |
|---|---|---|
| `id` | UUID, pk | |
| `project` | FK → Project | `CASCADE` |
| `name` | CharField(200) | Original filename or user label |
| `file` | FileField | → `var/media/datasets/<uuid>/<name>` |
| `checksum_sha256` | CharField(64) | Computed on upload, never recomputed |
| `size_bytes` | BigInteger | |
| `schema_version` | CharField(20) | Which input format this was validated against |
| `validation_status` | Choices | `PENDING` · `VALID` · `INVALID` |
| `validation_report` | JSONField | Row/column counts, detected columns, errors, warnings |
| `uploaded_by` | FK → User | |
| `created_at` | DateTime | |

Validation is **synchronous on upload** and deliberately shallow: readable file, expected
columns present, sane row count, parseable numerics. Deep scientific validation belongs to the
engine and happens at run time.

### `analyses.AnalysisRun`

The centre of the product. Immutable once submitted.

| Field | Type | Notes |
|---|---|---|
| `id` | UUID, pk | Also the external run identifier |
| `project` | FK → Project | `PROTECT` |
| `dataset` | FK → Dataset | `PROTECT` |
| `created_by` | FK → User | |
| `idempotency_key` | CharField(64), unique | Client-supplied or server-generated |
| `params_snapshot` | JSONField | **Immutable** full normalized configuration |
| `gate_families` | JSONField (list[str]) | e.g. `["toehold"]` |
| `scoring_profile` | CharField(50) | e.g. `default-v1` |
| `seed` | Integer, null | Reproducibility |
| `engine_version` | CharField(50) | Recorded by the engine at completion |
| `status` | Choices | See §6 |
| `stage` | CharField(50) | Human-readable current stage |
| `progress_pct` | Integer 0–100 | |
| `error_summary` | TextField, blank | Safe, user-facing failure explanation |
| `warnings` | JSONField (list[str]) | |
| `cancel_requested` | Boolean | Cooperative cancellation flag |
| `submitted_at` / `started_at` / `finished_at` | DateTime, null | |

*Collapsed from the maps:* `AnalysisConfiguration` → `params_snapshot`;
`EngineJobReference` → `engine_version` + `status` + `stage`;
`ResultManifestRecord` → `engine_version` + `params_snapshot` + artifact checksums.

### `results.Candidate`

| Field | Type | Notes |
|---|---|---|
| `id` | UUID, pk | |
| `run` | FK → AnalysisRun | `CASCADE` |
| `engine_ref` | CharField(50) | Engine-local id; unique per run. Traceability back to the manifest |
| `rank` | Integer, null | Null for rejected candidates |
| `overall_score` | Float, null | |
| `gate_family` | CharField(50) | |
| `logic_type` | CharField(50) | e.g. `AND`, `single-input` |
| `triggers` | JSONField | Trigger set: gene ids, expression evidence |
| `design` | JSONField | Sequences, structure, logic graph |
| `summary` | TextField | One-line human description |
| `warnings` | JSONField (list[str]) | |
| `is_rejected` | Boolean | |
| `rejection_reason` | TextField, blank | **Never leave blank when rejected** |

Rule 8 is enforced by a database `CheckConstraint`, not by a code path: a rejected
candidate without a reason cannot be written at all. Two further constraints hold the
line — rejected candidates cannot carry a rank, and `engine_ref` is unique per run.

### `results.CandidateMetric`

A separate table rather than a JSON blob, so the comparison UI can sort and filter in SQL.

| Field | Type |
|---|---|
| `candidate` | FK → Candidate, `CASCADE` |
| `name` | CharField(100) |
| `raw_value` | Float, null |
| `normalized_value` | Float, null |
| `weight` | Float |
| `direction` | Choices: `HIGHER_BETTER` · `LOWER_BETTER` |

Unique together: `(candidate, name)`.

### `results.Artifact`

| Field | Type | Notes |
|---|---|---|
| `id` | UUID, pk | |
| `run` | FK → AnalysisRun | `CASCADE` |
| `candidate` | FK → Candidate, null | Null = run-level artifact |
| `kind` | CharField(50) | `sequence_fasta`, `design_table`, `logic_graph`, `plot`, `report` |
| `file` | FileField | → `var/media/artifacts/<run_id>/<name>` |
| `media_type` | CharField(100) | |
| `checksum_sha256` | CharField(64) | |
| `size_bytes` | BigInteger | |

Artifacts are **never** served by a static file handler. They go through an authorized
download view that checks run ownership (§7).

### `results.Annotation`

Product-owned, entirely independent of engine output. Survives re-runs.

| Field | Type |
|---|---|
| `candidate` | FK → Candidate, `CASCADE` |
| `author` | FK → User |
| `text` | TextField |
| `decision_tag` | Choices: `NONE` · `PINNED` · `SHORTLISTED` · `REJECTED` · `SYNTHESIZE` |
| `created_at` | DateTime |

---

## 6. Run state machine

Six states, down from fourteen.

```
   DRAFT ──submit──► QUEUED ──worker picks up──► RUNNING ──► COMPLETED
                        │                          │
                        │                          ├──► FAILED
                        └──────cancel──────────────┴──► CANCELLED
```

| State | Meaning | Terminal |
|---|---|---|
| `DRAFT` | Created but not submitted; parameters still editable | no |
| `QUEUED` | Submitted; snapshot frozen; waiting for a worker | no |
| `RUNNING` | Worker executing; `stage` and `progress_pct` update as it goes | no |
| `COMPLETED` | Results persisted and readable | **yes** |
| `FAILED` | Engine raised, or result persistence failed; `error_summary` populated | **yes** |
| `CANCELLED` | Cancellation requested and honoured | **yes** |

### 6.1 Why the maps' extra states are gone

`UPLOADING`/`VALIDATING`/`READY` belong to the dataset, not the run — dataset upload and
validation are synchronous and finish before a run can reference the dataset.
`SUBMITTING` and `IMPORTING RESULTS` were artifacts of a network boundary: with an in-process
engine, submission is a database write and result import is the same transaction that ends the
run. `VALIDATION FAILED` lives on `Dataset.validation_status`. `SUBMISSION FAILED` cannot occur.

Re-add the finer states when the engine moves off-box — that is exactly when they start
carrying information.

### 6.2 Rules

- Transitions happen **only** in `apps/analyses/services.py`. No view, task or admin action
  sets `status` directly.
- Terminal states never transition again. Guard every transition.
- `error_summary` must be safe to show a researcher: no stack traces, no file paths, no
  credentials. Full detail goes to the log with the run id as correlation key.
- **Cancellation is cooperative.** `POST /runs/{id}/cancel` sets `cancel_requested=True`. The
  engine's progress callback returns a "should stop" signal, and the pipeline checks it between
  stages. There is no thread killing.
- **Result persistence is one atomic transaction.** Candidates, metrics and artifacts are
  written together with the `COMPLETED` status. A partially-imported run must be impossible.

---

## 7. HTTP API

Single surface, built with **django-ninja** (see ADR 0004). Everything under `/api/`.
The OpenAPI document is auto-generated at `/api/openapi.json` — the React app can generate a
typed client from it, giving us the maps' "Central Typed API Client" at near-zero cost.

```
POST   /api/auth/login                     Session login  {username, password}
POST   /api/auth/logout
GET    /api/auth/me                        Current user, or 401

GET    /api/projects                       List (owner-scoped)
POST   /api/projects
GET    /api/projects/{id}
PATCH  /api/projects/{id}
DELETE /api/projects/{id}

GET    /api/projects/{id}/datasets
POST   /api/projects/{id}/datasets         multipart; validates + checksums synchronously
GET    /api/datasets/{id}
DELETE /api/datasets/{id}                  409 if referenced by any run

GET    /api/projects/{id}/runs
POST   /api/projects/{id}/runs             → 202 {id, status:"QUEUED"}; honours Idempotency-Key
GET    /api/runs/{id}                      ★ the polling endpoint
POST   /api/runs/{id}/cancel

GET    /api/runs/{id}/candidates           paginated · ?sort= ?gate_family= ?include_rejected=
GET    /api/candidates/{id}                full detail incl. metrics
GET    /api/runs/{id}/artifacts
GET    /api/artifacts/{id}/download        ★ authorized file serve, never static
GET    /api/runs/{id}/export.csv           flat candidate × metric table

GET    /api/candidates/{id}/annotations
POST   /api/candidates/{id}/annotations
DELETE /api/annotations/{id}

GET    /api/health                         liveness
GET    /api/version                        app version, engine version, schema versions
```

### 7.1 The polling contract

`GET /api/runs/{id}` is called every ~3 seconds by the SPA while a run is active. It must stay
cheap — no joins across candidates.

```jsonc
{
  "id": "…", "status": "RUNNING", "stage": "Evaluating gate designs",
  "progress_pct": 62, "error_summary": null, "warnings": [],
  "submitted_at": "…", "started_at": "…", "finished_at": null,
  "counts": { "candidates": 0, "artifacts": 0 }
}
```

### 7.2 API rules

- **Authorization on every object read and write.** Helper: `get_owned_or_404(model, id, user)`.
  Staff users bypass. There is no other permission logic in v1 — but there is no endpoint
  without this check either.
- Errors use a single envelope: `{"error": {"code": "...", "message": "...", "detail": {...}}}`.
- The API never returns filesystem paths, storage internals, engine tracebacks or settings.
- Uploads are capped (`DATA_UPLOAD_MAX_MEMORY_SIZE`, plus an explicit dataset size limit).
- Write endpoints require CSRF; the SPA reads the `csrftoken` cookie (same-origin, so this
  works without configuration).

---

## 8. Frontend integration

The existing **Lovable / React** application is kept and lives in `frontend/`.

**Decision: serve it same-origin from Django.** Vite builds into `src/static/app/`; Whitenoise
serves it in production; `config/urls.py` has a catch-all that returns `index.html` for any
non-`/api/`, non-`/admin/`, non-`/static/` path so client-side routing works.

Why this matters more than it looks:

- Session cookies work with no configuration → **no JWT, no refresh tokens, no token storage
  in the browser**, which is both simpler and safer.
- **No CORS** — no preflight, no origin allowlist, no cookie `SameSite` puzzles.
- One deployment unit, one TLS certificate, one origin to reason about.

Rules carried over from the maps that still apply:

1. No scientific computation in React components.
2. The browser never receives engine credentials, database credentials, storage paths or
   internal identifiers beyond the UUIDs the API exposes.
3. Asynchronous states are modelled explicitly — every run view handles queued, running,
   failed, cancelled and partial data.
4. All network access goes through one API client module. No `fetch` calls scattered in
   components.

**WSL note:** `npm` currently resolves to the Windows installation
(`/mnt/c/Program Files/nodejs/`). Running Vite across the WSL↔Windows filesystem boundary is
slow and produces path bugs. Install Node **inside** WSL (nvm) before doing frontend work.

---

## 9. Background work

**`django-q2` with the ORM broker.** One extra process: `python manage.py qcluster`.

- No Redis, no RabbitMQ — the queue is a table in the same SQLite file.
- Successes and failures are browsable in Django admin, which matters for a student team with
  rotating members and no on-call.
- Configured with a single worker and generous timeouts; an analysis is long-running and rare,
  and concurrency of one removes a whole class of SQLite write contention.

The only task in v1:

```python
# src/apps/analyses/tasks.py
def run_analysis(run_id: str) -> None:
    """Queued by AnalysisRun submission. Owns the RUNNING → terminal transition."""
```

Task rules:

- Tasks take **primitive arguments** (a UUID string), never model instances. They re-fetch.
- The task is a thin shell: it calls `apps/analyses/services.py`, which holds the real logic
  and is directly unit-testable without a worker running.
- Every exception path must reach a terminal state. A run stuck in `RUNNING` forever is the
  worst failure mode in the system; wrap the body in `try/except/finally`.
- Tasks must be safe to re-run. Re-running a `COMPLETED` run is a no-op.

---

## 10. Engine contract

Lives in `src/engine/contract.py`. Frozen dataclasses, no Django, no Pydantic. These fields are
deliberately the same fields the maps' `POST /v1/jobs` and result manifest carry, so the future
HTTP version is a serialisation exercise and nothing more.

```python
@dataclass(frozen=True)
class JobRequest:
    schema_version: str  # "1"
    run_id: str  # AnalysisRun.id — correlation key
    idempotency_key: str
    input_path: str  # absolute path to the dataset file
    input_checksum: str  # sha256; the engine re-verifies
    organism: str
    params: dict  # normalized snapshot, engine-defined shape
    gate_families: list[str]
    scoring_profile: str
    seed: int | None
    output_dir: str  # where the engine may write artifacts


@dataclass(frozen=True)
class MetricValue:
    name: str
    raw_value: float | None
    normalized_value: float | None
    weight: float
    direction: str  # "HIGHER_BETTER" | "LOWER_BETTER"


@dataclass(frozen=True)
class ArtifactRef:
    kind: str
    path: str  # relative to output_dir
    media_type: str
    checksum_sha256: str
    candidate_ref: str | None  # local id, links to CandidateResult.ref


@dataclass(frozen=True)
class CandidateResult:
    ref: str  # engine-local id, unique within the job
    rank: int | None
    overall_score: float | None
    gate_family: str
    logic_type: str
    triggers: dict
    design: dict
    summary: str
    metrics: list[MetricValue]
    warnings: list[str]
    is_rejected: bool
    rejection_reason: str


@dataclass(frozen=True)
class JobResult:
    schema_version: str
    engine_version: str
    status: str  # "succeeded" | "failed" | "cancelled"
    candidates: list[CandidateResult]
    artifacts: list[ArtifactRef]
    warnings: list[str]
    error: str | None  # safe, user-facing
    input_checksum: str  # echoed back, verified by the Platform
    params: dict  # echoed back for reproducibility
```

### 10.1 The client interface

```python
# src/engine/client.py
ProgressFn = Callable[[int, str], bool]  # (pct, stage) -> keep_going


class EngineClient(Protocol):
    def run(self, request: JobRequest, on_progress: ProgressFn) -> JobResult: ...
```

Two implementations in v1:

- **`MockEngine`** — deterministic. Seeded from `idempotency_key` so the same request always
  produces the same candidates. Emits realistic progress updates, sleeps briefly to make the UI
  observable, writes small real artifact files, and honours `on_progress` returning `False` by
  returning a `cancelled` result. It also has a fault-injection mode for testing failure paths.
- **`LocalEngine`** — calls `engine.pipeline`. In v1 the pipeline stages exist as stubs that
  raise `NotImplementedError`, documenting their signatures.

Selected by setting, resolved by dotted path:

```python
CERNAL_ENGINE = "engine.client.MockEngine"  # dev/test
```

### 10.2 Scientific stubs shipped in v1

Present so the shape is visible and the real work is a fill-in, not a design exercise:

- `engine/gates/base.py` — `GateFamily` ABC: `is_compatible`, `generate_designs`,
  `evaluate_design`, `emit_sequence`, `emit_artifacts`, `required_tools`.
- `engine/gates/toehold.py` — a `ToeholdGate` stub implementing the ABC.
- `engine/gates/registry.py` — name → class lookup, so gate families are pluggable.
- `engine/scoring/profiles.py` — `default-v1` profile: metric list, weights, hard filters,
  tie-breaking.
- `engine/scoring/normalize.py` — normalization rules per metric direction.
- `engine/pipeline/` — one module per stage from map 11, signatures only.

---

## 11. Testing

`pytest` + `pytest-django`. Not exhaustive coverage — targeted at the places where breakage
would be expensive or silent.

### 11.1 What gets tested

| Area | What |
|---|---|
| Boundary | `engine/` imports nothing from Django or the Platform (§11.2) |
| Engine contract | `MockEngine` is deterministic for a fixed idempotency key; honours cancellation; fault injection produces a `failed` result |
| State machine | Every legal transition; every illegal transition raises; terminal states are terminal |
| Idempotency | Submitting twice with the same key yields one run |
| Authorization | Every endpoint rejects a non-owner with 404 (not 403 — do not leak existence) |
| Persistence | A failing result import leaves the run `FAILED`, never half-imported |
| E2E | project → upload → submit → task executes → candidates readable → CSV export |

### 11.2 The boundary test

```python
# tests/test_boundary.py — the most important test in the repo
FORBIDDEN = ("django", "apps", "api", "config")


def test_engine_is_framework_free():
    """src/engine/ must not import Django or Platform code. See docs/software-design.md §3."""
    # AST-walk every .py under src/engine/, collect Import / ImportFrom module roots,
    # assert none start with a FORBIDDEN prefix. Report file and line on failure.
```

An AST scan, not a runtime import hook: it is fast, has no side effects, and catches
conditional and function-local imports too.

---

## 12. Configuration

Twelve-factor via `.env`, read by `django-environ`. `.env.example` lists every variable with a
comment and a safe default; it is the reference, and it is committed.

| Variable | Dev default | Notes |
|---|---|---|
| `DJANGO_SETTINGS_MODULE` | `config.settings.dev` | |
| `SECRET_KEY` | dev-only literal | **prod must fail loudly if unset** |
| `DEBUG` | `True` | Always `False` in prod |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | |
| `DATABASE_URL` | `sqlite:///var/cernal.db` | Postgres is a URL change, nothing more |
| `CERNAL_ENGINE` | `engine.client.MockEngine` | Dotted path to an `EngineClient` |
| `MEDIA_ROOT` | `var/media` | |
| `MAX_DATASET_MB` | `50` | |
| `LOG_LEVEL` | `INFO` | |

Settings rules:

- `base.py` holds everything shared. `dev.py` and `prod.py` import from it and override.
  There is no `if DEBUG:` branching inside `base.py`.
- `prod.py` reads secrets from the environment and **raises at import time** if a required one
  is missing. Silent insecure defaults in production are not acceptable.
- SQLite is configured with `PRAGMA journal_mode=WAL` and a busy timeout via a connection
  signal handler.

---

## 13. Build steps

Each step is independently reviewable and leaves the repository in a working state.
**Do not begin a step before the previous one's "Done when" is fully satisfied.**

### Step 0 — Scaffold

*Goal: an empty but complete and runnable skeleton.*

- `git init`; `.gitignore` covering `var/`, `.env`, `__pycache__`, `src/static/app/`,
  `node_modules/`.
- `pyproject.toml`: Django, django-ninja, django-q2, django-environ, whitenoise, gunicorn;
  dev extras pytest, pytest-django, ruff. Ruff config: line length 100, isort enabled.
- Directory tree from §4, with `__init__.py` files and `.gitkeep` where needed.
- `config/settings/{base,dev,prod}.py`, `urls.py`, `wsgi.py`; root `manage.py` with the
  `sys.path` insert.
- `apps/accounts` with the empty custom `User` and `AUTH_USER_MODEL` set. **Before any
  migration is generated.**
- `do`: an executable shell script exposing `install`, `dev`, `worker`, `test`, `lint`,
  `format`, `migrate`, `makemigrations`, `superuser`, `check`, `manage`, `reset-db`.
  Not a `Makefile` — `make` is absent from a default WSL Ubuntu image, and requiring a
  package install before the project will run at all contradicts rule 11.
- `.env.example`; `README.md` quickstart; ADRs 0001–0004; doc stubs.

**Done when:** `./do install && ./do migrate && ./do dev` serves the admin at
`localhost:8000/admin/`, `./do test` passes and `./do lint` is clean.

### Step 1 — Engine contract + MockEngine

*Goal: the seam exists and is enforced, before anything depends on it.*

- `engine/contract.py` — the dataclasses from §10, complete.
- `engine/client.py` — `EngineClient` Protocol, `MockEngine`, `LocalEngine` skeleton,
  `load_engine(dotted_path)` resolving a client by dotted path. It takes the path as an
  argument: reading `settings` here would violate §3.
- `engine/errors.py`; `engine/artifacts.py` (write file + checksum).
- Complete: `gates/base.py` (`GateFamily` ABC and its types), `gates/registry.py`,
  `scoring/profiles.py`, `scoring/normalize.py`.
- Stubs: `gates/toehold.py`, `pipeline/stages.py` (13 stage signatures).
- `tests/test_boundary.py` and `tests/engine/` determinism + cancellation tests.
- `docs/engine-contract.md`, including the field-for-field mapping to the future
  `POST /v1/jobs` payload.

**Done when:** `MockEngine.run()` returns a populated `JobResult` with real artifact files on
disk; the same idempotency key gives byte-identical candidates; the boundary test passes.
*No Django code has been written yet — that is intentional.*

### Step 2 — Domain model

*Goal: the database exists and is inspectable.*

- All eight models from §5, in their apps, with indexes on the foreign keys that the list
  endpoints filter by.
- `apps/common/`: UUID+timestamp base model, `sha256_file()` helper.
- Initial migrations.
- Django admin registrations for every model — this is the v1 back-office and it is worth the
  30 minutes: list displays, filters by status, read-only computed fields, inlines for metrics
  and annotations.
- A `seed_demo` management command creating a user, project, dataset and completed run, so the
  frontend has something to render before the API is finished.

**Done when:** `./do migrate` is clean; every model is manageable in admin;
`./do manage seed_demo` produces a browsable run.

### Step 3 — API + orchestration (the vertical slice)

*Goal: the whole product workflow works end to end against `MockEngine`. This is the milestone.*

- `api/` with the endpoints in §7, session auth, the ownership helper, the error envelope.
- `apps/datasets/services.py` — upload, checksum, synchronous validation.
- `apps/analyses/services.py` — **the state machine lives here**: `submit_run` (snapshot,
  idempotency, enqueue), `execute_run` (calls the engine, streams progress into the run row),
  `persist_result` (one atomic transaction), `cancel_run`.
- `apps/analyses/tasks.py` — the thin `run_analysis` shell.
- django-q2 configured; `./do worker`.
- Tests: state machine, idempotency, authorization, atomic persistence, and the full E2E.

**Done when:** with `./do dev` and `./do worker` running, a scripted client can create a
project, upload a dataset, submit a run, watch `progress_pct` climb via polling, and read back
ranked candidates with metrics and downloadable artifacts. **The product is now real; only the
science is fake.**

### Step 4 — Frontend integration

*Goal: the Lovable app drives the real backend.*

- Vendor `frontend/` into the repo. Install Node **inside WSL** first.
- Vite: `base: "/static/app/"`, build output to `src/static/app/`.
- Replace mock data with one API client module generated from `/api/openapi.json`.
- Wire login, project list, dataset upload with progress, run configuration, the run progress
  view (3s polling with backoff on error), the results explorer, annotations, CSV export.
- SPA catch-all route in `config/urls.py`; Whitenoise for static.
- `./do build-frontend`, and `./do dev` builds the frontend if it is missing.

**Done when:** a researcher completes the full workflow in the browser, logged in, with no CORS
configuration and no token handling anywhere in the client.

### Step 5 — Real science

*Goal: swap the fake engine for the real one. Steps 2–4 do not change.*

- Implement `engine/pipeline/` stages: validate → preprocess → trigger generation → trigger
  evaluation → gate generation → gate evaluation → circuit construction → normalize → score →
  rank/filter → artifacts.
- Implement `ToeholdGate` against the `GateFamily` ABC.
- Finalize the `default-v1` scoring profile and its metric definitions.
- Add scientific dependencies (numpy, pandas, ViennaRNA or equivalent).
- Switch `CERNAL_ENGINE=engine.client.LocalEngine`.
- Keep `MockEngine` — it remains the engine used by CI and by frontend development.

**Done when:** a real dataset produces scientifically meaningful ranked candidates, and the
entire diff is confined to `src/engine/`.

### Step 6 — VPS deployment

*Goal: reachable, backed up, restartable.*

- `deploy/`: Caddyfile (automatic TLS), `cernal-web.service` (gunicorn), `cernal-worker.service`
  (qcluster), `backup.sh` (`sqlite3 .backup` + `var/media/` archive, nightly cron).
- `config/settings/prod.py`: `DEBUG=False`, real `ALLOWED_HOSTS`, `SECURE_*` headers, HSTS,
  file logging with rotation.
- `docs/deployment.md`: provision → deploy → migrate → restart → restore-from-backup runbook.
- Optional at this point: switch `DATABASE_URL` to Postgres. One variable.

**Done when:** the app is live over HTTPS, both services restart on boot, a nightly backup
exists, and a restore has been tested at least once.

---

## 14. Rules for agents working in this repository

1. **Read this document before changing architecture.** If a change contradicts it, update
   this document in the same commit, with the reason.
2. **Never import Django from `src/engine/`.** §3. The test will catch you; understand why it
   exists before trying to work around it.
3. **Never import `engine.pipeline`, `engine.gates` or `engine.scoring` from Platform code.**
   Only `engine.contract` and `engine.client`.
4. **Business logic goes in `services.py`**, not in views, tasks, models or admin. Views parse
   and authorize; tasks are shells; services decide.
5. **State transitions only through `apps/analyses/services.py`.**
6. **Every object endpoint checks ownership.** No exceptions, including "internal" ones.
7. **A submitted run is immutable.** Changing a project never rewrites a submitted run's
   `params_snapshot`.
8. **Rejected candidates are stored with a reason.** Never filter them away silently.
9. **All mutable state lives in `var/`.** `rm -rf var/ && ./do migrate` must yield a clean
   system.
10. **Do not add a service** (Redis, Celery, Postgres, Docker, nginx, S3) without first writing
    an ADR in `docs/decisions/` explaining what broke without it.
11. **Do not add a dependency** that only saves a few lines. Every dependency is a future
    upgrade problem for a student team.
12. **Prefer boring.** This project is maintained by rotating iGEM members. Clever code is a
    liability.
13. **Update §0** when a build step completes.

---

## 15. Environment notes (WSL)

Two issues to settle at Step 0.

**Python version — settled in Step 0.** The system interpreter was 3.14.4, and scientific
wheels (ViennaRNA especially) lag new CPython releases by months. Discovering that at Step 5,
with the whole product built on 3.14, would be an expensive migration. The project is now
pinned to **3.13** via `requires-python` in `pyproject.toml` and `.python-version`, with
`uv` managing the toolchain:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"   # add to ~/.bashrc
uv python install 3.13
```

`uv` reads both pins automatically, so `./do install` provisions the right interpreter with
no further action. The system 3.14 is untouched.

**`npm` resolves to the Windows installation** (`/mnt/c/Program Files/nodejs/`). Vite across
the WSL↔Windows filesystem boundary is slow and produces path bugs. Install Node inside WSL via
nvm before Step 4.

Keep the repository on the **Linux filesystem** (`/home/...`), never under `/mnt/c/`.
Filesystem performance and file-watching both degrade badly across the boundary.

---

## 16. Growth path

None of these are v1 work. They are recorded so that when the trigger fires, the move is known
and small.

| Trigger | Move |
|---|---|
| Engine needs more compute than the VPS has | Add `engine/service.py` (FastAPI) + `HttpEngineClient`; set `CERNAL_ENGINE`. §3. |
| Slurm access granted | Add `engine/providers/` with the `ComputeProvider` interface from map 14, behind the engine — the Platform never learns about it |
| SQLite write contention | `DATABASE_URL` → Postgres; run migrations |
| Queue depth or multi-machine workers | django-q2 → Redis broker, or Celery |
| Disk pressure / multi-host | `django-storages` → S3-compatible; `Artifact.file` is already an abstraction |
| External collaborators | Re-introduce `Workspace` + `WorkspaceMembership` + role checks (maps 05, 16) |
| Two teams blocking each other | Split into `cernal-platform` / `cernal-engine` (map 19); the contract is already frozen |

---

## 17. Reference: Design Maps index

The original vault lives in `Design Maps/` and opens as an Obsidian vault. Maps most worth
consulting during v1:

| Map | Why |
|---|---|
| 02 Researcher Workflow | The 12-step user journey v1 implements |
| 05 Platform Domain and Database | Full entity set; §5 is the subset |
| 07 Platform Run State Machine | Full state set; §6 is the subset |
| 08 Platform-Engine API Contract | The contract §10 mirrors — read before changing `contract.py` |
| 11 Scientific Pipeline | The stage list Step 5 implements |
| 12 Gate and Scoring Architecture | `GateFamily` and metric design — read before Step 5 |
| 03 Frontend Architecture | Screen inventory and frontend rules |
| 20 Implementation Roadmap | The 11-phase original; §13 compresses it to 7 |
