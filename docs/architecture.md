# CERNAL — Architecture

> **Read this first.** The authoritative reference for how the CERNAL software product is
> structured. It exists so that any developer or AI agent joining the project can act
> without re-deriving the architecture or re-litigating decisions already made.
>
> - **Audience:** developers and AI coding agents working in this repository.
> - **Supersedes:** the `Design Maps/` Obsidian vault, for implementation purposes. The
>   maps remain the long-term north star; this document is what we actually build.
> - **Future work is not here.** It is in [ROADMAP.md](ROADMAP.md).

| Looking for | Go to |
|---|---|
| What is built, what is next, open questions | [ROADMAP.md](ROADMAP.md) |
| Input modes, organisms, gate chemistries, payloads | [modalities.md](modalities.md) |
| How the scientific engine is built inside its boundary | [engine.md](engine.md) |
| Field-level model reference | [domain-model.md](domain-model.md) |
| Endpoint reference | [api.md](api.md) |
| Running it day to day | [development.md](development.md) |
| Where it runs in production | [deployment.md](deployment.md) |

---

## 1. Context and goal

CERNAL is a research tool for an **iGEM** team. A researcher supplies a transcriptomic
signal — either a differential-expression table or a trigger mRNA directly — defines a
biological objective, configures an analysis, and receives a ranked list of candidate RNA
logic circuits with scores, metrics, sequences and downloadable artifacts.

**Expected load: a few dozen users, roughly 5 analyses per day.** This number drives every
decision in this document. It is not a placeholder — it is the reason the architecture
below looks the way it does.

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

That design is correct for a mature product with a dedicated ops owner. At 5 analyses/day
it costs far more than it returns: two repositories, two deployment units, two
authentication systems, a network boundary to version and test, and four long-running
background services — before a single researcher can run an analysis.

**The goal of v1 is a working end-to-end product on one small VPS, with the architectural
seams placed exactly where the maps say they belong, so that growing into the full design
is a series of local substitutions rather than a rewrite.**

### 1.3 The one idea we preserve at full strength

