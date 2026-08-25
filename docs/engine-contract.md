# Engine contract

The Platform and the Engine communicate through exactly two modules —
`engine.contract` and `engine.client`. Everything else under `src/engine/` is private
to the engine. See [software-design.md §3](software-design.md) for the boundary rule and
`tests/test_boundary.py` for its enforcement.

In v1 the contract is a set of frozen dataclasses passed in-process. **The fields are
the ones the design maps specify for the eventual HTTP service**, so promoting the
engine to a standalone deployment is a serialisation exercise, not a redesign.
[§4](#4-the-future-http-mapping) gives the mapping.

---

## 1. The interface

```python
ProgressFn = Callable[[int, str], bool]  # (percent, stage) -> keep_going


class EngineClient(Protocol):
    def run(self, request: JobRequest, on_progress: ProgressFn) -> JobResult: ...
```

Implementations:

| Class | Purpose |
|---|---|
| `MockEngine` | Deterministic fake science. The default, and what CI and frontend work use. |
| `LocalEngine` | The real pipeline, in-process. Raises `NotImplementedError` until Step 5. |
| *`HttpEngineClient`* | *Future.* Same Protocol, talks to a deployed engine service. |

Selected by dotted path:

```python
engine = load_engine(settings.CERNAL_ENGINE)  # "engine.client.MockEngine"
```

`load_engine` takes the path **as an argument** rather than reading `settings` itself —
`engine/` may not import Django. The Platform passes the setting in.

---

## 2. The types

### `JobRequest`

An immutable snapshot of one submission. Carries references and values only — never a
model instance, a file handle or an open connection.

| Field | Type | Notes |
|---|---|---|
| `schema_version` | `str` | Currently `"1"` |
| `run_id` | `str` | `AnalysisRun.id`; the correlation key in every log line |
| `idempotency_key` | `str` | A retry with the same key must not launch a second computation |
| `input_path` | `str` | Absolute path the engine may read |
| `input_checksum` | `str` | SHA-256; **the engine re-verifies before use** |
| `organism` | `str` | |
| `params` | `dict` | The normalized parameter snapshot |
| `gate_families` | `list[str]` | Resolved via `engine.gates.registry` |
| `scoring_profile` | `str` | Resolved via `engine.scoring.profiles` |
| `seed` | `int \| None` | Reproducibility |
| `output_dir` | `str` | Where the engine may write artifacts |

### `JobResult`

The versioned result manifest. `input_checksum` and `params` are echoed back so the
Platform can verify the engine computed against what it actually sent.

| Field | Type | Notes |
|---|---|---|
| `schema_version` | `str` | |
| `engine_version` | `str` | Recorded on the run |
| `status` | `str` | `succeeded` · `failed` · `cancelled` |
| `candidates` | `list[CandidateResult]` | Includes rejected ones |
| `artifacts` | `list[ArtifactRef]` | |
| `warnings` | `list[str]` | |
| `error` | `str \| None` | Safe to show a researcher |
| `input_checksum` | `str` | Echoed |
| `params` | `dict` | Echoed |

Convenience properties: `.accepted` (non-rejected, rank order) and `.rejected`.

### `CandidateResult`

| Field | Type | Notes |
|---|---|---|
| `ref` | `str` | Engine-local id, unique within the job |
| `rank` | `int \| None` | `None` for rejected candidates |
| `overall_score` | `float \| None` | 0–1, higher is better |
| `gate_family` / `logic_type` | `str` | |
| `triggers` / `design` | `dict` | Sequences, structure, logic graph |
| `summary` | `str` | One-line human description |
| `metrics` | `list[MetricValue]` | The full decomposition |
| `warnings` | `list[str]` | |
| `is_rejected` | `bool` | |
| `rejection_reason` | `str` | **Never empty when rejected** |

### `MetricValue` and `ArtifactRef`

`MetricValue` keeps `raw_value` *and* `normalized_value`, plus `weight` and `direction`,
because the researcher is shown the decomposition rather than a single opaque score
(design map 12).

`ArtifactRef.path` is **relative to `output_dir`**, so the Platform can relocate the
directory without rewriting references. `checksum_sha256` is verified on import.

---

## 3. Behavioural rules

**Failures are data; bugs are exceptions.** An expected scientific failure returns a
`JobResult` with `status="failed"` and a safe `error` string. A programming error
propagates as an exception so the Platform logs a traceback and the bug is visible.

**Error text is user-facing.** No paths, no credentials, no stack traces, no internals.
Full detail goes to the log, keyed by `run_id`.

**Cancellation is cooperative.** The engine calls `on_progress(percent, stage)` between
stages; a `False` return means stop. The engine raises `JobCancelled` internally and
returns `status="cancelled"`. Threads are never killed.

**Progress is monotonic**, and every callback carries a human-readable stage label — the
Platform shows these to the researcher directly.

**Determinism.** The same `idempotency_key` and `seed` must produce identical candidates
and byte-identical artifacts. `MockEngine` guarantees this and is tested for it.

**Rejected candidates survive** with a reason attached. Never filtered away silently.

---

## 4. The future HTTP mapping

When the engine becomes a service (design map 08), these dataclasses serialise directly.

### `POST /v1/jobs`

| Map 08 field | Contract field |
|---|---|
| API/schema version | `JobRequest.schema_version` |
| platform run ID / correlation ID | `run_id` |
| idempotency key | `idempotency_key` |
| immutable input bundle references + checksums | `input_path` + `input_checksum` |
| normalized parameter snapshot | `params` |
| organism / state metadata | `organism` |
| requested gate families | `gate_families` |
| scoring / reproducibility settings | `scoring_profile` + `seed` |

Response `202 Accepted` with `engine_job_id` — in v1 there is no separate engine job id
because `run_id` already identifies the work.

### `GET /v1/jobs/{id}`

The `on_progress(percent, stage)` callback is the in-process form of polling. Over HTTP
it becomes a status document; the Platform maps it into product status exactly the same
way ([§6](software-design.md)).

### `GET /v1/jobs/{id}/result`

`JobResult` verbatim — it *is* the versioned result manifest. Artifact bytes move to
signed object references; `ArtifactRef` already carries `path`, `media_type` and
`checksum_sha256`, so only the resolution of `path` changes.

### `POST /v1/jobs/{id}/cancel`

Becomes the transport for what `on_progress` returning `False` does today.

**What must not change across that migration:** field names and semantics, the status
vocabulary, checksum rules, idempotency behaviour, and the guarantee that rejected
candidates carry reasons.

---

## 5. Engine internals (not part of the contract)

Platform code must never import these — `tests/test_boundary.py` fails the build if it
does.

| Module | Role | State |
|---|---|---|
| `engine.pipeline` | The 13 scientific stages from design map 11 | **Stub** — Step 5 |
| `engine.gates.base` | `GateFamily` ABC, `TriggerSet`, `GateDesign`, `Constraints` | Complete |
| `engine.gates.toehold` | Toehold switch family | **Stub** — Step 5 |
| `engine.gates.registry` | Name → class lookup | Complete |
| `engine.scoring.profiles` | `MetricSpec`, `HardFilter`, `ScoringProfile`, `default-v1` | Complete; metric set provisional |
| `engine.scoring.normalize` | Normalization, weighting, hard filters, ranking | Complete |
| `engine.artifacts` | Checksummed artifact writing | Complete |
| `engine.errors` | `EngineError` hierarchy | Complete |

### Adding a gate family

1. Subclass `GateFamily` in `engine/gates/`, setting `name` and `version`.
2. Implement `required_tools`, `is_compatible`, `generate_designs`, `evaluate_design`,
   `emit_sequence`, `emit_artifacts`.
3. `register(YourFamily)` in `engine/gates/registry.py`.

Nothing outside `engine/gates/` changes. `evaluate_design` returns **raw** values only —
normalization and weighting belong to the scoring layer, which is what keeps unlike
families comparable.

---

## 6. Using MockEngine

Options go under `JobRequest.params["mock"]` and are ignored by every real engine.

| Option | Default | Effect |
|---|---|---|
| `candidate_count` | `12` | How many candidates to generate |
| `step_delay` | `0.0` | Seconds per stage — set to ~0.5 to watch progress in the UI |
| `fail` | `false` | Produce a `failed` result |
| `fail_message` | generic | The `error` text |
| `fail_at_stage` | last | Zero-based stage index to fail at |

```python
request = JobRequest(..., params={"mock": {"candidate_count": 30, "step_delay": 0.4}})
```
