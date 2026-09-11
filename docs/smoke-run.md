# The first real run — what actually blocks it

**Status:** Assessment. Nothing here is built yet.
**Question it answers:** *"What stops me doing one basic run end to end, on real science
instead of `MockEngine`?"*
**Companion documents:** [`ROADMAP.md`](ROADMAP.md) §5 is the full Phase E plan this is a
subset of; [`modalities.md`](modalities.md) §1 defines the two input paths;
[`engine.md`](engine.md) is the architecture.

> **This is a design document, not a planning file.** [ROADMAP.md](ROADMAP.md) is the
> single place work is recorded. §9 below gives the rows to paste into it. This file holds
> the *evidence and the reasoning*; the ROADMAP holds the *work*. Same split
> [`public-api.md`](public-api.md) uses.

---

## 1. The verdict

**Closer than the stub count suggests. There is one wall, and the science behind it
already works.**

`docs/api-surface.md` reports 36 stubs, which reads like the engine is months away. It
isn't, for one specific run shape. Most of those stubs are on the `de` (differential
expression) path or in stages 4–6; a **`direct`-mode** run — the researcher pastes a
trigger sequence — skips stages 1–2 *by design* and needs a much smaller set.

Two measurements, both run against this commit:

**(a) `LocalEngine` dies immediately, before reaching any science.**

```
FIRST BLOCKER: NotImplementedError:
  The real pipeline lands in Step 5. Set CERNAL_ENGINE=engine.client.MockEngine.
```

Nothing downstream of `engine/pipeline.py::run_pipeline` is even attempted. The stub
count is misleading because the *orchestrator* is missing, so no stage gets a chance to
fail.

**(b) With the orchestration done by hand, the scientific core runs today.**

Synthesising one `TriggerCandidate` from a pasted sequence and driving the gate directly:

```
is_compatible: True
designs generated: 3
  toehold-trig-000001-12    score=0.19326233552511776   rejected=None
  toehold-trig-000001-15    score=0.20268245354294206   rejected=None
emit_sequence length: 83
```

Those are **real ViennaRNA numbers** through the **real scoring layer** — `FoldEngine.mfe`,
`base_pair_probabilities`, `build_metrics`, `failed_filter`, `weighted_score`. Designs are
generated, evaluated, filtered and ranked. A synthesis-ready 83 nt sequence comes out.

**So the gap is wiring, not science.** What is missing is the code that assembles the run:
turn the request into a trigger, loop trigger sets across families, validate, convert
designs into `CandidateResult`s, write artifacts, return a `JobResult`.

---

## 2. Choose the run shape first — it changes everything

| | `de` — upload a DE table | `direct` — paste a sequence |
|---|---|---|
| Stages needed | 1 → 6 | **3 → 6** (1–2 skipped by design) |
| Blocked on **Q1** (where trigger sequences come from) | **Yes — hard** | **No.** The user supplies the sequence |
| Needs the CSV → `CountMatrix`/`DgeTable` parser | Yes — **and it has no home in `src/engine/` today** | No |
| Needs `GeneSelector` (stage 1) | Yes | No |
| Needs `TriggerScorer` (stage 2) | Yes — and although it is *built*, two of its four tools are stubs | No |
| Needs `OffTargetScanner` + a transcriptome | Yes | No |

[`modalities.md`](modalities.md) §A2 is explicit: on a `direct` run *"the pipeline picks up
at `SwitchDesigner`."* Its own status table already lists this branch as
*"Stubbed — the branch that skips stages 1–2 is not written."*

> **Recommendation: smoke-test `direct` first.** It sidesteps **Q1**, the one blocker the
> software side cannot resolve alone — a reference transcriptome per organism is a data,
> storage and licensing decision, not a coding task. `de` is the real product, but it
> cannot be the *first* run.

### Why `de` is not a smoke run

Stage 2 (`TriggerScorer.score`) is **built** — but it calls two stubs and would die on the
first transcript:

