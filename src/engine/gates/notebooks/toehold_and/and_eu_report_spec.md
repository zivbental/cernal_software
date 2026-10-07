# Spec — `and_eu_report.ipynb` (eukaryotic toehold switch ON/OFF report)

> Current as of 2026-10-07. The code is the source of truth: if this file and the notebook
> or `_joint_state_parallel.py` disagree, the code wins and this file is wrong. Cell numbers
> below are the notebook's cell indices on this date and shift when cells are added.

This file describes the pipeline and methods as they exist now, with the rationale inline.
The "why" matters: the Traps section is made of real mistakes, and without the reasoning it
gets "simplified" straight back into the bugs it describes. Dated history is in the
**Change log** at the bottom.

## Context to read first

- `CLAUDE.md` §1 (do not rewrite existing functions), §3 (raw values, `None` never
  defaulted), §5 (tools injected; `FoldEngine` is the only folding adapter), §6
  (units, conventions).
- `and_eu_report.ipynb` — the notebook this file specifies.
- `_joint_state_parallel.py` (this folder) — process-pool workers, `designed_pairs`,
  `both_triggers_extra`, fake-trigger selection, overlap screens, spacer selection.
- `_switch_construct.py` (this folder) — `fuse`, `measure`, `load_ranked_designs`,
  `motif_self_bind_score`, shared with `toehold_and_eu_test.ipynb`.
- `src/engine/gates/tools/folding.py` — `FoldEngine` (`mfe`, `partition`,
  `base_pair_probabilities`, `constrained_probability`, `layout_coordinates`, `versions`);
  tests in `tests/engine/test_fold_constrained_probability.py`.
- `src/engine/gates/notebooks/toehold/render_pdf.py` — HTML to PDF.

## Hard rules

1. **Fold only through `FoldEngine`.** One instance, built once in cell 5 via
   `fx.fold_engine(real=True, temperature=TEMPERATURE_C)` and published to the worker
   module with `use_fold_engine(folder)` before any pool starts (the pools fork, so every
   worker inherits that one instance and its cache). No `import RNA`; enforced for module
   code by `tests/engine/test_house_rules.py`.
2. **Reuse, do not rewrite.** `fuse`, `measure`, `load_ranked_designs`,
   `motif_self_bind_score` (`_switch_construct.py`); `designed_pairs`,
   `both_triggers_extra`, `pick_fake_trigger`/`pick_fake_triggers`,
   `trigger_pair_too_similar`, `generate_spacer_candidates`, `pick_optimized_spacer`,
   `SingleExactJob`/`run_parallel_single_exact`, `and_pair_jobs` (builds the
   `AndDecompJob`s of one pair)/`run_parallel_and_decomp` (`_joint_state_parallel.py`);
   `longest_homopolymer` from `engine.sequences`. The
   sampled workers that remain in `_joint_state_parallel.py` (`SingleStateJob`,
   `FakeSweepJob`, `ConstrainedBindJob`, `SingleDecompJob`) are for other notebooks; this
   report does not use them.
3. **One process-pool call per batch**, never one pool spin-up per job (measured 5.8x
   overhead for the anti-pattern).
4. **Raw values only.** A metric that could not be computed is `None` and renders `--`.
   Never `0.0`, `-1` or `nan` as a stand-in.
5. **No randomness without a literal seed.** Only the spacer candidate pool is random
   (`SPACER_SEED`).
6. **Everything runs through notebook cells**, including verification. No standalone
   scripts (a script copy of notebook code once produced a silent indexing bug here).
   Verification cells stay in the file, under the "Verification" heading.
7. **Do not edit test files.**

## Step 0 — shared module (done; for orientation only)

`fuse`, `measure`, `motif_self_bind_score`, `load_ranked_designs`, `_maybe_float` and
`_toehold_self_fold` live in `_switch_construct.py`, moved out of
`toehold_and_eu_test.ipynb` so the two notebooks share one implementation. Notebook-level
configuration is passed in explicitly, never defaulted in the module: `load_ranked_designs`
takes `columns=COLUMNS`, `carry_metrics=CARRY_METRICS`; `fuse` takes
`cut_before=CUT_5P_BEFORE`, `keep_after=KEEP_3P_AFTER`, `spacer`. `_switch_construct.py`
imports `both_triggers_extra` from `_joint_state_parallel.py` (not the other way round), so
helpers the workers need must live in `_joint_state_parallel.py`.

## Step 1 — parameters (cell 4; every tunable lives here)