The **Platform / Engine boundary**. In v1 it is a *module* boundary rather than a *network*
boundary, but it is enforced just as strictly ([§3](#3-the-boundary-rule)). The Platform
never calls scientific code directly; it goes through an `EngineClient` interface. The day
one machine is no longer enough, `engine/` is wrapped in a thin service and `LocalEngine`
is swapped for another implementation. Nothing else in the codebase changes.

---

## 2. Simplification ledger

Every row is a deliberate decision, with the condition that should make us revisit it.

| Concern | Design Maps | v1 | Rationale | Re-add when |
|---|---|---|---|---|
| Repositories | 2 (`cernal-platform`, `cernal-engine`) | 1 | Two repos need two CI pipelines, two release cadences, a shared contract package | Two teams are genuinely blocking each other |
| Deploy units | Platform + Engine services | 1 web process + 1 worker process | One `systemd` unit each on one VPS | Engine needs to scale or move off-box |
| Engine transport | Versioned REST + OpenAPI + contract tests | Python `Protocol` + frozen dataclasses | Same field-for-field payload shape, checked by the type system instead of serialised | Engine moves off-box |
| Task queue | Redis + Celery | `django-q2`, ORM broker | No broker service to run or back up; tasks and failures are visible in Django admin | Sustained queue depth, or multi-machine workers |
| Database | PostgreSQL | SQLite in WAL mode | At this volume SQLite is genuinely sufficient; backup is copying one file | Concurrent writers cause lock contention |
| File storage | Object storage + signed URLs | `FileField` into `var/media/` | Identical `storage_ref` + `checksum` model, local backend | Disk pressure, or multi-host serving |
| Compute | `ComputeProvider` adapter → Slurm | Runs inline in the worker process | No Slurm access is needed to build the product | Analyses exceed the VPS's memory/time budget |
| Domain entities | 15 | 8 | See [§5](#5-domain-model) | Multi-tenancy or dataset lineage becomes real |
| Run states | 14 | 6 | See [§6](#6-run-state-machine) | Users need finer-grained failure recovery |
| Auth | Identity service, workspaces, roles, object-level permissions | Django auth + per-object ownership check | An iGEM team is one trusted group | External collaborators get accounts |
| Frontend | React SPA + typed API client | **Kept** — existing Lovable app, served same-origin by Django | Already built; same-origin removes CORS and token handling | — |
| Notifications / audit / export services | Separate services | Model fields, Django admin, CSV endpoints | Services with one caller are not services | Real audit requirements appear |
| Observability | Structured logs, metrics, alerting | Django logging to file + `qcluster` admin views | — | The VPS has users depending on uptime |

### 2.1 Explicitly kept from the maps

These cost almost nothing now and are expensive to retrofit:

1. **Immutable run submissions.** An `AnalysisRun` snapshots its full parameter set as JSON
   at submit time. Editing a project never mutates a submitted run.
2. **Idempotency keys.** Every run submission carries one. Re-submitting the same key
   returns the existing run instead of launching a second expensive computation.
3. **Checksums** on every dataset input and every produced artifact.
4. **Versioned scoring profiles** recorded on the run, so a score is always interpretable.
5. **`GateFamily` plugin interface** — the core scientific extensibility seam.
6. **Explicit rejection reasons** on candidates. Rejected candidates are stored, not
   silently dropped.
7. **A deterministic mock engine**, so product work never waits on scientific work.
8. **Product-facing status vocabulary** distinct from engine-internal stages.

---

## 3. The boundary rule

> **`src/engine/` must never import Django, and must never import from `src/apps/`,
> `src/api/` or `src/config/`.**

This is the single invariant that keeps v1 upgradeable into the full design. It is enforced
by an automated test (`tests/test_boundary.py`, [§11](#11-testing)), not by convention.

Consequences that follow from it, and which agents must respect:

- `engine/` receives **plain paths and dataclasses**, never Django model instances,
  `QuerySet`s, `Request` objects or `settings`.
- `engine/` never writes to the database. It returns a `JobResult`; the Platform persists it.
- `engine/` never reads Django settings. Configuration arrives inside `JobRequest`.
- Conversely, `apps/` and `api/` never import from `engine.pipeline`, `engine.gates`,
  `engine.stages`, `engine.gates.tools` or `engine.scoring`. They may import only
  `engine.contract` and `engine.client`.

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
     │   engine/{contract,client,domain,pipeline,stages,gates,tools,scoring}│
     │   no django · no db · no settings · no http                          │
     └──────────────────────────────────────────────────────────────────────┘
```

**Swapping in the real architecture later:** add a service exposing `POST /v1/jobs`,
`GET /v1/jobs/{id}`, `GET /v1/jobs/{id}/result`, `POST /v1/jobs/{id}/cancel`, serialising
the same dataclasses. Add a client implementing the same `Protocol`. Change one setting.
The Platform is untouched. [deployment.md](deployment.md) works this through concretely.

---

## 4. Repository layout

```
cernal/
├── README.md                     Quickstart only; design lives in docs/
├── pyproject.toml                Deps, ruff, pytest config
├── do                            Task runner: ./do dev | test | lint | migrate …
├── manage.py                     At root; inserts src/ onto sys.path
├── .env.example                  Every env var, documented, with safe defaults
│
├── docs/                         See docs/README.md
│
├── src/
│   ├── config/                   Django project
│   │   ├── settings/{base,dev,prod}.py
│   │   ├── urls.py               /api/ → ninja, /admin/, SPA catch-all
│   │   └── wsgi.py · asgi.py
│   │
│   ├── apps/                     Django apps — product logic only
│   │   ├── accounts/             Custom User + admin approval
│   │   ├── common/               Base models, checksums, SQLite pragmas
│   │   ├── projects/             Project
│   │   ├── datasets/             Dataset + upload validation
│   │   ├── analyses/             AnalysisRun, orchestration, the queue task
│   │   ├── results/              Candidate, CandidateMetric, Artifact, Annotation
│   │   └── web/                  The SPA catch-all view
│   │
│   ├── api/                      The ONLY HTTP surface
│   │   ├── __init__.py           NinjaAPI instance
│   │   ├── schemas.py            Request/response models
│   │   ├── auth.py               Session auth + ownership checks
│   │   ├── errors.py             The single error envelope
│   │   └── routers/              auth · projects · datasets · runs · results · meta
│   │
│   ├── engine/                   ★ NO DJANGO. See §3, and engine.md
│   │   ├── contract.py           JobRequest · JobResult · CandidateResult · …
│   │   ├── client.py             EngineClient Protocol · MockEngine · LocalEngine
│   │   ├── domain.py             The scientific vocabulary
│   │   ├── errors.py             EngineError hierarchy
│   │   ├── artifacts.py          Checksummed artifact writing
│   │   ├── pipeline.py           Composition only
│   │   ├── store.py              CandidateStore · ParetoFilter
│   │   ├── stages/               Six pipeline stages + QC
│   │   ├── gates/                GateFamily ABC · registry · toehold · antisense · crispr
│   │   ├── tools/                S1–S9 scientific primitives
│   │   └── scoring/              Normalization, weighting, filters, ranking
│   │
│   └── static/app/               Vite build output (gitignored)
│
├── frontend/                     React application (Lovable origin)
├── tests/
│   ├── test_boundary.py          ★ Enforces §3
│   ├── engine/ · api/ · e2e/
├── var/                          gitignored — all mutable state
│   ├── cernal.db · media/datasets/ · media/artifacts/ · logs/
└── deploy/                       Deployment configuration
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
- **`./do` replaces a `Makefile`.** `make` is not present on a default WSL Ubuntu image and
  installing it needs root; a dependency-free shell script keeps "clone and run" true.

---

## 5. Domain model

Eight models, down from fifteen. UUID primary keys throughout, because identifiers appear
in URLs and are handed to the engine.

```
User ──┬── Project ──┬── Dataset ────┐
       │             │               │
       │             └── AnalysisRun ┘  (PROTECT both)
       │                     │
       │                     ├── Candidate ──┬── CandidateMetric
       │                     │               ├── Artifact
       │                     │               └── Annotation ── User
       │                     └── Artifact (run-level)
       └── Annotation
```

| Model | Role |
|---|---|
| `accounts.User` | `AbstractUser`, intentionally empty. Self-service registration, **admin-approved** |
| `projects.Project` | Owner, name, organism, biological objective |
| `datasets.Dataset` | **Immutable.** Re-uploading creates a new row — the Dataset *is* the version |
| `analyses.AnalysisRun` | The centre of the product. **Immutable once submitted** |
| `results.Candidate` | One proposed circuit, ranked or rejected-with-reason |
| `results.CandidateMetric` | A table rather than a JSON blob, so the comparison UI sorts in SQL |
| `results.Artifact` | A produced file, checksummed, served only through an authorized view |
| `results.Annotation` | Product-owned decisions, independent of engine output. Survive re-runs |

**Field-level detail is in [domain-model.md](domain-model.md).** Three things that belong
here because they are architecture rather than schema:

- **`AUTH_USER_MODEL` was set before the first migration.** Swapping the user model after
  migrations exist is a well-documented Django trap. This was free insurance.
- **Dropped from the maps:** `Workspace`, `WorkspaceMembership`, `DatasetVersion`,
  `AnalysisConfiguration`, `EngineJobReference`, `ResultManifestRecord`. The last three
  collapse into `params_snapshot` + `engine_version` + `status` + `stage` + artifact
  checksums.
- **Rule 8 lives in the schema, not in a code path.** A rejected candidate without a reason
  cannot be written at all, so no future import path, admin action or data migration can
  quietly drop it.

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
`SUBMITTING` and `IMPORTING RESULTS` were artifacts of a network boundary: with an
in-process engine, submission is a database write and result import is the same transaction
that ends the run. `VALIDATION FAILED` lives on `Dataset.validation_status`.
`SUBMISSION FAILED` cannot occur.

Re-add the finer states when the engine moves off-box — that is exactly when they start
carrying information.

### 6.2 Rules

- Transitions happen **only** in `apps/analyses/services.py`. No view, task or admin action
  sets `status` directly. Django admin renders `status` read-only and refuses to create runs.
- Terminal states never transition again. Guard every transition.
- `error_summary` must be safe to show a researcher: no stack traces, no file paths, no
  credentials. Full detail goes to the log with the run id as correlation key.
- **Cancellation is cooperative.** `POST /runs/{id}/cancel` sets `cancel_requested=True`.
  The engine's progress callback returns a "should stop" signal, and the pipeline checks it
  between stages. There is no thread killing.
- **Result persistence is one atomic transaction.** Candidates, metrics and artifacts are
  written together with the `COMPLETED` status. A partially-imported run must be impossible.

---

## 7. HTTP API

Single surface, built with **django-ninja** ([ADR 0004](decisions/0004-django-ninja-over-drf.md)).
Everything under `/api/`. **32 endpoints.** The OpenAPI document is auto-generated at
`/api/openapi.json`, giving the maps' "Central Typed API Client" at near-zero cost.

**The endpoint reference is [api.md](api.md).** What belongs here is the shape:

```
/api/auth/…            csrf · register · login · logout · me
/api/projects…         CRUD, owner-scoped
/api/…/datasets…       upload (multipart, validated synchronously) · examples · delete
/api/…/runs…           submit (202) · poll ★ · detail · cancel
/api/…/candidates…     list · detail · artifacts · download ★ · export.csv
/api/…/annotations…    list · create · delete
/api/health · version  liveness · app + engine versions + engine capabilities
```

### 7.1 The polling contract

`GET /api/runs/{id}` is called every ~3 seconds by the SPA while a run is active. It must
stay cheap — no joins across candidates.

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
- **404, never 403, for objects you do not own.** Returning 403 for an object that exists
  would confirm its existence to someone who should not know.
- Errors use a single envelope: `{"error": {"code": …, "message": …, "detail": {…}}}`.
- The API never returns filesystem paths, storage internals, engine tracebacks or settings.
- Artifacts are **never** served by a static file handler — always through an authorized
  download view that checks run ownership.
- Uploads are capped (`DATA_UPLOAD_MAX_MEMORY_SIZE`, plus an explicit dataset size limit).
- Write endpoints require CSRF; the SPA reads the `csrftoken` cookie (same-origin, so this
  works without configuration).

---

## 8. Frontend integration

The existing **Lovable / React** application is kept and lives in `frontend/`.

**Decision: serve it same-origin from Django**
([ADR 0003](decisions/0003-same-origin-spa-session-auth.md),
[ADR 0005](decisions/0005-static-spa-not-tanstack-start.md)). Vite builds into
`src/static/app/`; Whitenoise serves it in production; `config/urls.py` has a catch-all
returning `index.html` for any non-`/api/`, non-`/admin/`, non-`/static/` path so
client-side routing works.

Why this matters more than it looks:

- Session cookies work with no configuration → **no JWT, no refresh tokens, no token
  storage in the browser**, which is both simpler and safer.
- **No CORS** — no preflight, no origin allowlist, no cookie `SameSite` puzzles.
- One deployment unit, one TLS certificate, one origin to reason about.

Rules carried over from the maps that still apply:

1. **No scientific computation in React components.** Anything the mockup displays that the
   engine does not yet produce is a *scientific output* and belongs in `src/engine/`.
2. The browser never receives engine credentials, database credentials, storage paths or
   internal identifiers beyond the UUIDs the API exposes.
3. Asynchronous states are modelled explicitly — every run view handles queued, running,
   failed, cancelled and partial data.
4. All network access goes through one API client module. No `fetch` calls scattered in
   components.
5. **Metrics render from data, not from a hardcoded list.** A metric with no display-name
   entry shows its raw name. Adding a metric therefore needs no frontend release.

**WSL note:** install Node **inside** WSL (nvm) before doing frontend work. Running Vite
across the WSL↔Windows filesystem boundary is slow and produces path bugs.

---

## 9. Background work

**`django-q2` with the ORM broker** ([ADR 0002](decisions/0002-sqlite-and-orm-task-queue.md)).
One extra process: `python manage.py qcluster`.

- No Redis, no RabbitMQ — the queue is a table in the same SQLite file.
- Successes and failures are browsable in Django admin, which matters for a student team
  with rotating members and no on-call.
- One worker, generous timeouts. An analysis is long-running and rare, and concurrency of
  one removes a whole class of SQLite write contention.
- `max_attempts = 1` — an expensive scientific computation must never be silently re-run.
  `retry` is set above `timeout` so django-q2 does not re-queue a task that is still running.

The only task:

```python
# src/apps/analyses/tasks.py
def run_analysis(run_id: str) -> None:
    """Queued by AnalysisRun submission. Owns the RUNNING → terminal transition."""
```

Task rules:

- Tasks take **primitive arguments** (a UUID string), never model instances. They re-fetch.
- The task is a thin shell: it calls `apps/analyses/services.py`, which holds the real logic
  and is directly unit-testable without a worker running.
- Every exception path must reach a terminal state. **A run stuck in `RUNNING` forever is
  the worst failure mode in the system**; wrap the body in `try/except/finally`.
- Tasks must be safe to re-run. Re-running a `COMPLETED` run is a no-op.
- Runs are enqueued in `transaction.on_commit`, so the worker can never pick up a run that
  is not yet visible.

---

## 10. Engine contract

Lives in `src/engine/contract.py`: frozen dataclasses, no Django, no Pydantic. The fields
are deliberately the ones the maps' `POST /v1/jobs` and result manifest carry, so the
future HTTP version is a serialisation exercise and nothing more.

```python
ProgressFn = Callable[[int, str], bool]  # (pct, stage) -> keep_going


class EngineClient(Protocol):
    def run(self, request: JobRequest, on_progress: ProgressFn) -> JobResult: ...
    def capabilities(self) -> EngineCapabilities: ...
```

| Implementation | Purpose |
|---|---|
| `MockEngine` | Deterministic fake science. **The default**, and what CI and frontend work use |
| `LocalEngine` | The real pipeline, in-process. Raises `NotImplementedError` until Step 5 |

Selected by dotted path: `CERNAL_ENGINE = "engine.client.MockEngine"`. `load_engine` takes
the path **as an argument** rather than reading `settings` itself — `engine/` may not import
Django, so the Platform passes the setting in.

**`EngineCapabilities` is why the Platform can validate a submission** without importing
`engine.gates.registry` (which [§3](#3-the-boundary-rule) forbids): the engine advertises
its gate families and scoring profiles, and `GET /api/version` surfaces them.

**Full type inventory, behavioural rules and the future HTTP mapping: [engine.md §1](engine.md).**

---

## 11. Testing

`pytest` + `pytest-django`. **415 tests.** Not exhaustive coverage — targeted at the places
where breakage would be expensive or silent.

| Area | What |
|---|---|
| **Boundary** | `engine/` imports nothing from Django or the Platform |
| Engine contract | `MockEngine` is deterministic for a fixed idempotency key; honours cancellation; fault injection produces a `failed` result |
| State machine | Every legal transition; every illegal transition raises; terminal states are terminal |
| Idempotency | Submitting twice with the same key yields one run |
| Authorization | Every endpoint rejects a non-owner with 404 (not 403 — do not leak existence) |
| Persistence | A failing result import leaves the run `FAILED`, never half-imported |
| E2E | project → upload → submit → task executes → candidates readable → CSV export |

**The boundary test is the most important test in the repo.** It is an AST scan, not a
runtime import hook: fast, no side effects, and it catches conditional and function-local
imports too.

```python
# tests/test_boundary.py
FORBIDDEN = ("django", "apps", "api", "config")
# AST-walk every .py under src/engine/, collect Import / ImportFrom module roots,
# assert none start with a FORBIDDEN prefix. Report file and line on failure.
```

**If it fails, do not add an exception to it.** The failure means Platform code has leaked
into `src/engine/`, and that is the one thing this architecture is protecting.

Testing *scientific* code is a different problem — golden tests, property tests,
determinism tests. See [engine.md §8](engine.md).

---

## 12. Configuration

Twelve-factor via `.env`, read by `django-environ`. `.env.example` lists every variable with
a comment and a safe default; it is the reference, and it is committed.

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
- `prod.py` reads secrets from the environment and **raises at import time** if a required
  one is missing. Silent insecure defaults in production are not acceptable.
- SQLite is configured with `PRAGMA journal_mode=WAL`, `synchronous=NORMAL`, a 10 s busy
  timeout and foreign key enforcement, via a `connection_created` receiver in
  `apps/common/db.py`.

---

## 13. Build history

Each step was independently reviewable and left the repository in a working state. **The
remaining steps are in [ROADMAP.md](ROADMAP.md); this is the record of what happened.**

| Step | Delivered |
|---|---|
| **0 — Scaffold** | Directory tree, settings, `./do`, empty custom `User` before the first migration, ADRs 0001–0004 |
| **1 — Engine contract + MockEngine** | `contract.py`, `client.py`, `errors.py`, `artifacts.py`, `GateFamily` ABC, registry, **scoring implemented**, the boundary test. *No Django code was written in this step — that was intentional* |
| **2 — Domain model** | 8 models, migrations, admin back-office for every model, `seed_demo` |
| **3 — API + orchestration** | 32 endpoints, session auth, ownership helper, error envelope, the run state machine in `services.py`, django-q2 worker. **The product became real; only the science was fake** |
| **4 — Frontend integration** | Vendored React app, Vite → `src/static/app/`, one API client module, login, wizard, progress, results explorer, annotations, CSV export, static pages, registration with admin approval |

**Deviations from the original plan**, recorded because they are still live decisions:

- **`./do` replaces the `Makefile`.** `make` is absent from a default WSL Ubuntu image.
- **`load_engine(dotted_path)` replaces `get_engine()`.** Reading Django settings from
  inside `engine/` would violate [§3](#3-the-boundary-rule) outright, so the function takes
  the path as an argument and the Platform passes `settings.CERNAL_ENGINE` in.
- **`EngineCapabilities` added to the contract.** The Platform must validate a submission's
  gate families and scoring profile, but §3 forbids it importing the engine's registries.
- **`GET /api/auth/csrf` added.** Session auth means writes are CSRF-protected, and an SPA
  has no server-rendered form to carry the token. Django's test client bypasses CSRF, so
  this gap only appeared when driving the API over real HTTP.
- **`Annotation` has a UUID primary key.** It was the one API-exposed model left with a
  sequential integer id, which both broke its `DELETE` route and leaked how many decisions
  had been recorded.
- **`Candidate.engine_ref` added.** The engine's local candidate id is stored so a database
  row can be traced back to the manifest that produced it, and so a manifest cannot be
  imported twice into one run.
- **`import_job_result` was pulled forward from Step 3 into Step 2.** Step 2's "done when"
  required `seed_demo` to produce a browsable run, which needs result persistence. Step 3
  still owns the run *lifecycle* — that function deliberately does not touch `run.status`.
- **`engine/scoring/` is implemented, not stubbed.** Normalization, weighting, hard filters
  and ranking are generic, science-free machinery that `MockEngine` needs in order to
  produce meaningful score decompositions. The *metric set* in `default-v1` remains
  provisional and is owned by the scientific team.
- **Input modes were added in Step 4.** `AnalysisRun` gained `input_mode`, a nullable
  `dataset`, `trigger_sequence`, and a `CheckConstraint` enforcing exactly one input source.
  See [modalities.md §1](modalities.md).

---

## 14. Rules for agents working in this repository

1. **Read this document before changing architecture.** If a change contradicts it, update
   this document in the same commit, with the reason.
2. **Never import Django from `src/engine/`.** [§3](#3-the-boundary-rule). The test will
   catch you; understand why it exists before trying to work around it.
3. **Never import the engine's internals from Platform code.** Only `engine.contract` and
   `engine.client`.
4. **Business logic goes in `services.py`**, not in views, tasks, models or admin. Views
   parse and authorize; tasks are shells; services decide.
5. **State transitions only through `apps/analyses/services.py`.**
6. **Every object endpoint checks ownership.** No exceptions, including "internal" ones.
7. **A submitted run is immutable.** Changing a project never rewrites a submitted run's
   `params_snapshot`.
8. **Rejected candidates are stored with a reason.** Never filter them away silently.
9. **All mutable state lives in `var/`.** `rm -rf var/ && ./do migrate` must yield a clean
   system.
10. **Do not add a service** (Redis, Celery, Postgres, Docker, nginx, S3) without first
    writing an ADR in [decisions/](decisions/) explaining what broke without it.
11. **Do not add a dependency** that only saves a few lines. Every dependency is a future
    upgrade problem for a student team.
12. **Prefer boring.** This project is maintained by rotating iGEM members. Clever code is a
    liability.
13. **Record future work in [ROADMAP.md](ROADMAP.md)**, not in a new planning document.

---

## 15. Environment notes (WSL)

**Python 3.13, not 3.14.** Scientific wheels — ViennaRNA especially — lag new CPython
releases by months. Discovering that at Step 5, with the whole product built on 3.14, would
be an expensive migration. The project is pinned via `requires-python` in `pyproject.toml`
and `.python-version`, with `uv` managing the toolchain. `uv` reads both pins
automatically, so `./do install` provisions the right interpreter with no further action.

**`npm` may resolve to the Windows installation** (`/mnt/c/Program Files/nodejs/`). Install
Node inside WSL via nvm before doing frontend work.

**Keep the repository on the Linux filesystem** (`/home/...`), never under `/mnt/c/`.
Filesystem performance and file-watching both degrade badly across the boundary.

Setup commands are in [development.md](development.md).

---

## 16. Growth path

Recorded so that when a trigger fires, the move is known and small. **The full table, with
the engine-specific triggers, is [ROADMAP.md §8](ROADMAP.md).**

| Trigger | Move |
|---|---|
| Engine needs more compute than the VPS has | Containerise the engine; add a client implementing the same `Protocol`; set `CERNAL_ENGINE`. [deployment.md](deployment.md) |
| Slurm access granted | Add a `ComputeProvider` interface *behind* the engine — the Platform never learns about it |
| SQLite write contention | `DATABASE_URL` → Postgres; run migrations |
| Queue depth or multi-machine workers | django-q2 → Redis broker, or Celery |
| Disk pressure / multi-host | `django-storages` → S3-compatible; `Artifact.file` is already an abstraction |
| External collaborators | Re-introduce `Workspace` + `WorkspaceMembership` + role checks |
| Two teams blocking each other | Split into `cernal-platform` / `cernal-engine`; the contract is already frozen |

---

## 17. Reference: Design Maps index

The original vault lives in `Design Maps/` and opens as an Obsidian vault. Maps most worth
consulting:

| Map | Why |
|---|---|
| 02 Researcher Workflow | The 12-step user journey v1 implements |
| 05 Platform Domain and Database | Full entity set; [§5](#5-domain-model) is the subset |
| 07 Platform Run State Machine | Full state set; [§6](#6-run-state-machine) is the subset |
| 08 Platform-Engine API Contract | The contract [§10](#10-engine-contract) mirrors — read before changing `contract.py` |
| 11 Scientific Pipeline | The stage list Step 5 implements |
| 12 Gate and Scoring Architecture | `GateFamily` and metric design — read before Step 5 |
| 03 Frontend Architecture | Screen inventory and frontend rules |
| 14 / 17 Compute Providers | Slurm, and why no public API may listen on a login node |
| 19 / 20 Repository split, Implementation Roadmap | The end state, and the 11-phase original |

*CERNAL Computational Pipeline Map* is the source for [engine.md](engine.md) and
[modalities.md](modalities.md).