```python
profile = self.profiler.profile(transcript)  # FoldProfiler — STUB
off_target_report = self.off_target.scan_trigger(window)  # OffTargetScanner — STUB
```

On top of that: `GeneSelector.select` is a stub, nothing in `src/engine/` parses
`JobRequest.input_path`, and nothing constructs a `CountMatrix` or `DgeTable` anywhere in
the engine (verified by grep — zero occurrences). That is **E2 in full**, not a smoke run.

---

## 3. The minimal build list for a `direct` smoke run

Five items. Sizes use the ROADMAP's scale (S ≈ half a day, M ≈ 1–2 days).

| # | What | Where | Size |
|---|---|---|---|
| **S1** | `build_tools` + `run_pipeline` — the orchestrator | `engine/pipeline.py` | **M** |
| **S2** | Direct-mode trigger synthesis: one pasted sequence → one `TriggerCandidate` | `engine/pipeline.py` (+ `stages/folding.py`, see below) | **S** |
| **S3** | `SwitchDesigner.design` + `build_trigger_sets` | `engine/stages/switches.py` | **S** |
| **S4** | `SwitchValidator.validate` — cheap sequence rules only | `engine/stages/switches.py` | **S** |
| **S5** | `GateDesign` → `CandidateResult`, plus artifact writing | `engine/pipeline.py` | **S** |

### S1 · The orchestrator

`run_pipeline`'s own docstring already contains the shape to fill in, and `build_tools`
constructs everything once (`FoldEngine`'s cache is per-instance — two instances means two
cold caches and two chances to fold at different temperatures). Every constructor involved
is already implemented; only the *methods* are stubs, so `build_tools` can build the full
set today and simply not call the ones that aren't needed.

Composition only. The module docstring says: *"if it grows past ~150 lines, logic has
leaked into it from a stage."*

### S2 · Turning a pasted sequence into a trigger

The built gates read exactly four fields off a `TriggerCandidate` (verified):
`sequence`, `trigger_id`, `length`, and **`accessibility`**.

`accessibility` normally comes from stage 2 via `FoldProfiler.openness` — a stub. Two ways
to supply it:

- **(a) Implement `FoldProfiler.profile` + `openness`** — the windowed `RNAplfold` wrapper.
  Two methods, and it is **E1 rung 4**, already on the critical path for `de` later. It
  also deletes the standing `xfail` in `test_house_rules.py`
  (`test_both_folding_adapters_actually_fold`). **Recommended.**
- **(b) Derive it from `FoldEngine.base_pair_probabilities`**, which is already built — mean
  unpaired probability over the window is precisely what `openness` means. Cheaper, but it
  leaves `stages/folding.py` stubbed and the xfail standing.

Either way, compute it **once**, here. CLAUDE.md §5 is explicit that
`TriggerCandidate.accessibility` is read downstream, never recomputed.

### S3 · Switch design

`SwitchDesigner.design`'s docstring specifies the loop precisely (trigger sets → families
supporting the host → `is_compatible` → `generate_designs` → `validate` →
`evaluate_design`). For a `direct` run, `build_trigger_sets` yields exactly **one**
singleton set, so the combinatorial half of that method is not exercised at all.
`ToeholdAndGate` has nothing to pair and stays out of scope — [`modalities.md`](modalities.md)
says so directly: *"A `direct` run supplies exactly one trigger sequence, so `toehold_and`
has nothing to"* combine.

### S4 · Validation, minus the structural rule

`SwitchValidator.__init__` takes four tools; two are fully stubbed (`OffTargetScanner`,
`TranslationScorer`). They can be *constructed* and simply not called.

Of the six documented rules, four are runnable today on built helpers — exactly one AUG
(`sequences.find_augs`), no in-frame stops (`find_stops`), no prohibited motifs
(`MotifScreener.violations`), and length. The fifth, *"structure matches intent"*, needs
`FoldEngine.ensemble_defect` — a stub. Either implement it (small, and it is the honest
check) or **defer that one rule with a comment naming it**, so nobody later mistakes the
validator for complete.

