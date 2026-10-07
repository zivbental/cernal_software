# API and Configuration · 2.0.1

The default application address is `http://127.0.0.1:8765`. The web interface, Python API and command line share the same validation and calculation core.

## Python API

Run from the project root:

```python
from codon_v2.pipeline import optimize

result = optimize({
    "host_id": "atcc6919_GCF_008728435.1",
    "cds": "GTGGCTGCCTAA",
    "strategies": ["host_sampling", "cai_max", "tai_max"],
    "gc_policy": {"mode": "report"},
    "seed": 42,
    "candidates_per_strategy": 1,
})
for candidate in result["candidates"]:
    print(candidate["candidate_id"], candidate["sequence"])
```

This short example explicitly uses report-only GC. The default is a host-derived hard global GC interval; for short sequences, no integer GC count may fall inside it.

Pass a `progress(report)` callback to receive snapshots after strategy stages. A `cancelled()` callback returning `True` requests cancellation. `disable_rna=True` supports diagnostics without an RNA engine; RNA metrics then include the unavailability reason.

## Local HTTP endpoints

| Method and path | Response or action |
|---|---|
| GET `/api/meta` | Version, host availability, reference hashes, RNA model, budgets and current local token |
| GET `/api/example` | Complete example request ready for submission |
| GET `/api/references/<host_id>/codons.csv` | The strain's 61-codon master parameter table |
| POST `/api/jobs` | Validate and submit a request; return HTTP 202 and `job_id` |
| GET `/api/jobs/<job_id>` | Job `state`, available portions of `report` and any error |
| POST `/api/jobs/<job_id>/cancel` | Request cancellation; body `{}` |
| GET `/api/jobs/<job_id>/fasta` | All unique candidates in FASTA format |
| GET `/api/jobs/<job_id>/csv` | Original input and candidate metrics |
| GET `/api/jobs/<job_id>/json` | Complete run record |

Append `?ids=SEQ-AAA,SEQ-BBB` to a download endpoint to select existing IDs. Unknown IDs return HTTP 400; repeated IDs are deduplicated. Partial JSON exports retain full-run status and identify the subset in `export.selected_ids`.

POST requests require `Content-Type: application/json` and `X-Codon-Token`. Obtain the token from `/api/meta` on the same service. Local Host validation prevents unrelated websites from submitting requests to the application. The service has no public account system.

The request-body limit is 131,072 bytes. Invalid input returns 400, a full queue returns 429, and a missing or expired job returns 404. Asynchronous job states are `queued / running / finished / failed / cancelled`; these are distinct from individual strategy statuses within the report.

## Online HTTP endpoints

Vercel loads `wsgi:app`, which exposes the same `/`, `/app.js`, `/style.css`, `/api/meta`, `/api/example` and host parameter downloads. Online metadata includes `execution_mode: "online"` and deployment limits. There is no local token or persistent job ID in this mode.

POST `/api/optimize` accepts the request schema below with `Content-Type: application/json`. A supplied browser Origin must match the service host. The request body limit remains 131,072 bytes. An online request must use at most 40 `wall_seconds` per preference; larger values are rejected rather than silently changed.

HTTP 200 returns an object with `report` and `exports`. The report is the normal optimizer report plus `run.execution`, which records online mode, the 240-second cooperative request deadline and whether it was reached. A deadline retains valid completed results, marks interrupted strategies with `online_time_limit_reached`, and reports `partial_results` or `no_results`. The request does not continue as a background job after the response.

`exports.fasta` and `exports.csv` each contain `all` and `by_id` server-generated text. The page downloads these directly as browser files; selected CSV output includes its header and original baseline once. JSON downloads are serialized from the received report, with the same selected-subset fields used locally. No follow-up export request or server-side result cache is needed.

Malformed JSON/input returns 400, cross-origin browser submissions return 403, oversized input or a report exceeding the online delivery limit returns 413, unsupported content types return 415, and a busy worker returns 429 with `Retry-After: 5`. Unexpected failures return a generic 500 response. Responses use `Cache-Control: no-store`. The application does not write user reports or request bodies to disk or application logs.

The online interface hides cancellation and disables the Thorough preset. Closing the page does not promise to stop a calculation already running on the server. Use local mode for a larger budget or cooperative user cancellation. See the [README](../README.md) for deployment setup.

## Request fields

Unknown fields produce an error. Nested objects may include only the fields to override; omitted fields use defaults.

| Field | Default or allowed values |
|---|---|
| `cds` | Required; one sequence or FASTA record; up to 9,000 nt |
| `host_id` | Required; `atcc6919_GCF_008728435.1` or `kpa171202_GCF_000008345.1` |
| `strategies` | RNA, sampling, CAI and tAI by default; at least one; deduplicated and scheduled in a fixed order |
| `upstream_transcribed_sequence` | Empty by default; up to 300 nt; fixed |
| `source_host_id` | Optional built-in source reference; mutually exclusive with a custom reference |
| `source_reference` | Optional `{name, counts}`; format below |
| `locked_codon_positions` | Empty by default; list of 1-based integer codon positions; first codon and existing stop are added automatically |
| `tai_model` | `classic` (default) or `stai` |
| `seed` | Integer 0–4294967295; default 42 |
| `candidates_per_strategy` | Fixed integer 1; may be omitted; other values produce an input error |

