# Platform data model

Source baseline: `main` at `c1bb92cc085a6bad272298b81bda28c22b1d57f5` (16 October 2026).
See [status and remaining work](status.md) for verification and release limits.

This is a navigation and invariant guide. The linked Django model definitions and
migrations are the field-level authority; the engine's frozen scientific records are
separate in [domain.py](../src/engine/domain.py) and [contract.py](../src/engine/contract.py).

## Stored objects

| Model | Purpose and relationships |
|---|---|
| [User, ApiKey](../src/apps/accounts/models.py) | Standard custom AbstractUser; keys belong to users, retain prefix/digest, scopes, expiry/revocation and quotas. User IDs are integers; API-facing research IDs are generally UUIDs. |
| [Dataset](../src/apps/datasets/models.py) | Owner, immutable uploaded file, checksum/size, validation report/status and optional provenance. Re-upload creates a new row. |
| [Expression catalog](../src/apps/expression/models.py) | Public experiment/comparison metadata and cached expression provenance; catalog materialization creates an owned dataset. |
| [AnalysisRun](../src/apps/analyses/models.py) | Owner, input, frozen configuration, seed/families/profile, state/progress, timestamps, queue time and execution lease token. |
| [Candidate](../src/apps/results/models.py) | Run-local engine reference, rank, score, triggers/design, warnings and rejection reason. |
| CandidateMetric | Unique `(candidate, name)`; nullable raw/normalized values plus weight and direction. Missing is not zero. |
| Artifact | Run, optional candidate, stored file, checksum/size, MIME type, kind and `sequence_free` classification. |
| Annotation | Candidate, author, text and decision tag; researcher judgment rather than engine output. |

## Input and lifecycle invariants

`input_mode` is `de`, `direct` or `gene`. DE requires a dataset; direct and gene runs
have no dataset. Services enforce sequence/gene semantics beyond the database's
mode/dataset check. Organism is a supported host key, not arbitrary display text;
query `/api/version` for the current capability set.

Idempotency is unique per `(created_by, idempotency_key)`, not globally. A retry of the
same normalized request returns its existing run; conflicting reuse is rejected.
The submitted configuration remains frozen while lifecycle fields change.
Progress is database-constrained to 0–100. The state graph, including QUEUED → FAILED
on timeout, lives in `ALLOWED_TRANSITIONS`; see [architecture](architecture.md).

Rejected candidates must carry a reason and have no rank. `(run, engine_ref)` is
unique. An annotation's `REJECTED` tag is a human review decision and does not rewrite
the candidate's scientific rejection status. Tags include NONE, PINNED, SHORTLISTED,
REJECTED and SYNTHESIZE; the last is not a sequence-release authorization.

## Import, artifacts and release

[Result services](../src/apps/results/services.py) validate the result and artifact
checksums, import database records atomically, and write derived `summary.csv` and
`manifest.json`. They do not own run-state transitions. Staging and import failure
recovery are described in [operations](operations.md); database atomicity does not
make filesystem writes transactional.

Artifact `kind` describes content; category/label are computed from `_KIND_INFO`.
Unmapped kinds remain available under `other`. Plasmid, reporting and structure code
exists; do not infer artifact availability from an old “stage is a stub” statement.
What a particular run emits depends on accepted candidates, configuration and release
policy. List that run's artifacts and inspect `download_available`.

Owner/staff checks and release checks apply to downloads. Individual sequence-bearing
files can be withheld; ZIP requests containing withheld artifacts fail rather than
silently supplying an incomplete archive. Never serve media directly from the proxy.

## Deletion and ownership

Run deletion cascades to its candidates, metrics, artifacts and annotations at the
model level; this is not a promise of a public run-delete HTTP route. Referenced datasets
and users with protected research relationships cannot simply be removed. File retention
and orphan cleanup are separate operational concerns. Review [security](security.md)
and dry-run cleanup output before deleting data.

Ordinary object queries scope by dataset uploader or run creator; staff can access
other owners' records. Missing and unauthorized objects both return 404. Annotation
records remain tied to their candidate; a new run does not automatically copy them.

The [original detailed model notes](archive/operator-design/domain-model.md) preserve
historical rationale and field tables, but contain obsolete model counts, global
idempotency and MockEngine claims. Consult source for current fields.