| Parameter | Current value | Meaning |
|---|---|---|
| `CSV_PATH` | NucSyn `.../output_T2/targets/sele/basic_switch/results_ranked.csv` | Source CSV, sorted best-first by `postgen_global_rank`; printed on both reports |
| `COLUMNS` | dict: `switch`, `trigger`, `domains`, `rank`, `trigger_start`, `trigger_end` mapped to CSV column names | Column map `load_ranked_designs` requires |
| `CARRY_METRICS` | `("sim_score", "mcc", "switch_toehold_unpaired_prob_mean", "energy_trigger_mfe")` | CSV columns carried into `design["metrics"]` unchanged (read, not recomputed) |
| `CUT_5P_BEFORE` | `"kozak"` | 5' half of an AND construct keeps everything before its own kozak |
| `KEEP_3P_AFTER` | `"prefix"` | 3' half keeps everything after its own prefix |
| `TEMPERATURE_C` | `37.0` | Folding temperature for the one `FoldEngine` and every job |
| `SINGLE_POOL_N` | `1000` | Ranked designs loaded and scored in the single-switch screen |
| `SINGLE_REPORT_N` | `20` | Singles shown in the Single Switch report |
| `AND_GRID_N` | `30` | Top singles (by single-switch ON - OFF order) fed into the N x N AND grid |
| `AND_REPORT_N` | `20` | AND pairs shown in the AND report |
| `OFF_FLOOR_PCT` | `1.0` | Floor for OFF (percentage points) in the ratio: `ratio = ON% / max(OFF%, OFF_FLOOR_PCT)`; floored rows are marked `*` |
| `OPEN_THRESHOLD` | `0.70` | HIGH/LOW cutoff of the green/red plan colouring **only** (HIGH >= 0.70, LOW <= 0.30); never enters a score |
| `SINGLE_N_FAKES` | `10` | Distinct fakes per single-switch candidate, averaged into its OFF fakes term |
| `AND_N_FAKES` | `10` | Distinct fakes drawn **per side** (A and B, two independent rotations) per AND pair; separate from `SINGLE_N_FAKES` because the two footprints are screened and reported separately, so changing one must never change the other |
| `FAKE_MAX_SEQ_OVERLAP_NT` | `8` | Max identical run (nt) a fake trigger may share with a real trigger; also the cap for the AND trigger-vs-trigger screen |
| `WOBBLE_MAX_FRACTION` | `0.50` | Used by the AND trigger-vs-trigger complementarity screen only: max share of a counted complementary run that may be G·U wobble. Fakes ignore it |
| `SPACER_VARIANTS` | `("no_spacer", "spacer")` | Both run and reported separately |
| `SPACER_MIN_LENGTH` / `SPACER_MAX_LENGTH` | `15` / `20` | Spacer candidate length range |
| `SPACER_SEED` | `1` | Literal seed of the spacer candidate pool |
| `SPACER_CANDIDATE_POOL_SIZE` | `150` | Candidates `generate_spacer_candidates` draws |
| `FILTER_HOMOPOLYMER_RUN` | `False` | Exclude toeholds with a homopolymer run > `MAX_HOMOPOLYMER_RUN` |
| `MAX_HOMOPOLYMER_RUN` | `5` | Threshold for the above |
| `MAX_WORKERS` | `6` | Process-pool width |
| `SNAPSHOT_TO_LOAD` | `None` | Snapshot file (name or absolute path) to restore instead of running any heavy cell |

There is no sample-count parameter: nothing in the report is sampled.

## Step 2 — definitions

### Constructs

- **Footprint** = toehold (TBS) + `stem_up`. Every "bound" question is asked about it.
- **Single switch:** `prefix - TBS - stem_up - loop - stem_down - kozak - CDS`.
- **AND construct** (`fuse()`; hairpin A loses its kozak, hairpin B loses its prefix):
  `prefix - TBS1 - stem_up1 - loop1 - stem_down1 - [spacer] - TBS2 - stem_up2 - loop2 - stem_down2 - kozak - CDS`.
  `fuse(design_5p, design_3p, cut_before, keep_after, spacer)` keeps the 5' design's switch
  up to the start of its `cut_before` domain, appends the spacer, then the 3' design's
  switch after the end of its `keep_after` domain; every surviving domain is relocated into
  the fused frame (`domains_5p`, `domains_3p`, `footprint_5p`, `footprint_3p`,
  `spacer_span`) and each relocation is asserted to hold the original sequence. A design
  lacking the needed domain or `stem_up` returns `(None, problem)` and the pair is skipped.
- **Spacer:** `SPACER_VARIANTS` runs each pair twice. `no_spacer` is the empty string.
  `spacer` is `pick_optimized_spacer`: from the seeded pool (`generate_spacer_candidates`:
  A/U-biased, lengths cycling over the range) the candidate with the smallest worst-case
  complementary run against either toehold or either trigger; ties go to lower GC, then
  to pool order (deterministic).

### Per-hairpin metrics (all exact, from one `FoldEngine.base_pair_probabilities` matrix)

`_exact_decomp_means` reads, for each position, the total probability of pairing into a
target set, and averages over a span (`None` for an empty span). Indices below `n_self`
(`len(fused)` or `len(switch)`) are the switch; at or past it, an external strand.

| Metric | Span (denominator) | Pairs into | Ideal |
|---|---|---|---|
| `stem_closed` | `stem_up` | the hairpin's own `stem_down` | high in OFF states, low once its own trigger is bound |
| `misfolded` | footprint | the switch, but not its own `stem_down` | low in every state |
| `trigger_bound` | footprint | any external strand (index >= `n_self`) | high with its own trigger, ~0 otherwise |

Per position, unpaired + external + own-`stem_down` + other-intramolecular probabilities sum
to 1 (verification 3). Each metric is the expected fraction of its span's
nt; the report also shows it as nt out of the span length. Do not collapse them into one
number: "footprint is paired" cannot tell "the trigger bound it" from "it cross-hybridised
with the other hairpin".

### States

- **Single:** `alone`, `+real trigger`, `+fake` (one job per fake, up to `SINGLE_N_FAKES`).
- **AND:** `alone`, `+A`, `+B`, `+A+B`, and per side up to `AND_N_FAKES` draws of
  `+fakeA`, `+A+fakeA`, `+fakeB`, `+B+fakeB`. Worst case `4 + 4*AND_N_FAKES` jobs per
  (pair, spacer).
