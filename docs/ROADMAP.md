# Roadmap

> **The single place future work is recorded.** Every task, open question and planned
> implementation lives here. If it is not in this file, it is not planned — and if you
> finish something here, update it in the same commit.
>
> Architecture that is already decided is in [architecture.md](architecture.md); it is
> not repeated here. Rationale that is already settled is in [decisions/](decisions/);
> §9 lists what is closed so nobody re-opens it.

---

## 0. Where we are

| Step | State | Evidence |
|---|---|---|
| Step 0 — Scaffold | **Complete** | Boots, migrates, admin reachable |
| Step 1 — Engine contract + MockEngine | **Complete** | Contract, `MockEngine`, gate/scoring layers, boundary test |
| Step 2 — Domain model | **Complete** | 8 models, migrations, admin back-office, `seed_demo` |
| Step 3 — API + orchestration | **Complete** | 32 endpoints, run state machine, django-q2 worker |
| Step 4 — Frontend integration | **Complete** | React SPA served same-origin: login, wizard, progress, results, static pages |
| **Step 5 — Real science** | **Not started** | §5. The engine is 50 documented stubs raising `NotImplementedError` |
| **Step 6 — Deployment** | **Not started** | §6 |

`./do test` → **415 passing**, and `.gitlab-ci.yml` runs the same checks plus the frontend
build on every push. `CERNAL_ENGINE` defaults to `engine.client.MockEngine`, so the entire
product works end to end on deterministic fake science today.

**What "the engine is stubbed" means precisely:** every class, method and signature
exists with a docstring recording what it owes its caller. Filling one in is a scientific
problem, not an architectural one. The stubs are in `src/engine/stages/`,
`src/engine/tools/`, `src/engine/gates/` and `src/engine/pipeline.py`.

---

## 1. The critical path

```
Q1 (where do trigger sequences come from?)
      │  blocks
      ▼
E1 domain+tools ──▶ E2 stages 1–3 ──▶ E3 pruning ──▶ E4 toehold ──▶ E6 measure
      │                                                                 │
      │                                                                 ▼
      └──▶ E0 dep groups ──▶ C1 container ──▶ C2 equivalence ──▶ C3–C7 cloud
```

**Three things can start today with no scientific input:** E0 (dependency groups), E1
(`domain.py` is already written; `tools/sequences.py` and `tools/motifs.py` need no
ViennaRNA), and every task in §4.

**One thing blocks everything else: Q1.** The DE table has gene identifiers, not
sequences. No amount of infrastructure work answers it.

---

## 2. Open questions for the scientific team

These are scientific decisions that cannot be made from the software side. Each blocks a
specific task.

| # | Question | Blocks |
|---|---|---|
| **Q1** | **Where do trigger sequences come from?** The DE table has gene identifiers, not sequences. A reference transcriptome per organism? An accession lookup? User-supplied FASTA? | **E2** — and it may introduce a new data dependency with its own storage and licensing questions |
| **Q2** | Thresholds for a usable trigger: minimum fold change, maximum adjusted p, expression bounds | E3 |
| **Q3** | Maximum trigger-set size. Are 3-input circuits in scope, or is 2 the ceiling? | E3, and the whole compute budget (§3) |
| **Q4** | Toehold construction rules: stem and loop lengths, RBS sequence, linker, start-codon placement, which toehold lengths to vary | E4 |
| **Q5** | How leakage and dynamic range are computed from folding energies | E4 |
| **Q6** | Final metric set and weights for `default-v1`. The nine metrics in place are provisional placeholders | E5 |
| **Q7** | Hard filters — what disqualifies a candidate outright | E5 |
| **Q8** | Does the organism affect the design rules, or only the input data? | E2, E4 |
| **Q9** | Antisense NOT: does the trigger transcript *act* as the antisense, or *drive* a separate one? | Deferred family, §7 |
| **Q10** | CRISPR: activator or repressor effector? It changes what the circuit means and has no home in the run configuration | Deferred family, §7 |
| **Q11** | Payload sequences. There is no library for GFP, mCherry, luciferase, AmpR or an apoptosis inducer | E5 |

**Q1 first.** Without trigger sequences there is nothing to fold.

---

## 3. The compute budget

Not architecture — arithmetic. The engine's cost is dominated by RNA folding. Measured
on ViennaRNA 2.7.2 on a development machine:

