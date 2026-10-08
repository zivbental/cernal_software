# Findings register — every measured number, and what reproduces it

One row per finding: the number, the file that holds its reasoning, and the command that
reproduces it. This exists so a finding survives a context reset, a new contributor or a different
agent: the reasoning lives in docstrings beside the code, and this is the index into them.

**Rules for this file.** A row is added only when the number has been measured and the reproduction
command has been run. Where a later measurement contradicts an earlier one, both rows stay and the
later one says so — a register that quietly overwrites its own history is worse than none. `n` is
quoted beside every rate, because a rate over seven cells and a rate over three hundred are not the
same claim.

**Scope note.** *E. coli* and PFAS are the **use case**, not the platform. Findings below are
labelled by the dataset they were measured on, and **no metric in this work has held its sign
across datasets** — see `no-metric-holds-sign` below before carrying any of them over.

---

## How to read the dataset column

| label | what it means |
|---|---|
| **mCherry** | the A0 sweep: both trigger windows are segments of one 711-nt mCherry transcript |
| **PFAS** | the real target: windows in two different endogenous *E. coli* mRNAs (`ggt`, `fadB`, `astC`, `aldA`) |
| **Green 168** | Green et al. 2014's built-and-measured one-input switches — external ground truth |
| **Kim** | Kim et al. 2019's four AND constructs |

---

## The architecture and what it rests on

| finding | number | dataset | reasoning lives in | reproduce |
|---|---|---|---|---|
| State 10 is the only leak that matters | leakiest OFF state in **400 of 400** designs | mCherry | `docs/igem-model-page.md` §Architecture | — |
| A 4-nt minimum overlap is what makes endogenous triggers findable | **53,530** trigger pairs over 3 gene pairs; **73.1%** are exactly `len_x` 4 (17,977 of 24,597 on ggt×fadB) | PFAS | `toehold.find_cross_gene_pairs` | `uv run python tools/pair_budget_on_pfas.py` |
| Trigger footprints are a constant size whatever the overlap | A 36 nt / B 50 nt naive; A 35 / B 49 Kim | both | `_CrossGenePair.window_a/window_b` | `uv run python src/engine/gates/notebooks/toehold_and/review/step2_switch_construction.py` |
| The two geometries differ in the **secondary** arm, not the main one | `ARM_LEN` 18 in both; `SECONDARY_ARM_LEN` 20 (Kim) vs 18 (naive); switch 165 vs 161 nt | both | `ToeholdAndGate.geometry_name` | as above |
| 33 of a 161-nt switch are gene bases nothing downstream can edit | `sw_x` 13 + `secondary_z` 5 + `main_z` 6 + `main_pre` 9 | PFAS | `review/step2_switch_construction.py` | as above |

## Gaps found by reading the code, not by measuring

| gap | what it is | consequence |
|---|---|---|
| **No partner-aware `x*` measure exists in the engine** | `A_S_00/01/10/11` are `_mean_unpaired` — **open or closed, partner-blind**. The partner-specific terms (`xstar_locked`, `free_xstar`, `xstar_engA`) live only in the notebook (`drift_fold.py`, `full_sweep.py`, `candidates.py`) and never came across | τ6 (`A_S_11 > 0.5`) passes a design whose `x*` is open but **not bound to trigger A** — refolded elsewhere. That is the exact failure `open_penalty`'s own docstring warns about, and the engine cannot see it |
| **`free_xstar_01` is a declared column with 0 of 346,528 values** | I listed it in `characterise_axes.FIELDS`; `measure_design` never returns it | a header that promises a measurement and delivers an empty cell, which reads as "measured, came back None". Worse than an absent column |
| **`A_M_*` includes the AUG; `open_*` excludes it** | `A_M = (main_z[0], main_pre[1])` is one contiguous span, so it covers `main_z → aug → main_pre`. `main_stem_arms = (main_z, main_pre)` is two spans with the bulge left out, on purpose | two measures both called "the main stem" over different regions, with nothing saying so. Same trap as `open_11` vs `dG_open_11`. **Both choices are right for their own purpose** — recommendation is to document, not to change, since changing either moves every stored number |

## The competition at `x*` — the clearest result this work has