- **Strand order.** A state is folded as `switch & extra1 & extra2 ...`. Every state
  holding both real triggers uses `both_triggers_extra(trigger_a, trigger_b)` =
  `(trigger_b, trigger_a)`: B first, A last. ViennaRNA's multi-strand folding represents
  only structures nested along the written strand order; `fused&tA&tB` makes
  footprint A/tA cross footprint B/tB (a pseudoknot), so trigger B cannot bind. Measured
  on pair 4+6 no_spacer: trigger B to footprint B 0.00 in that order, 0.98 in `fused&tB&tA`
  (MFE -70.8 vs -88.2 kcal/mol). Physically the order is irrelevant; it is a modelling
  constraint. `+A+fakeA` / `+B+fakeB` keep (real, fake): one real footprint is in play, so
  its duplex nests either way. The helper is used by `and_pair_jobs` (grid),
  `measure()`, and the figures.

### ON (exact joint probability)

`designed_pairs(fused, duplexes)` builds the designed footprint-trigger duplex from the
sequences, not from an MFE: each `(footprint_start, trigger, trigger_offset)` aligns the
trigger antiparallel to the switch from its footprint start (trigger base `k` faces switch
base `footprint_start + len(trigger) - 1 - k`) and keeps every facing pair that can pair
(Watson-Crick or GU), using the shared `binding.alignment_pairs` taken from Offer's branch;
a designed mismatch is skipped. If a duplex keeps no pair it returns
`None`. (An earlier version took the pairs from the state's MFE; that counted only the
toehold when the MFE had not opened the stem, and left a state undefined whenever its MFE kept
the footprint closed.) Then
`FoldEngine.constrained_probability(strands, pairs)` returns

    P(all pairs present) = Z(forced)/Z = exp(-(G_forced - G) / RT),  RT = FoldEngine.rt (ViennaRNA GASCONST, same as Offer's `p_open`)

from two partition functions (the constrained one uses `hc_add_bp` with all-loop
enforcement). Pairs are 0-indexed over the `&`-removed concatenation. It returns `None`,
never 0.0 or 1.0, for an empty pair list, an infeasible or conflicting constraint set, or a
ViennaRNA failure; for a single pair it equals the `base_pair_probabilities` entry (to about
3e-6).

- `p_on` is computed only for the `+real trigger` state (single) and the `+A+B` state
  (AND); every other state has `p_on = None`. `ON = p_on`; `None` shows `--`, the ratio is
  `None`, and the row sorts last.
- For display only (not scored), the AND `+A` and `+B` states also get `p_own_duplex`: the
  same exact probability over that one hairpin's own footprint (A in `+A`, B in `+B`;
  `AndDecompJob.own_side`). It shows in the P(duplexes) column of those rows, next to the
  averaged `trigger_bound`. It is `None` (`--`) when that footprint has no designed pair.
  Snapshots exported before this field existed show `--` there.
- The event is **strict**: every designed pair must be present at once, so `P(duplexes)` is
  below the probability of each single designed pair (a joint event cannot exceed one of
  its parts; asserted in verification 6 against the weakest designed pair of the top rows).
  The product of per-side bound means is not the quantity.

### OFF (worst state's stem opening)

OFF is the **stem opening**, whatever the cause: for each state, the share of a hairpin's
`stem_up` that is NOT paired to its own `stem_down`. Trigger binding to the footprint is no
longer part of OFF (it stays visible in the decomposition tables); a stem that opens because
a fake trigger invaded, because the other trigger acted, or because the hairpin folded open
on its own counts the same.

Per state, for every hairpin whose **own real trigger is absent** (`mask_side` names the
side whose own trigger is present and is exempt):

- stem-loosening = `1 - mean_stem_closed`

State leak = the largest stem-loosening over its non-exempt hairpins (`_single_badness`,
`_and_off_term`); `OFF` = the largest leak over the states; `off_source` = the winning
state, `off_criterion` = the winning term (`stem-loosening`, with `(A)`/`(B)` in AND),
`off_terms` = all terms of that state (shown on every card, with every state in the card's
"How ON and OFF were computed" table). Without the mask, a working design's own trigger
binding, which necessarily opens its `stem_up`, would read as a leak in every state holding
a real trigger and collapse OFF to ~100% for every candidate (verified).

- **Single:** states `alone` and `fakes` (the mean of the per-draw exact means over the
  found fakes).
- **AND:** `alone`, `+A`, `+B`, `+fakeA`, `+fakeB`, `+A+fakeA`, `+B+fakeB` (fake states pooled
  as the mean of per-draw exact means). `+A` and `+A+fakeA` score hairpin B only; `+B` and
  `+B+fakeB` score hairpin A only; `alone`, `+fakeA`, `+fakeB` score both.
- A missing input (including a pooled fake mean lacking one draw) makes that state's
  leak, OFF and the ratio `None`; it is never dropped to give a lower OFF.
- OFF is measured **across states**, never as `1 - ON` within one (see Traps).
- History: until 2026-10-07 OFF was the larger of this stem opening and the trigger-binding
  mean (`mean_trigger_bound`) of the same hairpin; a fake trigger paired to part of a
  footprint without opening the stem then set OFF (7.2% for the top AND pair, of which the
  stem opening was 0.3%).

### Ratio and ranking

`ratio = (ON*100) / max(OFF*100, OFF_FLOOR_PCT)` in percentage points. An OFF below
`OFF_FLOOR_PCT` (1%) is replaced by it in the ratio, so OFF values of 0.2% and 0.9% give the
same ratio and a measured OFF of 0 stays finite. Rows where the floor was used carry
`off_floored = True`; the reports mark their ratio with `*` and print a note under the summary
table, while the OFF column keeps the measured value. `ON - OFF` is shown
beside it.

