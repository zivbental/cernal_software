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

## 2026-10-05, round 3 — OFF-broadening, cross-domain binding, PDF legibility

Rendered from the same `and_eu_report_snapshot_20261004T203534.json` snapshot (no
re-screen, no re-grid), plus two narrow backfills on the ~40 report rows only (the
existing `n_stem_closed`/`n_misfolded`/`n_unique_structures` backfill, unchanged, and
a brand-new one for the cross-domain-binding fields below).

- **OFF broadening (user-approved)**: OFF used to be picked by trigger-binding leak
  (`frac_open`/`frac_both_open`) alone — blind to a state whose STEM is independently
  loose for an unrelated reason while `frac_open` stays ~0 (nothing legitimate present
  to trigger-bind). `badness = max(trigger-binding leak, stem-loosening leak
  [, AND: the OTHER (absent-trigger) hairpin's own trigger_bound opening anyway —
  cross-talk])`, shared via `_single_badness`/`_and_badness`/`_and_off_term` (cell 7)
  so the snapshot-restore path (cell 9) and a fresh full run's own scoring cells (12,
  19) score identically. `off_criterion` records which term won, shown on every card
  ("OFF set by: fakes's stem-loosening"). **Load-bearing correctness fix found while
  building this**: a state's own ACTING side must be exempt from its own
  stem-loosening term — e.g. in AND's "+A" state, A's own trigger legitimately
  displaces A's stem_up from stem_down, which is the intended result of real binding,
  not a leak. Without this mask, every state with any real trigger present reads
  ~100% stem-loosening badness for the bound side, collapsing OFF to ~100% and ratio
  to ~0 for every candidate uniformly (verified directly, then masked via
  `_and_off_term(..., mask_side=...)`).
  - Single report: top-5 reordered (rank 4, 12, 72, 40, 44 replace 4, 6, 7, 9, 11) —
    e.g. rank 72 was OFF=0.0%/ratio=100.0 under the old frac_open-only formula and is
    now OFF=11.1%/ratio=8.3 (`off_source=fakes`, `off_criterion=stem-loosening`): its
    fakes' trigger-binding leak was genuinely ~0, but its stem was independently loose
    against those same fakes, previously invisible.
  - AND report: top-20 pair order is stable except a 3-way shuffle at #3–#5 (70+6,
    11+55, 63+56 permute among themselves); #1/#2 (56+63 spacer/no_spacer) and the
    rest of the top 20 are unchanged in rank. OFF values for nearly every AND
    candidate now sit near 100% (ratio near 0), because at least one hairpin's stem
    reliably fails to stay closed in at least one of the states that are NOT its own
    binding state (e.g. 56+63's hairpin B: `n_stem_closed_b=0/1200` during "+A only").
    This is a real, previously-invisible characteristic of this candidate pool, not a
    scoring bug — flagged explicitly here because it changes the AND ratio column from
    a wide, discriminating range into a narrow one dominated by this one failure mode;
    worth a follow-up decision on whether stem-loosening should carry full weight
    equal to trigger-binding leak in the AND `max()`, or a smaller one, in a future
    round.
- **Cross-domain binding (new field, display-only, AND report only)**: for each AND
  report row's "+A+B" (ON) state, mean fraction of spacer nt paired to either hairpin's
  own toehold, and mean fraction of each hairpin's toehold paired to the OTHER
  hairpin's prefix domain — `CrossDomainJob`/`_cross_domain_worker`/
  `run_parallel_cross_domain` in `_joint_state_parallel.py`, reusing `_partner_table`
  (no second pairing walker). Backfilled narrowly for only `and_report_rows`'s "+A+B"
  state (~20 jobs, under a second). `None`/"--" when a term cannot be measured (no
  spacer in this variant; hairpin B's own prefix domain is cut away entirely by
  `fuse()` under this topology's `KEEP_3P_AFTER="prefix"`, so `toeholdA↔prefixB` reads
  "--" for every AND candidate here, not 0.0%) — CLAUDE.md sec 3. No ranking effect.
- **FAKES-%-fix**: new `_nt_pct` helper (cell 7) shows the mean % right next to the
  nt-count (`"6.8/18 nt (37.8%)"`), applied everywhere a FAKES-related nt-count is
  shown (summary column, per-side AND summary columns, single decomp table's +fake row).
- **OFF-criterion note**: every card head now states which criterion decided that
  candidate's own OFF (`"(OFF set by: fakes's stem-loosening)"`, AND also names A/B/
  cross-talk) so the FAKES column and OFF column are never silently about two
  different things again.
