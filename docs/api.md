# HTTP API reference

Source baseline: `main` at `c1bb92cc085a6bad272298b81bda28c22b1d57f5` (16 October 2026).
See [status and remaining work](status.md) for verification and release limits.

The running service publishes `/api/openapi.json` and interactive `/api/docs`.
[Router registration](../src/api/__init__.py), [schemas](../src/api/schemas.py) and
[routers](../src/api/routers/) are the HTTP authority. The generated
[api-surface.md](api-surface.md) is an engine Python symbol inventory, not an HTTP
endpoint list. For a runnable first request use [the tutorial](tutorial.md); for
language wrappers use [external clients](public-api.md).

## Authentication and ownership

Most routes accept either session cookies or `X-API-Key`. Session writes need a CSRF
cookie from `GET /api/auth/csrf` and its value in `X-CSRFToken`; login/register/reviewer
entry points also enforce CSRF. API keys are tried first and do not require CSRF.
A supplied nonempty invalid key is rejected instead of falling back to a session.

Registration creates an inactive account pending staff approval. Login with correct
credentials for a pending account returns `pending_approval`; incorrect credentials
return a generic error. There is no email password-reset flow. Reviewer login is
configuration-controlled and must be disabled for real user data.

Key create/list/revoke/regenerate are session-only; whoami is key-only. Creation and
regeneration return the secret once, while storage retains a SHA-256 digest. `read`
permits authenticated reads and `design` implies read plus design-scoped mutations.
Dataset deletion is session-only. Do not assume every route accepts both credentials.
Keys default to 60 requests/minute and two owner-active runs; honor `Retry-After` on
429. Owner/staff checks apply independently of scope, with inaccessible objects
reported as 404. Public metadata/catalog routes are marked below.

## Endpoint inventory

Paths below include the `/api` mount. Request/response field types and query defaults
come from the live OpenAPI schema. This table is source-audited for the baseline, not
an additional generated schema.