The five strategy IDs are `rna_start`, `host_sampling`, `cai_max`, `tai_max` and `harmonize`. There is no `rna_cai` or other implicit combined objective.

A successful strategy has `returned_count=1`; a strategy without a valid result has `returned_count=0`. Identical DNA can belong to several strategies, so there may be fewer unique sequences than successful strategies. Internal search pools and budgets still explore multiple candidates. The retained JSON field `candidate_number` is fixed at 1 for compatibility with the report structure; the web interface does not show within-strategy numbering.

### motif_policy

```json
{"mode": "custom", "custom": "GAATTC"}
```

`mode` is `none / AGCAGY / custom`; default `none`. A custom motif must contain 2–32 literal ACGT nucleotides. For KPA, the resolved configuration always enforces AGCAGY even if the request says `none`. The response's `run.config` records the applied rule. Scanning covers both strands of the submitted CDS, including its terminal stop.

### gc_policy

```json
{
  "mode": "hard",
  "bounds": [0.54, 0.65],
  "local_mode": "report",
  "local_bounds": [0.30, 0.80],
  "local_window_nt": 60,
  "local_step_nt": 3
}
```

Global and local modes are `hard / report`. Bounds use fractions from 0 to 1; the web interface displays percentages. Omitted global bounds use the host's exact frozen P5–P95 values. Window length is 3–300 nt; step size is 1 to the window length.

### repeat_policy

```json
{
  "mode": "warn",
  "homopolymer_min_nt": 8,
  "tandem_unit_min_nt": 2,
  "tandem_unit_max_nt": 6,
  "tandem_min_copies": 3,
  "tandem_min_total_nt": 12,
  "direct_repeat_min_nt": 20
}
```

Modes are `warn / repair / strict`. Thresholds are integers from 2 to 100, with an additional 12 nt maximum for tandem unit length. Scanning processes at most 30,000 direct-repeat seed pairs and retains at most 500 detailed hits; reaching a limit sets `scan_complete=false`. Strict mode requires a complete scan with zero hits.

### rna_config

```json
{
  "temperature_c": 37,
  "context_cds_nt": 150,
  "target_start_nt": 1,
  "target_end_nt": 15,
  "mutable_start_codon": 2,
  "mutable_end_codon": 30
}
```

Temperature is 0–80°C; CDS context length is 15–300 nt. Target coordinates are relative to the CDS. The start must be within the actual sequence; the end may be shortened to fit a short CDS. The mutable interval lies within codons 2–100; the first codon and user locks take precedence. All actual coordinates are included in the output.

### search_budget

| Field | Standard value | Maximum |
|---|---:|---:|
| `sampling_attempts` | 256 | 5,000 |
| `rna_evaluations` | 128 | 1,000 |
| `max_transitions` | 600,000 | 5,000,000 |
| `max_frontier` | 1,200 | 4,000 |
| `beam_width` | 160 | 1,000; also limited by the frontier maximum |
| `wall_seconds` | 40 | 120 |
| `repair_evaluations` | 48 | 256 |

Budgets are counted independently for each strategy. Original-input scoring, the shared seed pool and final report scoring are recorded separately. At most five unique sequences can be delivered in one run, one per selected strategy before deduplication. Identical RNA contexts may share real engine results in a cache without changing each strategy's logical context count.

The shared pool attempts at most 64 rounds of full-length/start-window sampling, targets 16 seeds and has a five-second limit. Feasibility-DP fallback has separate counters and a five-second limit. Time-based stopping may produce different results on different hardware.

## Custom source host

See [the complete example](../examples/source_reference.json). A source reference contains `name` and `counts`:

```text
{
  "name": "your host / assembly / full-CDS count version",
  "counts": { ... counts for all 61 sense codons, uppercase DNA keys ... }
}
```

Counts must be finite and nonnegative, with at least one positive count per synonymous family. Source and target must both use whole-CDS synonymous frequencies. Do not supply ribosomal CAI weights as counts. The provider is responsible for the reference's counting convention; the application checks coverage and values and records a content hash.

## Report structure

`run` contains code/reference versions, code hashes, normalized configuration, seeds, the shared initial pool and budgets. `reference_manifest` and `source_reference` contain provenance. `original_result` is the separate baseline; `candidates` contains unique sequences; `strategy_status` records each strategy's solver outcome.

A candidate contains `candidate_id`, `sequence`, a full SHA-256 hash, protein, changes, constraint checks, metrics and `strategy_memberships`. Each membership retains its strategy, compatibility number, representative type, source seed and repeat-repair history.

Metric objects contain `value / status / reason`, plus units, scored-position counts, reference IDs or RNA structures/context where applicable. A missing value is `null`, not zero.

In `candidate_provenance.objective_value`, CAI/tAI use accumulated log weights, RNA uses negative opening energy, and harmonization uses the negative sum of position-wise rank differences. The web interface and CSV show geometric-mean CAI/tAI instead. Internal objective values are not comparable across strategies.

Only `solver=dp_exact` with a fully solved constraint subproblem carries a guarantee within its stated scope. `beam_approx`, `dp_interrupted`, RNA search and sampling do not claim global optimality. Successful partial results remain available.

To rerun an exported report, save its `run.config` as a new request JSON and use `python -m codon_v2 run --request ... --output ...`. Do not submit the entire report object as a request.
