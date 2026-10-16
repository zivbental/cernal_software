# Architecture

Source baseline: `main` at `c1bb92cc085a6bad272298b81bda28c22b1d57f5` (16 October 2026).
See [status and remaining work](status.md) for verification and release limits.

## System boundary

CERNAL has a Django platform and a framework-independent scientific engine. The
platform owns accounts, uploads, queue dispatch, durable run state, result import,
annotations and authorized downloads. The engine accepts a frozen job request and
produces a result manifest and files. The browser is a same-origin React application.

Platform imports from the engine are restricted to [contract.py](../src/engine/contract.py)
and [client.py](../src/engine/client.py). Engine code must not import Django, platform
apps, API or settings. [Boundary tests](../tests/test_boundary.py) enforce this with
an AST scan, including local and type-checking imports. The supported implementation
is `engine.client.LocalEngine`; there is no supported MockEngine or cloud runner.

## Component map

| Component | Responsibility / source |
|---|---|
| React/Vite | [frontend](../frontend/), wizard, results, in-app help |
| Django Ninja | [API](../src/api/), schemas, authentication, ownership, HTTP errors |
| Accounts | [accounts](../src/apps/accounts/), approval, sessions, hashed API keys |
| Datasets | [datasets](../src/apps/datasets/), immutable uploads and validation |
| Expression catalog | [expression](../src/apps/expression/), cached public comparisons and provenance |
| Analysis services | [analyses](../src/apps/analyses/), submission, claims, cancellation and reconciliation |
| Results | [results](../src/apps/results/), checked import, metrics, files, review notes |
| Engine | [engine](../src/engine/), input → genes → triggers → gates → circuits → assembly/reporting |
| Deployment | [deploy](../deploy/), Caddy + Gunicorn + worker + reconciler on one Linux machine |

The engine builds shared tools once and injects them. Scientific records are frozen
dataclasses; CSVs are exports, not the inter-stage interface. Scoring normalization,
weights and filters have one owner in `engine.scoring`. Read [CLAUDE.md](../CLAUDE.md)
before modifying science, and use the generated [engine symbol inventory](api-surface.md)
to find existing functions. A generated `BUILT` label means a callable body exists,
not that the chemistry is experimentally validated or advertised as available.

## Submission to results

1. An authenticated user submits one input: DE dataset, direct RNA, or reference gene.
2. Services validate supported configuration, resolve gene input, freeze normalized
   parameters and sequence/reference evidence, and create a durable QUEUED run.
3. The ORM broker queues the run ID. The Linux worker acquires an atomic execution
   token before running LocalEngine; duplicate delivery cannot claim a live run.
4. Progress and cancellation callbacks cross the contract boundary. Separate file-cache
   heartbeats remain writable during long SQLite imports.
5. Engine outputs are staged by run and execution token, then validated and imported.
   Database import is atomic; files require explicit cleanup/recovery handling.
6. The platform stores candidates, raw/normalized metrics and artifact checksums.
   It writes derived summary/manifest artifacts, marks completion, and serves owner-
   authorized results subject to sequence-release restrictions.

`ALLOWED_TRANSITIONS` in [models.py](../src/apps/analyses/models.py) is authoritative:
DRAFT → QUEUED/CANCELLED; QUEUED → RUNNING/FAILED/CANCELLED;
RUNNING → COMPLETED/FAILED/CANCELLED. Terminal states have no outgoing transitions.
Cancellation is cooperative. Reconciliation can fail an expired queued or abandoned
running job and fences stale execution tokens; it does not silently rerun science.
Recovery import creates a new completed run and preserves the original failure.

## Storage and trust boundaries

SQLite (WAL/busy timeout), the ORM queue and the database-backed authentication cache
are local. Worker status uses a separate file cache. Uploaded files, artifacts, staged
results and logs live under `var/` by default. The shipped topology is single-host;
network-mounted SQLite or distributed workers need a new reviewed design.

Sessions require CSRF on writes. API keys use `X-API-Key` and scopes. Owner queries
allow staff access and otherwise conceal inaccessible objects as 404. UUIDs are
identifiers, not authorization. Artifacts must never be exposed as public `/media/`
files. Scientific release checks are additional to ownership.

## Reading paths and design history

- [Install/develop](development.md), [first run](tutorial.md), [tests](testing.md)
- [HTTP reference](api.md), [external clients](public-api.md), [data model](domain-model.md)
- [Configuration](configuration.md), [deployment](deployment.md), [operations](operations.md), [security](security.md)
- [Scientific architecture](engine.md), [interpretation](scientific-interpretation.md)
- [Architecture decisions](decisions/) retain the rationale for individual choices.

The [original architecture/design ledger](archive/operator-design/architecture.md)
is historical context, including original scope cuts and Design Maps references.
Its step numbers, old model counts, mock engine examples and future deployment ideas
are not the current implementation contract. Current behavior comes from the linked
source and tests, with remaining work tracked in [status](status.md).