| Method | Path | Handler source | Authentication override |
|---|---|---|---|
| GET | `/api/auth/csrf` | [csrf](../src/api/routers/auth.py) | Public |
| POST | `/api/auth/register` | [register](../src/api/routers/auth.py) | Public |
| POST | `/api/auth/login` | [login](../src/api/routers/auth.py) | Public |
| POST | `/api/auth/reviewer-login` | [reviewer_login](../src/api/routers/auth.py) | Public |
| POST | `/api/auth/logout` | [logout](../src/api/routers/auth.py) | Default |
| GET | `/api/auth/me` | [me](../src/api/routers/auth.py) | Default |
| GET | `/api/auth/keys` | [list_keys](../src/api/routers/auth.py) | Session only |
| POST | `/api/auth/keys` | [create_key](../src/api/routers/auth.py) | Session only |
| DELETE | `/api/auth/keys/{key_id}` | [delete_key](../src/api/routers/auth.py) | Session only |
| POST | `/api/auth/keys/{key_id}/regenerate` | [regenerate_key](../src/api/routers/auth.py) | Session only |
| GET | `/api/auth/whoami` | [whoami](../src/api/routers/auth.py) | API key only |
| GET | `/api/datasets` | [list_datasets](../src/api/routers/datasets.py) | Default |
| POST | `/api/datasets` | [upload_dataset](../src/api/routers/datasets.py) | Default |
| GET | `/api/example-datasets` | [list_examples](../src/api/routers/datasets.py) | Public |
| POST | `/api/datasets/example` | [use_example_dataset](../src/api/routers/datasets.py) | Default |
| GET | `/api/datasets/{dataset_id}` | [get_dataset](../src/api/routers/datasets.py) | Default |
| GET | `/api/datasets/{dataset_id}/preview` | [preview_dataset](../src/api/routers/datasets.py) | Default |
| DELETE | `/api/datasets/{dataset_id}` | [remove_dataset](../src/api/routers/datasets.py) | Session only |
| POST | `/api/design` | [create_design](../src/api/routers/design.py) | Default |
| GET | `/api/design/{run_id}` | [get_design_status](../src/api/routers/design.py) | Default |
| GET | `/api/design/{run_id}/results` | [get_design_results](../src/api/routers/design.py) | Default |
| GET | `/api/reference-genes/resolve` | [resolve_reference_gene](../src/api/routers/expression.py) | Default |
| GET | `/api/public-datasets/organisms` | [organisms](../src/api/routers/expression.py) | Public |
| GET | `/api/public-datasets/experiments` | [experiments](../src/api/routers/expression.py) | Public |
| GET | `/api/public-datasets/comparisons` | [comparisons](../src/api/routers/expression.py) | Public |
| POST | `/api/public-datasets/materialize` | [materialize](../src/api/routers/expression.py) | Default |
| GET | `/api/public-datasets/{comparison_key}` | [comparison_info](../src/api/routers/expression.py) | Public |
| GET | `/api/health` | [health](../src/api/routers/meta.py) | Public |
| GET | `/api/ready` | [ready](../src/api/routers/meta.py) | Public |
| GET | `/api/version` | [version](../src/api/routers/meta.py) | Public |
| GET | `/api/runs/{run_id}/candidates` | [list_candidates](../src/api/routers/results.py) | Default |
| GET | `/api/candidates/{candidate_id}` | [get_candidate](../src/api/routers/results.py) | Default |
| GET | `/api/candidates/{candidate_id}/structure` | [get_candidate_structure](../src/api/routers/results.py) | Default |
| GET | `/api/runs/{run_id}/artifacts` | [list_artifacts](../src/api/routers/results.py) | Default |
| GET | `/api/artifacts/{artifact_id}/download` | [download_artifact](../src/api/routers/results.py) | Default |
| GET | `/api/runs/{run_id}/export.csv` | [export_candidates_csv](../src/api/routers/results.py) | Default |
| GET | `/api/runs/{run_id}/artifacts/download` | [download_artifacts_zip](../src/api/routers/results.py) | Default |
| GET | `/api/candidates/{candidate_id}/annotations` | [list_annotations](../src/api/routers/results.py) | Default |
| POST | `/api/candidates/{candidate_id}/annotations` | [create_annotation](../src/api/routers/results.py) | Default |
| DELETE | `/api/annotations/{annotation_id}` | [delete_annotation](../src/api/routers/results.py) | Default |
| GET | `/api/runs/{run_id}/review.json` | [export_review](../src/api/routers/results.py) | Default |
| GET | `/api/runs` | [list_all_runs](../src/api/routers/runs.py) | Default |
| POST | `/api/runs` | [create_run](../src/api/routers/runs.py) | Default |
| GET | `/api/runs/{run_id}` | [get_run_status](../src/api/routers/runs.py) | Default |
| GET | `/api/runs/{run_id}/detail` | [get_run](../src/api/routers/runs.py) | Default |
| POST | `/api/runs/{run_id}/cancel` | [cancel](../src/api/routers/runs.py) | Default |

## Inputs and submission

`POST /api/design` accepts exactly one nonempty input:

| Input | Meaning |
|---|---|
| `trigger_sequence` | Direct RNA; skips differential-expression discovery |
| `gene_id` | Stable reference ID or unambiguous symbol, resolved for the host |
| `dataset_id` | A usable dataset owned by the caller (or accessible to staff) |
| `dge_csv` | Inline differential-expression CSV, materialized as a dataset on submission |

Use host keys such as `ecoli`, not display names. Discover hosts, input modes,
available families, family/host compatibility, output/backbone compatibility, metrics,
filters, constraint definitions and limits at `GET /api/version`; do not enable a
family merely because its Python class exists. See [modalities](modalities.md).
`GET /api/reference-genes/resolve?organism=human&gene=SELE` inspects reference resolution;
gene submissions freeze resolved sequence and provenance.

`POST /api/runs` provides the lower-level equivalent: set `input_mode` to `de`,
`direct` or `gene`, provide the corresponding dataset/sequence/gene, and put run
configuration in `params`. In contrast, `/design` exposes configuration blocks directly.
Both use the same submission service and immutable normalized run snapshot.

Datasets upload as multipart `file`; CSV/TSV/TXT/XLSX are handled by the dataset service.
Validation is synchronous and checks structure/numerics; an INVALID stored dataset
can be inspected but cannot be submitted. Public catalog materialization is a separate
owned-dataset action; it does not query remote scientific services during a run.

### Configuration and result controls

`/design` accepts `constraints`, `folding`, `scoring`, `budget`, `payload`, `backbone`,
`gate_families`/`exclude_gate_families`, `seed`, `idempotency_key`, `notes`, `strict`,
and result-selection fields. `strict` defaults true and rejects unknown keys in the
validated configuration blocks. `strict=false` is not a way to bypass typed engine
validation, family availability, folding validation or release restrictions.
`/runs` explicitly checks constraints/scoring/backbone keys, with normalized scientific
configuration validated by the shared service/client boundary.

