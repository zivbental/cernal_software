# cernal (Python client)

A thin, idiomatic wrapper over five HTTP calls (docs/public-api.md §11) — not a
generated mirror of all 32 endpoints. Anyone needing more talks to the documented,
self-describing REST API directly (`/api/docs`, `/api/openapi.json`).

```bash
pip install cernal            # or: cernal[pandas]
```

```python
import os
from cernal import Client

c = Client(api_key=os.environ["CERNAL_API_KEY"], base_url="https://your-cernal-host")

job = c.design(trigger_sequence="AUGGCUAAGCUUAACGGAUCC", organism="ecoli")
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
        "max_triggers": 2,
        "min_separation": 1.0,
        "max_p_adj": 0.01,
        "trigger_lengths": [30, 36],
        "standard": "RFC10",
    },
    scoring={
        "weights": {"predicted_leakage": 4.0, "gc_content": 0.0},
        "hard_filters": [{"metric": "dynamic_range", "minimum": 10.0}],
    },
    budget={"max_designs": 50_000, "max_runtime_seconds": 1800},
    seed=42,
    top_n=25,
)
print(job.estimate)  # from the 202, before waiting
best = job.wait().best()  # highest-ranked candidate, as a dict
job.artifact("fasta").save("best.fa")
```

Cost a whole sweep before running any of it:

```python
c = Client(api_key=..., dry_run=True)
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
to `pip install cernal[pandas]`; `.to_dicts()` always works.