| finding | number | dataset | reasoning lives in | reproduce |
|---|---|---|---|---|
| **Trigger A's `x` is sequence-identical to the switch's own `sw_x`** | **1,344 of 1,344 designs**, and structurally: `assemble` writes `("sw_x", x)` and `("sw_xs", revcomp(x))`, paired at line 1477 | PFAS | `toehold.assemble` lines 1366/1370/1477 | `uv run python tools/xstar_competition.py` |
| So A has **no energetic advantage at `x*`** — it offers the duplex the hairpin already has | the fold charges **6.06** kcal/mol to free `x*`; A offers **2.00** | PFAS | `tools/xstar_competition.py` | as above |
| The competition margin, length-cancelled | `median -4.36` (Q1 −5.82, Q3 −1.61, min −6.93, **max +2.66**); positive in 256 of 1,344 (19.0%) | PFAS | as above | as above |
| **Our maximum is below Kim's working construct** | ours **+2.66** against his **+3.86**; his two non-gating ones are −1.32 and −5.61 | PFAS vs Kim | `tools/kim_competition.py` | `uv run python tools/kim_competition.py` |
| Kim's `hold` is nearly constant while burial doubles | 9.41, 10.52, 10.54 kcal/mol at 5, 8, 11 nt buried — so the hold is a fold cost, not a length | Kim | as above | as above |
| But his series **cannot calibrate the axis** | burial and his primary-hairpin toehold sum to 15 nt by construction, so they move together in opposite directions | Kim | as above | — |
| And equilibrium fails on his own working gate | margin **+3.86** says A should strip the secondary hairpin unaided, which is a state-10 leak, yet it gates cleanly | Kim | `kim2019_comparison.md` | — |
| ⚠ **A superseded number.** `\|lock_energy\| − hold` is **+8.52** median on the same designs — ~13 kcal/mol from the true margin and the opposite sign | an earlier turn reported "+10.70, far past Kim's +3.86, too generous to A". Wrong twice: we are too **stingy** | PFAS | `tools/xstar_competition.py` docstring | as above |
| The lever it exposes | `sw_x` need not be `x`; weakening it lowers `hold` without touching `grip`, which is the asymmetry Kim's different sequences give him free. Closing 8 kcal/mol needs several substitutions, so parity may be unreachable | — | as above | not yet measured |

## The secondary stem — the axis the claim rests on and nothing ranks

| finding | number | dataset | reasoning lives in | reproduce |
|---|---|---|---|---|
| `secondary_stems` returns a **Pareto front**, not a candidate list | non-dominated over `(lock_energy, a_site_energy, b_site_energy)` | — | `toehold._pareto_front`, `_select_stems` | — |
| A pair offers far more stems than assumed | offered: median **95**, mean 101.6, sd 49.1, max 297, min 10 (n=404 pairs) | PFAS | `tools/stem_census_on_pfas.py` | `uv run python tools/stem_census_on_pfas.py` |
| …of which usable (B-anchored/mixed, `lock_energy ≤ 0`) | median **82**, mean 89.4, sd 44.3, max 268 | PFAS | as above | as above |
| `stems_per_pair = 2` keeps **2.2%** of them, and every pair has more than two | 404 of 404 | PFAS | `generate_designs`' comment at the stem sort | as above |
| The cut is arbitrary in the quantity it sorts on | best **dropped** stem is median **0.40** kcal/mol behind the last kept (mean 0.64, max 3.90) | PFAS | as above | as above |
| Scheme split over every stem offered | mixed **77.4%**, B-anchored 13.9%, A-anchored 8.2%, unlocked 0.6% | PFAS | as above | as above |
| `lock_energy` is the secondary hairpin's own stem dG, cap included | negative = a duplex forms, hence the `≤ 0` filter | — | `_SecondaryStem.lock_energy` docstring | — |
| `a_site_energy` is **trigger A's binding to the secondary arm**, kcal/mol | carried on every design; **nothing ranks on it** | — | `_SecondaryStem.a_site_energy` docstring | — |
| Three measures of A's grip exist and none is ranked | `a_site_energy`, `lock_minus_a_site`, and `x_mech`'s `xstar_engA_11` | — | same, plus `full_sweep.py` `x_mech` | — |
| Carrying every usable stem is infeasible | **612M** designs over all PFAS pairs = **354 days** on six cores | PFAS | `tools/stem_census_on_pfas.py` | as above |

## Survival through the filters — and why every win-rate is conditioned on it

| finding | number | dataset | reasoning lives in | reproduce |
|---|---|---|---|---|
| `feasible()` is **sixteen** tests, not one | the ON ceiling, dead schemes, and floors on `aug_11`, `lock`, `lock01`, off-target, `hairpin_worst`, `engages_stem_mfe`, `engaged_arm_11`, `l_local`, out-of-frame AUG, drift cover, `lower3` keep/grip, closure drop, rare codons | — | `objective_panel.feasible` | `uv run python tools/attribute_survival.py` |
| The **ON ceiling dominates** every level's losses | 57–90% of each upper3 level's rejections | mCherry | `tools/attribute_survival.py` | as above |
| The all-weak upper3 overrides survive the ON ceiling best — as intended | lost to the ceiling: `WWW_UAU` **56.9%**, `WWW_AUA` 57.9%, `trigger_derived` 76.3%, `WWS_AUG` 81.5%, `WSW_AGA` 89.6% | mCherry | as above | as above |
| `WWW_AUA` creates out-of-frame AUGs **17×** more often than `WWW_UAU` | 5.2% vs 0.3% of rows rejected for it | mCherry | as above | as above |
| Overall survival through `feasible()` differs up to **37×** between levels | `open_3x3` 7.5%, `closed_CAU` 0.2%, `WSS` lower3 **0 of 7,208** | mCherry | as above | as above |
| So every lift/win-rate so far is **selection on the dependent variable** | it can say "among designs that already open, which level wins" and no more | mCherry | `review/axis_effects_on_objectives.py` docstring | — |
| The ON ceiling is externally calibrated and should stay | Green's 168 have median ON cost **3.64**; the 77 above 20-fold ON/OFF, **3.07**; so 4.0 admits designs no costlier than a switch known to work. An earlier version used **our** median, 8.0, and admitted a design 97% paired in the ON state | Green 168 | `objective_energy.ON_CEILING` docstring | — |
| Designs passing the ceiling | **12.9%** on PFAS, 19.2% quoted on mCherry | both | `tools/characterise_axes.py` | `tools\axes_status.cmd` |