- `budget.max_designs` limits evaluation, not biological risk or elapsed time.
- `top_n` (1–1000, default 25) selects ranked rows returned, not candidates evaluated/stored.
- `include_rejected`, `include_metrics`, `include_artifacts` shape responses.
- Custom scoring weights/filters must use advertised metric names; missing metrics
  remain null rather than becoming zero. Direction/units are not user preferences.
- Preserve seed, normalized input, reference/tool versions and manifest alongside the
  snapshot; a response with defaults alone is not a complete reproducibility archive.

### Dry run, waiting and retries

`POST /api/design?dry_run=true` validates and estimates without persisting a dataset/run.
The estimate is deliberately uncalibrated: `seconds` is unknown/null and
`runtime_calibrated` is false. Counts are rough bounds, not latency promises.
`?wait=<seconds>` accepts 0–300; it may return 200 with results or 202 with a handle.
An expired wait does not mean the computation failed. Prefer polling long runs and set
your transport timeout above the requested wait.

Keep one `idempotency_key` per intended submission and reuse it after a transport
failure. Matching normalized requests return the same owner-scoped run; changed
configuration under the same key produces 409. Use a new key for a different run.

## Polling and cancellation

202 means accepted, not completed. Use the returned `poll_url`, or `/api/runs/{id}`.
States are DRAFT, QUEUED, RUNNING, COMPLETED, FAILED and CANCELLED; the last three are
terminal. `stage`, `progress_pct`, warnings, safe error summary, timestamps and result
counts support the UI. `worker_available` is meaningful for queued runs; false does
not invalidate the durable submission. A queue deadline can eventually fail it.

`POST /api/runs/{id}/cancel` returns `cancelled`, `cancellation_requested` or
`already_terminal`. Running cancellation is cooperative at callback checkpoints;
native computations need not stop immediately. See [operations](operations.md) for
abandoned-run and execution-token reconciliation.

## Results, review and artifact access

`/design/{id}/results` returns ranked candidate JSON plus resolved configuration.
Its result options are query parameters; clients must retain options when resuming a
job. `format=csv` delegates to the common CSV export. Raw JSON preserves nested design,
triggers, warnings and metrics; flattened client tables are a different representation.

`/runs/{id}/candidates` supports detailed browsing; candidate detail includes stored
science and metrics. A rejected candidate is unranked and carries its reason. Human
annotations are separate review decisions. The SYNTHESIZE tag does not grant release.

Artifact listing includes `download_available` and authenticated download URLs.
Individual sequence-bearing downloads can return 409 while release approval is absent.
ZIP selection accepts category or comma-separated IDs (IDs win), rejects unknown
categories and refuses an archive containing withheld or missing files. Do not infer
release authorization from COMPUTATIONAL completion or artifact metadata.
See [release decisions](release-decisions.md).

### Stored candidate structure

Candidate `/structure` renders saved sequence/structure through the local renderer;
it is not a fresh folding computation. Status is available/unavailable/invalid/error,
with provenance and reason fields. Older candidates may lack saved structures.
The viewer's primary-switch scope is documented in [user help](user-help.md).

## Errors and versioning

API-handled errors use `{"error":{"code":"…","message":"…","detail":{}}}`.
Middleware/proxy failures can differ, so tolerate non-JSON errors in transport code.

| HTTP | Typical interpretation |
|---|---|
| 401 | Missing/invalid authentication |
| 403 | CSRF, insufficient scope, account pending approval |
| 404 | Absent or inaccessible object |
| 409 | Idempotency/configuration conflict, protected deletion, withheld/missing archive content |
| 422 | Invalid input/configuration, unknown parameter |
| 429 | Rate or active-run quota, inspect Retry-After |
| 500 | Generic server failure; details go to protected logs |
| 503 | `/ready` reports unavailable database/worker |

`/health` proves only that the web process responds; `/ready` adds database read and
worker heartbeat checks. Neither certifies references, backup health or scientific
validity. `/version` advertises API/engine versions. Clients should ignore unknown
response fields. A future `/api/v2` mount or competition-season support promise from
the original design proposal is not an implemented alternate endpoint.

## Folding model

Set `folding` on `POST /api/design`, or the same object at `params.folding` on
`POST /api/runs`. Omitted fields receive the defaults below. One model is shared by
design folding and local transcript accessibility calculations within the run.

