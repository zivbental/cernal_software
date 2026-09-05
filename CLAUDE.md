# CLAUDE.md — rules for AI code writers in this repo

CERNAL compiles a transcriptomic signature into an RNA logic circuit on a plasmid. The
Python engine lives under `src/engine/`; a Django platform wraps it and never touches its
internals. The engine is **stub-first**: every class, method and docstring already exists,
and 48 public callables still `raise NotImplementedError("Step 5 — …")`.

> **The one-line rule: your job is almost always to FILL A STUB, not to create a file.**
> If you are about to write `class X:` or create a new module, stop and find the stub that
> already has X's name and signature. Adding a parallel implementation is how this project
> fails, because two implementations of one measurement produce two numbers and only one
> reaches the report.

Background: [`docs/engine.md`](docs/engine.md) (architecture, tool map),
[`docs/architecture.md`](docs/architecture.md) (the Platform⇄Engine boundary),
[`docs/ROADMAP.md`](docs/ROADMAP.md) (open decisions). This file is the operative subset,
not a second copy — when they disagree, the source code wins and you should say so.

---

## 1. Before you write a function, check whether it exists

These are **built and tested**. Writing your own is the single most common merge defect.

| You need | Call this | Import |
|---|---|---|
| reverse complement, GC%, AUG/STOP finding, translate, hamming, sliding windows | `reverse_complement`, `gc_content`, `find_augs`, `find_stops`, `translate`, `codons`, `longest_homopolymer`, `hamming`, `windows`, `to_rna`, `to_dna`, `is_valid_rna` | `from engine import sequences` |
| forbidden motifs, restriction sites, homopolymer runs | `MotifScreener.violations(seq)`, `.is_compliant(seq)` | `from engine.stages.motifs import MotifScreener` |
| normalising, weighting, filtering, ranking | `normalize_value`, `build_metrics`, `weighted_score`, `failed_filter`, `rank_candidates` | `from engine.scoring.normalize import …` |
| the metric vocabulary | `DEFAULT_V1`, `MetricSpec`, `HardFilter` | `from engine.scoring.profiles import DEFAULT_V1` |
| any record or enum (`TriggerCandidate`, `GateDesign`, `Constraints`, `Host`, `BooleanExpression`, `ConfusionMatrix`, …) | all of `domain.py` | `from engine.domain import …` |
| writing any output file, with its SHA-256 | `write_artifact(output_dir, name, content, *, kind, media_type, candidate_ref=None)` | `from engine.artifacts import write_artifact` |
| a candidate ID (`trig-000001`) | `CandidateStore.mint_id(kind)` | `from engine.store import CandidateStore` |
| folding one sequence or a dimer | `FoldEngine.mfe(strands)` — **already implemented and cached** | injected, see §5 |
| boolean logic, confusion matrices, Youden's J | `BooleanExpression.evaluate/gene_ids/complexity/render`, `ConfusionMatrix.sensitivity/specificity/separation_margin` | `from engine.domain import …` |

A private `reverse_complement`, a private GC calculator, a private `import RNA` or a
private confusion matrix in your module is a merge defect even when the code is correct.
Delete it and call the shared one. The tool import root is `engine.gates.tools` (plus
`engine.sequences` at the root); `engine.tools` is a stale leftover that fails confusingly.

---

## 2. The nine metric names

Copied verbatim from [`src/engine/scoring/profiles.py`](src/engine/scoring/profiles.py)
`DEFAULT_V1`. `evaluate_design` may return **only** these keys.

| Metric | Direction | Weight | valid_range | Unit / meaning |
|---|---|---|---|---|
| `state_separation` | higher better | 3.0 | 0.0 – 10.0 | log2 fold between base and target state |
| `trigger_accessibility` | higher better | 2.0 | 0.0 – 1.0 | fraction free of self-structure |
| `gate_folding_energy` | **lower** better | 2.0 | −60.0 – 0.0 | kcal/mol MFE |
| `predicted_leakage` | **lower** better | 2.5 | 0.0 – 1.0 | proxy for OFF-state activation |
| `orthogonality` | higher better | 1.5 | 0.0 – 1.0 | independence from other gates |
| `gc_content` | higher better | 0.5 | 30.0 – 70.0 | **percent, 0–100** |
| `dynamic_range` | higher better | 2.0 | 1.0 – 500.0 | **linear ON/OFF fold change** |
| `predicted_success_rate` | higher better | 1.0 | 0.0 – 1.0 | model confidence |
| `circuit_complexity` | **lower** better | 1.0 | 1.0 – 10.0 | component count penalty |

