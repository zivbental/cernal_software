# Build `and_eu_report.ipynb` — eukaryotic toehold switch ON/OFF report

> **What this file is:** a ready-to-paste prompt for building this notebook. It is written
> for a session with no memory of the conversation that produced it, which is why the
> rationale is inline — without the "why", the Traps section at the bottom gets
> "simplified" straight back into the bugs it describes.

## Context to read first

- `CLAUDE.md` §1 (don't rewrite existing functions), §3 (raw values, `None` never
  defaulted), §5 (tools injected, `FoldEngine` is the only folding adapter), §6
  (units/conventions).
- Existing notebook: `toehold_and_eu_test.ipynb` — the predecessor, in this same folder.
  Read its cells before writing anything; ~80% of what is needed already exists there and
  is debugged.
- Existing module: `_joint_state_parallel.py` — parallel workers, fake-trigger selection,
  state sampling.

## Hard rules

1. **Fold only through `FoldEngine`.** One instance, built once via
   `fx.fold_engine(real=True, temperature=TEMPERATURE_C)`, published to the worker module
   with `use_fold_engine(folder)`. No `import RNA` anywhere —
   `tests/engine/test_house_rules.py` enforces this for module code.
2. **Reuse, don't rewrite.** Before writing any function, search for it. Already built and
   tested: `fuse()`, `measure()`, `motif_self_bind_score()`, `load_ranked_designs()`,
   `FakeSweepJob`/`run_parallel_fake_sweep`, `SingleStateJob`/`run_parallel_single`,
   `ConstrainedBindJob`/`run_parallel_constrained_bind`, `pick_fake_design`,
   `pick_optimized_spacer`, `generate_spacer_candidates`, `_frac_paired_to_external`,
   `_partner_table`, `render_layout_bar_png`, `render_register_png`,
   `render_trigger_position_png`, `_structure_png`, `_bpp_heatmap_png`,
   `FoldEngine.sample_structures`, and from `engine.sequences`:
   `longest_homopolymer`, `reverse_complement`, `windows`, `hamming`, `gc_content`.
3. **Parallelise with one pool call per batch**, never one pool spin-up per job (measured
   5.8x overhead for the anti-pattern).
4. **Raw values only.** A metric that could not be computed is `None` and renders `--`.
   Never `0.0`, `-1`, or `nan` as a stand-in.
5. **No randomness without a literal seed.** Only the spacer candidate pool needs one.
6. **Everything runs through notebook cells** — including your own verification. No
   standalone scripts; a script copy of notebook code already produced a silent indexing
   bug on this project. Verification cells go at the bottom under a marked heading and
   stay in the file.
7. **Don't edit test files.**

## Step 0 — migration (do this first)

Create `_switch_construct.py` in this folder, moved verbatim out of
`toehold_and_eu_test.ipynb`, holding **six** functions. Decided: the CSV parser moves too,
so there is exactly one of it rather than one per notebook.

| Function | Currently in | Why it has to move |
|---|---|---|
| `fuse()` | its own cell | the AND construct builder, needed by both notebooks |
| `measure()` | its own cell | the energy/accessibility measurement, needed by both |
| `motif_self_bind_score()` | loader cell | `measure()` and `load_ranked_designs()` both call it |
| `load_ranked_designs()` | loader cell | the NucSyn CSV parser, needed by both |
| `_maybe_float()` | loader cell | `load_ranked_designs()` calls it |
| `_toehold_self_fold()` | loader cell | `load_ranked_designs()` calls it — itself calls `_mean_unpaired`, imported in the loader cell from `engine.gates.toehold`, not defined there; the module needs that same import line or this `NameError`s on first real call |

That is every top-level `def` in the loader cell plus the two standalone cells — so three
cells collapse into imports.

**Config stays in the notebook, passed in explicitly.** `load_ranked_designs` currently
closes over the notebook's `COLUMNS` and `CARRY_METRICS`. In the module these become
required parameters, not module-level defaults — a second copy of the column map living
in the module is the same drift problem one level down. Same for `fuse()`'s
`cut_before`/`keep_after`/`spacer` defaults (`CUT_5P_BEFORE`, `KEEP_3P_AFTER`,
`SPACER_SEQ`): keep them in the notebook's parameters cell and pass them.

