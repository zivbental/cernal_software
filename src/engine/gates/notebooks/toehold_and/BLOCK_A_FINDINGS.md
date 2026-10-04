# Block A: what folding the axes actually showed

Measured 2026-09-20 on **3,600 folded designs** — 10 pair-stems × all 360 axis points, all
four tubes each, no duplicates and nothing unmeasurable. Reproduce with
`uv run python src/engine/gates/notebooks/toehold_and/fold_analysis.py`.

Block A existed to resolve `closure` and `lower3`, which stage 1 is structurally blind to
(SWEEP_FINDINGS.md §2). It did, and the answer is not the one the joint `separation` implied.

---

## 1. `separation` carries no information about whether the switch opens

Over all 3,600 designs:

| A | B | r |
|---|---|---|
| `mean_separation` | `A_M_gain` | **0.932** |
| `mean_separation` | `A_M(11)` | 0.773 |
| `A_M_gain` | `A_M(11)` | 0.768 |
| `mean_separation` | `separation` | **0.159** |
| `separation` | `A_M(11)` | **−0.063** |
| `separation` | `log10_rate_advantage` | −0.041 |

**The joint `separation` is orthogonal to everything else we measure**, including — decisively
— to `A_M(11)`, the ON-state availability of the RBS/AUG region. A design's `separation` tells
you nothing about whether it turns on.

And the "three ranking statistics" are really **two**: `mean_separation` and `A_M_gain`
correlate 0.932, so they carry one fact between them. `separation` carries the other.

This is what `SELECTION_SPEC.md` §1 already required — arm E ranks on `mean_separation` — and
the code had been ranking on `separation` until 2026-09-20. The measurement now shows what
that cost.

## 2. The mechanism: a large `separation` usually means "shut in all four states"

Medians per closure, all 3,600 designs:

| closure | A_M(00) | A_M(01) | A_M(10) | **A_M(11)** | `separation` |
|---|---|---|---|---|---|
| `open_3x3` | 0.122 | 0.118 | 0.147 | **0.365** | 2.47 |
| `pair1_CCC` | 0.123 | 0.119 | 0.123 | **0.137** | 4.20 |
| `pair2_CCU` | 0.069 | 0.064 | 0.069 | **0.072** | 5.19 |
| `closed_UAU` | 0.011 | 0.007 | 0.012 | **0.011** | 5.44 |
| `closed_CGU` | 0.011 | 0.007 | 0.012 | **0.011** | 5.35 |
| `closed_CAU` | 0.011 | 0.006 | 0.012 | **0.011** | 5.57 |

The three fully-closed variants sit at `A_M ≈ 0.011` **in all four states**, with
`P_open(11)` around 2×10⁻¹³. They are shut whether or not both triggers are present. Their
`separation` of 5.4–5.6 is the difference between two dead states.

**Only 15.6% of the 3,600 designs open at all** (`A_M(11) > 0.3`); 6.9% clear 0.5 and 0.2%
clear 0.7.

## 3. Every axis shows the same ON/OFF trade, in the same direction

For each axis, two views: *paired* (pair-stem and the other three axes held fixed — the
comparison that controls for which pair-stems landed where), and *conditional on opening*.

| axis | paired winner, all designs | winner among designs that open |
|---|---|---|
| `closure` | **`open_3x3`** 392 of 600 | **`closed_CAU`** 0.261 vs `open_3x3` 0.109 |
| `lower3` | **`trigger_derived`** 374 of 600 | **`SSS`** 0.166 vs `trigger_derived` 0.120 |
| `upper3` | **`trigger_derived`** 305 of 720 | **`WWW_AUA`** 0.174 vs `trigger_derived` 0.142 |
| `island` | **`trigger_derived`** 1154 of 1800 | `WWW` 0.144 vs `trigger_derived` 0.138 |

One shape, four times: **every designed modification improves separation among the designs
that still open, and reduces how many of them open.** `closed_CAU` reaches the best
conditional `mean_separation` of any closure (0.261) on **7 designs of 600**; `open_3x3`
reaches 0.109 on 341.

This is not "the modifications are wrong". It is a dose problem: they are being applied at a
strength the main hairpin cannot afford, to pair-stems that cannot afford them. Which
pair-stems can is the question Block B exists to answer.

`lower3` deserves a specific note. Unconditionally, leaving it trigger-derived wins 374 of
600 paired comparisons and gives 198 opening designs against 48–100 for the designed
alternatives. Conditionally, `SSS` — three G·C, the *strongest* option — is best. Green's
"2 of 3 G·C is optimal" is a statement about a target, and both halves of our result are
consistent with overshooting it in one direction and undershooting in the other.

## 4. The designs that both open and separate

Top 12 by `mean_separation` among designs with `A_M(11) > 0.3`. **They come from only 3
distinct pair-stems**, so read this as a description of those three, not of the axes:

| closure | upper3 | lower3 | island | scheme | x@ | stem | mean_sep | A_M_gain | A_M(11) | joint_sep | log10 kin |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `pair1_CCC` | `WWW_AUA` | trigger | trigger | mixed | 237 | 0 | **0.329** | 0.653 | **0.782** | 2.61 | 0.22 |
| `closed_CGU` | `WWW_AUA` | trigger | trigger | B-anch | 116 | 0 | 0.326 | 0.564 | 0.595 | 8.60 | **3.11** |
| `closed_CGU` | `WWW_UAU` | trigger | trigger | B-anch | 116 | 0 | 0.323 | 0.527 | 0.557 | **11.53** | **3.11** |
| `closed_CGU` | trigger | trigger | trigger | B-anch | 116 | 0 | 0.322 | 0.565 | 0.590 | 7.13 | **3.11** |
| `closed_UAU` | trigger | trigger | trigger | B-anch | 116 | 0 | 0.321 | 0.563 | 0.588 | 9.67 | **3.11** |
| `open_3x3` | `WWW_UAU` | `SWS` | trigger | B-anch | 391 | 3 | 0.319 | 0.517 | 0.602 | 7.72 | 2.23 |

Two things stand out.

**x@116 stem 0 is strong on both arms at once.** It reaches `mean_separation` ~0.32 with
`A_M(11)` ~0.59 *and* `log10_rate_advantage` 3.11 — a ~1,300× nucleation advantage. Arms E
and K have disagreed on every previous comparison; here they agree. That is the first design
in this project where they do.

**The single best equilibrium design is the worst of the twelve kinetically.** x@237 reaches
`A_M(11)` 0.782, the highest ON-state availability seen, and `log10_rate_advantage` 0.22 —
essentially no kinetic help. The arms still disagree, just not everywhere.

## 5. What this does not establish

* **10 pair-stems, and the top table draws on 3.** The axis effects are paired and so control
  for pair-stem, but "which pair-stem" is exactly what Block A does not sample. Block B is
  the complement and has not been run.
* **No bench data.** Against Green's 168 measured switches these statistics scored ρ −0.107
  (`separation`), +0.077 (`mean_separation`) and +0.320 (`A_M_gain`). §1 shows
  `mean_separation` and `A_M_gain` are near-duplicates *here*, which is mildly reassuring for
  the better-correlated one, but none of this is validation.
* **`A_M(11) > 0.3` is a reported cut, not a filter.** Nothing was removed from the file or
  from any ranking; the counts at 0.1/0.2/0.3/0.5/0.7 are printed so the choice is visible.
* **Three axes are still not swept** — `toehold_trim`, `rbs_loop_len`, `secondary_arm` need an
  `assemble()` change.
