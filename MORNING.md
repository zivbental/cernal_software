# A0 objective function — where it stands

    uv run python src/engine/gates/notebooks/toehold_and/objective_panel.py --want 12 --out panel_energy

**21,136 designs scored.** 4,909 gate below −2 kcal/mol. Panel written to
`results/panel_energy.csv`.

---

## 1. There is no objective-function experiment to run

I applied your principle — match every component, vary only what is tested — and it
dissolves the comparison:

| comparison | rank agreement |
|---|---|
| energy vs joint (log ratio) | **−1.000 exactly** (dG = −RT ln p is monotone) |
| energy vs mean ratio | −0.958 |
| energy vs mean gain | −0.955 |
| mean ratio vs mean gain | +0.998 |
| stem arms vs A_M window | +0.950 |
| stem arms vs RBS→AUG window | +0.956 |

The 10.99-against-0.00 gap was an **unbounded ratio against a bounded difference** — a scale
difference, not an ordering one. Ten constructs separating metrics that rank at ρ ≥ 0.95
would buy nothing. The energy form is still the one to keep: it names the leaking state and
does not underflow. But it is not a rival hypothesis.

## 2. What the panel tests instead — the design axes, which genuinely differ

**A-anchored gates in 0 of 4,330 designs. B-anchored in 31.4%.**

The reason was already in the repo: `full_sweep.py --stems-by` records that A-anchored builds
"spend lock strength on trigger A's site (median lock −5.8 against B-anchored's −12.2)". So
trigger A opens the stem unaided, `open_10` = `open_11`, AND-ness zero. That is why `a1top`
scored 0 of 4,800. One panel row shows it as 15.17 against 15.17.

Within B-anchored, so the confound is removed:

| axis | best | gating | worst | gating |
|---|---|---|---|---|
| arm length | **161 nt** | 51.9% | 165 nt | 19.5% |
| closure | closed_CAU/CGU/UAU | ~55% | **open_3x3** | 14.3% |
| upper3 | trigger_derived, WSW_AGA | 74–78% | WWW_UAU | 22.6% |
| lower3 | **SSS** | 76.9% | trigger_derived | 14.3% |
| len_x | 7 | 41.1% | 4 | 31.1% |

Two things worth knowing: **`len_x` barely matters for gating** (31% → 41%), which retires it
as a priority. And the "leave the trigger's bases alone" rule **inverts between levels** —
best at `upper3` (78%), worst at `lower3` (14%), where a strong pair is what resists trigger A.

**The recipe:** B-anchored, 161 nt, a *closed* closure, SSS lower3. Best found: **−16.46
kcal/mol**.

## 3. The panel's controls

* `scheme/A-anchored` — predicted failure, `open_10` = `open_11` = 15.17.
* `gradient/none` — **+16.06**, an anti-gate: state 11 is *harder* to open than state 10.
* `gradient/marginal` — −2.00, the middle of the axis.
* `closure/open_3x3`, `len_x/6`, both arm lengths, distinct trigger pairs.

Read every bench result against `open_10` vs `open_11`, not the score: **state 10 is the
weakest OFF state in 400 of 400 designs.**

## 4. Caveats, not to be taken on trust

* **165 nt is *inferred* to be `--kim-arm`.** Nothing in the folded shards records the flag.
  161 nt is the documented default and 165 is 4 nt longer, which matches 20/17/AUA — confirm
  against the run before reporting it as Kim-versus-default.
* **No trigger pair appears in both arm lengths**, so the cleanest controlled contrast is
  still not populated. The arm-length numbers above are across different pairs.
* `upper3` trigger_derived and the engineered levels have n = 216–227 against WWW_UAU's
  8,027. The effect is large but the sampling is very unequal.
* Off-target is in the objective formula but not joined to the scorer.
* The barrier is computed on the switch alone (findpath takes one strand), so it is the
  switch own refolding wall, not the trigger-bound path, and it is an upper bound.