| Operation | Sequence | Per call | Throughput, 1 core |
|---|---|---|---|
| `RNA.fold` | toehold switch, ~92 nt | 2.76 ms | 363/s |
| `RNA.fold` | switch + trigger, ~150 nt | 9.09 ms | 110/s |
| `RNA.cofold` | switch & trigger | 6.89 ms | 145/s |
| partition function | accessibility, ~92 nt | 4.99 ms | 200/s |

Evaluating one gate design realistically means a fold, a cofold and a partition function:
**~15 ms per design on one core**, so ~65 designs/s per core.

| Designs evaluated | 1 core | 2 vCPU | 4 vCPU |
|---|---|---|---|
| 10,000 | 2.5 min | 1.3 min | 40 s |
| 50,000 | 13 min | 6.4 min | 3.2 min |
| 100,000 | 26 min | 13 min | 6.4 min |
| 500,000 | 2.1 h | 64 min | 32 min |

The worker's timeout is **1 hour** (`Q_CLUSTER["timeout"]`). So a modest VPS absorbs
~100k designs comfortably, and ~500k with in-process parallelism (E7).

### The number that decides everything

Search space, and it is a **scientific decision (Q2, Q3), not an infrastructure one**:

- Top 50 DE genes, pairs → 1,225 trigger sets × ~10 designs = **12k designs → about a
  minute.** Comfortable.
- Top 200 genes, triples → 1.3M trigger sets × 10 = **13M designs → ~55 hours on one
  core.** No VPS saves you; that needs pruning or a cluster.

**Prune before you combine.** Filter triggers by fold change, adjusted p and accessibility
*first*, then build combinations from the survivors, and the problem stays inside one
machine. Exhaustive enumeration is what forces a cluster, and it is rarely the better
science anyway.

> **The first thing Step 5 should produce is a real timing on a real dataset** (E6).
> Everything in §6 is contingent on it, and it takes one afternoon to know.

---

## 4. Phase P — Platform gaps

Things that are wrong or missing *today*, independent of the science. All are small, none
are blocked, and each is a good first task for someone new.

| # | Task | Where | Size |
|---|---|---|---|
| **P1** | **Reconcile the two organism fields.** `Project.organism` is free text (`"E. coli"`); `params_snapshot["organism"]` is a `Host` value (`"ecoli"`). `JobRequest.organism` is populated from the free-text one, but the engine will parse it as a `Host`. Decide which is authoritative, constrain it to the enum, and migrate | `apps/projects/models.py`, `apps/analyses/services.py`, frontend project form | S |
| **P2** | **Report gate families per host.** `available_families(host)` exists in the registry but `GET /api/version` calls it without a host, so the wizard cannot grey CRISPR out for *E. coli*. Add an optional `?organism=` and use it in the wizard | `api/routers/meta.py`, `api/schemas.py`, `frontend/src/components/compile/Steps.tsx` | S |
| **P3** | **Validate `custom_sequence`.** The `other` output accepts any pasted string — no ORF check, no stop-codon check, no length cap | `apps/analyses/services.py` | S |
| **P4** | **Artifact retention.** `var/media/artifacts/` grows without bound. Add a retention policy before it matters, not after | `apps/results/`, a management command | S |
| **P5** | **Weight `progress_pct` by expected cost.** `STAGE_WEIGHTS` exists in `pipeline.py` but nothing consumes it. Real stages are unevenly sized; by stage index the bar sits at 60% for ten minutes | `engine/pipeline.py` | S |
| **P6** | **Raise the worker timeout deliberately.** 1 h today. Raise `Q_CLUSTER["timeout"]` *and* `retry` together — `retry` must stay above `timeout` or django-q2 re-queues a running job | `config/settings/base.py` | S |
| **P7** | **Extend CI.** `.gitlab-ci.yml` already runs backend lint + format + `manage.py check` + pytest, and frontend type-check + render test + build, on every push. What it does not yet have is the container build and the equivalence job — those arrive with **C1/C2**. Keep `MockEngine` as CI's engine: deterministic, no scientific dependencies, fast enough that people run it | `.gitlab-ci.yml` | S |
| **P8** | **A type checker on `engine/` only.** Ruff catches style; pyright or mypy catches a `float \| None` used as a `float`, which is the failure mode of algorithmic code | `pyproject.toml` | S |
| **P9** | **`ToeholdAndGate` is selectable but unimplemented.** It subclasses `ToeholdGate` and does not override `available`, so it inherits `True`. A submission requesting `toehold_and` passes validation and then raises `NotImplementedError` under `LocalEngine`. Set `available = False` until E4 lands, or decide deliberately to leave it on | `engine/gates/toehold.py` | S |