Hard filters: `predicted_leakage` max 0.85; `state_separation` min 0.5. Tie-breakers, in
order: `state_separation`, `predicted_leakage`.

**The failure this prevents.** `ScoringProfile.spec()` returns `None` for a name it does
not know, and `build_metrics`/`weighted_score`/`failed_filter` all skip unknown names —
deliberately, with a test asserting it. So emitting `leakage` instead of
`predicted_leakage` is a *triple* silent failure: your number is discarded, the profile
scores the metric as missing (0.0 at full weight under `TREAT_AS_WORST`), and the hard
filter that should have rejected the design never fires. Verified:
`failed_filter({"leakage": 0.9}, DEFAULT_V1)` → `None`, while
`failed_filter({"predicted_leakage": 0.9}, DEFAULT_V1)` → the `HardFilter`. Nothing logs,
nothing raises; the candidate ranks on the metrics it spelled correctly.

**Adding a metric is an edit to `profiles.py` in the same PR** — a new `MetricSpec` with
its name, direction, weight and `valid_range`, plus a version bump on `DEFAULT_V1`, since
the profile label is recorded on every run. `structure_deviation`, `translation_score`,
`off_target_penalty`, `binding_site_accessibility` and `condition_specificity` are real
fields on the records with **no spec** — they are stored, not scored.

---

## 3. Raw values only

`GateFamily.evaluate_design` returns `dict[str, float | None]` of **raw measurements**.
Never normalised, never weighted, never a `final_score`, never batch-relative
(`leak / max_leak_in_batch` makes a design's score depend on which designs happened to be
in its batch). Normalisation, weighting, hard filters and ranking are `engine.scoring`'s
exclusive job — that is what makes a toehold comparable with a CRISPR gate.
See [`src/engine/gates/base.py:79-85`](src/engine/gates/base.py).

**A metric you could not compute is `None`. Never `0.0`, `-1`, `999` or `nan`.**

Verified with the real code: `normalize_value(0.0, predicted_leakage_spec)` → **1.0**, a
perfect score, and `failed_filter({"predicted_leakage": 0.0}, DEFAULT_V1)` → `None`, so it
passes the 0.85 gate. Meanwhile `normalize_value(None, spec)` → `None`, which the scoring
layer handles explicitly. A `try: … except: return 0.0` around a folding call therefore
converts every design you *failed* to measure into a flawless one that outranks every
correctly-measured design and cannot be filtered out. So:

- no `except …: return 0.0`
- no `raw.get("leak", 0.0)`
- no `float(row["mfe"] or 0)` when reading a CSV cell back
- `None` for a failed measurement, every time

Silent drops are also banned. A family rejects a trigger set with
`Compatibility.no(reason)`, the validator collects **every** violation with
`ValidationResult.failed(*violations)`, and a rejected circuit is yielded with its reason
and no rank. Thresholds come from `self.constraints`, never a module-level literal — an
undeclared numeric cutoff inside `generate_designs` is an invisible per-family filter that
makes your candidate pool incomparable with everyone else's.

---

## 4. Layering: imports point downward only

```
pipeline  →  stages  →  gates  →  gates/tools  →  sequences  →  domain
                  ↘         scoring          ↗
```

`domain` imports nothing. A tool imports only `domain`, `sequences` and its scientific
library. **Nothing imports upward** — a tool that needs to know which stage called it is
the signal something is in the wrong place.

The one sideways exception: the stage-level tools S1 `stages/folding.py`, S5
`stages/off_target.py` and S7 `stages/motifs.py` may be imported by sibling stages. One
screener, three callers. A stage importing another *stage* is not allowed.

`src/engine/` must never import `django`, `apps`, `api` or `config`; platform code imports
only `engine.contract` and `engine.client`. This half is machine-checked by
[`tests/test_boundary.py`](tests/test_boundary.py), an AST scan that catches
function-local and `TYPE_CHECKING` imports too. **Never add an exception to
`FORBIDDEN_IN_ENGINE`.**

Every other rule in this file — the metric vocabulary, raw-values-only, one folding
adapter, tools built once, downward imports — is enforced the same way, by
[`tests/engine/test_house_rules.py`](tests/engine/test_house_rules.py). `uv run pytest`
runs it automatically. If your PR fails it, the assertion message names the file and line;
fix the code, do not edit the test.

---

## 5. Tools are injected, never constructed

Every tool is built **once** in `pipeline.build_tools()` and passed down. Your class
receives them in `__init__` and stores them. Do not write `FoldEngine()`,
`OffTargetScanner()`, `MotifScreener()`, `CodonOptimizer()`, `TranslationScorer()` or
`FoldProfiler()` anywhere outside `pipeline.py` — not in a stage, not in a gate family,
not in a helper, not in a loop.

