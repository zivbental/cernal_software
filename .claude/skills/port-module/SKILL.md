---
name: port-module
description: Merge one team member's separately vibe-coded module into this repo — use whenever someone brings code from another repo, notebook or ZIP and wants it to land in src/engine/, or asks "where does my code go?", "how do I integrate my part?", or opens a PR that adds new files under src/engine/.
---

# Porting one member's module into CERNAL

A member's module was written to run **alone**. This repo runs seven of them **together** and
compares their numbers on one axis. Porting is therefore mostly deletion: the standalone code
carries its own copies of shared science, its own I/O and its own final score, and every copy is
a place where two members' numbers stop meaning the same thing. Work the steps in order — writing
code before the inventory is how scaffolding gets ported.

## STEP 0 — Locate the target, then read its docstring

Every port has exactly one destination that already exists. **The stub's docstring is the spec** —
it states the contract, the tools to call and the traps, in more detail than this file can.
Read it before writing a line.

| Member | Their code | Destination | The method it becomes |
|---|---|---|---|
| Shir | input QC | `src/engine/stages/quality.py` | `InputQualityCheck.check(counts, metadata) -> QcReport` |
| Shir | CSV parsing | **no home yet** | Stop. Ask the lead where the parser lives before porting. |
| Ze'ev | gene selection | `src/engine/stages/genes.py` | `GeneSelector.select(counts, dge) -> list[SelectedGene]` |
| Ze'ev | databases | **no module yet** | Stop. Ask the lead. |
| Liran | trigger scoring | `src/engine/stages/triggers.py` | `TriggerScorer.score(genes, sequences, constraints) -> Iterator[TriggerCandidate]` |
| Aviv | switch generation | `src/engine/gates/toehold.py` | `ToeholdGate.is_compatible / generate_designs / evaluate_design / emit_sequence` |
| Aviv | switch validation | `src/engine/stages/switches.py` | `SwitchValidator.validate(design) -> ValidationResult` |
| Offer | circuit design | `src/engine/stages/circuits.py` | `CircuitDesigner.design(...)`, `ConfusionEvaluator.evaluate(...)` |
| Ziv | plasmid assembly | `src/engine/stages/plasmids.py` | `PlasmidBuilder.build(circuit, outcome) -> PlasmidDesign` |
| Ziv | figures and report | `src/engine/stages/reporting.py` | `StructureRenderer.*`, `ReportBuilder.build(circuits, plasmids, output_dir)` |
| unassigned | NOT gate / CRISPR | `src/engine/gates/antisense.py`, `src/engine/gates/crispr.py` | both carry `available = False` |

One source file often splits across several destinations — Aviv's single script goes to four
(generation, validation, off-target, figures). Split it; do not pick one and dump the rest there.

## STEP 1 — Inventory, then classify into exactly four buckets

List **every** function in the incoming file with one line on what it does. Then put each in one
bucket. Report the counts; they are the port's real summary.

**(a) ALREADY EXISTS — delete it, call ours.** These are written and tested. A second copy is not
a duplicate, it is a second answer.

Safe from **any** file in the engine:

```python
# S6: to_rna, to_dna, is_valid_rna, reverse_complement, gc_content, codons, translate,
# find_augs, find_stops, longest_homopolymer, hamming, windows, CODON_TABLE
from engine import sequences as sq
from engine.domain import Constraints, GateDesign, SelectedGene, TriggerCandidate  # every record
from engine.artifacts import write_artifact  # writes the sha256 the Platform verifies
```

Legal in a **stage** (`src/engine/stages/…`) and **nowhere under `src/engine/gates/`**:

```python
from engine.stages.motifs import MotifScreener  # S7: violations(), is_compliant()
from engine.scoring.normalize import build_metrics, failed_filter, rank_candidates, weighted_score
from engine.scoring.profiles import DEFAULT_V1, get_profile  # S10
```

Those three lines inside a gate family are **test failures, not style opinions**.
`tests/engine/test_house_rules.py::test_gate_families_never_import_scoring` fails the first two —
a gate emits raw numbers and must not know how they are weighted — and
`::test_intra_engine_imports_point_downward` fails the third, because `gates/` is layer 3 and
`stages/` is layer 4, so that import points upward. This bites exactly one person: whoever ports
into `src/engine/gates/toehold.py`. A gate needs neither. Motif screening happens once, in
`SwitchValidator`; scoring happens once, in `engine.scoring`.