Keep the documented order — cheapest first, so a design failing on a stop codon is never
folded — and collect *every* violation rather than returning on the first.

### S5 · Results out

Nothing in the engine converts a `GateDesign` into a `CandidateResult` today; the only
construction site is inside `MockEngine` (`client.py:419`), which is a usable template.
`engine.artifacts.write_artifact` is built, and `MockEngine._write_artifacts` shows the
pattern — a design table plus a FASTA per accepted candidate is enough to prove artifacts
flow through to the UI's download button.

---

## 4. What we deliberately skip — and what it costs

| Skipped | Why it is safe for a smoke run | What you lose |
|---|---|---|
| Stage 4 — `CircuitDesigner`, `ConfusionEvaluator` | A `direct` run has one trigger; there is no Boolean circuit to design | No `logic_graph` in `design`, so the results page's circuit diagram renders empty |
| Stage 5 — `PlasmidBuilder` | Blocked on **Q11** — there is no sequence library for GFP, mCherry, AmpR | No `plasmid_segments`, so the plasmid ring renders empty |
| Stage 6 — `ReportBuilder`, `StructureRenderer` | A FASTA proves the artifact path works | No SVG structure/circuit renders, no report |
| `OffTargetScanner` (4 stubs) | No transcriptome in `direct` mode — construct with `{}` and never call it | No off-target penalty; `off_target_penalty` stays 0.0 |
| `TranslationScorer`, `CodonOptimizer` (6 stubs) | **Verified: the built gates never call them.** Only `folder.mfe` and `folder.base_pair_probabilities` are called | Nothing, for this run |
| `GeneSelector`, `InputQualityCheck`, the CSV parser | `de`-path only | Cannot run `de` mode — expected |
| `CandidateStore.snapshot` / `load_snapshot` | Provenance CSVs, not needed to execute | No per-stage snapshots to inspect |
| `ToeholdAndGate.generate_designs` | One trigger, so AND has nothing to pair | No two-input designs |

**The UI consequence is worth stating plainly:** a first `direct` smoke run will produce
real ranked candidates with real sequences and real folding numbers, and the results page
will show them — but the circuit diagram and plasmid map will be blank, because stages 4
and 5 are what populate those. That is a *presentation* gap, not a failed run. Decide
before demoing whether that matters.

---

## 5. Gotchas that will otherwise cost an afternoon

- **Scores will look low — around 0.20 — and that is correct.**
  `ToeholdGate.evaluate_design` emits **5 of the 9** metrics (`gate_folding_energy`,
  `predicted_leakage`, `dynamic_range`, `trigger_accessibility`, `gc_content`). The other
  four are absent, and absent means `TREAT_AS_WORST` — 0.0 at full weight. Measured above:
  0.193 and 0.203. Do not "fix" this by inventing values; CLAUDE.md §3 is explicit that an
  unmeasured metric is `None`, never a number.

- **A missing metric does *not* trip its hard filter.** `failed_filter` skips `None`
  (`normalize.py:88`), so the `state_separation >= 0.5` filter does not silently reject
  every candidate. Verified — this was the most plausible way for a smoke run to produce
  zero output.

- **`predicted_leakage` *is* emitted and *is* filtered at 0.85.** Some candidates will be
  legitimately rejected. That is the filter working, not a bug.

- **The design count is tiny.** Three designs from one trigger at default constraints —
  which is exactly what a smoke run wants. Do not widen `trigger_lengths` to "get more
  results" on the first run.

- **Platform ingestion is already clean for `direct`.** `_verify_manifest` short-circuits
  when `run.dataset is None`, so there is no checksum to satisfy, and `import_job_result`
  maps `CandidateResult` fields straight through — `design` and `triggers` are free-form
  JSON.

- **`on_progress` is both the progress bar and the cancellation check.** Call it between
  stages *and* between batches; a `False` return must raise `JobCancelled`, or a cancelled
  run keeps computing.