`FoldEngine`'s cache lives on the instance, so a second instance means a cold cache and,
worse, a second chance to fold at a different temperature — two designs folded at
different temperatures get normalised onto the same `gate_folding_energy` axis as if
comparable, and nothing detects it. Same for the index: one `OffTargetScanner`, on the
same transcriptome build the trigger sequences came from.

**Only two modules may `import RNA`:** `src/engine/gates/tools/folding.py` (design-side
MFE and ensemble, cached) and `src/engine/stages/folding.py` (windowed RNAplfold). Today
only the first actually does. Never call `RNA.fold`/`RNA.cofold` directly from anywhere
else, never add a second folding library, and never mutate `RNA.cvar.temperature` — it is
process-global and unsafe; model parameters travel on an explicit `RNA.md()`.

Values already computed upstream are **read, not recomputed**:
`TriggerCandidate.accessibility`, `openness`, `off_target_penalty`,
`GateDesign.binding_site_off_target`. Recomputing with a slightly different window or
mismatch model produces two numbers for one quantity, and both get persisted.

---

## 6. Units and conventions

| Quantity | The convention | The trap |
|---|---|---|
| Free energy | **kcal/mol** floats | ViennaRNA's `subopt` takes an integer **dekacal/mol** window. Reporting −1850 instead of −18.5 clamps to a perfect 1.0 score — verified |
| Two molecules | one string with an **`&`** separator through `FoldEngine.mfe` | `folder.mfe(switch + trigger)` type-checks, runs, caches and returns a plausible number that means nothing — it covalently joins molecules that are not joined |
| Alphabet | **RNA, ACGU, uppercase** | `reverse_complement("ATGC")` → `"GCAU"`; `reverse_complement("AUGC", dna=True)` → `"GCUT"` (a U left in a "DNA" string). Normalise with `to_rna`/`to_dna` first |
| Coordinates | **0-indexed, inclusive start, exclusive end** | GenBank, BLAST/bowtie and ViennaRNA's bppm are all 1-based. Every external-tool wrapper is an off-by-one; assert `transcript[start:start+length] == candidate.sequence` |
| `gc_content` | **percent, 0–100** (`sequences.gc_content` returns `100.0 * …`) | `openness`, `accessibility`, `leakage`, `orthogonality` are **probabilities, 0–1**. `normalize_value(85.0, accessibility_spec)` → 1.0, same as 40.0 and 100.0: the metric silently stops discriminating |
| `dynamic_range` | **linear fold change** (1.0–500.0) | `state_separation` directly above it *is* log2. Reporting log10(ON/OFF)=2.0 for a 100× switch scores 0.002 instead of 0.198 — a hundredfold penalty applied only to your designs, which reads as "your chemistry is worse" |
| `structure_deviation` | **normalised by length** | Raw ensemble defect is a length bias; a value above 1.0 means someone stored the raw defect |
| `predicted_leakage` | same name, opposite biological event per chemistry | OFF-state translation for a toehold; residual expression **with** the trigger for an antisense NOT. State which one your family means |
| CSVs | **exports, never the inter-stage interface** | Stages pass frozen dataclasses. `load_snapshot` returns dicts of strings — that is where `float(x or 0)` gets written |
| Randomness | seed from `JobRequest.seed`, threaded in | No module-level `random.`/`np.random.`, no `uuid4`, no wall clock, no `set` iteration order in anything that reaches output |

Records in `domain.py` and `contract.py` are `@dataclass(frozen=True, slots=True)`. Never
mutate one, never add a mutable field, never introduce a `Job`-style god object or a
mutable `RunContext` that accumulates stage state.

---

## 7. Where your code goes