## Which design decisions move the objectives — single-axis, mCherry only

Read these **with the survival caveat above**: they describe designs that already pass the funnel.
Lift is win-rate ÷ chance within a (pair, geometry) cell; gap is the median distance to the cell's
best when the level loses. `review/one_cell_worked_example.py` prints one cell in full.

| axis level | IED gain | A_M ratio | opening SEP | reading |
|---|---|---|---|---|
| scheme B-anchored / mixed | 1.20 / 0.80 | 1.11 / 0.89 | 0.91 / 1.09 | **gap 0.000 both ways on all three** — the arms cannot see this axis |
| closure `open_3x3` | 0.41 | **2.23** | 0.37 (gap 3.50) | each arm has a different champion |
| closure `closed_UAU` | 0.38 | 0.19 (gap **23.4**) | **1.92** | so closures cannot be cut |
| closure `pair1_CCC` | **1.48** | 0.74 | 1.05 | |
| upper3 `WWW_UAU` | 0.91 | **1.26** | **1.13** | UAU over AUA |
| upper3 `WWW_AUA` | 1.02 | 0.69 | 0.85 | at or below chance on all three |
| lower3 `wobble_GU` | **1.57** | 0.90 | **1.79** | complementary — |
| lower3 `trigger_derived` | 0.49 | **1.80** | 0.57 (gap 2.52) | keep both |
| geometry Kim / naive | 0.94 / 1.06 | 1.15 / 0.85 | **1.35** / 0.65 | Kim takes SEP, near-tied elsewhere |

Reproduce: `uv run python src/engine/gates/notebooks/toehold_and/review/axis_effects_on_objectives.py`

**Only 6 of 16 closures ever reached a scored population.** The ten absent ones are the systematic
ladder `d2_*`/`d1_*`/`d0_*` (mismatch count × GC count) — where a non-monotonic optimum would live.

## Open contradictions, kept rather than resolved by assertion

| the two claims | status |
|---|---|
| "`closed_*` holds 89 of the top 100 by A_M ratio" vs "`open_3x3` wins most cells at lift 2.23" | **Both true.** `closed_*` survives at 0.2–0.6% against `open_3x3`'s 7.5%, so its survivors are an extreme tail. Simpson's-paradox-shaped, and the mechanism is survival |
| `a_site_energy` is the architecture's central mechanism vs the scheme axis shows lift≈1, gap 0.000 | **Unresolved.** Either the mechanism does not matter, or the three arms do not measure it. The scheme axis was measured on data already cut to 2 stems **by `lock_energy`**, so it could not have seen it |
| Kim's constructs read as leaking in state 10 although they work | **Unresolved.** Equilibrium metrics on a kinetic gate. Kim's four constructs are a null test — trigger B moves `A_M` by 1e-13 — so they cannot calibrate a ranking; the open question is whether `a_site_energy` and `x_mech` separate them |

<a id="no-metric-holds-sign"></a>
## Cross-dataset warnings

| warning | number |
|---|---|
| **No metric holds its sign across datasets** | `A_M_ratio` +0.306 on Green 168, −0.016 on VISTA; three metrics flip |
| VISTA inverts and window matching does not explain it | all five objectives negative there |
| VISTA's Table 6 is not reproducible | use their Tables 4/5 as data, never Table 6 as a target |
| Green's correlation with our arms is real but modest | ρ ≈ +0.3 for IED and A_M; f5 +0.366, f2 +0.306, f4 +0.213, Barrier +0.179, f1 **−0.107** |
| The bundled transcripts are **CDS only** | no UTRs, no operon context, so accessibility is folded on an incomplete molecule |

## Method notes that cost time to learn

| note | why |
|---|---|
| Compare variants **per trigger pair**, never per row | a cell fixes the transcript and both windows, so the axis is the only variable |
| Report mean, sd, max beside every median | median-only let one finding be argued both ways |
| Print `n` beside every rate | 0 of 6 became 22.6% over 470 |
| The first items of a sorted list are not representative | sample every Nth instead |
| A filter cannot set its own threshold | `l_green`'s min came back at 0.4838 against its own 0.483 floor |
| Rebuild aggregates the way production does | a two-term scratch copy moved f4 by +0.139 |
| Coordinates are 0-based, **end exclusive** | I read a window `end` as inclusive and 940 of 941 checks failed |
| Measure, don't estimate | five runtime estimates were wrong; `secondary_stems` alone was ~60× slower than assumed |