Then in the old notebook, replace each emptied cell **in the same position** (keeps cell
indices stable, and tells a reader where the code went rather than leaving a hole):

```python
# These now live in _switch_construct.py so this notebook and and_eu_report.ipynb share
# one implementation rather than two that drift apart (CLAUDE.md §1).
from _switch_construct import (
    fuse,
    load_ranked_designs,
    measure,
    motif_self_bind_score,
)
```

Call sites in the old notebook then need `columns=COLUMNS` / `carry_metrics=CARRY_METRICS`
added where `load_ranked_designs` is called, and `cut_before=`/`keep_after=` where `fuse`
relies on the old defaults. Grep for every call site; there are several, including inside
the snapshot dG-backfill cell.

**Verify the move changed nothing:** re-render the old notebook's report via its snapshot
path (`SNAPSHOT_TO_LOAD`, ~20 s, skips all heavy cells) and confirm the energies are
identical to the digit. If any number moves, stop and find out why before continuing —
this migration must be behaviour-neutral by construction.

## Step 1 — parameters, all in cell 1, each with a comment

| Parameter | Default | Meaning |
|---|---|---|
| `CSV_PATH` | current sele export | Source NucSyn CSV; printed on both reports |
| `TEMPERATURE_C` | `37.0` | Folding temperature, recorded on every energy |
| `SINGLE_POOL_N` | `300` | Ranked designs loaded for the single-switch screen |
| `SINGLE_REPORT_N` | `20` | How many reach the Single Switch report |
| `AND_GRID_N` | `20` | Top-N singles fed into the N x N AND grid |
| `AND_REPORT_N` | `20` | How many pairs reach the AND report |
| `N_SAMPLES` | `1200` | Boltzmann samples per state |
| `OPEN_THRESHOLD` | `0.70` | Fraction of footprint bound externally to call a state open |
| `SINGLE_N_FAKES` | `10` | Distinct fake triggers checked per single-switch candidate, **averaged** into its OFF term — matches the original ask ("10 different fake triggers... the mean will be the result"), do not reuse this count for AND |
| `AND_N_FAKES` | `10` | Distinct fakes drawn **per side** for each AND pair — 10 for the A-side states, 10 for the B-side states (20 fake-involving folds total per pair, two independent pools) — each side's result is the **mean** over its 10, same averaging shape as `SINGLE_N_FAKES`. Two separate parameters only because they're drawn from, and screened against, two different footprints — not because the counts differ (they're both 10) |
| `FAKE_MAX_SEQ_OVERLAP_NT` | `8` | Max shared/complementary run a fake may have |
| `WOBBLE_MAX_FRACTION` | `0.50` | Max share of a matched run that may be G·U |
| `SPACER_VARIANTS` | `("no_spacer", "spacer")` | Both are run and reported separately |
| `SPACER_MIN_LENGTH` / `SPACER_MAX_LENGTH` | `15` / `20` | Per-pair spacer search bounds |
| `SPACER_SEED` | `1` | Literal seed for the candidate pool |
| `FILTER_HOMOPOLYMER_RUN` | `False` | Exclude toeholds with a run > `MAX_HOMOPOLYMER_RUN` |
| `MAX_HOMOPOLYMER_RUN` | `5` | Threshold for the above |
| `MAX_WORKERS` | `6` | Process-pool width |
| `SNAPSHOT_TO_LOAD` | `None` | Set to a snapshot file to skip every heavy cell |

## Step 2 — definitions

**Footprint** = TBS (toehold) + stem_up. This is the span every "bound/open" question is
asked about.

**Single switch topology:** `prefix - TBS - stemup - loop - stemdown - kozak - CDS`

**AND topology** (hairpin 1 loses its kozak, hairpin 2 loses its prefix):

```
prefix - TBS1 - stemup1 - loop1 - stemdown1 - [spacer] - TBS2 - stemup2 - loop2 - stemdown2 - kozak - CDS
```

**Three-way state decomposition** — compute all three from the same sampled structures,
per footprint, per state:

| Metric | Definition | Ideal |
|---|---|---|
| `stem_closed` | stem_up paired specifically to **stem_down** | high in OFF |
| `misfolded` | footprint paired intramolecularly but **not** to its own stem_down | **low in every state** |
| `trigger_bound` | footprint paired to an **external** strand | high in ON, zero in OFF |

A state is "open" when `trigger_bound >= OPEN_THRESHOLD`.

Report all three. Do **not** collapse them into one number: with triggers present,
"footprint is paired" cannot distinguish "the trigger bound it" from "it
cross-hybridised with the other hairpin", and that conflation is what made the
predecessor's leak metric wrong.

**Implementation note — all three now exist, in `_joint_state_parallel.py`.**
`trigger_bound` is `_frac_paired_to_external(structure, start, end, n_self)`, already
written before this spec and already the fix for the bug above. `stem_closed_fraction`
and `misfolded_fraction` were added for this spec, built on the same `_partner_table`
stack-walk, right next to `_frac_paired_to_external` — **not** in `_switch_construct.py`
as this spec originally said: that module imports `_partner_table` *from*
`_joint_state_parallel.py`, so defining these two the other way round would be
circular. All three live where the parallel workers that call them also live.
Verified against this session's own hand-traced ground truth (rank 100+111, no_spacer):
`misfolded_fraction` reproduces 13/15=0.87 (A toehold, paired to exp_gene + B's toehold)
and 2/15=0.13 (B toehold) exactly; `stem_closed_fraction` reads 1.00 for both hairpins'
own stems.

**Fake-trigger selection** — a real trigger from the same CSV qualifies as a fake only if
its longest complementary run against the footprint is both (a)
`<= FAKE_MAX_SEQ_OVERLAP_NT`, and (b) strictly less than the real trigger's own run
against that same footprint. Allow G·U wobbles for at most `WOBBLE_MAX_FRACTION` of a
run's positions, and record `wobble_positions_used` on every reported fake set so a
wobble-driven decision is visible. Rotate the pool deterministically (`start_offset`),
never randomly.

**ON/OFF ratio** — the ranking metric, higher is better. Measured **across states**, never
within one:

- Single: `ON = trigger_bound(+real trigger)`;
  `OFF = max(open fraction over: alone, mean over SINGLE_N_FAKES fakes)`
- AND: `ON = P(both open | +A+B)`;
  `OFF = max(P(both open) over: alone, +A, +B, mean(+fakeA over AND_N_FAKES draws),
  mean(+fakeB over AND_N_FAKES draws), mean(+A+fakeA over AND_N_FAKES draws),
  mean(+B+fakeB over AND_N_FAKES draws))` — `fakeA` is drawn from a pool screened
  against *both* real triggers (reuse `pick_fake_design` as-is; it already checks both
  footprints in one call), independently per pair, 10 distinct draws averaged, same shape
  as `fakeB`. Resolved: this notebook computes the mean from the start — there is no
  separate single-draw screen followed by a later refinement pass, unlike the
  predecessor notebook's two-stage history. One pass, already averaged.

Floor `OFF` at `1/N_SAMPLES`. When `OFF` is genuinely zero, display **`>=1200`** (a bound,
not a measurement). Show `ON - OFF` in the adjacent column.

**Energies** (ensemble free energy, kcal/mol, sign convention stated next to every
number):

- Single: switch alone, trigger alone, switch+trigger, `dG`, and the mean `dG` across the
  `SINGLE_N_FAKES` fakes
- AND: alone, trigger A alone, trigger B alone, +A, +B, +A+B, and
  `Δ(ON) = ee_both - min(ee_off, ee_+A, ee_+B)`. **More negative is better.**

## Step 3 — pipeline

1. Load `SINGLE_POOL_N` designs. If `FILTER_HOMOPOLYMER_RUN`, load the whole file, filter,
   *then* cut to `SINGLE_POOL_N` — filtering a pre-capped pool shrinks it instead of
   backfilling with the next candidates that pass.
2. **Single-switch screen**, parallel per candidate: alone, +real trigger, +each fake.
   Three-way decomposition each. Rank by ON/OFF.
3. **Single Switch report** — top `SINGLE_REPORT_N`.
4. **AND grid** — `AND_GRID_N` x itself, self-pairs excluded, both spacer variants. States:
   `alone`, `+A`, `+B`, `+A+B`, `+fakeA` (mean of `AND_N_FAKES`), `+fakeB` (mean of
   `AND_N_FAKES`), `+A+fakeA` (mean), `+B+fakeB` (mean) — 8 states, the fake-involving
   four each already averaged in this one pass. Rank by ON/OFF.
5. **AND report** — top `AND_REPORT_N`.

   **Cost consequence of `AND_N_FAKES = 10` per side:** each pair now folds/samples 4
   fake-involving states x 10 draws = 40 extra jobs, on top of the 4 base states
   (`alone`/`+A`/`+B`/`+A+B`). At `AND_GRID_N = 20` that is 380 pairs x 2 spacer
   variants x 40 = ~30,400 fake-related jobs, each `N_SAMPLES` Boltzmann draws — well
   above the 2-per-pair this was costed at earlier. Benchmark one pair's full job count
   before launching the whole grid (same benchmark-first pattern the predecessor
   notebook uses for its NUPACK calls), not after.
6. **Snapshot export** (opt-in cell, timestamped JSON) and **snapshot load**
   (`SNAPSHOT_TO_LOAD`, `None` by default). Every heavy cell checks that flag at its top
   and prints a one-line skip notice instead of running. Copy this pattern from the
   predecessor notebook — it is verified working there.

## Step 4 — reports

Both as **HTML + PDF, timestamped filenames, `CSV_PATH` printed on the page.** Single
Switch and AND render in separate cells of the same notebook.

Per candidate:

- **Metrics table** — energies above; the three-way decomposition per state; Boltzmann
  agreement as *"k of N structures"*, not just a percentage; nt of trigger hybridised to
  the switch (high in ON, low in OFF/fake); nt of stem still hybridised
  (stem_up <-> stem_down) for OFF states.
- **Probability matrices** — single: alone and +trigger. AND: alone, +A, +B, +A+B. Each
  with a labelled colourbar, numbered axes, and base letters where spacing allows.
- **Domain diagram** — 2D structure plus layout bar, one colour per domain with a legend,
  and each domain's **sequence** printed. AND needs a doubled palette so hairpin 1 and 2
  are distinguishable.
- Written so someone new to the project can read it: every metric gets a one-line
  explanation of what it measures and which direction is good.

## Step 5 — state these limitations in the report itself

- `OPEN_THRESHOLD = 0.70` => numbers are **not** comparable to the predecessor notebook's
  reports (which used 0.80).
- Rows where `OFF = 0` give a ratio **bound**, not a value.
- `misfolded` is a structural risk signal, not a measured expression leak.
- The AND grid never scores a pair outside the top `AND_GRID_N` singles.

## Traps — real mistakes already made on this project. Do not repeat them.

1. **"Open" meaning "paired to anything."** The predecessor read 80-90% "open" with zero
   triggers present, purely from intramolecular misfolding. Open must mean *paired to an
   external strand*. Use `_frac_paired_to_external`.
2. **Selecting fakes by transcript position.** A positionally non-overlapping candidate was
   measured with an 8nt complementary run to a footprint whose real trigger managed only
   6nt — a "fake" that outcompetes the true pair. Screen by sequence complementarity, not
   coordinates.
3. **Watson-Crick-only complementarity scans.** A real, ViennaRNA-confirmed 12 bp helix
   scored as only 4nt under exact-complement matching because four positions were G·U
   wobbles. Any complementarity screen must accept wobbles.
4. **ON/OFF as an unguarded ratio.** `OFF = 0` occurs on real candidates. With 1200 samples
   a one-sample change moves the ratio 1200 -> 600 -> 400, so the best candidates would
   rank on sampling noise. Floor it and label bounds.
5. **Defining OFF within a single state.** `1 - P(both open)` makes the ratio a pure
   function of ON and carries no independent leak information. OFF is the worst across
   illegitimate *states*.
6. **One process pool per job.** Measured 5.8x slower than batching.
7. **`try/except: return 0.0` around a folding call.**
   `normalize_value(0.0, predicted_leakage_spec)` returns a *perfect* score, so a failed
   measurement outranks every correct one and no filter catches it. `None`, always.
8. **Assuming instead of measuring.** Every mechanism claim on this project that was
   reasoned rather than folded turned out wrong at least once. Fold it and read the base
   pairs.

## 2026-10-05 fix round (on top of the 2026-10-04 report-fix pass)

Rendered from the same `and_eu_report_snapshot_20261004T203534.json` snapshot, no
re-screen / re-grid. Changes, both reports unless noted:

- **Root bug fixed**: `_kofn_pct` used to print `"k/N (XX%)"` with `XX%` a *continuous
  mean* that does not equal `k/n*100` (verified: a real cell read `"6/1200 (29.3%)"`
  where `6/1200 = 0.5%`, not `29.3%`). Now the percentage next to `k/N` is always
  literally `k/n*100`; the mean is kept as a separately-labelled second line
  (`"k/N — XX.X% of samples · mean YY.Y%"`). Also applied to AND's per-side
  `trigger_bound_a/b` (previously a bare mean with no k/N at all) and to "both open"
  (previously `round(frac_both_open * n_samples)`, which can be off-by-one against the
  real count; the worker now returns the exact `n_both_open`/`n_a_open`/`n_b_open`
  integers instead).
- **item N**: `n_unique_structures` added to both decomp workers via the existing
  `_sample_coverage()` helper (no new sampling) and displayed as a new "unique
  structures" column in both decomp tables; backfilled narrowly for only the ~40
  report rows' states, same mechanism as the prior round's `n_stem_closed`/
  `n_misfolded` backfill.
- **item K**: `_nt`/`_nt_n` now show the denominator (`"27.0/27 nt"`, not `"27.0 nt"`).
- Metric glossary added before each report's Summary table; `OFF (fakes, nt bound to
  stem_down)` column header shortened to `FAKES` with its full definition moved into
  the glossary (not duplicated).
- Energy table narrowed to `max-width:420px` (summary/decomp tables untouched).
- Real trigger length shown next to "Trigger:" in every card head; AND also shows
  spacer length, or states explicitly when a variant has no spacer.
- Single report's zero-qualifying-fakes row (this snapshot's #1-by-ratio candidate has
  a real trigger/footprint complementary run of only 4nt, so almost nothing in the
  300-pool can score below it under `pick_fake_design`'s self-calibrated screen) now
  renders an explanatory message instead of a bare "--" row.
- `loop`/`prefix` given distinct colors in both domain palettes (previously `loop` was
  literally `_DEFAULT_FILL` and `prefix` nearly matched it); `spacer` added as a real
  palette key (shared teal) instead of a hardcoded near-invisible color in the AND
  images cell.
- `exp_gene`/`opt_exp_gene` dropped from the rendered layout bar and structure-plot
  `domain_fill`/legend in both reports (the domain itself is untouched in `fuse()`/
  `measure()`'s own output) via a shared `_PAYLOAD_DOMAINS` constant; total switch /
  fused-construct length now printed on each layout bar's title.
- Single report's ON structure plot gives the real trigger strand its own color
  (previously flat default fill) and a caption noting its drawn position is a
  `FoldEngine` `&`-join layout artifact, not meaningful.
- AND decomp table gets a one-line caption explaining "both open" is a joint
  per-sample event, not derivable from the two `trigger_bound_a/b` marginals —
  addresses the "82% trigger_bound but 4/1200 both-open" confusion directly.