---

## 5. Phase E — The engine

**This is Step 5, and it is the long pole.** Order is bottom-up, because every stage
depends on the tools. Each task leaves the engine runnable.

### E0 · Split dependency groups — *do this now*

Independent of everything else and it costs nothing. Today `engine/` imports only the
standard library; Step 5 changes that, and this is the moment to stop the two halves'
dependencies from mixing.

Today `[project].dependencies` holds the Django stack and there is one `dev` extra. Move
the Django stack into a `platform` extra and add an `engine` one:

```toml
[project]
dependencies = []          # nothing shared

[project.optional-dependencies]
platform = ["django>=5.2,<6.0", "django-ninja>=1.3", "django-q2>=1.7", …]
engine   = ["viennarna>=2.7", "numpy>=2.0", "pandas>=2.2"]
dev      = ["pytest>=8.3", "pytest-django>=4.9", "ruff>=0.8"]   # unchanged
```

The VM installs `platform`; the container installs `engine`. Neither installs the other.
Also update `./do install` and the CI `backend` job to `--extra platform --extra dev`.

**Done when:** `uv sync --extra engine --no-dev` produces an environment with no Django in
it, and `./do test` still passes.

### E1 · Tools — the scientific primitives

`domain.py` is already written and tested. The tools are not.

| Order | Build | Needs |
|---|---|---|
| 1 | `tools/sequences.py` (S6) — `reverse_complement`, `translate`, `find_stops`, `find_augs`, `gc_content`, `longest_homopolymer` | Nothing. Start here |
| 2 | `tools/motifs.py` (S7) — `MotifScreener`: RFC10/RFC1000 sites, RBP motifs, RNase sites, homopolymers > 5 nt | Nothing |
| 3 | `tools/folding.py` (S1, S2, S4) — `FoldEngine`, `FoldProfiler`, `structure_match` | ViennaRNA |
| 4 | `tools/binding.py` (S3) — `hybridization_energy` | ViennaRNA |
| 5 | `tools/off_target.py` (S5) — `OffTargetScanner`, both directions | Q1's transcriptome |
| 6 | `tools/codons.py` (S8), `tools/translation.py` (S9) | Codon tables per host |

**`FoldEngine` is the highest-leverage thing in the engine.** Every generator and
validator folds sequences. Two rules:

- **It is the only module that imports `RNA`.** One place to swap the library, one place
  to record its version.
- **Cache aggressively.** `lru_cache` on `mfe` is the single biggest speed win available —
  the same subsequence recurs constantly across designs, and folding it twice is pure
  waste. (This is why sequences are `str` and trigger sets are tuples: `lru_cache` needs
  hashable arguments.)

**Done when:** `./do test tests/engine` passes in under a second with real folding, and
`FoldEngine.versions()` returns the ViennaRNA version.

### E2 · Stages 1–3 — input, genes, triggers · **blocked on Q1**

`InputQualityCheck` → `GeneSelector` → `TriggerScorer`.

- Read the DE table with pandas. **Do not carry DataFrames through the pipeline** —
  convert to `DgeTable` at the edge.
- `GeneSelector` keeps genes that separate the two states: fold change, adjusted p, and a
  usable absolute expression range in both states. Too low gives false negatives, too high
  false positives.
- `TriggerScorer` slides a window along each surviving transcript and ranks every
  sub-segment. **Per length class**, because each gate family needs a different footprint.
- Genes DESeq2 filtered out carry **no** `p_adj` at all. "Not tested" must not be treated
  as "not significant".

**Also build the `direct` branch here** — a pasted sequence becomes one `TriggerCandidate`
and stages 1–2 are skipped ([modalities.md §1](modalities.md)).

**Done when:** a real DE file produces ranked `TriggerCandidate` records with real
openness and GC numbers.

### E3 · Stages 4–5 — trigger sets and pruning · **blocked on Q2, Q3**

**The most important step for performance.** Everything downstream scales with what
survives here.

- Combine surviving triggers into `TriggerSet`s up to `max_triggers`.
- **Two triggers may come from the same gene.** Nothing here may deduplicate by
  `gene_id`.
- Prune on separation quality, expression bounds and accessibility — *before* combining,
  not after.

**Done when:** the number of trigger sets produced from a real dataset is a number you
chose, not a number you discovered.

### E4 · Toehold design and evaluation · **blocked on Q4, Q5**