Four destinations for what was one script is normal here — a switch chemistry's
generator+validation code splits four ways. Generation → `gates/toehold.py`; validation
→ `stages/switches.py`; off-target → `stages/off_target.py`; visualisation →
`stages/reporting.py`. (docs/engine.md §5: no possessive or personal names in this
repo's naming — a pipeline step, not the person who ports it, identifies the row below.)

| Pipeline area | File | Class | Signature to implement |
|---|---|---|---|
| Input QC (S15) | `src/engine/stages/quality.py` | `InputQualityCheck` | `check(self, counts: CountMatrix, metadata: SampleMetadata) -> QcReport` |
| Gene Selection (stage 1) | `src/engine/stages/genes.py` | `GeneSelector` | `select(self, counts: CountMatrix, dge: DgeTable) -> list[SelectedGene]` |
| Trigger Scoring (stage 2) | `src/engine/stages/triggers.py` | `TriggerScorer` | `score(self, genes, sequences: dict[str, str], constraints) -> Iterator[TriggerCandidate]` |
| Switch generation (stage 3a) | `src/engine/gates/toehold.py` | `ToeholdGate`, `ToeholdAndGate` | `is_compatible`, `generate_designs`, `evaluate_design`, `emit_sequence`, `required_tools` |
| Switch validation (stage 3b) | `src/engine/stages/switches.py` | `SwitchValidator`, `SwitchDesigner` | `validate(design) -> ValidationResult`; `design(triggers, constraints) -> Iterator[GateDesign]`; `build_trigger_sets(triggers, constraints) -> Iterator[TriggerSet]` |
| Circuit Design (stage 4) | `src/engine/stages/circuits.py` | `CircuitDesigner`, `ConfusionEvaluator` | `design(genes, designs, counts) -> Iterator[CircuitCandidate]`; `enumerate_expressions(genes)`; `evaluate(expression, counts, threshold) -> ConfusionMatrix`; `cross_talk_penalty(designs) -> float` |
| Plasmid Construction (stage 5) | `src/engine/stages/plasmids.py` | `PlasmidBuilder` | `build(circuit, outcome) -> PlasmidDesign`; `payload_segment(outcome) -> Segment` |
| Compiler's Output (stage 6, S14) | `src/engine/stages/reporting.py` | `StructureRenderer`, `ReportBuilder` | `render_structure(design, output_dir)`; `render_circuit(circuit, output_dir)`; `build(circuits, plasmids, output_dir) -> list[ArtifactRef]` |
| Antisense / CRISPR gates (unassigned) | `src/engine/gates/antisense.py`, `crispr.py` | `AntisenseNotGate`, `CrisprGate` | both `available = False` today; flipping it is a deliberate declaration |
| Folding tool (S2, S4 — shared) | `src/engine/gates/tools/folding.py` | `FoldEngine` | `partition`, `ensemble_defect`, `base_pair_probabilities`, `suboptimal`, `versions`; `structure_match()`. **Highest fan-in in the repo — build first** |

Two things have **no home yet** and need a decision before code lands: the CSV →
`CountMatrix`/`DgeTable` parser (nothing in `src/engine/` parses `JobRequest.input_path`),
and the supporting-database module (codon tables, transcript sequences, cell atlas,
backbone). Ask rather than inventing a path — and never let pandas DataFrames travel
between stages; convert at the edge.

Every method annotated `-> Iterator[...]` must actually `yield`; `return list(...)` is the
violation. Expensive stages call `on_progress(pct, stage)` between batches, not only
between stages, and raise `JobCancelled` when it returns `False`.

---

## 8. How to run things

`uv` is mandatory — the repo pins Python 3.13 and plain `pip` on 3.14 fails outright.
Install once: `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`.

| Task | Command |
|---|---|
| Install / sync | `uv sync --extra dev` |
| **Engine tests — the fast loop** | `uv run pytest tests/engine -q` |
| Full suite | `uv run pytest -q` |
| Lint | `uv run ruff check .` and `uv run ruff format --check .` |
| Django sanity check | `uv run python manage.py check` |

`tests/engine` is 119 tests in **under half a second** and needs no Django settings — run
it after every edit; there is no excuse not to. The full suite is ~90 s. Ruff config:
line-length 100, target py313, rules `E,F,I,UP,B,C4,DJ,RUF`.

`./do` is a bash wrapper over exactly these commands. It needs Git Bash **and** `uv` on
PATH, so on Windows prefer `uv run …` directly. **Never keep a git clone inside OneDrive,
Dropbox or Google Drive** — the sync client holds handles on `.git` mid-write and corrupts
rebases and merges; clone to `C:\dev\cernal_software`. ViennaRNA ships a prebuilt cp313
Windows wheel, so no compiler and no WSL are needed.

---

## 9. Workflow

Only Offer and Ziv merge to `main`. Everyone else: **never push to `main`.**

1. `git switch -c <your-name>/<what-you-are-doing>` from an up-to-date `main`.
2. Fill the stub. Run `uv run pytest tests/engine -q` and `uv run ruff check .`.
3. Commit small and often, in English, describing *why*.
4. Push the branch and open a Pull Request. In the description answer one question:
   **which shared function did you call instead of writing your own?**
5. A reviewer merges it. Do not merge your own.

Hebrew step-by-step for git, branches and pull requests:
[`docs/onboarding.he.md`](docs/onboarding.he.md).

Any change that legitimately moves the numbers updates the golden fixture in the same
commit and bumps the gate family's `version` (and `ENGINE_VERSION` where relevant). A
refactor that silently changes a score with no version bump makes every stored result
uninterpretable.