- **Single order** (`_single_sort_key`): `ON - OFF` in percentage points rounded to 1
  decimal, descending, then `dG` ascending (more negative first), `dG = None` last within a
  tie, `ON - OFF = None` last overall. Applied to the whole pool in cell 12; the top
  `AND_GRID_N` of this order enter the AND grid.
- **AND order:** `ON - OFF` descending, `None` last (no tie-break).
- The ratio is computed and shown in both reports but orders neither list.

### Fake triggers

`pick_fake_trigger(real_triggers, exclude_ranks, pool, start_offset=0, *, max_overlap_nt=8)`
scans the pool from `start_offset`, wrapping, and returns the first design whose trigger has a
longest same-direction identical run (`_longest_identity_run`, plain longest common
substring) of at most `FAKE_MAX_SEQ_OVERLAP_NT` against **every** real trigger given. Rule:
a fake shares at most `FAKE_MAX_SEQ_OVERLAP_NT` nt of sequence with any real trigger.
Identity only: no complementarity or wobble test. `pick_fake_triggers(real_triggers,
exclude_ranks, pool, n, start_offset, *, max_overlap_nt)` collects up to `n` distinct fakes
by calling it with `start_offset + k` and excluding each pick from the next. Single:
`real_triggers = (trigger,)`; AND: `(trigger_a, trigger_b)` for both sides, since both real
triggers are in the construct. Single fakes come from the full single pool
(`start_offset = i + 1`); AND fakes also come from the full single pool (`SINGLE_POOL_N`
candidates), side A with `start_offset = 0`, side B with `1000`, each side excluding the pair
itself and its own earlier picks. The pool can run out: fewer than `N_FAKES` fakes are used
and reported as found, never padded; zero found renders an explanatory note, not a
measurement. `pick_fake_design` (footprint-complementarity screen) remains in the module
for the other notebooks but this report does not call it.

### AND trigger-vs-trigger overlap screen

`trigger_pair_too_similar(trigger_a, trigger_b, max_overlap_nt, wobble_max_fraction)` is
checked per ordered pair before any job is built, with the same
`FAKE_MAX_SEQ_OVERLAP_NT` / `WOBBLE_MAX_FRACTION`. A pair is excluded (not scored, not
shown) when **either** the longest complementary run (wobble-tolerant) **or** the longest
same-direction identity run (`_longest_identity_run`, exact match, no tolerance) exceeds
the cap. Both checks are needed: two near-duplicate triggers from one transcript region
are same-direction identical and generally not complementary to each other, so a
complementarity check alone cannot see them (Trap 4). Self-pairs are also excluded, and a
pair for which `fuse()` reports a problem is skipped and counted in the grid cell's printout.

### Energies (ensemble free energy, kcal/mol, more negative = more stable)

- Single (cells 12-13): switch alone, trigger alone, switch + trigger, `dG` = ee(switch +
  trigger) - ee(switch alone), and the mean `dG` over the fakes. All via `FoldEngine.partition`.
- AND (cell 19): alone, trigger A alone, trigger B alone, +A, +B, +A+B and
  `dG` = `measure()`'s `d_ee_worst_alt` = ee(+A+B) - min(ee(alone), ee(+A), ee(+B)).

## Step 3 — pipeline (cell by cell)

| Cell | Role | Exact / parallel |
|---|---|---|
| 0, 2 | Intro markdown; path setup and `fx.bootstrap()` | |
| 4 | Parameters (Step 1) | |
| 5 | One `FoldEngine`; `use_fold_engine`; imports | one instance for the whole notebook |
| 7 | Plotting, CSS and scoring helpers: `structure_png`, `bpp_heatmap_png`, `layout_bar_png`, `_single_badness`, `_and_off_term`, `_on_off_ratio`, `_mean_or_none`, `_plan_class`, `_off_breakdown_text`, `_single_sort_key`, `_average_ranks`, `_spearman_rho`, `_kendall_tau_b`, `csv_vs_report_rank_png`, `_render_pdf`, formatting helpers | no folding of its own |
| 9 | **Snapshot restore** (pure load) and `_report_root` (`var/reports`, found by walking up to `pyproject.toml`) | |
| 10 | Load `SINGLE_POOL_N` designs. With `FILTER_HOMOPOLYMER_RUN`: load the whole file, filter, then cut (filtering a pre-capped pool would shrink it instead of backfilling) | |
| 11 | Single screen: for every candidate the jobs `alone`, `real` (`with_joint=True`), up to `SINGLE_N_FAKES` fakes (`pick_fake_triggers`); all of all candidates in **one** `run_parallel_single_exact` call | exact, parallel |
| 12 | Single scoring: ON, OFF (source/criterion/terms), ratio, `dG` for the whole pool; sort by `_single_sort_key`; `single_report_rows` = top `SINGLE_REPORT_N`; `single_scored_pool` (slim: `csv_rank`, `on`, `off`, `ratio`, `d_ee`, `off_source`, `off_criterion`) | exact (cached `partition`) |
| 13 | Mean `dG` over fakes for report rows | |
| 14 | Single images (OFF alone and ON +trigger structures and matrices through Kozak, layout bar) | cache hits |
| 15 | Single report: CSV-vs-report rank section and PNG, HTML, PDF | |
| 17 | AND grid: `AND_GRID_N` x itself, self-pairs, overlap-screen failures and `fuse()` failures excluded, both spacer variants; every job of every pair (`and_pair_jobs`) submitted in **one** `run_parallel_and_decomp` call | exact, parallel |
| 18 | AND scoring: ON, OFF, ratio; sort by ON - OFF; `and_report_rows` = top `AND_REPORT_N` | exact |
| 19 | AND energies (`measure()` plus trigger energies) for report rows | cached |
| 20 | AND images (structures for `alone` and `+A+B`; matrices for `alone`, `+A`, `+B`, `+A+B`; layout bar) | cache hits |
| 21 | AND report HTML and PDF | |
| 23 | **Snapshot export**: timestamped JSON `and_eu_report_snapshot_<ts>.json` with `single_report_rows`, `and_report_rows`, `single_scored_pool`, `csv_path`, `temperature_c`, `open_threshold`, `exported_at`; every row key ending `_png` is stripped (images rebuild in seconds) | |
| 24 | Prints the four report paths | |
| 26-31 | Verification | |

