# cernal (Python client)

Source client; no registry publication is claimed. See the [current integration guide](../../docs/public-api.md), [API reference](../../docs/api.md), and [pinned status](../../docs/status.md). Results are computational; sequence exports can be withheld independently of successful completion.


A thin wrapper over the design workflow, not a generated mirror of every endpoint. Anyone needing more talks to the documented,
self-describing REST API directly (`/api/docs`, `/api/openapi.json`).

```bash
uv pip install "./clients/python[pandas]"  # omit [pandas] for dictionary-only results
```

```python
import os
from cernal import Client

c = Client(api_key=os.environ["CERNAL_API_KEY"], base_url="https://your-cernal-host")

job = c.design(trigger_sequence="AACUUGUUGGCCCAGUGUGAAUCGCUUAAGGGUUAA", organism="ecoli")
df = job.wait().to_dataframe()
print(df.head())
```

Constrained, with custom scoring:

```python
job = c.design(
    dge_csv=open("deseq2.csv").read(),
    organism="ecoli",
    gate_families=["toehold"],
    constraints={
        "max_triggers": 1,
        "min_separation": 1.0,
        "max_p_adj": 0.01,
        "trigger_lengths": [30, 33, 36],
        "standard": "RFC10",
    },
    scoring={
        "weights": {"predicted_leakage": 4.0, "gc_content": 0.0},
        "hard_filters": [{"metric": "dynamic_range", "minimum": 10.0}],
    },
    budget={"max_designs": 20},
    seed=42,
    top_n=25,
)
print(job.estimate)  # from the 202, before waiting
best = job.wait().best()  # highest-ranked candidate, as a dict
# Download only an available, release-authorized artifact; see below.
```

Inspect uncalibrated estimates before a sweep (not timing guarantees):

```python
c = Client(
    api_key=os.environ["CERNAL_API_KEY"],
    base_url=os.environ["CERNAL_BASE_URL"],
    dry_run=True,
)
for organism in ("ecoli", "yeast"):
    print(c.design(trigger_sequence=seq, organism=organism).estimate)
```

## What's here

- `Client` — holds a key and a base URL. `.design()`, `.status()`, `.results()`,
  `.artifact()`, `.capabilities()`.
- `Job` — a submitted design. `.wait()` polls with backoff (2s, growing to 15s, up to
  an overall timeout); `.candidates()` / `.to_dicts()` / `.to_dataframe()`; `.best()`;
  `.artifact(kind)`.
- Errors map to exception classes: `AuthError` (401), `ValidationError` (422, carries
  `.did_you_mean`), `RateLimited` (429, carries `.retry_after`), `RunFailed` (a
  terminal FAILED/CANCELLED run, carries `.error_summary`).

`requests` only. **pandas is optional** — `.to_dataframe()` raises a message telling you
to `uv pip install ./clients/python[pandas]`; `.to_dicts()` always works.

## Verification and result contracts (8 October 2026)

No package publication is claimed. Install from this repository's source; public
registry releases require separate maintainer authorization. Python HTTP conformance
and transport/ranking regressions execute against a local API. The R raw/table and
live HTTP conformance suite passed in [hosted Ubuntu CI](https://github.com/zivbental/cernal_software/actions/runs/37802426550/job/113397823314).
MATLAB runtime conformance remains unexecuted; its source changes are experimental.

Submission result options (`top_n`, `include_rejected`, `include_metrics`,
`include_artifacts`) remain on the job handle across queued completion. Persist them
when reconstructing a resumed handle; explicit results calls can override them.
Server-side `wait` is bounded to 0–300 seconds and submission transport timeout is
at least `wait + 10` seconds. Best-candidate helpers choose the lowest accepted rank
and return no result when all candidates are rejected or unranked.

Raw candidate JSON retains nested design, triggers, warnings and metrics. Flattened
tables are a separate convenience contract and are not compared to raw JSON column
sets. R exposes `cernal_candidates(job)` and MATLAB `job.rawCandidates()`.

## Artifact availability

Completed computation does not guarantee an artifact of a requested kind exists or is
released. Inspect the results artifact metadata and `download_available` before calling
`job.artifact(kind).save(path)`. Missing kinds raise `KeyError`; held downloads can return
409. Follow the [release-aware tutorial](../../docs/tutorial.md), never bypass the API
by reading server files.
