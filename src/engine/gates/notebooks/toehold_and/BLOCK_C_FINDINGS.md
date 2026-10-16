# Block C: the overnight run, what it found and what it could not see

Folded 2026-09-21/22 in three phases on six cores. **197,784 distinct designs**, four tubes
each, covering **every one of the 1,036 trigger pairs** and **every one of the 4,144
pair-stems** in the stage-1 sweep.

Reproduce with
`uv run python src/engine/gates/notebooks/toehold_and/fold_analysis.py --out p1` (or `p2`,
`p3`). Every number below was re-queried against the CSVs after this file was written.

| phase | selection | designs | pair-stems | trigger pairs |
|---|---|---|---|---|
| **p1** | `B-anchored`, 36-axis grid | 91,908 | 2,553 | 1,014 |
| **p2** | `mixed`, same grid | 57,276 | 1,591 | 924 |
| **p3** | 150 leading pair-stems, **full 360-axis grid** | 54,000 | 150 | 53 |
| | distinct after dedup | **197,784** | **4,144** | **1,036** |

The grid was `closure` × 6, `upper3` ∈ {`AUA`,`UAU`}, `lower3` ∈ {`SSW`,`SWS`,`WSS`} (2
strong + 1 weak), `island` trigger-derived — Offer's priorities 3–8. Priorities 1 and 2 (the
toehold trim axis and the 20-nt secondary arm) are **not** in this run; both change a domain
length and so change `assemble`'s layout.

---

## 1. The scheme restriction was wrong, and the control caught it

Priority 3 was "only B-anchored for now". p2 ran `mixed` on the identical grid as a control,
using capacity that would otherwise have idled. It wins:

| scheme | designs | median `mean_separation` | best | designs that open (`A_M(11)` > 0.3) |
|---|---|---|---|---|
| `B-anchored` | 91,908 | −0.0005 | 0.4624 | 12,106 (**13.2%**) |
| `mixed` | 57,276 | −0.0002 | **0.4668** | 9,117 (**15.9%**) |

**All ten of the top designs are `mixed`.** Restricting to B-anchored would have discarded
the best design and 21% of the opening rate. The medians are indistinguishable; the
difference is in the tail and in how often a design opens at all, neither of which a median
shows.

## 2. Only one design in seven opens at all

`A_M(11)` is the ON-state availability of the RBS/AUG region. Over p1's 91,908 designs:

| threshold | designs | share |
|---|---|---|
| `A_M(11)` > 0.1 | 30,888 | 33.6% |
| > 0.2 | 13,946 | 15.2% |
| > 0.3 | 12,106 | **13.2%** |
| > 0.5 | 5,425 | 5.9% |
| > 0.7 | 867 | 0.9% |

**87% of designs never open**, so any metric that predicts opening cheaply is worth more than
one that ranks designs which are all shut. Which brings us to §4.

The ranking statistics behave as block A found, at 25× the sample:
`mean_separation` ↔ `A_M_gain` **r = 0.95** (one fact between them), `mean_separation` ↔
`separation` **r = 0.262** (nearly orthogonal). The joint `separation` still carries almost
no information about whether a switch opens.

## 3. The candidate pool, and how concentrated it is

| condition | distinct trigger pairs |
|---|---|
| opens and `mean_separation` > 0.1 | 714 |
| > 0.2 | 464 |
| > 0.3 | **141** |
| > 0.4 | **34** |

But the very top is narrow: the **top 10 designs come from 2 trigger pairs**, dominated by
`x@525`, all `mixed`, all `open_3x3`, all `upper3 = UAU`. Best single design:

| closure | upper3 | lower3 | scheme | x@ | stem | `mean_sep` | `A_M(11)` | `separation` | log₁₀ kin |
|---|---|---|---|---|---|---|---|---|---|
| `open_3x3` | `UAU` | `SSS` | mixed | 525 | 2 | **0.4672** | **0.874** | 5.17 | 1.07 |
| `closed_CGU` | `UAU` | trigger | mixed | 118 | 1 | 0.4624 | 0.772 | 7.27 | **3.69** |

The second row is there because it is the best design that is also strong kinetically
(log₁₀ 3.69, a ~4,900× nucleation advantage) — the two arms agreeing, which is still rare.

## 4. `dG_rbs_stem`: one 54-nt MFE predicts whether a switch opens

The VISTA-style metrics, joined onto all 91,908 p1 designs (`vista_metrics.py`):