Rules:

- Every heavy cell (10-13, 17-20, 24) is wrapped in `if SNAPSHOT_TO_LOAD is None:` and
  prints a one-line skip notice otherwise. Image and report cells always run.
- **Snapshot restore is a pure load.** It reads the rows and `single_scored_pool`,
  converts two-int lists back to tuples, and nothing else: no backfill, no rescoring, no
  re-applied screen. A full run already produces every field. Snapshots exported before
  the exact method (those lacking `_bpp` fields) are not supported. A snapshot without
  `single_scored_pool` still loads; the single report then shows "pool scores not in this
  snapshot; re-run the notebook to produce them".
- Each job is one `base_pair_probabilities` matrix for its state; the `real` / `+A+B` job
  adds two constrained partition functions (`p_on`).
- A cache hit is guaranteed in report cells because those sequences were folded earlier
  through the same `FoldEngine`.
- Cost: at `AND_GRID_N = 20`, 380 ordered pairs x 2 spacer variants (minus excluded pairs),
  each up to `4 + 4*AND_N_FAKES = 44` jobs. Many pairs find fewer than 10 fakes per side;
  the grid cell prints the real job count and total time when it finishes.

## Step 4 — reports

Both reports: HTML written to `var/reports/` with a timestamp in the name
(`single_switch_report_<ts>.html`, `and_report_<ts>.html`), PDF by
`toehold/render_pdf.py` (skipped with a message if the script is not found), `CSV_PATH`
printed on the page, FoldEngine versions and `OPEN_THRESHOLD` in the footer.

**Intro** is built from the parameters, never hand-typed numbers. The AND intro is a bullet
list: Source; Top N singles / pool (cut/keep domains, spacer variants, `AND_REPORT_N`);
Method (exact, temperature); ON; OFF (states, up to `AND_N_FAKES` fakes per side, each
sharing at most `FAKE_MAX_SEQ_OVERLAP_NT` nt of identical sequence with either real trigger); Ratio; Trigger overlap screen. The single intro is one paragraph of the same
content.

**Glossary** is definitions only (no history, no sampling vocabulary): ON / P(duplexes),
OFF, ratio, dG, FAKES, `trigger_bound`, `stem_closed`, `misfolded` (and for AND: footprint
bound, stem still closed, trigger overlap screen, per-hairpin A/B forms; for single:
Spearman rho / Kendall tau-b). Worked examples are computed live from the render's own
first row so they cannot go stale.

**Summary table.** Single: `#`, rank, ON (P(duplexes) over footprint-bound nt), OFF
(leak in the worst OFF state over `off_source` / `off_criterion` and the stem-closed nt there),
ratio, ON-OFF, dG, detail link. AND: `#`, spacer, pair, ON, OFF, ratio, ON-OFF, dG. The
FAKES values (mean nt of `stem_up` still bound to `stem_down` over the fakes, with %; per
side in AND) are in each card, not in the summary. A `--` means not measured, never zero.
A "How to read ON and OFF" paragraph sits above each summary table (ON % is P(duplexes) of
the ON state; OFF % is the share of stem_up open in the worst OFF state, an average share
of nucleotides and not the probability of one event). Domains named `exp_gene` / `opt_exp_gene` are never drawn.

**Candidate card.** A head block of separate lines (rank or pair, trigger length and
sequence, spacer on its own line for AND, ON, OFF with its `off_source` /
`off_criterion` and every term, FAKES, ratio); a "How ON and OFF were computed" block (ON:
designed pairs forced, P(duplexes), cost -RT ln P of forcing them, average footprint nt
bound in the same state; OFF: every OFF state's stem-loosening per scored hairpin and the
state leak, the worst in bold, exempt sides marked); an energy table (`max-width` 420 px, one caption
sentence above it); the per-state table (`table-layout:fixed` with explicit column
widths, or the PDF clips the last columns); layout bar and per-domain sequences; figures
two per row, larger than the single report's, legend below the plot.

- Single per-state table: `alone`, `+real trigger`, `+fake trigger` (mean of the found
  fakes), columns `trigger_bound`, `stem_closed`, `misfolded`, nt hybridised, `P(duplexes)`
  (filled only in the `+real trigger` row).
- AND per-state table: per state, hairpin A and B `bound / closed / misfolded`, plus
  `P(duplexes)` (`p_own_duplex` of that hairpin in `+A` / `+B`, `p_on` in `+A+B`).
