# Engine internal design

> **Planning document.** The stubs exist; the science does not.
> [`engine-contract.md`](engine-contract.md) covers what crosses the boundary.
> This covers how the engine is built **inside** it.

You proposed classes for `Job`, `Plasmid`, `Gate`, `GateType`. That instinct is right in
one place and a trap in another, and the difference is worth being precise about.

---

## 1. The rule

> **Classes where you need polymorphism. Frozen dataclasses for data.
> Plain functions for transformations.**

| Your idea | What it should be | Why |
|---|---|---|
| `GateType` | **Class hierarchy** — `GateFamily` ABC | Toehold, CRISPR and antisense genuinely behave differently. This is what polymorphism is for |
| `Gate` | **Frozen dataclass** — `GateDesign` | A design is a *record of what was computed*, not an object with behaviour |
| `Plasmid` | **Frozen dataclass** — a tuple of segments | Same. It is data with a couple of computed properties |
| `Job` | **A function** — `run_pipeline(request, on_progress)` | See [§3](#3-the-one-thing-not-to-build). This is the trap |

The repo already follows this: `GateFamily` is an ABC (behaviour), `Trigger`, `TriggerSet`
and `GateDesign` are `@dataclass(frozen=True, slots=True)` (data).

**So your model maps onto what exists** — `GateType` → `GateFamily`, `Gate` → `GateDesign`.
The rest of this document extends that, rather than replacing it.

---

## 2. Why immutability, specifically here

Not style preference. Four concrete reasons, in the order they will bite you:

**Parallelism.** Gate evaluation is embarrassingly parallel and will need
`ProcessPoolExecutor` ([step-5 §7](step-5-engine-plan.md)). Workers communicate by
pickling. Frozen dataclasses pickle cleanly and cannot be mutated across a process
boundary in a way you would never see. Mutable shared objects simply do not survive this.

**Determinism.** The engine must produce identical output for identical input — the
contract promises it and a test asserts it. Mutation is where nondeterminism hides: a
stage quietly modifying a design that a later stage also reads, and the result depending
on ordering.

**Reproducibility.** A `CandidateResult` is a record of what was computed. If it can be
edited after the fact, it stops being evidence.

**Memory.** `slots=True` removes each instance's `__dict__`. Across 100k designs that is
the difference between comfortable and swapping.

**And testability**, which falls out for free: a pure function over frozen data needs no
setup, no mocks, and no teardown.

---

## 3. The one thing not to build

The `Job` class. It is the natural first design and it goes wrong the same way every time:

```python
# Don't.
class Job:
    def __init__(self, request): ...
    def load_data(self):        self.data = ...
    def find_triggers(self):    self.triggers = ...
    def generate_gates(self):   self.designs = ...
    def evaluate(self):         self.metrics = ...
    def score(self):            self.candidates = ...
```

Four problems, all of which arrive late:

1. **You cannot test a stage in isolation.** Testing `score()` means constructing a `Job`
   and running everything before it.
2. **It is a god object.** Every stage can read and write every attribute, so the actual
   data flow becomes unknowable.
3. **It forces materialisation.** `self.designs` is a list, so all 100k live in memory at
   once. Generators are impossible.
4. **It fights parallelism.** You cannot hand `self` to a worker process.

**Instead: functions that take what they need and return what they produce.**

```python
def run_pipeline(request: JobRequest, on_progress: ProgressFn) -> JobResult:
    profile   = get_profile(request.scoring_profile)
    table     = load_expression_table(request.input_path)     # 1-2
    triggers  = discover_features(table, constraints)         # 3
    sets      = generate_trigger_sets(triggers, constraints)  # 4-5, generator
    designs   = generate_gates(sets, families, constraints)   # 6,   generator
    scored    = evaluate_and_score(designs, profile)          # 7-10, generator
    ranked    = rank_and_filter(scored, profile)              # 11,  materialised
    artifacts = generate_artifacts(ranked, request.output_dir)# 12
    return publish_result(request, ranked, artifacts)         # 13
```

The data flow is the code. Every step is independently testable, and the generators mean
memory stays flat until `rank_and_filter` — which is the one place that legitimately needs
everything at once, and by then pruning has cut the volume.

---

## 4. The domain model

Concretely, and where each type belongs.

### Move the shared types out of `gates/base.py`

They live there today because `GateFamily` was the first thing that needed them. As the
engine grows, an ABC and every shared type in one module gets crowded.

```
src/engine/
├── domain.py        ★ NEW — the vocabulary: Trigger, TriggerSet, GateDesign,
│                            Circuit, Plasmid, Constraints
├── gates/
│   └── base.py        GateFamily ABC only — imports from domain
```

One module, not a package. Split it when it exceeds a few hundred lines, not before
(rule 12).

### The types

```python
# engine/domain.py

@dataclass(frozen=True, slots=True)
class Trigger:
    """One input signal: a transcript whose presence drives the switch."""
    feature_id: str
    sequence: str
    base_expression: float
    target_expression: float

    @property
    def separation(self) -> float:
        return self.target_expression - self.base_expression


@dataclass(frozen=True, slots=True)
class TriggerSet:
    """The inputs to one circuit. Size determines the logic arity."""
    triggers: tuple[Trigger, ...]          # tuple, not list — hashable and frozen
    repressors: tuple[Trigger, ...] = ()   # must be ABSENT for the circuit to fire

    @property
    def arity(self) -> int:
        return len(self.triggers)


@dataclass(frozen=True, slots=True)
class GateDesign:
    """One concrete realisation of a trigger set in a particular chemistry."""
    ref: str
    family: str
    trigger_set: TriggerSet
    switch_sequence: str
    structure: str = ""
    toehold_length: int = 0
    properties: dict = field(default_factory=dict)   # family-specific, opaque


@dataclass(frozen=True, slots=True)
class Segment:
    """One stretch of the construct. `kind` is a closed vocabulary."""
    kind: SegmentKind
    name: str
    sequence: str
    length_bp: int


@dataclass(frozen=True, slots=True)
class Plasmid:
    """The assembled construct. Data plus arithmetic, no behaviour."""
    segments: tuple[Segment, ...]

    @property
    def length_bp(self) -> int:
        return sum(s.length_bp for s in self.segments)

    @property
    def gc_content(self) -> float: ...

    def sequence(self) -> str:
        return "".join(s.sequence for s in self.segments)


@dataclass(frozen=True, slots=True)
class Circuit:
    """A complete candidate: inputs, gate, construct, and the logic they express."""
    ref: str
    trigger_set: TriggerSet
    design: GateDesign
    plasmid: Plasmid
    output: str
```

### Closed vocabularies get enums

Strings work until someone types `"promotor"`. These are small, fixed, and appear in
output:

```python
class SegmentKind(StrEnum):
    PROMOTER = "promoter"
    SWITCH = "switch"
    PAYLOAD = "payload"
    TERMINATOR = "terminator"
    BACKBONE = "backbone"

class Direction(StrEnum):
    HIGHER_BETTER = "HIGHER_BETTER"
    LOWER_BETTER = "LOWER_BETTER"
```

`StrEnum` members *are* strings, so they serialise into `JobResult` unchanged and the
contract does not need to know.

### Domain types stay inside the engine

`Circuit` and `Plasmid` never cross the boundary. `publish_result` converts them into
`CandidateResult` — plain dicts and floats. That is what keeps the contract stable while
the science churns underneath it.

---

## 5. Where behaviour lives

`GateFamily` is the one real class hierarchy, and it already exists.

```python
class GateFamily(ABC):
    name: ClassVar[str]
    version: ClassVar[str]
    label: ClassVar[str]
    available: ClassVar[bool]

    @abstractmethod
    def is_compatible(self, ts: TriggerSet, c: Constraints) -> Compatibility: ...
    @abstractmethod
    def generate_designs(self, ts: TriggerSet, c: Constraints) -> Iterator[GateDesign]: ...
    @abstractmethod
    def evaluate_design(self, d: GateDesign) -> dict[str, float | None]: ...
    @abstractmethod
    def emit_sequence(self, d: GateDesign) -> str: ...
```

Three properties worth preserving as you fill it in:

**`evaluate_design` returns raw values only.** Normalization, weighting and filtering
belong to `engine.scoring`, which is already implemented and tested. A family that scored
its own designs could not be compared with another family — that is the central problem
design map 12 identifies.

**`generate_designs` yields.** A family exploring toehold lengths 12–18 across 5,000
trigger sets produces 35,000 designs. Returning a list materialises all of them.

**Families never fold anything directly.** They call `engine.tools.rna` ([§6](#6-the-tool-adapter)).

Adding CRISPR later is then: one module, one `register()` call, nothing else.

---

## 6. The tool adapter

Every ViennaRNA call goes through one module. This is the highest-leverage boundary inside
the engine after the contract itself.

```python
# engine/tools/rna.py — the ONLY module that imports RNA

@lru_cache(maxsize=100_000)
def mfe(sequence: str) -> tuple[str, float]:
    """Structure and minimum free energy. Cached: the same subsequence recurs
    constantly across designs, and folding it twice is pure waste."""
    return RNA.fold(sequence)

def hybridisation_energy(switch: str, trigger: str) -> float: ...
def accessibility(sequence: str, start: int, end: int) -> float: ...

def tool_versions() -> dict[str, str]:
    """Recorded on every run. Without this, a result from six months ago is
    uninterpretable after a ViennaRNA upgrade."""
    return {"ViennaRNA": RNA.__version__}
```

Four things this buys you: a **cache** on the hottest operation; **version recording** for
reproducibility; **one place to swap** the folding library; and **testability**, since
stubbing one module fakes all folding.

> `lru_cache` requires hashable arguments — another reason sequences are `str` and trigger
> sets are tuples.

---

## 7. Pipeline shape

Keep the thirteen stage functions: they are the scientific vocabulary and they match
design map 11. Compose them with generators.

```python
def evaluate_and_score(
    designs: Iterator[GateDesign], profile: ScoringProfile
) -> Iterator[ScoredCandidate]:
    """Stages 7-10. The expensive part, and the parallel one."""
    for design in designs:
        raw = evaluate_gates(design)                  # folding happens here
        if breach := failed_filter(raw, profile):     # prune in the stream
            yield rejected(design, breach.reason)
            continue
        metrics = build_metrics(raw, profile)
        yield ScoredCandidate(design, metrics, weighted_score(metrics, profile))
```

Two principles that keep this workable at scale:

**Filter in the stream.** A rejected candidate is yielded with its reason and never
evaluated further. Rule 8 is satisfied *and* the work is avoided.

**Materialise only survivors.** `rank_and_filter` is the first stage that needs everything
at once. By then pruning has done its job.

### Progress and cancellation

`on_progress(pct, stage)` returns `False` to cancel. Call it **between batches**, not only
between stages — a ten-minute evaluation that never checks makes cancellation a lie.

```python
for batch_index, batch in enumerate(batched(designs, 500)):
    if not on_progress(pct_for(batch_index), "Evaluating gate designs"):
        raise JobCancelled()
    yield from evaluate_batch(batch)
```

Weight `pct` by expected cost, not stage index, or the bar sits at 60% for ten minutes.

---

## 8. Modern Python worth using — and what to skip

You asked what you might be unaware of.

| Tool | Use it for | Notes |
|---|---|---|
| `@dataclass(frozen=True, slots=True)` | Every domain type | Already used. `slots` matters at 100k objects |
| `Protocol` | `EngineClient` | Structural typing — no inheritance needed |
| `ABC` | `GateFamily` | When you *want* a base class with shared helpers |
| `StrEnum` | Closed vocabularies | Serialises as a plain string |
| Generators / `itertools.batched` | The whole pipeline | Flat memory. `batched` is 3.12+ |
| `functools.lru_cache` | Folding | The single biggest speed win |
| `ProcessPoolExecutor` | Gate evaluation | ~3.5× on 4 cores, ~10 lines |
| numpy | Metric arrays, normalization | Vectorise arithmetic over many candidates — not sequence work |
| pandas | Reading the DE table | For input parsing. Do not carry DataFrames through the pipeline |
| **pyright / mypy** on `engine/` only | Algorithmic code | **Worth adding.** Ruff catches style; a type checker catches a `float \| None` used as a `float` |
| `hypothesis` | Scoring invariants | Optional, but a natural fit — "normalized value is always in 0–1, for any input" |

### What to skip

**Pydantic inside the engine.** It is the right tool at the API edge — django-ninja
already uses it — but validation on every object in a hot loop is cost you do not need.
**Validate at the edges, trust inside.**

**A workflow framework** (Prefect, Dagster, Airflow). Thirteen sequential stages in one
process is a function call, not a DAG. These solve distributed scheduling, retries and
backfills — problems you do not have.

**An ORM or database inside the engine.** It receives a request and returns a result. The
Platform owns persistence, and §3 depends on this staying true.

**Inheritance beyond `GateFamily`.** One hierarchy, one level deep. Composition for
everything else.

---

## 9. Target layout

```
src/engine/
├── contract.py          crosses the boundary — change deliberately
├── client.py            MockEngine · LocalEngine · CloudRunEngineClient
├── errors.py
├── artifacts.py
├── domain.py          ★ Trigger · TriggerSet · GateDesign · Plasmid · Circuit
├── tools/
│   └── rna.py         ★ the only ViennaRNA caller
├── gates/
│   ├── base.py          GateFamily ABC (types move to domain.py)
│   ├── registry.py
│   ├── toehold.py     ★ the real implementation
│   └── planned.py
├── scoring/             already implemented and tested
│   ├── profiles.py
│   └── normalize.py
├── pipeline/
│   ├── __init__.py      run_pipeline — composition only
│   └── stages.py      ★ the thirteen stages
└── runner/
    └── gcs_entry.py   ★ container entrypoint (engine-development.md)
```

Everything scientific is under `engine/`, as you wanted — and the boundary test already
guarantees nothing outside reaches into it.

---

## 10. Testing scientific code

Different from testing product code, and worth planning.

| Kind | What | Example |
|---|---|---|
| **Unit** | One stage, tiny fixture | 20 genes → expected triggers |
| **Golden** | Fixed input → known output, committed | Catches "the numbers moved" on a refactor |
| **Property** | Invariants over any input | Score in 0–1; ranks contiguous; rejected have reasons |
| **Determinism** | Same seed twice → identical | Already asserted for `MockEngine`; must hold for `LocalEngine` |
| **Tool** | The adapter against known structures | A hairpin folds as a hairpin |
| **Equivalence** | `LocalEngine` vs container | [engine-development.md §5](engine-development.md) |

**Golden tests are the ones teams skip and regret.** Commit a small input and its full
expected output. When a refactor changes a score, you find out immediately — and if the
change was intended, you update the file deliberately and bump `ENGINE_VERSION`.

Keep fixtures small enough that `./do test tests/engine` stays under a second. A test
suite nobody runs protects nothing.

---

## 11. Performance, in order

Do these in this order, and stop when it is fast enough.

1. **Prune early.** Search space dwarfs everything else ([step-5 §3](step-5-engine-plan.md)).
2. **Cache folding.** `lru_cache` on `mfe`. Enormous, nearly free.
3. **Generators.** Flat memory, no swapping.
4. **`ProcessPoolExecutor`** on evaluation. ~3.5× on 4 cores.
5. **numpy** for metric arithmetic across candidates.
6. **Only then** consider a bigger machine.

**Measure before optimising.** `cProfile` on a real run will point somewhere you did not
expect — and if it does not point at folding, the intuition behind this whole plan is
wrong and worth knowing early.

---

## 12. What to build first

| # | Step | Why first |
|---|---|---|
| 1 | `domain.py` — move types out of `gates/base.py`, add `Plasmid`, `Circuit`, enums | Everything else references these |
| 2 | `tools/rna.py` with `mfe`, `accessibility`, `tool_versions` | Every stage below needs it |
| 3 | Stages 1–3: read the table, discover triggers | First real output; answers scientific question 1 |
| 4 | Stages 4–5: trigger sets **and pruning** | Sets the compute budget |
| 5 | `ToeholdGate.generate_designs` + `evaluate_design` | The science proper |
| 6 | Stages 8–13, reusing existing `scoring` | Mostly wiring |
| 7 | Golden + determinism tests | Lock in what you just built |

Steps 1 and 2 are pure software and can start now. **Step 3 is blocked on where trigger
sequences come from** ([step-5 §10](step-5-engine-plan.md), question 1) — the DE table has
identifiers, not sequences, and no design decision here answers that.