- **Energy table legibility**: header text shortened to `energy`/`kcal/mol`, the
  "ensemble ΔG..." sentence moved to a one-time `<p class="scr-p">` caption above the
  table; print CSS gives `.scr-table-energy` its own exemption from the generic
  tight-print squeeze (10.5px/5-8px padding vs. the generic 8px/3-4px). Confirmed by
  rendering to PDF and reading it directly: energy numbers are now clearly larger than
  the surrounding decomp table, not squeezed to the same 8px as every other table.
- **Decomp table PDF fit**: `<colgroup>` with explicit percent widths (summing to
  100%) on both decomp tables, headers shortened (the repeated "(k of N, mean %)"
  suffixes cut to a one-word `<small>` hint, since the glossary now explains the
  convention once). **Load-bearing fix found while verifying the PDF render**:
  `<colgroup>` widths alone do nothing without `table-layout:fixed` on the `<table>`
  itself — without it the browser auto-sizes columns by content and silently clips
  the last 1-2 columns at the container's right edge in the static Chromium PDF
  render (no horizontal scrollbar exists there to reveal the loss). Added
  `table-layout:fixed` inline on both tables, plus a CSS rule letting the `<small>`
  secondary line wrap independently of its parent `td.num`'s `white-space:nowrap` (the
  compound "k/N / pct-of-samples / mean" cells are too long for a ~90px fixed column
  on one line otherwise). AND's wider 7-data-column layout additionally gets its own
  smaller base font (`.scr-table-and-decomp`, 7px in print) rather than being split
  into two stacked tables — confirmed by rendering to landscape A4 PDF at actual page
  width: all 7/9 columns visible on both tables, no truncation, no overflow.
