# What the full stage-1 sweep showed

Measured 2026-09-20 on the completed stage-1 sweep: **1,491,840 designs**, 1,036 trigger
pairs, 4 secondary stems per pair, 360 axis points per stem. No gaps — every pair yielded
exactly 4 stems and every pair-stem exactly 360 rows.

Reproduce any number here with
`uv run python src/engine/gates/notebooks/toehold_and/sweep_analysis.py`, or query it
directly with `--sql "..."` against a view named `sweep`.

**Nothing in this file is a performance result.** Stage 1 folds no switches: there is no
`p_open`, no `separation`, no `A_M`, no state resolution. These are facts about the design
space we enumerated and about the cheap screens, and their only job is to decide how stage 2
should spend its folding budget.

---

## 1. The stage-2 selection, as written, discards the sweep

`_fold` takes the strongest `lock_energy` per closure arm. That is the right *metric* —
`lock_energy` is the strongest single predictor we have, rho −0.938 against locked(10) — and
the wrong *shape*, because `lock_energy` is a property of the **pair-stem**, not of the
design. All 360 axis points of a pair-stem carry the same value.

The consequence, emulating the heap's exact tie-break (equal locks keep the earlier row):

| `--fold` | designs folded | **trigger pairs covered** | pair-stems | inside grip window |
|---|---|---|---|---|
| 400 | 396 | **2** of 1036 | 2 | 18.2% |
| 1,000 | 996 | 3 | 3 | 24.7% |
| 5,000 | 4,998 | 13 | 14 | 31.2% |
| 10,000 | 9,996 | 23 | 28 | 28.1% |
| 50,000 | 49,998 | 76 | 139 | 30.9% |

`--fold 400` folds **two trigger pairs**. Even 50,000 folds — about 22 hours — reaches 76 of
1,036. We swept 1,036 pairs and would have measured 2.

The cause is degeneracy: `lock_energy` takes only **195 distinct values** across 1.49 M rows,
spanning −35.20 to −10.60, and the median value is shared by **6,840 rows**. "Top 66 per
closure" is therefore a slice of one tie group, not a ranking.

It is also counter-productive on the one necessary condition we can check cheaply: the
strongest-lock selection lands inside the grip window **18.2%** of the time against **28.9%**
for the sweep as a whole. Selecting on lock actively anti-selects for eligibility.

---

## 2. The four axes split into two groups, and the split is total

Medians over all 1,491,840 rows:

| axis | `lock_energy` | `stem_dG` | `grip_alone` | `grip_with_x` | inside window |
|---|---|---|---|---|---|
| **closure** — all 6 levels | −25.2 | −24.2 | −26.4 | −37.8 | 28.9% each |
| **lower3** — all 6 levels | −25.2 | −24.2 | −26.4 | −37.8 | 28.9% each |
| upper3 `trigger_derived` | −25.2 | −26.3 | −31.2 | −42.4 | 17.4% |
| upper3 `WSW_AGA` | −25.2 | −25.0 | −26.4 | −37.6 | 33.9% |
| upper3 `WWS_AUG` | −25.2 | −24.2 | −25.4 | −36.4 | **37.0%** |
| upper3 `WWW_AUA` | −25.2 | −22.9 | −25.7 | −36.7 | 24.4% |
| upper3 `WWW_UAU` | −25.2 | −22.9 | −25.0 | −36.2 | 31.7% |
| island `trigger_derived` | −25.2 | −26.0 | −31.3 | −42.6 | **6.6%** |
| island `WWW` | −25.2 | −22.3 | −22.1 | −33.3 | **51.2%** |

**`closure` and `lower3` are invisible to every cheap metric** — identical to the decimal
across all six levels, and identical window membership. That is the design working as
intended (neither reaches `main_z`), but it has a hard consequence: **no cheap screen will
ever separate them, so stage 2 is the only instrument we have for those two axes.**

This is consistent with the best result measured so far being a closure effect —
`aug_closed_au` (`UAU`), separation 6.90 — which stage 1 is structurally blind to.

`island` is close to a switch: `WWW` is **8× more likely** to land inside the grip window
than `trigger_derived` (51.2% vs 6.6%). `upper3` spans 17.4% to 37.0%.

---

## 3. The grip window: which half is doing the work

A thermodynamic AND needs `grip_with_x < stem_dG < grip_alone` — trigger A loses to the stem
alone and wins only once trigger B has freed `sw_xs`.

| condition | designs | share |
|---|---|---|
| `grip_with_x < stem_dG` (A wins with x) | 1,488,672 | **99.8%** |
| `grip_alone > stem_dG` (A loses alone) | 433,872 | **29.1%** |
| both — the full window | 430,704 | 28.9% |