- **Plan colouring** (`_plan_class`, colouring only, never scored): for `trigger_bound` of
  hairpin H, HIGH wanted iff H's own trigger is present; for `stem_closed`, LOW wanted iff
  its own trigger is present, else HIGH; `misfolded` LOW everywhere; fake rows count as no
  real trigger. HIGH = value >= `OPEN_THRESHOLD`, LOW = value <= `1 - OPEN_THRESHOLD`;
  a value in between agrees with neither and is red; `None` gets no colour. **`P(duplexes)`
  is coloured too**: HIGH expected in every row that holds a real trigger (+A, +B, +A+B)
  (single: the +real trigger row is not shaded because the single table has no plan colouring).
- **Figures.** Single: OFF and ON structures plus both probability matrices (structures
  through Kozak, a real separate fold; the ON plot draws the trigger in its own colour, and
  its position is a `FoldEngine` `&`-join layout artifact). AND: structures for `alone` and
  `+A+B` only, matrices for `alone`, `+A`, `+B`, `+A+B`; structures are clipped at the end
  of the last kozak domain. The two AND structure plots are inline SVG (`structure_svg`,
  cell 7), full card width, one above the other: every base a circle with its letter, filled
  by domain, backbone and a rung per base pair, same ring and `visible_len` rules as
  `structure_png`; bases are 23 units apart so the canvas grows with the molecule; a layout
  taller than wide is turned 90 degrees to fit a landscape page; height is capped at 640 px
  and the figure is kept on one page when printed. The matrices stay PNG. The displayed
  one-piece switch sequence of every card ends at the Kozak (`Switch sequence through the
  Kozak`); the folded sequence still includes the reporter payload. In the `+A+B` plot the trigger strands are hidden
  (`visible_len`): a base pair whose partner is outside the drawn range gets a dangling
  ring instead of a line, amber (`_PAYLOAD_RING_COLOR`) when the partner is the
  construct's own hidden payload tail (`index < construct_len`), red when it is a hidden
  trigger strand. Matrix crosshairs mark each strand junction in that strand's colour; in
  `+A+B` the order is B (pink) first, then A (blue). Palette: shared teal for `spacer`,
  distinct colours for `loop` and `prefix`.

**Single report only: CSV ranking vs this report's ranking** (between Summary and
Candidates). A scatter of CSV rank (`postgen_global_rank`, x) against rank by this report's
order (y, 1 = best at top) for the **whole scored pool**, report rows highlighted, with
Spearman rho and Kendall tau-b; saved as `csv_vs_report_rank_<ts>.png` with the same
timestamp as the HTML. Ties: the report ranking is the position under `_single_sort_key`
(`ON - OFF` rounded to 1 decimal, then dG); only candidates tied in both get the average
of the positions they span. rho = Pearson correlation of the two average-rank vectors; tau-b =
`(C - D) / sqrt((n0 - n1)(n0 - n2))`. Both vectors are oriented 1 = best, so a positive
value means the CSV order and the report order agree. numpy / pure python only.
A second scatter in the same section ranks the pool by dG alone (more negative = 1) against
the CSV rank, with its own rho and tau-b, saved as `csv_vs_dg_rank_<ts>.png`; it leaves ON
and OFF out entirely.

## Step 5 — limitations to state in the report

- **Strict ON.** `P(duplexes)` requires every designed pair (every complementary position of
  the trigger against its footprint) at once, so it is lower than the probability of any one
  of those pairs; a duplex that is mostly formed but frays at one pair counts only for
  structures that keep all pairs. It is not comparable with `trigger_bound`, which averages
  over the whole footprint including positions the trigger does not cover.
- **Exact quantities only, by necessity.** `FoldEngine.sample_structures` was found to
  contradict `base_pair_probabilities` for some multi-strand complexes (a reproducer is
  written up separately as an issue for the repository owners; more draws do not fix it).
  That is why every number here is a partition-function quantity. `FoldEngine` itself is
  not changed by this report.
- **Strand order is a model constraint** (`both_triggers_extra`), not physics.
- `misfolded` is a structural risk signal, not a measured expression leak.
- The AND grid never scores a pair outside the top `AND_GRID_N` singles, and the single
  order that selects them uses the dG tie-break.
- A fake screen that finds fewer than the requested fakes, or none, says so; an OFF built on
  fewer fakes is less well averaged.
- `OPEN_THRESHOLD` affects colour only; ratios are not comparable with reports from
  earlier designs (see Change log) or with the predecessor notebook's.

## Verification (cells 26-31, kept in the file)

1. **Ranking** (27): single rows sorted by `_single_sort_key`; AND rows by `ON - OFF`
   descending, `None` last.
2. **Trap 1 regression** (28): `trigger_bound` of the `alone` state <= 2% for every single
   and AND report row.
3. **Three-way partition** (29): for the top single's ON state, every footprint position's
   unpaired + external + own-`stem_down` + other-intramolecular probabilities sum to 1, and
   the module's `trigger_bound` and `misfolded` means equal the independently summed ones.
4. **Fake identity rule** (30): for every fake used in the report rows, the longest identity
   run against its real trigger(s) (single: the candidate; AND: both triggers of the pair)
   is asserted `<= FAKE_MAX_SEQ_OVERLAP_NT`; prints the max run observed and the count.
5. **Strand order** (31): for the top AND pair's `+A+B` strand list, both triggers must bind
   their own footprint with mean probability > 0.5; the reversed (A-then-B) order is folded
   and printed for information only.
6. **Joint ON sanity** (32): for the top single and top AND row, `p_on` exists, lies in
   (0, 1], and does not exceed the weakest designed pair it requires (the smallest
   `base_pair_probabilities` entry among its `designed_pairs`), tolerance 1e-6.