Also already built: `FoldEngine.mfe` (cached, dimer-aware) in `engine.gates.tools.folding`, and
`CandidateStore.mint_id` in `engine.store` — every `gene`/`trig`/`sw`/`circ`/`plasmid` id comes
from there. Do **not** write `FoldEngine(...)` or `MotifScreener(...)` inside a stage or a gate:
tools are constructed once in `pipeline.build_tools()` and arrive through `__init__`.

**(b) IS A SHARED PRIMITIVE (S1–S9) — it belongs to everyone, not to this module.** Move it to
its file, in a **separate commit and a separate PR**, merged *before* the port. Otherwise the port
review has to review two things and approves neither properly.

S1 `FoldProfiler` → `stages/folding.py` · S2 `FoldEngine` and S4 `structure_match` →
`gates/tools/folding.py` · S3 `hybridization_energy` → `gates/tools/binding.py` ·
S5 `OffTargetScanner` → `stages/off_target.py` · S6 `sequences` → `engine/sequences.py` ·
S7 `MotifScreener` → `stages/motifs.py` · S8 `CodonOptimizer` → `gates/tools/codons.py` ·
S9 `TranslationScorer` → `gates/tools/translation.py`.

**(c) THIS MEMBER'S ACTUAL SCIENCE.** The only code that lands in the stub. It is usually a small
fraction of the file, and that is the correct outcome.

**(d) SCAFFOLDING — delete it.** File reading and writing, `argparse`/CLI, `print`, matplotlib,
DataFrame plumbing, a `final_score` column, a hand-rolled results CSV, a `main()`. The pipeline,
`CandidateStore`, `ReportBuilder` and `engine.scoring` already own all of it. **Bucket (d) is
normally the largest bucket, and deleting it is the point of the exercise** — it is what made the
module runnable alone and it is exactly what makes seven modules incompatible together.

## STEP 2 — Convert to the class shape

- A procedural script becomes **one method on the class that already exists**. Do not add a class.
- Configuration becomes a constructor parameter or is read from `self.constraints`
  (`max_triggers`, `min_separation`, `max_p_adj`, `trigger_lengths`, `max_switch_length`,
  `forbidden_motifs`, `standard`). A module-level constant or a hardcoded cutoff
  (`if gc < 0.4: continue`) is a **defect**: it becomes an undeclared filter that only this
  family applies, so its survivors' scores are not comparable with a family that filters nothing.
- Anything the spec calls a generator **yields**; it does not build a list. `generate_designs`
  and `TriggerScorer.score` return `Iterator[...]` so memory stays flat.
- Return the frozen dataclass from `engine.domain` — `SelectedGene`, `TriggerCandidate`,
  `GateDesign`, `CircuitCandidate`, `PlasmidDesign`. Never a dict, never a DataFrame.
  **CSVs are exports, never the interface between stages.**
- Rejections travel: `Compatibility.no(reason)`, `ValidationResult.failed(*violations)` — and
  the validator collects *every* violation, it does not return on the first.

## STEP 3 — Reconcile the input/output mismatch

**The decision rule: if the member's function computes the same quantity as an existing shared
tool, the shared tool's computation wins and the member's version is deleted. Never forked, never
wrapped.**

A thin **adapter** is allowed only at the edge, to reshape arguments and returns — their function
took a DataFrame and returned a dict, the adapter turns rows into `SelectedGene` records and back.
**An adapter contains no arithmetic.** If it multiplies, divides, clamps, rescales or picks a
different default, it is a fork wearing a disguise; delete it and fix the caller.

Why this is worth an argument: two versions of one quantity — two mismatch conventions in an
off-target scan, two temperatures in a fold, two CAI definitions — produce numbers that
`engine.scoring` then normalises onto the *same* axis as though they were comparable. Nothing
crashes. The ranking is simply, quietly wrong, and it looks like a scientific result.

## STEP 4 — Metrics audit

Walk **every number the module returns** and check four things. Anything that fails is fixed
before the PR, not after.

1. **Name.** `evaluate_design` may return only these nine, spelled exactly:
   `state_separation`, `trigger_accessibility`, `gate_folding_energy`, `predicted_leakage`,
   `orthogonality`, `gc_content`, `dynamic_range`, `predicted_success_rate`, `circuit_complexity`.
   Anything else — `leakage`, `mfe`, `dG`, `accessibility`, `cai` — is silently discarded, the
   real metric is scored as missing (worst, at full weight), and the hard filter that should have
   rejected the candidate never fires. A metric with no `MetricSpec` cannot be emitted; adding one
   is its own PR against `engine/scoring/profiles.py`.