`ToeholdGate.generate_designs` and `evaluate_design`. **This is where the CPU time goes.**

Construction and the metric list are spelled out in the stubs and summarised in
[modalities.md §3](modalities.md). Two things worth repeating because they are the
expensive mistakes:

- Fold the ON state as a **dimer** (`cofold`, `&` separator), not a concatenated strand.
- Return **raw** values with `None` for anything uncomputable. Normalization, weighting
  and filtering belong to `engine.scoring`, which is already built and tested.

**Done when:** a golden test fixes a small input to its full expected output, and
`ENGINE_VERSION` is bumped whenever that file legitimately changes.

### E5 · Circuits, plasmids, report · **blocked on Q6, Q7, Q11**

`CircuitDesigner` → `PlasmidBuilder` → `ReportBuilder`, then the already-implemented
scoring layer.

- `CircuitDesigner` turns the genes' up/down pattern into a Boolean function, generates
  the expressions reproducing it, keeps only those buildable from switches actually
  designed upstream, and ranks by **separation versus complexity**.
- Cross-talk: the circuit's own triggers against the circuit's *other* switches. **Do not
  re-scan the transcriptome** — per-trigger and per-switch penalties are already computed
  and stored upstream, and re-scanning would be both slow and inconsistent with the
  numbers already recorded.
- `PlasmidBuilder` needs a payload sequence library (Q11) and a backbone spec.
- Screen the **whole assembled construct** for restriction sites, not each segment —
  screening segments individually misses sites formed across a junction.

**Done when:** `JobResult` from `LocalEngine` populates every field the results screen
already renders from `MockEngine`.

### E6 · Switch over and measure

Set `CERNAL_ENGINE=engine.client.LocalEngine`, run a real dataset, and record wall time,
peak RAM and core count. **Compare against §3.** This number sizes everything in §6.

**`MockEngine` stays.** It remains what CI and frontend development use, and it is the
control when a real result looks wrong.

### E7 · Parallelism — the cheap win

Before any thought of another machine. Gate evaluation is embarrassingly parallel —
independent designs, no shared state, pure CPU.

```python
with ProcessPoolExecutor(max_workers=os.cpu_count()) as pool:
    metrics = pool.map(evaluate_design, designs, chunksize=64)
```

Roughly **3.5× on a 4-vCPU box for about ten lines**. Two caveats: leave a core for the
web process, and call `on_progress` from the parent so cancellation still works between
batches. A segfault in a C extension kills the worker process — `ProcessPoolExecutor`
contains that, which is a second reason to do it.

**Order of optimisation, and stop when it is fast enough:** prune early → cache folding →
generators → process pool → numpy for metric arithmetic → *only then* a bigger machine.
**Measure before optimising.** If `cProfile` on a real run does not point at folding, the
intuition behind this whole plan is wrong and worth knowing early.

### E8 · Tests that lock it in

| Kind | What |
|---|---|
| **Golden** | Fixed input → committed expected output. **The one teams skip and regret** |
| **Property** | Score in 0–1; ranks contiguous; rejected candidates always carry reasons |
| **Determinism** | Same seed twice → identical. Already asserted for `MockEngine`; must hold for `LocalEngine` |
| **Tool** | The adapter against known structures — a hairpin folds as a hairpin |

Keep fixtures small enough that `./do test tests/engine` stays under a second. A test
suite nobody runs protects nothing.

### E9 · Report the things a column header cannot say

Three known reporting requirements that fall out of the modalities:

1. **A gate's default state alongside its payload.** An antisense NOT gate is ON by
   default, so a failed gate *expresses* the payload. With an apoptosis inducer that is a
   safety failure ([modalities.md §5](modalities.md)).
2. **When `predicted_leakage` means the opposite.** Same metric name, same direction,
   opposite biological event between toehold and antisense.
3. **Tool versions and model parameters**, recorded on every run. Without them a result
   from six months ago is uninterpretable after a ViennaRNA upgrade.

### E10 · Settle `CandidateStore`

The pipeline map says every stage reads its input and writes its output through a store,
with CSV as the only interface. **That is two ideas and only one of them is free.**

**Worth keeping:** every stage writing an inspectable CSV with stable IDs and provenance.
The scientific team can open stage 2's output in Excel, a run is auditable, and a stage
can be re-run from saved input while it is being developed.

**Worth reconsidering:** making CSV the *only* interface. It costs streaming (stage 3
cannot start until stage 2 has written every row), types (every read re-parses strings,
and a column typo fails at runtime rather than in the type checker), speed, and code
(every record needs a writer, a reader and a schema).

