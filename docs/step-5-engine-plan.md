# Step 5 — Engine implementation plan

> **Planning document. Nothing here is implemented yet.**
> Read [`software-design.md`](software-design.md) §3 for the boundary this depends on,
> and [`engine-contract.md`](engine-contract.md) for the contract it fills in.
> [`engine-design.md`](engine-design.md) covers how the engine is structured internally.

You asked: should the engine run on the same server or a different one, and how should
they talk? This answers that, then sets out how to build the science behind it.

---

## 1. The short answer

**Keep it on the same VPS, in-process, for the foreseeable future.** Not as a compromise
— on measured numbers it is the right call, and it will stay right for longer than this
project needs.

The interesting part is that **you do not have to decide now**. The boundary from
[§3](software-design.md) already exists and is enforced by a test, so moving the engine
to another machine later is a serialisation exercise, not a rewrite. The expensive
mistake would be splitting it *before* you know the compute profile, and paying for a
network boundary you never needed.

So: implement the science behind `LocalEngine`, measure a real run, and split only if a
number in [§4](#4-when-to-move-it) tells you to.

---

## 2. Why this question is cheaper than it looks

Three things are already in place, from Steps 1–4:

| Already built | What it buys you |
|---|---|
| `engine/` imports no Django, enforced by `tests/test_boundary.py` | The engine is already a standalone Python package. It can be lifted out |
| `EngineClient` protocol with `MockEngine` and `LocalEngine` | A third implementation, `HttpEngineClient`, slots in behind the same interface |
| `JobRequest` / `JobResult` frozen dataclasses | Field-for-field the payloads design map 08 specifies. Serialising them is mechanical |
| `CERNAL_ENGINE` setting resolved by dotted path | Switching engines is one environment variable |
| `EngineCapabilities` | The Platform already asks the engine what it can do rather than assuming |

The seam is real. **Use it to defer the decision, not to make it early.**

---

## 3. What actually determines the answer

Not architecture — arithmetic. The engine's cost is dominated by RNA folding, so I
benchmarked ViennaRNA 2.7.2 on this machine:

| Operation | Sequence | Per call | Throughput (1 core) |
|---|---|---|---|
| `RNA.fold` | toehold switch, ~92 nt | 2.76 ms | 363/s |
| `RNA.fold` | switch + trigger, ~150 nt | 9.09 ms | 110/s |
| `RNA.cofold` | switch & trigger | 6.89 ms | 145/s |
| partition function | accessibility, ~92 nt | 4.99 ms | 200/s |

Evaluating one gate design realistically means a fold, a cofold and a partition function:
**~15 ms per design on one core**, so ~65 designs/s per core.

### What that means for a run

| Designs evaluated | 1 core | 2 vCPU VPS | 4 vCPU VPS |
|---|---|---|---|
| 10,000 | 2.5 min | 1.3 min | 40 s |
| 50,000 | 13 min | 6.4 min | 3.2 min |
| 100,000 | 26 min | 13 min | 6.4 min |
| 500,000 | 2.1 h | 64 min | 32 min |

The worker's current timeout is **1 hour** (`Q_CLUSTER["timeout"]`). So a modest VPS
absorbs a search space of ~100k designs without breaking a sweat, and ~500k with
parallelism ([§7](#7-the-cheap-win-parallelism-inside-the-engine)).

### The number that would change the answer

Search space, and it is a **scientific decision, not an infrastructure one**:

- Top 50 differentially expressed genes, pairs → 1,225 trigger sets × ~10 designs =
  **12k designs → about a minute.** Comfortable.
- Top 200 genes, triples → 1.3M trigger sets × 10 = **13M designs → ~55 hours on one
  core.** No VPS saves you; that needs pruning or a cluster.

**Prune before you combine** — filter triggers by fold change, adjusted p-value and
accessibility *first*, then build combinations from the survivors — and the problem stays
firmly inside one machine. Exhaustive enumeration is what forces a cluster, and it is
rarely the better science anyway.

> **Action:** the first thing Step 5 should produce is a real timing on a real dataset.
> Everything below is contingent on it, and it takes one afternoon to know.

---

## 4. When to move it

Four options, in the order you would reach for them.

### A. In-process on the VPS — **recommended now**

`LocalEngine` runs inside the django-q2 worker. This is what exists today.

**Good:** no network, no serialisation, no second deployment, no second thing to
monitor. Tracebacks land in one log. `./do dev` + `./do worker` is the whole system.

**Limits:** one analysis at a time (`workers: 1`); a run competes with the web process
for CPU; a crash in scientific code takes the worker down (though never a run — see
`execute_run`'s safety net).

**Move on when:** ✗ any of the triggers below fires.

### B. Separate process, same VPS

Engine behind a local HTTP service on `127.0.0.1`, or simply more `qcluster` workers.

**Reach for it when:** the web app becomes sluggish during runs, or two people need to
run analyses concurrently. Raising `Q_CLUSTER["workers"]` to 2–3 is a one-line change and
solves most of this — but note SQLite write contention ([ADR 0002](decisions/0002-sqlite-and-orm-task-queue.md)),
which is the point at which Postgres earns its place.

### C. Separate compute server — *planned in [engine-deployment.md](engine-deployment.md)*

A dedicated VM running `engine/service.py` over HTTP, called by `HttpEngineClient`.

**Reach for it when:** analyses need more RAM or cores than the web VPS should have; or
the scientific team wants to deploy engine changes without touching the product; or runs
routinely exceed ~30 minutes.

**Cost:** a real network boundary — authentication, timeouts, retries, a second
deployment, artifact transfer. Everything ADR 0001 deliberately deferred.

### D. Slurm / PowerSlurm at TAU

The design maps' end state: the Engine submits to a scheduler and collects outputs.

**Reach for it when:** a single analysis genuinely needs hours of CPU or many GB of RAM
— realistically only if you go to exhaustive high-order trigger combinations, or add
something far heavier than RNA folding (structure prediction, ML models, genome-wide
off-target screens).

**Cost:** highest by a distance. Login-node access rules, no public listener on the
cluster, shared filesystem staging, queue waits measured in hours, and an operational
story that only works when someone with TAU HPC access is available. Design map 14
describes it; design map 17 is explicit that no public API may listen on a Slurm login
node.

**My honest read:** for ~5 analyses/day with pruned search, this is unlikely to be worth
it during the competition. Keep it as the documented growth path, not the plan.

### Summary

| Trigger | Move to |
|---|---|
| Runs take >30 min, or the web app stutters during them | **B** — more workers, or Postgres |
| Concurrent runs needed by several researchers | **B** |
| Engine needs cores/RAM the web VPS should not have | **C** |
| Scientific team wants an independent release cadence | **C** |
| One analysis needs hours, or many GB | **D** |
| None of the above | **Stay at A** |

---

## 5. How you would split it, when the time comes

Recorded here so the decision stays cheap. Roughly a day's work.

```python
# src/engine/service.py — new, ~80 lines
from fastapi import FastAPI
from engine.client import LocalEngine
from engine.contract import JobRequest

app = FastAPI()

@app.post("/v1/jobs")          # accept, queue, return a job id
@app.get("/v1/jobs/{id}")      # technical status + progress
@app.get("/v1/jobs/{id}/result")   # the JobResult, verbatim
@app.post("/v1/jobs/{id}/cancel")
@app.get("/version")           # EngineCapabilities
```

```python
# src/engine/client.py — one more implementation of the same Protocol
class HttpEngineClient:
    def run(self, request: JobRequest, on_progress: ProgressFn) -> JobResult:
        # POST the dataclass as JSON, poll status, translate into on_progress,
        # fetch the result, return it. Same return type as LocalEngine.
    def capabilities(self) -> EngineCapabilities: ...
```

Then `CERNAL_ENGINE=engine.client.HttpEngineClient`. **No Platform code changes** — the
boundary test guarantees it, because `apps/` and `api/` may only import
`engine.contract` and `engine.client`.

What the split adds, and why it is worth avoiding until needed:

| Concern | What you must then build |
|---|---|
| Input transfer | The engine can no longer read `dataset.file.path`. Shared storage, or upload-on-submit |
| Artifact return | Currently files on a local disk. Becomes a download step |
| Authentication | A service credential the Platform holds and the engine verifies. Never in the browser |
| Idempotency | The key already exists in `JobRequest`; the engine must now store it |
| Timeouts and retries | Every call becomes fallible |
| Versioning | Platform and engine can now be at different versions simultaneously |

`engine-contract.md` §4 already maps every field onto these endpoints, so the payloads
need no design work.

---

## 6. What I have in mind for the science itself

The deployment answer is "don't move it". The real work is the thirteen stubs in
`engine/pipeline/stages.py`. Suggested order — each step leaves the engine runnable:

### 5a — Dependencies and a folding adapter

Add `viennarna`, `numpy`, `pandas` (all resolve on our pinned Python 3.13 — I checked).
Write `engine/tools/rna.py` wrapping ViennaRNA: `mfe()`, `cofold()`, `accessibility()`,
each recording the tool version for reproducibility. **Nothing else calls ViennaRNA
directly**, so swapping it later touches one file.

### 5b — Input and trigger discovery *(stages 1–3)*

`validate_inputs`, `load_and_preprocess`, `discover_features`. Read the DE table with
pandas, apply fold-change and adjusted-p thresholds, produce `Trigger` objects. This is
also where trigger *sequences* come from — see the open questions in
[§10](#10-what-i-need-from-the-scientific-team).

### 5c — Trigger sets and pruning *(stages 4–5)*

`generate_trigger_sets`, `evaluate_triggers`. **The most important step for
performance.** Prune here, not later: separation quality, expression bounds,
accessibility. Everything downstream scales with what survives.

### 5d — Toehold design and evaluation *(stages 6–7)*

`ToeholdGate.generate_designs` and `evaluate_design`. Construct the switch around each
trigger's reverse complement, vary toehold length across a small window, then fold. This
is where the CPU time goes.

### 5e — Circuits, scoring, artifacts *(stages 8–13)*

`construct_circuits`, then reuse the **already-implemented** `engine.scoring` layer, then
`generate_artifacts` and `publish_result`. Normalization, weighting, hard filters and
ranking already exist and are tested — Step 5 supplies raw metrics, not scoring logic.

### 5f — Switch over

`CERNAL_ENGINE=engine.client.LocalEngine`, measure a real run, and compare against
[§3](#3-what-actually-determines-the-answer).

**`MockEngine` stays.** It remains what CI and frontend development use, and it is the
control when a real result looks wrong.

---

## 7. The cheap win: parallelism inside the engine

Before any thought of another machine. Gate evaluation is embarrassingly parallel —
independent designs, no shared state, pure CPU.

```python
with ProcessPoolExecutor(max_workers=os.cpu_count()) as pool:
    metrics = pool.map(evaluate_design, designs, chunksize=64)
```

On a 4-vCPU VPS that is roughly a **3.5× speedup for about ten lines**, and it keeps the
whole system on one box. Two caveats: leave a core for the web process, and call
`on_progress` from the parent so cancellation still works between batches.

---

## 8. Practical concerns on one box

| Concern | Handling |
|---|---|
| **Worker timeout** | 1 h today. Raise `Q_CLUSTER["timeout"]` *and* `retry` together — retry must stay above timeout or django-q2 re-queues a running job |
| **Memory** | Folding is small per call, but holding 100k designs in a list is not. Stream and prune; do not materialise the full space |
| **CPU starvation** | Reserve a core; consider `nice` on the worker so the web process stays responsive |
| **Cancellation** | Already cooperative. Check `on_progress` between *batches*, not only between stages, or a long evaluation ignores cancellation for minutes |
| **Progress** | Real stages are unevenly sized. Weight `progress_pct` by expected cost, not stage index, or the bar sits at 60% for ten minutes |
| **Disk** | Artifacts land in `var/media/artifacts/`. Add retention before this matters |
| **Reproducibility** | Record ViennaRNA version, model parameters and seed on every run. `engine_version` exists for this |
| **Crash isolation** | A segfault in a C extension kills the worker process. `ProcessPoolExecutor` contains that — another reason for §7 |

---

## 9. Recommendation

1. **Do not split the engine.** Implement 5a–5f behind `LocalEngine`, on the VPS.
2. **Measure a real run** as soon as 5d works. That number decides everything else.
3. **Parallelise in-process** (§7) before considering another machine.
4. **Prune early** (§5c). Search space, not hardware, is the lever.
5. **Keep §5 in your back pocket.** The seam is built and tested; use it if a trigger
   fires, not before.
6. **Treat Slurm as documented, not planned.** It is the right end state for a research
   platform with heavy compute, and probably not this competition.

Deployment (Step 6) is **independent of all of this** and can happen first. You could
ship the mock-engine version this week and let people use it, then switch
`CERNAL_ENGINE` when the science lands, with no downtime and no user-visible change.

---

## 10. What I need from the scientific team

These are scientific decisions I cannot make, and each blocks a specific stage:

| # | Question | Blocks |
|---|---|---|
| 1 | **Where do trigger sequences come from?** The DE table has gene identifiers, not sequences. A reference transcriptome per organism? An accession lookup? User-supplied FASTA? | 5b — and it is the biggest unknown |
| 2 | Thresholds for a usable trigger: minimum fold change, maximum adjusted p, expression bounds | 5c |
| 3 | Maximum trigger-set size. Are 3-input circuits in scope, or is 2 the ceiling? | 5c, and the whole compute budget |
| 4 | Toehold construction rules: stem and loop lengths, RBS, linker, start codon placement, which toehold lengths to vary | 5d |
| 5 | How leakage and dynamic range are computed from folding energies | 5d |
| 6 | Final metric set and weights for `default-v1`. The nine metrics in place now are provisional placeholders I invented | 5e |
| 7 | Hard filters — what disqualifies a candidate outright | 5e |
| 8 | Does organism affect the design rules, or only the input data? | 5b, 5d |

**Question 1 is the one to answer first.** Without trigger sequences there is no design
to fold, and it may require a data source the app does not yet have — which would be a
new dependency with its own storage and licensing questions.