| metric | vs `A_M(11)` | vs `mean_separation` | vs `separation` |
|---|---|---|---|
| **`dG_rbs_stem`** | **+0.509** | +0.187 | −0.105 |
| `dG_switch_off` | +0.301 | +0.124 | −0.009 |
| `dG_rbs_linker` | −0.014 | +0.032 | +0.022 |
| `sed_toehold_linker` | +0.060 | −0.005 | −0.079 |
| `gcau_balance6_loopside` | +0.036 | +0.022 | +0.002 |
| `a_content6_loopside` | +0.051 | +0.052 | +0.001 |

`dG_rbs_stem` — the MFE of the main hairpin region [86,140), **one fold of 54 nt** —
explains 26% of the variance in ON-state availability. Given that 87% of designs never open,
this is a usable pre-screen: it costs ~10 ms against ~1.4 s for a four-tube evaluation.

**A caution about how this was found.** On a 60-row sample `dG_switch_off` scored +0.592 and
looked like the headline. At n = 91,908 it fell to +0.301 while `dG_rbs_stem` held. The 60-row
number was reported at the time as indicative only, and it is the reason for saying so.

`dG_rbs_linker` is **flat** here (−0.014) despite `SELECTION_SPEC.md` §4.2 calling it our best
cheap predictor at ρ +0.334 on Green's 168 measured switches. Both can be true: the Green
figure is against *measured ON/OFF* on real switches, this one is against *our model's*
`A_M(11)`. Where they disagree, the bench data is the better authority and the model is what
is on trial.

## 5. What this run could not see: the A-anchored corner

`secondary_stems` labels a build from its per-position states — `mixed`, `A-anchored`,
`B-anchored`, or `unlocked` (all positions `both`). **Four labels. Our 4,144 pair-stems carry
two.** Measured over 40 trigger pairs, on the Pareto front after `lock_energy ≤ 0`:

| scheme | builds surviving | median lock | best lock | median `a_site` | reached the folded top-4 |
|---|---|---|---|---|---|
| `mixed` | 1,933 | −11.1 | −24.2 | −30.1 | 60 |
| `B-anchored` | 512 | −12.2 | −26.4 | −23.4 | 100 |
| **`A-anchored`** | **240** | **−5.8** | −14.6 | **−38.5** | **0** |
| `unlocked` | 9 | −1.6 | −9.0 | −36.2 | **0** |

The driver keeps the **4 strongest locks per pair** (`--stems 4`). A-anchored builds lock
trigger A's positions, which costs lock strength — median −5.8 against B-anchored's −12.2 —
so **not one of the 240 ever entered the folded set**.

And they are the builds that serve trigger A best: median `a_site_energy` **−38.5** against
B-anchored's −23.4, a 15 kcal/mol advantage. That is precisely the lever Offer asked to be
protected ("the a binding was rewarded after b binds").

So the scope of this run: the 3ⁿ enumeration was explored in full when *generating* stems, but
we folded **160 of 2,694 surviving builds — 5.9%** — selected purely by lock strength.

### Measured afterwards: the corner loses on both arms, for one reason

**This section originally ended "Nothing here says A-anchored designs are bad. It says they
were never measured." They have since been measured and they are worse.** Stage 1 was re-run
with `--stems-by a_site_energy` and a 5-trigger-pair subset folded — 960 designs on the same
pairs as a lock-selected control, so the comparison is paired:

| | `a_site` selection | `lock_energy` selection |
|---|---|---|
| median `lock_energy` | **−6.2** | **−22.3** |
| median `a_site_energy` | **−42.4** | −15.2 |
| `A_M(10)` / `A_M(11)` | 0.066 / **0.066** | 0.046 / 0.064 |
| best `mean_separation` | **0.000000** | **0.4668** |
| median `log10_rate_advantage` | 1.50 | **2.01** |
| best `log10_rate_advantage` | 2.15 | **3.81** |
| `free_xstar_00` (before B binds) | 0.015 | **0.001** |

`A_M(10)` **equals** `A_M(11)`: trigger A alone opens the switch as fully as both triggers
together, so there is no gate — best `mean_separation`, `A_M_gain` and `separation` are all
exactly zero across 960 designs.

They are **not** kinetically dead — a median 10¹·⁵ is a ~32× nucleation advantage — but they
lose on that arm too, 1.50 against 2.01. One cause explains both: selecting on `a_site` buys
trigger-A grip by spending the lock, and a weak lock cannot hold state 10 shut **and** leaves
`x*` 15× more free before trigger B arrives, so B has less left to unlock.

