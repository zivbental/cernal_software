# Domain model reference

Eight models, down from the fifteen entities in design map 05. The architectural
reasoning for the cuts is in [software-design.md §5](software-design.md); this document
is the field-level reference for what actually exists.

UUID primary keys throughout — identifiers appear in URLs and are handed to the engine,
so they must not leak row counts or be guessable by increment.

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

---

## `accounts.User`

`AbstractUser`, intentionally empty. Declared at Step 0 **before the first migration** —
swapping `AUTH_USER_MODEL` afterwards is a well-known Django trap.

Workspaces, memberships and roles from design map 05 are **not** implemented. An iGEM
team is one trusted group; authorization is "is this object mine, or am I staff".
Re-add when external collaborators need scoped access.

## `projects.Project`

| Field | Type | Notes |
|---|---|---|
| `id` | UUID pk | |
| `owner` | FK → User, PROTECT | Deleting an account never orphans research |
| `name` | Char(200) | Unique per owner |
| `organism` | Char(100) | |
| `biological_objective` | Text | Base state, target state, desired logic |
| `created_at` / `updated_at` | DateTime | |

Editing a project never rewrites a submitted run (rule 7).

## `datasets.Dataset`

**Immutable.** Re-uploading creates a new row — the Dataset *is* the version, which is
why map 05's separate `DatasetVersion` table is unnecessary.

| Field | Type | Notes |
|---|---|---|
| `id` | UUID pk | |
| `project` | FK → Project, CASCADE | |
| `name` | Char(200) | |
| `file` | FileField | `var/media/datasets/<id>/<name>` |
| `checksum_sha256` | Char(64), read-only | Computed once on upload |
| `size_bytes` | BigInt, read-only | |
| `schema_version` | Char(20) | Format this was validated against |
| `validation_status` | `PENDING` · `VALID` · `INVALID` | |
| `validation_report` | JSON | Columns, row counts, errors, warnings |
| `uploaded_by` | FK → User, PROTECT | |
| `created_at` | DateTime | |

`is_usable` → only a `VALID` dataset may be submitted.

Validation is **synchronous on upload** and deliberately shallow: readable file,
expected columns, sane row count, parseable numerics. Deep scientific validation belongs
to the engine and happens at run time.

## `analyses.AnalysisRun`

The centre of the product. **Immutable once submitted.**

| Field | Type | Notes |
|---|---|---|
| `id` | UUID pk | Also the external run identifier |
| `project` / `dataset` | FK, **PROTECT** | Results never outlive their inputs |
| `created_by` | FK → User, PROTECT | |
| `idempotency_key` | Char(64), **unique** | A retry must not launch a second computation |
| `params_snapshot` | JSON | Full normalized configuration, frozen at submission |
| `gate_families` | JSON list | |
| `scoring_profile` | Char(50) | |
| `seed` | Int, null | |
| `status` | see below | |
| `stage` | Char(100) | Human-readable, shown to the user |
| `progress_pct` | Int 0–100 | DB-enforced bounds |
| `cancel_requested` | Bool | Cancellation is cooperative |
| `engine_version` | Char(50) | Recorded at completion |
| `error_summary` | Text | Safe to show a researcher |
| `warnings` | JSON list | |
| `submitted_at` / `started_at` / `finished_at` | DateTime, null | |

**Collapsed from map 05:** `AnalysisConfiguration` → `params_snapshot`;
`EngineJobReference` → `engine_version` + `status` + `stage`; `ResultManifestRecord` →
`engine_version` + `params_snapshot` + artifact checksums.

### States

```
DRAFT ──submit──► QUEUED ──worker──► RUNNING ──► COMPLETED
                    │                   │
                    │                   ├──► FAILED
                    └────cancel─────────┴──► CANCELLED
```

`ALLOWED_TRANSITIONS` in `apps/analyses/models.py` is the specification, and is asserted
by `tests/test_models.py`. Terminal states have no outgoing edges.

Helpers: `is_terminal`, `is_active`, `can_transition_to(status)`.

> Transitions happen **only** in `apps/analyses/services.py` (rule 5). Django admin
> renders `status` read-only and refuses to create runs, so admin cannot be used to
> sidestep this.

## `results.Candidate`