2. **Units.** The traps, all verified against `profiles.py`:

   | Metric | Expected | The mistake |
   |---|---|---|
   | `gc_content` | percent, 30–70 | returning a 0–1 fraction |
   | `trigger_accessibility`, `predicted_leakage`, `orthogonality`, `predicted_success_rate` | fraction, 0–1 | returning a percent — 85.0 clamps to a perfect 1.0 and stops discriminating |
   | `gate_folding_energy` | kcal/mol, −60…0 | dekacal (−1850.0 normalises to a perfect, unbeatable 1.0) |
   | `dynamic_range` | **linear** fold, 1–500 | reporting log2 or log10 — a 100× switch scores 0.002 instead of 0.198 |
   | `state_separation` | log2 fold, 0–10 | reporting a linear ratio |

3. **Failure returns `None`, never `0.0`.** `0.0` on a LOWER_BETTER metric normalises to
   *perfect* and passes the hard filter, so `try: ... except: return 0.0` and
   `raw.get("predicted_leakage", 0.0)` turn every design you could not measure into a flawless one
   that outranks the measured ones. Missing means `None`.
4. **Raw, not normalised, not weighted, not filtered.** No `_score` / `_norm` / `final_*` key, no
   division by a batch maximum. A design's numbers must be identical whether it is evaluated alone
   or inside a batch of fifty.

Also: values already measured upstream are **read, not recomputed** — `trigger_accessibility` from
the `TriggerCandidate`, `binding_site_off_target` from the validator. Recomputing gives a second
value for one name, and both get persisted.

## STEP 5 — Prove it

```
uv run pytest tests/engine -q                     # under a second — run it constantly
uv run pytest tests/engine/test_house_rules.py    # the repo's own invariants
uv run ruff check .
uv run ruff format .
```

Then write **at least one test for the ported science**, in the style of
`tests/engine/test_tools.py`: one behaviour per test, a name that is a sentence, and a docstring
saying what breaks if it regresses. A round-trip or a known-answer case beats an assertion that
the function returns a float. For anything with a sequence index, assert the round trip
(`transcript[start : start + length] == candidate.sequence`) — that is the only thing that catches
an off-by-one, because an off-by-one still folds and still scores.

## STEP 6 — Report

Six lines in the PR description:

- **Reused** — which shared functions replaced their code (this is the headline).
- **Deleted** — scaffolding removed, with the line count.
- **Promoted** — anything moved to S1–S9, and the PR number it went in.
- **Landed** — the science that is now in the stub.
- **Metrics** — the names emitted, their units, and what each returns on failure.
- **Open questions** — every ambiguity the port surfaced. Do not resolve a scientific question by
  picking a value silently; a hardcoded guess is invisible, a question in the PR is not.

## WHAT NOT TO DO

Each of these is a real hazard found in this repo, and each fails **silently**.

- **`import RNA` anywhere but `gates/tools/folding.py` and `stages/folding.py`.** A private
  ViennaRNA call bypasses the shared cache and the recorded temperature model, and `RNA.fold`
  reads a process-global temperature — so its energies come from a different physical model than
  the rest of the run.
- **`self.folder = FoldEngine()` inside a family or stage.** Tools are injected. Constructing one
  gives you a cold cache and a second temperature.
- **`folder.mfe(switch + trigger)`.** Concatenation covalently joins two molecules that are not
  joined and returns a plausible, too-negative number. Duplexes need ViennaRNA's `&` dimer form.
- **Mixing estimators.** `mfe()`, `partition()` and `ensemble_defect()` have the same units and
  the same sign. Report `gate_folding_energy` from `mfe()` unless the lead says otherwise.
- **`except Exception: return 0.0`, or `.get(name, 0.0)` for a metric.** See Step 4.3.
- **Your own final score, or normalising against the batch.** `engine.scoring` owns that.
- **Hardcoded thresholds and module constants.** Read `self.constraints`.
- **Module-level `random.` / `np.random.`.** The run promises that the same seed reproduces the
  same candidates and byte-identical artifacts.
- **`reverse_complement` on the wrong alphabet.** `reverse_complement("ATGC")` returns `"GCAU"`
  and `reverse_complement("AUGC", dna=True)` returns `"GCUT"` — normalise with `to_rna`/`to_dna`
  first, then assert `is_valid_rna`.
- **1-based indices.** The engine is 0-indexed, inclusive start, exclusive end. BLAST, GenBank and
  ViennaRNA's pair matrix are not; convert at the wrapper.
- **Subclassing a gate family without re-declaring `available` and `version` in the subclass.**
  `ToeholdAndGate` inherits `available = True` over stub bodies today — the submission validates,
  then crashes ten minutes into the run.
- **Importing Django, or passing a DataFrame between stages.** `tests/test_boundary.py` fails the
  first; nothing yet fails the second, which is why it is on this list.