**Recommendation: typed objects between stages, CSV snapshots at stage boundaries.** A
recorder, not a bus. You keep debuggability, provenance and re-runnability, and lose only
the constraint that made streaming impossible.

**This is a team decision, and it should be made deliberately** — it is hard to reverse
once six stages depend on it.

### E11 · Pareto filtering

`rank_candidates` ranks; **Pareto filtering across score-versus-complexity is not built**.
A circuit with a slightly lower score and half the components is often the better answer,
and only a Pareto front says so.

---

## 6. Phase C — Container and cloud

**Step 6.** Nothing here starts before E6 produces a measured run — sizing the compute is
guesswork until then.

### The shape

A small always-on VM runs the product; a container runs the science on demand and stops.
**Idle compute cost is zero.**

```
┌─ Compute Engine · e2-small · always on ────────────────────┐
│   Caddy → gunicorn → Django                                │
│   django-q2 worker                                         │
│   Persistent disk:  var/cernal.db                          │
└───────────┬────────────────────────────────────────────────┘
            │ 1. upload dataset          ┌────────────────────┐
            ├───────────────────────────▶│  Cloud Storage     │
            │                            │   datasets/        │
            │ 2. jobs.run(overrides)     │   runs/<id>/       │
            ▼                            │     progress.json  │
┌─ Cloud Run Job · 4–8 vCPU ─────────┐   │     result.json    │
│   cernal-engine container          │◀──┤     artifacts/     │
│   · starts on submit               │──▶│                    │
│   · stages input down              │   └────────────────────┘
│   · runs LocalEngine               │             ▲
│   · stages artifacts up            │             │
│   · exits · ZERO idle cost         │  3. poll progress, read result
└────────────────────────────────────┘
```

Full rationale — why a batch job rather than an auto-waking service, why a plain VM rather
than Cloud Run for the web app, why no presigned URLs — is in
[deployment.md](deployment.md).

### The tasks

| # | Task | Done when |
|---|---|---|
| **C0** | Measure a real run: wall time, peak RAM, cores (= E6) | You know what `--cpu` and `--memory` to ask for |
| **C1** | `engine/runner/gcs_entry.py` + `deploy/Dockerfile.engine`, **local paths only** | `docker run` on a laptop produces a `JobResult` |
| **C2** | **Equivalence tests** — the same request through `LocalEngine` and the container, compared field for field | The same run, two engines, identical output |
| **C3** | Bucket, service accounts, IAM. **No key files** | The VM can start a job; the job can reach only its bucket |
| **C4** | `CloudRunEngineClient` in `engine/client.py` | `CERNAL_ENGINE=engine.client.CloudRunEngineClient` runs a real job |
| **C5** | Upload the dataset to the bucket at submit time | **The only change to Platform code in this whole phase** |
| **C6** | Progress, cancellation, idempotency over the boundary | The bar moves; cancel stops it; a double submit runs once |
| **C7** | **Failure drills** — kill the execution mid-run, break IAM, submit twice, corrupt an artifact | Each lands in a terminal state with a readable message |

**C2 is the discipline that matters.** It is the only thing that stops "works on my
laptop" and "works on Cloud Run" from drifting apart, and it catches three failures
nothing else does: a dependency present locally but missing from the image;
non-determinism from an unseeded RNG or dictionary ordering; and a staging bug in
`gcs_entry.py` that corrupts input or loses artifacts.

For it to be runnable without a storage emulator, **`gcs_entry.py` must accept local
paths as well as `gs://`** — check the scheme, and if it is not `gs://` use the path
as-is. That is also how a failed production run gets reproduced on a laptop.

**C7 is not optional.** Every one of those failures is new, and the only way to know they
are handled is to cause them.

### New `./do` commands this phase adds

```
engine-run     Run the pipeline locally on a file — no worker, no database, no cloud
engine-build   Build the engine container
engine-test    Run the container against local paths (the equivalence test's engine)
deploy-engine  Build, push and update the Cloud Run Job:  ./do deploy-engine 0.4.0
deploy-web     Deploy the Django app to the VM
```

`engine-run` is the one that matters day to day: it is the scientific team's inner loop,
and it must never require Docker, a database or a network.

### Versioning

**Tag the image with `ENGINE_VERSION`, never `latest`.** Then `AnalysisRun.engine_version`
identifies the exact image that produced a result, and a result from six months ago can be
reproduced by running that tag. Bump it whenever output could change — a new metric, a
changed threshold, a ViennaRNA upgrade.