- **Trigger-hidden ON plot (AND only)**: `structure_png` gets an optional
  `visible_len` parameter — only positions `0..visible_len` of the sequence are
  scattered at all; a base pair with exactly one partner outside that range draws no
  connecting line (the hidden partner doesn't exist on the plot) but gives the
  switch-side base a dangling-ring indicator instead of looking falsely unpaired. Used
  only for the AND report's "+A+B" structure plot (not "alone", not "+A"/"+B", not the
  single report's ON plot) with a one-line figcaption noting triggers are hidden.
  Confirmed by rendering: the "+A+B" image now shows only the switch's own two-hairpin
  fold, the same visual style as the "alone" plot, no trigger dots anywhere.
- AND summary table headers renamed `OFF` → `OFF-STEM BOUND`, `FAKES` →
  `FAKES-STEM BOUND` (AND report only, per explicit request — single report's headers
  left as-is).
- Glossary worked examples (k/N-vs-mean, per-side nt base, cross-talk) are now computed
  live from each render's own `rows[0]`/matching candidate rather than hand-typed, so
  they can never go stale against a re-render.

Verified by executing the notebook end to end (`uv run python <jupyter_client runner>`)
and reading the real rendered HTML/PDF output (landscape A4, actual page width, not the
HTML in a browser) for both reports' summary tables and several candidate cards.
`uv run pytest tests/engine -q`: 730 passed. `uv run ruff check .`: clean (same
pre-existing, unrelated `_joint_state_parallel.py:767` format-only diff noted in the
prior round, confirmed still present and still unrelated to this round's changes).

## 2026-10-05, round 4 — trigger-vs-trigger overlap screen, summary-row breakdown revert, kozak-ring color

**Finding — the AND grid never screened a pair's own two REAL triggers against each
other.** `FAKE_MAX_SEQ_OVERLAP_NT`/`WOBBLE_MAX_FRACTION` only ever screened a FAKE
trigger against the real trigger of the SAME candidate, via `pick_fake_design` — never
trigger-A-vs-trigger-B of the pair actually being fused. Confirmed by direct
inspection on real data: the AND report's #1 candidate by ratio across the last two
rounds (56+63) has trigger A (30nt, `UUACCCCCUCAUUGUUUAUUAACAAAUUAU`) and trigger B
(33nt, `UCUAGAUUACCCCCUCAUUGUUUAUUAACAAAU`) sharing a **27nt IDENTICAL substring** — the
same transcript region, not independent AND inputs. The same pair's complementary-run
screen (the metric this fix actually applies, per the user-approved cap reusing
`_longest_complementary_run_wobble`) reads 9nt — just over the existing 8nt
`FAKE_MAX_SEQ_OVERLAP_NT` cap — confirming near-duplicate trigger sequences also carry
matching local self-complementarity artifacts, not only a long identical run. This is
very likely most of what the 2026-10-04/2026-10-05-round-3 investigations labelled
"real cross-hybridization" (trigger B opening hairpin A) for this same pair — not
subtle biology, near-duplicate trigger sequences being paired together.

**Fix**: `trigger_pair_too_similar(trigger_a, trigger_b, *, max_overlap_nt,
wobble_max_fraction)`, new in `_joint_state_parallel.py`, reuses
`_longest_complementary_run_wobble` (same helper, same semantics as the existing
fake-trigger screen) applied between the pair's own two real triggers. Called with
`max_overlap_nt=FAKE_MAX_SEQ_OVERLAP_NT, wobble_max_fraction=WOBBLE_MAX_FRACTION` (the
SAME parameters already governing fake screening — no new tunable). A pair that fails
is excluded entirely (not scored, not shown), from both the fresh-grid-building path
(before any job is submitted for it) and the snapshot-restore rescoring path (filtering
the already-scored/restored rows) — one shared predicate, not two copies of the same
condition. On the current 2026-10-04 snapshot's top-20 AND report rows: 3/20 excluded
(56+63 × both spacer variants, 70+6 — all three previously top-ranked candidates
flagged across the last two rounds' own screenshots), 17 remain. 11+55 and 63+56 (runs
of 6nt and 8nt respectively, at or under the cap) survive.

**Also reverted**: the AND summary table's OFF cell dropped the
`_off_breakdown_text`/`_off_breakdown_compact` sentence added last round — too much
text under the numbers in a 20-row table — back to the plain OFF percentage + per-side
nt-counts. The card head keeps the full breakdown (room for it there). Checked the
single report for the same pattern: its summary rows never called the breakdown helper
in the first place (only `_pct_nt_n`, a plain percentage/nt/n display) — no change
needed there.

**Also fixed**: a stray-looking red ring on kozak in the AND structure plots. Root
cause confirmed directly on real data (candidate 56+63, "alone" state): kozak(B) spans
`[140, 146)`, `visible_len` (the kozak-end clip) is 146, and the real MFE structure of
the fused construct pairs bases 141-143 (inside kozak) to bases 169-171 — squarely
inside the clipped exp_gene payload tail `[146, 176)`. **Correct, not a bug**: kozak
genuinely folds back onto the construct's own hidden payload bases just past the clip
boundary. The dangling-ring mechanism (`structure_png`, AND item 7/4) used ONE color
(`_TRIGGER_COLOR`, red) for every hidden partner regardless of cause, so this
correct-but-mundane payload fold-back read identically to "bound to a hidden trigger
strand" — alarming and misleading. Fixed by giving `structure_png` a new
`construct_len` parameter (the fused construct's own length, always `<= len(sequence)`
when trigger strands are appended): a hidden partner index `< construct_len` is the
construct's own hidden tail and now gets a new, less alarming `_PAYLOAD_RING_COLOR`
(amber, matching the existing exp_gene/payload domain color); `>= construct_len` is a
genuinely hidden trigger strand and keeps the original red. A one-line legend entry is
added per plot for whichever ring color(s) actually appear on it. Confirmed by
rasterizing the re-rendered PDF: candidates 11+55 and 63+56 both show the amber
"ring: paired into this construct's own hidden tail" ring (and matching legend entry)
at the kozak boundary in both their "alone" and "+A+B" structure plots — no red ring
present in either (would need a base pairing to a genuinely hidden trigger strand to
trigger). Checked the single report for the same mechanism: its structure plots never
pass `visible_len` at all — every sequence plotted is already truncated by a real
separate fold, nothing hidden past the plotted end — confirmed unaffected by
rasterizing its own #1 candidate.

Verified by executing the notebook end to end against the same 2026-10-04 snapshot (no
re-screen, no re-grid) and reading the real rendered HTML/PDF output.
`uv run pytest tests/engine -q`: 730 passed. `uv run ruff check .`: clean.

## 2026-10-05, round 5 — correctness bug in round 4's trigger-overlap screen (complementarity alone is the wrong check)

**Finding — round 4's `trigger_pair_too_similar` checked the wrong relationship.** It
screened only the longest COMPLEMENTARY run between trigger A and trigger B (would
they physically hybridize to EACH OTHER). That is the right check for fake-trigger
screening (`pick_fake_design`: does an off-target fake accidentally bind a footprint
meant for the real trigger), but it is the wrong check for "are these two triggers
drawn from the same transcript region" — two IDENTICAL, same-direction sequences are
generally NOT self-complementary, so a same-direction duplicate structurally cannot be
caught by a complementarity check.

**Confirmed by a real counterexample that passed round 4's screen and was ranked #1**:
after round 4 excluded 56+63/70+6, the new top candidate was **11+55** — trigger A
(30nt, `ACGAGAAGCCAACGUGUAAAGCUGUGACAU`) and trigger B (27nt,
`ACGAGAAGCCAACGUGUAAAGCUGUGA`), where B is a literal, exact 27/27nt PREFIX of A, same
direction. Their longest COMPLEMENTARY run is only 6nt (well under the 8nt cap, which
is exactly why round 4 let it through) while their longest IDENTITY run is the full
27nt.

**Fix**: added `_longest_identity_run(a, b)` to `_joint_state_parallel.py` — the same
ordinary longest-common-substring DP shape as the existing `_longest_complementary_run`
(checked first: nothing in `engine/sequences.py` or this notebook's own helpers already
did plain same-direction identity matching), just WITHOUT the `reverse_complement`
step. `trigger_pair_too_similar` now rejects a pair when EITHER the complementary run
OR the identity run exceeds `FAKE_MAX_SEQ_OVERLAP_NT` (8nt) — same cap, same parameter,
both checks. No wobble/mismatch tolerance on the identity check (unlike the
complementarity check's G·U wobble, which models a real physical base pair) — identity
is binary per position, so a plain exact-match run is the right analog, kept as
narrowly scoped as `_longest_complementary_run` itself.

**Re-verified on the same 2026-10-04 snapshot's top-20 AND rows**: **5/20 now excluded**
(up from round 4's 3/20) — 56+63 [spacer] (comp=9, ident=27), 56+63 [no_spacer]
(comp=9, ident=27), **11+55 [spacer]** (comp=6 — passed round 4 — ident=27, now
excluded), **63+56 [spacer]** (comp=8 — passed round 4 — ident=27, now excluded, the
mirror-image pair of 11+55), 70+6 [spacer] (comp=11, ident=30). 15 remain. Every
remaining "4+N [no_spacer]" row has an identity run of 3-6nt (genuinely different
transcript regions) and passes both checks. New top-5 by ratio: 4+6, 4+7, 4+9, 4+11,
4+12 (all `[no_spacer]`) — every previously top-ranked candidate from the last three
rounds' own screenshots (56+63, 70+6, 11+55, 63+56) is now excluded.

Dek/glossary updated again to describe both checks; both reports re-rendered from the
same snapshot, re-verified by rasterizing the new PDF with `pdftoppm`.

Verified by executing the notebook end to end against the same 2026-10-04 snapshot (no
re-screen, no re-grid) and reading the real rendered HTML/PDF output.
`uv run pytest tests/engine -q`: 730 passed. `uv run ruff check .`: clean.