```json
{
  "folding": {
    "temperature_celsius": 37.0,
    "dangles": 2,
    "special_hairpins": true,
    "no_lonely_pairs": false,
    "no_gu": false,
    "no_gu_closure": false,
    "energy_parameters": "turner2004"
  }
}
```

| Field | Accepted values | Meaning |
|---|---|---|
| `temperature_celsius` | Finite number, 0–100 inclusive | Folding temperature in °C |
| `dangles` | Integer `0` or `2` | Disable dangling-end energies or use the double-dangle model |
| `special_hairpins` | Boolean | Include special hairpin-loop energies |
| `no_lonely_pairs` | Boolean | Enable ViennaRNA's no-lonely-pairs model option |
| `no_gu` | Boolean | Disallow GU base pairs |
| `no_gu_closure` | Boolean | Disallow GU pairs closing loops |
| `energy_parameters` | `turner2004`, `turner1999`, `andronescu2007` | Built-in ViennaRNA RNA energy parameter set |

Only dangle models `0` and `2` are supported: ViennaRNA partition-function calculations
do not consistently implement `1` and `3`. Parameter file paths and arbitrary model
fields are unsupported. Values are checked without coercion: `"25"`, `true` as a
temperature, `2.0` as a dangle model, and `0`/`1` as booleans are rejected. Unknown fields,
non-object blocks and invalid values return 422 on both endpoints, including
`dry_run=true` and `strict=false`.

Every effective setting is stored in `params_snapshot.folding` and echoed as
`resolved.folding` by the design submission, dry-run and results responses. Changing
folding settings changes a run's idempotency identity; use a new `idempotency_key` for
a different model. An older stored run without recorded settings returns an empty
`resolved.folding` object rather than claiming it used today's defaults.

The result manifest records structured evidence at
`scientific_provenance.folding_model`; each candidate carries the same model at
`design.folding_model`. The legacy string-valued `tool_versions` also contains canonical
JSON under `folding_model`. Evidence includes the installed ViennaRNA version, normalized
configuration, actual native model fields, loaded energy-table identity and SHA-256 of
the exact bundled parameter string loaded. A name alone is not treated as identity.
Scanned trigger features additionally record the local model and clamped window/span at
`rnaplfold.folding_model`; older/manual records leave this `null`.

Suboptimal enumeration runs in an isolated process and receives the full configuration;
its algorithm-only `uniq_ML=1` override is recorded. Full-fold window/span defaults are
normalized to sequence length before native calculation; provenance states this rule.
Local opening-energy conversions use the same configured temperature as RNAplfold.

ViennaRNA's `noLP` partition-function approximation excludes pairs that cannot stack;
lonely pairs may still occur in ensemble structures. This caveat is recorded when enabled.
Salt remains explicitly fixed at the previous ViennaRNA default, 1.021 M. Built-in model
choices are computational settings, not experimental validation or calibrated physiological
conditions. The engine serializes global table loading/restoration and copies both MFE
and partition-function parameters into each compound. The AIS-China adapter's direct
`optimize` path shares this lock (its whole call may delay other compound construction);
ordinary production codon optimization consumes its reference tables only. Other
third-party code must not mutate
ViennaRNA globals concurrently outside the shared adapter.

Implementation references: [ViennaRNA model details](https://www.tbi.univie.ac.at/RNA/ViennaRNA/doc/html/eval/model.html),
[parameter snapshots and PF preparation](https://github.com/ViennaRNA/ViennaRNA/blob/v2.7.2/src/ViennaRNA/params/params.c),
and [RNAplfold window probabilities](https://www.tbi.univie.ac.at/RNA/ViennaRNA/doc/html/partfunc/window.html).
The snapshot cache invalidation and full-length PF normalization are covered by real-library
regression tests; they are required for ViennaRNA 2.7.2, not cosmetic metadata changes.

For direct Python use, pass `FoldEngine(config=FoldingConfig(...))` and
`FoldProfiler(config=the_same_config)`. `FoldingConfig` is a frozen dataclass in
`engine.domain`. Existing `FoldEngine(temperature=...)` calls remain supported.


## Historical rationale

The [original HTTP notes](archive/operator-design/api.md) preserve detailed examples
and historical evolution. They include obsolete endpoint counts, mock/stub claims,
optimistic runtime estimates and client-publication commands. The active reference,
source and running OpenAPI take precedence.