- **Do not flip `CERNAL_ENGINE` globally until it works.** It is an environment variable
  (`CERNAL_ENGINE=engine.client.LocalEngine`), so the smoke run can be a one-off while
  `MockEngine` stays the default for CI and the demo.

---

## 6. How we will know it worked

1. `CERNAL_ENGINE=engine.client.LocalEngine`, submit a `direct` run through
   `POST /api/design` with a pasted sequence.
2. The run reaches `COMPLETED` — not `FAILED`, and not stuck in `RUNNING`.
3. `GET /api/design/{id}/results` returns ≥ 1 ranked candidate with a real
   `gate_folding_energy` in kcal/mol and a real switch sequence.
4. At least one artifact downloads.
5. The same submission twice with the same `seed` produces identical candidates —
   determinism is the property most likely to break first, and the cheapest to check.
6. `uv run pytest -q` still green, and `MockEngine` still the default.

---

## 7. What this does **not** get us

Worth saying so nobody reads a green smoke run as more than it is:

- **No `de` path.** The product's actual workflow — upload a DE table, discover triggers —
  remains blocked on **Q1**.
- **No circuits.** One trigger is not a Boolean circuit. `A AND NOT B` is untested.
- **No plasmid.** Nothing orderable comes out until **Q11** gives us payload sequences.
- **No off-target validation.** Every candidate's `off_target_penalty` is 0.0 because
  nothing scanned anything.
- **The numbers are not yet calibrated.** **Q5** (how leakage and dynamic range are derived
  from folding energies) and **Q6** (the real metric set and weights) are still open. The
  run proves the *machinery*, not the *biology*.

---

## 8. Sequencing

```
S1 (orchestrator) ──┬─► S3 (switch design) ─► S4 (validation) ─► S5 (results out)
                    │
S2 (direct trigger) ┘        FoldProfiler (option a) feeds S2, and unblocks de later
```

S1 and S2 are the only ones that must come first. S3–S5 are each half a day and
independently testable against a hand-made trigger — the same way §1(b) above was measured,
which means each can be verified before the orchestrator is finished.

---

## 9. Rows for ROADMAP.md

Paste into [ROADMAP.md](ROADMAP.md) §5 as **"E2a — the `direct` smoke path"**, sitting
before E2 (which stays blocked on Q1).

| # | Task | Where | Size | Blocked on |
|---|---|---|---|---|
| **E2a-1** | `build_tools` + `run_pipeline` — composition only, no science | `engine/pipeline.py` | M | — |
| **E2a-2** | Direct-mode trigger synthesis: pasted sequence → one `TriggerCandidate`, accessibility computed once | `engine/pipeline.py` | S | E2a-4, or `FoldEngine.base_pair_probabilities` |
| **E2a-3** | `SwitchDesigner.design` + `build_trigger_sets`; `SwitchValidator.validate` (sequence rules; structural rule deferred or `ensemble_defect` implemented) | `engine/stages/switches.py` | S | — |
| **E2a-4** | `FoldProfiler.profile` + `openness` — the windowed RNAplfold wrapper. Deletes the `test_both_folding_adapters_actually_fold` xfail, and is **E1 rung 4**, needed for `de` regardless | `engine/stages/folding.py` | S | — |
| **E2a-5** | `GateDesign` → `CandidateResult` + artifact writing (design table, FASTA per candidate) | `engine/pipeline.py` | S | E2a-1 |
| **E2a-6** | Prove it: a `direct` run to `COMPLETED` under `LocalEngine`, twice with one seed, byte-identical | `tests/`, manual | S | E2a-1…5 |

**Not in this phase, deliberately:** stages 4–6, `OffTargetScanner`, `TranslationScorer`,
`CodonOptimizer`, `GeneSelector`, `InputQualityCheck`, the CSV parser,
`CandidateStore.snapshot`. Each is listed in §4 with what skipping it costs.