## Traps — real mistakes already made on this project. Do not repeat them.

1. **"Open" meaning "paired to anything".** An earlier version read 80-90% "open" with zero
   triggers present, purely from intramolecular misfolding. `trigger_bound` counts pairing
   to an **external strand** only (index >= `n_self`); misfolding is its own metric.
   Verification 2 re-checks this.
2. **Selecting fakes by transcript position.** Position says nothing about sequence
   similarity. Fakes are screened by sequence (identity with the real triggers), never by
   where on the transcript they sit.
3. **Watson-Crick-only complementarity scans.** A real, ViennaRNA-confirmed 12 bp helix
   scored as 4 nt under exact-complement matching because four positions were G·U wobbles.
   A complementarity screen must be able to accept wobbles; the parameter that controls it
   is `WOBBLE_MAX_FRACTION`, used by the AND trigger-vs-trigger screen (not by fakes).
4. **Complementarity alone is the wrong test for "same transcript region".** Two same-
   direction duplicates are not complementary to each other. The trigger-vs-trigger screen
   checks identity runs as well.
5. **Defining OFF within a single state.** `1 - ON` makes the ratio a pure function of ON
   and carries no leak information. OFF is the worst across illegitimate *states*, with
   the own-trigger mask so intended binding is not counted as a leak.
6. **Unmasked OFF terms.** Counting a hairpin's own trigger binding as stem-loosening
   collapses OFF to ~100% for every candidate.
7. **One process pool per job.** Measured 5.8x slower than one call per batch.
8. **`try/except: return 0.0` around a folding call.** `normalize_value(0.0,
   predicted_leakage_spec)` is a perfect score, so a failed measurement outranks every
   correct one and no filter catches it. `None`, always: `p_on`, OFF terms and the ratio
   all propagate `None`.
9. **Assuming instead of measuring.** Every mechanism claim here that was reasoned rather
   than folded turned out wrong at least once. Fold it and read the base pairs.
10. **Two-trigger strand order.** See Step 2, States: `fused&tA&tB` is a pseudoknot and
    trigger B cannot bind (0.00 vs 0.98). Every both-trigger state must use
    `both_triggers_extra`.
11. **Reading a joint event from marginals.** The product of per-side bound means (0.75-0.98
    on the top AND pairs) is not the probability that both duplexes exist (0.32-0.69).
    Use `constrained_probability`.
12. **Never use sampled marginals** (`sample_structures`) for per-hairpin fractions or
    joint events on multi-strand complexes; see Step 5.
13. **A forced pair ViennaRNA cannot place reads as P = 1.0.** `constrained_probability`
    checks that the constrained MFE actually contains every pair and returns `None`
    otherwise; keep that check.
14. **`<colgroup>` without `table-layout:fixed`** silently clips the last columns in the
    static PDF render.

## Change log (condensed; the body above is current)