**The lock does both jobs.** `lock_energy` is the right selection objective, and that is now a
measurement rather than an inherited default. 100 A-anchored pair-stems, one per trigger pair,
are folded alongside k1 to check that these five pairs were not unlucky.

## 6. Verification

Four checks, all clean.

* **Reproducibility.** p3 re-folded 5,400 designs that p1 and p2 had already done, in separate
  processes hours apart. `mean_separation`, `A_M(11)` and `separation` differ on **0** of them;
  largest discrepancy exactly `0.0`. The pipeline is deterministic.
* **Constants.** Across all 203,184 rows: every switch is **161 nt**, and the `GGG` cap,
  `secondary_loop`, `rbs_loop`, `AUG` at [128,131) and the 21-nt linker are each exactly in
  place. **Zero violations.**
* **The ranking window.** `span(-17, 13)` resolves to **[111, 141)**, 30 nt. Position 111 is
  the first base of the RBS proper (`AACAGAGGAGA`) and 141 is AUG+10, so the window covers
  RBS(11) + spacer(6) + AUG(3) + 10 nt. Correct, and identical on every design because the
  AUG is always at 128.
* **Transcript indices.** On 30,348 designs, `sw_x` equals `trigger_a[18:18+len_x]` and `r2*`
  equals `revcomp(trigger_b[18:])`, both sliced fresh from the transcript at the recorded
  coordinates. **0 mismatches.**
* **Grid completeness.** p3 carries **360 distinct axis points**, and **0** of its 150
  pair-stems is missing any of them.

### One defect found, in our own tooling

`fold_analysis.py` looked for `{out}_folded.csv`; sharded runs write `{out}_folded_0.csv`
through `_5.csv`. All three of the overnight run's analyses exited "not found", and because
`run_night.ps1` only tailed the log, the night completed with 203,184 designs folded and
**none of them analysed**. Fixed; the analyses in this file were run afterwards.

---

## 6b. What this document predates

Written before the k1 and a1top runs, so **nothing here reflects Kim's 20/17/`AUA` geometry
or the `wobble_GU` level**, both of which were added afterwards. The 420-point stage-1 grid
(`lower3` gained `wobble_GU`: 6 × 5 × 7 × 2) postdates it too — every grid figure above is
the 360-point version. When k1 lands, §1 and §5 are the sections to revisit: §1 compares
schemes on a geometry k1 changes, and §5's A-anchored correction was measured on 5 trigger
pairs with 100 more folding alongside k1 as the check.

Accessibility figures above and in `toehold.csv` were computed on **`r2`**, trigger B's own
domain. The strand that must be free for B to bind is **`r2*`**, the switch's toehold — a
different molecule, median 3' openness 0.69 against `r2`'s 0.839. The `r2star_*` columns were
added later and are the ones to use; `candidates.py` prefers them.

## 7. What is still open

1. **The A-anchored corner is unmeasured** (§5). Folding the 4 strongest *a_site* stems per
   pair, rather than the 4 strongest locks, is a one-flag change and a directly comparable run.
2. **Priorities 1 and 2 are not in this run** — the toehold trim axis and the 20-nt secondary
   arm with 17-nt invasion and `AUA` cap. The arm is now worth doing precisely because these
   203,184 designs are a paired baseline to diff against on the same trigger pairs.
3. **No bench data.** Every number here is model output. `dG_rbs_stem`'s +0.509 is against our
   own `A_M(11)`, not against measured fluorescence, and the one place model and bench have
   been compared (§4) they disagree.
4. **The panel is built but not ordered.** `candidates.py` picks trigger-pair *backgrounds*
   on toehold accessibility and ON-state availability, then fills one row per criterion:
   `arm-E` (`mean_separation`), `arm-E-ratio` (`A_M(11)` over the worst OFF state — a
   different statistic, correlating only 0.365 with the difference and sharing 10 of its top
   20, and closer to the fold change a bench measures), `arm-K`
   (`log10_rate_advantage`), `old-stat` (the retracted joint `separation`), `leaky-10` (a
   design where state 10 opens at least as much as state 11), and `closure`.
   Every role is pinned to one closure so role is not confounded with it — `old-stat` and
   `leaky-10` favour the closed variants, best `separation` 16.86 at `closed_CGU` against
   15.57 at `open_3x3` — and a role that has to drop the pin is marked `*`.
   The top 10 designs are **not** the panel: they come from 2 trigger pairs, and a panel of
   predicted winners tests only the cases the model was already confident about.