| Field | Type | Notes |
|---|---|---|
| `id` | UUID pk | |
| `run` | FK → AnalysisRun, CASCADE | |
| `engine_ref` | Char(50) | The engine's local id; unique per run |
| `rank` | Int, null | Null for rejected candidates |
| `overall_score` | Float, null | 0–1, higher is better |
| `gate_family` / `logic_type` | Char(50) | |
| `triggers` / `design` | JSON | Sequences, structure, logic graph |
| `summary` | Text | |
| `warnings` | JSON list | |
| `is_rejected` | Bool | |
| `rejection_reason` | Text | |

### Database-enforced invariants

| Constraint | Guarantees |
|---|---|
| `rejected_candidates_carry_a_reason` | **Rule 8** — a rejected candidate with no reason cannot be written |
| `rejected_candidates_are_unranked` | Rejected candidates never occupy a rank |
| `unique_engine_ref_per_run` | A result manifest cannot be imported twice into one run |

Rule 8 lives in the schema rather than in a code path, so no future import path, admin
action or data migration can quietly drop the reason.

## `results.CandidateMetric`

A table rather than a JSON blob, so the comparison UI can sort and filter in SQL.

| Field | Type |
|---|---|
| `candidate` | FK → Candidate, CASCADE |
| `name` | Char(100) |
| `raw_value` | Float, null |
| `normalized_value` | Float, null — 0–1, 1 is best |
| `weight` | Float |
| `direction` | `HIGHER_BETTER` · `LOWER_BETTER` |

Unique per `(candidate, name)`. Both raw and normalized values are kept: the researcher
is shown the decomposition, never a single opaque score (design map 12).

## `results.Artifact`

| Field | Type | Notes |
|---|---|---|
| `id` | UUID pk | |
| `run` | FK → AnalysisRun, CASCADE | |
| `candidate` | FK → Candidate, null | Null = run-level artifact |
| `kind` | Char(50) | `sequence_fasta`, `design_table`, `logic_graph`, `plot`, `report` |
| `file` | FileField | `var/media/artifacts/<run id>/<relative path>` |
| `media_type` | Char(100) | |
| `checksum_sha256` | Char(64), read-only | Verified on import |
| `size_bytes` | BigInt, read-only | |

Subdirectories from the engine's artifact paths are preserved, so `sequences/x.fasta`
and `plots/x.fasta` cannot collide. Path traversal and absolute paths are stripped.

> Artifacts are **never** served by a static file handler. They go through an authorized
> download view that checks run ownership (§7.2).

## `results.Annotation`

Product-owned and entirely independent of engine output, so decisions survive re-runs.

| Field | Type |
|---|---|
| `candidate` | FK → Candidate, CASCADE |
| `author` | FK → User, PROTECT |
| `text` | Text |
| `decision_tag` | `NONE` · `PINNED` · `SHORTLISTED` · `REJECTED` · `SYNTHESIZE` |
| `created_at` | DateTime |

---

## Deletion behaviour

| Action | Result |
|---|---|
| Delete a run | Candidates, metrics, artifacts and annotations go with it |
| Delete a dataset used by a run | **Blocked** (PROTECT) |
| Delete a project with runs | **Blocked** (PROTECT) |
| Delete a project with only datasets | Datasets cascade |
| Delete a user with projects | **Blocked** (PROTECT) |

Deleting demo data therefore requires dependency order — see `_reset()` in
`apps/common/management/commands/seed_demo.py`.

## Importing an engine result

`apps.results.services.import_job_result(run, result, output_dir)` writes a `JobResult`
into these tables **atomically**: either the whole result lands or none of it does. It
verifies the manifest's input checksum against the dataset, verifies every artifact's
checksum, links candidate-level artifacts to their candidate, and refuses to import
twice into the same run.

It deliberately does **not** touch `run.status` — transitions belong to
`apps/analyses/services.py` (rule 5).

## Seeing it populated

```bash
./do manage seed_demo --candidates 24
./do dev     # then browse http://localhost:8000/admin/
```

`seed_demo` drives `MockEngine` through the real import path, so what lands in the
database is exactly what Step 3's run lifecycle will produce — not hand-written fixtures
that drift away from reality.