- **2026-10-07 — OFF, ranking, ON definition, report layout.** OFF is now the worst state's
  stem opening only (`1 - mean_stem_closed` per scored hairpin; the trigger-binding term left
  OFF and stays in the decomposition tables), in both reports. Both lists are ranked by
  `ON - OFF` (single: with dG ties); the ratio is shown but orders nothing. ON's designed
  pairs come from the sequence design (`binding.alignment_pairs`: every complementary
  position of the trigger against its footprint), not from the MFE; `+A` / `+B` also show
  `p_own_duplex`. `FoldEngine.constrained_probability` uses `FoldEngine.rt` and clamps a
  result a single-precision ulp above 1 (both taken from Offer's branch). Cards gained the
  "How ON and OFF were computed" block and the FAKES line; the summary lost its FAKES column
  and gained a "How to read" paragraph. AND structure plots are lettered SVG. A second CSV
  correlation plot (CSV rank against dG rank) was added. Tested and not used: product of the
  per-pair probabilities (it is a lower bound on `P(duplexes)`, far below it for long
  duplexes) and `hc_add_bp` with no context as a forbid-pair constraint (it removed both
  bases from pairing, so it does not give 1 - bpp for a single pair).
- **2026-10-04 — original build.** Boltzmann sampling (1200 samples/state), ON = sampled
  P(both open) at an `OPEN_THRESHOLD` 0.70, OFF floored at 1/1200 with a `>=1200` bound,
  k-of-N tables. All AND values from that period were computed under the wrong strand
  order and must not be compared with new runs.
- **2026-10-05 — fix round.** `_kofn_pct` printed a continuous mean next to `k/N` (a real
  cell read "6/1200 (29.3%)" where 6/1200 = 0.5%); exact `n_both_open` etc. returned by
  workers; unique-structure column added; `loop`/`prefix`/`spacer` palette fixes;
  `exp_gene` dropped from drawn layouts; explanatory row when a single has zero qualifying
  fakes; "82% bound but 4/1200 both open" confusion explained as a joint event.
- **2026-10-05, round 3 — OFF broadened.** OFF previously used trigger-binding only, blind
  to a loose stem when nothing was present to bind (rank 72: OFF 0.0% / ratio 100.0 became
  OFF 11.1% / ratio 8.3). Found while building it: a state's acting side must be exempt
  from its own stem-loosening term (`mask_side`), else every state with a real trigger
  reads ~100% badness. AND OFF values moved to near 100% for nearly every candidate under
  the sampled method (e.g. 56+63 `+A` stem_closed_B 0/1200). Cross-domain binding
  diagnostic and its workers removed. Trigger-hidden `+A+B` plot added.
- **2026-10-05, round 4 — trigger-vs-trigger screen.** The AND grid never compared a
  pair's own two triggers. Top candidate 56+63 had triggers sharing a 27 nt identical
  substring (A, 30 nt `UUACCCCCUCAUUGUUUAUUAACAAAUUAU`; B, 33 nt
  `UCUAGAUUACCCCCUCAUUGUUUAUUAACAAAU`), complementary run 9 nt. Screen added (3/20 report
  rows excluded). Amber vs red dangling rings: kozak(B) folding onto the construct's own
  hidden payload tail is correct, not a bug. Summary-row OFF breakdown reverted (too much
  text).
- **2026-10-05, round 5 — identity check.** Round 4 checked complementarity only; 11+55 had
  B as a literal 27/27 nt same-direction prefix of A (30 nt `ACGAGAAGCCAACGUGUAAAGCUGUGACAU`
  vs 27 nt `ACGAGAAGCCAACGUGUAAAGCUGUGA`) with a complementary run of only 6 nt and passed.
  `_longest_identity_run` added; 5/20 rows now excluded; new top-5 were 4+6, 4+7, 4+9,
  4+11, 4+12 (all `no_spacer`).
- **2026-10-05 — exact means for the three metrics.** `sample_structures` disagreed with
  `base_pair_probabilities` (pair 141+7 spacer, `+A`: exact stem_up_B to stem_down_B ~0.99,
  sampled stem_closed_B 7.1%). `_exact_decomp_means` introduced; stem-loosening OFF term
  moved to exact; trigger-binding and ON stayed sampled until the next entry.
- **2026-10-05 — CSV vs report ranking.** `single_scored_pool` added to the snapshot; rank
  correlation section and PNG added. The single order became (rounded ratio, dG): ratios
  tie often (OFF = 0 gives ratio = ON%), and the dG tie-break now also decides which
  singles enter the AND grid.
- **2026-10-06 — fake rule clarified.** The old fake screen (complementary run against the
  footprint, strictly below the real trigger's own run) never found fakes for AND pairs: the
  real trigger's own run is 4-7 nt by that metric while pool candidates share 4-11 nt
  complementary runs with any footprint by chance, so every AND row had zero fakes. User
  rule: a fake must not share more than 8 nt of sequence (identity) with the real trigger(s).
  `pick_fake_trigger` added (identity vs every real trigger; AND: both); the report cells,
  texts and verification 4 follow it. `WOBBLE_MAX_FRACTION` now serves only the AND
  trigger-vs-trigger complementarity screen. `pick_fake_design` unchanged for other notebooks.
- **2026-10-06 — strand order and restore.** Two-trigger states were folded `fused&tA&tB`.
  Measured on 4+6 no_spacer: trigger B to footprint B 0.00 vs 0.98 in `fused&tB&tA`; MFE
  -70.8 vs -88.2 kcal/mol. `both_triggers_extra` introduced as the one place deciding
  order. Snapshot restore became a pure load (no backfill or rescoring; old snapshots
  unsupported). AND report layout round: bullet intro from parameters, definitions-only
  glossary, split ON/OFF cells, green/red plan colouring, larger 2-per-row figures.
- **2026-10-06 — sampling removed.** `FoldEngine.sample_structures` (pbacktrack) is
  unreliable on these complexes and more draws do not fix it. For the top AND pairs sampled
  "both open" was about 0.3-1% while the exact probability that both designed duplexes are
  present was 0.32-0.69 (product of exact per-side bound means 0.75-0.98).
  `FoldEngine.constrained_probability` added (agrees with `base_pair_probabilities` to ~3e-6
  for one pair). ON became the exact constrained probability; every OFF term exact;
  `N_SAMPLES`, `frac_open` / `frac_both_open`, k-of-N and unique-structure counts, and the
  `>=1200` notation removed; `OPEN_THRESHOLD` demoted to colouring only. The cost per job
  fell to one partition function per state (`+real` / `+A+B` adds one MFE and two
  constrained partition functions) instead of 1200 backtracks. ViennaRNA 2.7.2
  reproducer written up separately: one pair 0.996 exact vs 0.000 sampled. The sampled
  `SingleDecompJob` / `_single_decomp_worker` stay in the module because
  `toehold_context_report.ipynb` uses them.
- **2026-10-06 — cleanup, output unchanged.** Dead code and history comments removed from
  the notebook and both modules; duplicated logic moved to one helper each
  (`pick_fake_triggers`, `and_pair_jobs`, `_mean_or_none`, `_on_off_ratio`, `_render_pdf`);
  AND structure plots for `+A` and `+B` (never displayed) no longer built; the pointer cell
  and the tautological "fake counts independent" verification removed (cells and
  verification numbers above are the new ones); AND grid now counts `fuse()` failures
  instead of skipping them silently. A smoke run (`SINGLE_POOL_N=14`, `AND_GRID_N=6`)
  before and after gave identical `single_report_rows`, `and_report_rows` and
  `single_scored_pool` (8464 numbers, max difference 0).
- **2026-10-06 — ratio floor.** The ratio became `ON% / max(OFF%, OFF_FLOOR_PCT)` instead of
  `ON% / (1 + OFF%)`. With OFF mostly 0.3-4%, the old `+1` shrank every ratio by a similar
  factor and hid the OFF differences below 1%; the floor treats those as equal and marked `*`.
  Ratios tie more often (ratio = ON% whenever OFF < 1%), so the dG tie-break decides more of the
  single order. Needs a new full run: ranking, the AND pool and the top-20 lists all change.