**Only the second half discriminates.** `grip_with_x < stem_dG` is satisfied by essentially
everything and carries no information; the state-10 leak condition is the whole filter.

Coverage of the eligible set is wide, so restricting to it costs little breadth:

* **795 of 1,036** trigger pairs have at least one design inside the window
* **3,180 of 4,144** pair-stems have at least one

Standing caveat, unchanged: the window is **necessary and measured to be insufficient** —
40 variants spread from 0.1 to 10.7 kcal/mol inside it all returned `separation` 0.00. Use it
to screen, never to rank.

---

## 4. Only two schemes survive, and they differ where it matters

| scheme | designs | share | median `lock_energy` | median `a_site_energy` | median `b_site_energy` |
|---|---|---|---|---|---|
| `B-anchored` | 919,080 | 61.6% | −25.5 | **−7.3** | −26.2 |
| `mixed` | 572,760 | 38.4% | −24.6 | **−12.5** | −25.4 |

The locks are comparable; the **A-site differs by 5.2 kcal/mol**. Given the standing
requirement that A-binding be rewarded only *after* B binds, scheme is a real lever and
stage 2 should carry both rather than letting one dominate by count.

---

## 5. Redundant metrics

Pearson over all rows. Two metrics near ±1 carry one fact, so a Pareto front over both is a
front over one.

| A | B | r |
|---|---|---|
| `lock_energy` | `b_site_energy` | **0.973** |
| `grip_alone` | `grip_with_x` | **0.934** |
| `gc_bottom3` | `gc_gradient` | 0.737 |
| `gc_top3` | `gc_gradient` | −0.723 |
| `stem_dG` | `grip_alone` | 0.708 |

The §3b pair-level Pareto front over (lock, a_site, b_site) is effectively over
**(lock, a_site)**: at r = 0.973 the two share r² = 94.7% of their variance, so `b_site`
contributes about **5.2%** that `lock_energy` does not already carry.

---

## 6. `ddg_pref = 0` is legitimate, not the sentinel bug

453,960 rows (30.4%) have `ddg_pref` **exactly** 0.0, which is the signature the plan warns
about: ViennaRNA returns `100000.0` rather than raising, and `100000 − 100000 = 0.00` passes
`ddG_pref ≥ 0` for every build. Checked, and it is not that:

* `b_site_energy` is fully varied in both groups — 162 distinct values where `ddg_pref = 0`,
  177 where it is positive, same −35.2 range
* **no** energy anywhere in the sweep is at or above the 1e4 guard, and there are no nulls
* the zero rate tracks scheme (39.6% of `B-anchored`, 15.7% of `mixed`), which is what you
  expect when `secondaryZ` and `k2` coincide and the difference is exactly zero

`ddg_pref` spans 0.0 to 6.6. The guard in `fixed_alignment_energy` is doing its job.

---

## 7. What this implies for stage 2

The space factorises into two orthogonal dimensions:

* **pair-stem** (4,144) — sets `lock_energy`, `a_site_energy`, `scheme`
* **axes** (360) — sets `stem_dG`, the grip energies, window membership

The axes do not move `lock_energy` at all, and `closure`/`lower3` do not move anything cheap.
So **any top-N selection on a single metric collapses one dimension entirely**, which is
exactly what §1 measured. Two blocks instead:

**Block A — axis resolution.** ~10 pair-stems, stratified across the `lock_energy` range and
both schemes and restricted to the 3,180 pair-stems with a design inside the window, crossed
with **all 360 axes**. ~3,600 folds, ~1.6 h. The only instrument that can resolve `closure`
and `lower3`.

**Block B — trigger breadth.** ~1,036 pair-stems, one per pair, crossed with the two or three
reference axis settings Block A identifies. ~2,000–3,000 folds, ~1 h. The only way to learn
whether an axis finding generalises across triggers.

Block A runs first, because it is what chooses Block B's fixed axes — and nothing in stage 1
can choose them for us.

**Not in this sweep.** `toehold_trim`, `rbs_loop_len` and `secondary_arm` are recorded as
constant columns, not axes; sweeping them needs an `assemble()` change. `a = 0` is fixed by
instruction.

---

## Appendix: the analysis path

`sweep_cheap.csv` is 690 MB and stays the stage-2 input, untouched. `--build` derives
`sweep_analysis.parquet` — the same 1,491,840 rows minus the 161-nt `switch` column, at
**485 KB**, a 1,423× reduction because each pair-stem's 360 rows share most column values.
Validated against the CSV on row count, distinct counts, and exact sums of `lock_energy`,
`stem_dG`, `grip_with_x` and `gc_balance`. The full report runs in **1.4 s**.