---

## 7. Deferred work

Recorded so the decision is cheap when someone asks. **None of this is scheduled.**

| Item | Blocked on | Note |
|---|---|---|
| **`ToeholdAndGate` bodies** | E4 | The chemistry is inherited; the serial-stem construction is not. Watch the half-open intermediate state |
| **`AntisenseNotGate`** | Q9 | Unblocks NOT logic, and therefore down-regulated genes as inputs — half the DE signal |
| **`CrisprGate`** | Q10 + a genomic off-target scanner | `OffTargetScanner` searches the transcriptome; the spacer needs the genome |
| **GenBank export** | E5 | Needs a real annotated construct |
| **Plasmid synthesis ordering** | E5 | A partner integration, not a code problem |
| **3-input circuits** | Q3 | See §3 — this is what forces a cluster |
| **Repository split** | Nothing | See §9. Do it when it hurts not to, not on a date |
| **Slurm / TAU PowerSlurm** | — | The design maps' end state. For ~5 analyses/day with pruned search, unlikely to be worth it during the competition. Documented, not planned |

---

## 8. Growth path

None of this is current work. It is recorded so that when the trigger fires, the move is
known and small.

| Trigger | Move |
|---|---|
| Runs take > 30 min, or the web app stutters during them | Raise `Q_CLUSTER["workers"]` to 2–3, then Postgres when SQLite write contention appears |
| Concurrent runs needed by several researchers | Same |
| Engine needs cores or RAM the web VPS should not have | Phase C — the container was always the answer to this |
| Scientific team wants an independent release cadence | Phase C, then possibly a repo split |
| SQLite write contention in the logs | `DATABASE_URL` → Postgres; run migrations. One variable |
| Queue depth, or multi-machine workers | django-q2 → Redis broker, or Celery |
| Disk pressure, or multi-host serving | `django-storages` → S3-compatible; `Artifact.file` is already an abstraction |
| External collaborators need accounts | Re-introduce `Workspace` + `WorkspaceMembership` + role checks |
| One analysis genuinely needs hours or many GB | Slurm. Highest cost by a distance — login-node access rules, no public listener on the cluster, shared filesystem staging, queue waits in hours |

---

## 9. Settled — do not re-litigate

Each of these was decided with a reason. If you want to change one, the bar is a new ADR
in [decisions/](decisions/) explaining what broke without it.

| Decision | Where |
|---|---|
| One repository, in-process engine | [ADR 0001](decisions/0001-single-repo-in-process-engine.md) |
| SQLite + django-q2 ORM broker, not Postgres + Celery | [ADR 0002](decisions/0002-sqlite-and-orm-task-queue.md) |
| Same-origin SPA, session cookies, no JWT | [ADR 0003](decisions/0003-same-origin-spa-session-auth.md) |
| django-ninja over DRF | [ADR 0004](decisions/0004-django-ninja-over-drf.md) |
| Static SPA, not TanStack Start | [ADR 0005](decisions/0005-static-spa-not-tanstack-start.md) |
| **Deployment separation is not repository separation.** The container builds a subset of the repo; splitting it would cost the boundary test, atomic contract changes, and the equivalence tests | [deployment.md](deployment.md) |
| **No `Job` class.** The pipeline is functions over frozen data. A god object cannot be tested per stage, forces materialisation, and fights parallelism | [engine.md §2.3](engine.md) |
| **Gate families do not score themselves.** Raw metrics out, normalization in `engine.scoring` | [engine.md §3.6](engine.md) |
| **Tools are shared, not copied per gate.** Three transcriptome indexes means three mismatch conventions and three penalty scales — and scoring would normalise them onto one axis as though they were comparable | [engine.md §3.4](engine.md) |
| **Host is a parameter, not a subclass**, until the method bodies actually diverge | [engine.md §2.4](engine.md) |
| No Pydantic inside the engine, no workflow framework, no ORM in the engine | [engine.md §2.5](engine.md) |
| Python 3.13, not 3.14 — scientific wheels lag new CPython by months | [development.md](development.md) |

---

## How to use this file

- **Starting something?** Check its blockers in §2 first.
- **Finished something?** Update its row and §0 in the same commit.
- **Found new work?** Add it here, with an id, a size and what it blocks. Not in a
  separate document — that is how the previous fourteen planning files happened.
- **Want to change a settled decision?** Write the ADR first.
