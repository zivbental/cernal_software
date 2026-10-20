# Historical analysis notes — bacterial AND Results and Discussion

Archived analysis and editorial recommendations from the `axes_c8` study. These
notes predate the live Wiki and later model corrections; they are not current
compiler requirements. The original filename is retained for existing references.
Start with the [current code and reproduction map](../prokaryotic-and-reproducibility.md).

---

## 1. Evidence available to the original analysis

**Had:** the repo, `docs/assets/axes_c8/` (the committed tidy tables), and the numbers Offer ran
on his machine against the 301,440-row `axes_c8_{0..5}.csv` tables.

**Not directly available:** the 301,440-row tables themselves. They were ignored
local outputs, so the original analysis used reported command results and retained
summary tables. The available model draft was revision 52, ending at §1.6; the
live Wiki and later chapters were not part of that assessment. These limitations
remain relevant when deciding which claims can be independently reproduced.

---

## 2. What exists now

| file | what it is |
|---|---|
| `docs/wiki/and-gate-model.html` | 79 KB standalone page: `## Results` (R0–R10) and `## Discussion and Conclusions` (D1–D7). Its own 3.7 KB `<style>` block, its own heading scheme |
| `docs/wiki/shape_*.svg` (5 files) | the per-design scatters, ~240 KB each. **They must sit in the same directory as the page**; `<img src="shape_….svg">` is relative |
| `docs/assets/axes_c8/*` | the tidy tables and `.txt` reports every number is read off, plus the same five SVGs |
| `tools/analyse_axes.py` | contrasts decomposed into ON and worst-OFF terms, orientation declared per column in `ORIENTATION`, `binding_off_<contrast>` reported |
| `tools/sensitivity_filters.py` | new: the ON ceiling swept downward, the selection-time floors applied, conclusion stability per threshold |
| `tools/plot_axis_shape.py` | new: one dot per design, x raw, y within-cell z, seeded sample, bin medians over **all** designs |
| `tools/probe_axes.py` | probes 4 (Kim vs naive across matched cells), 5 (variance between pair and design), 6 (per-trigger accessibility) added |
| `tests/engine/gates/test_axes_analysis.py` | 9 tests, incl. one that fails on the `ied_gain` clobber this work fixed |
| `docs/findings-register.md` | the `axes_c8` section, with the rows this work added |

1,557 engine tests pass; `ruff check .` and `ruff format --check .` are clean.

---

## 3. The one decision to make first

`docs/wiki-page-brief.md` §1 says the page is `wiki/pages/model.html`, **one** page carrying
ABSTRACT → METHODS → RESULTS → DISCUSSION → REFERENCES, with "SUPPLEMENTARY DATA — a separate
page, so the wiki page stays readable". Offer asked this session for
`wiki/pages/and-gate-model.html`, a separate file. Both instructions are real and they disagree.

**Recommendation: both, split by depth rather than by topic.**

- **Into `model.html`, as its RESULTS and DISCUSSION sections:** R2 (state 10 binds the contrast
  in 80–99% of designs), R4 and R5 (lock hard / grip weakly, with the −15 to −17 kcal/mol
  threshold), R6 (closure scores opposite on survival and on gating), R8 (the threshold sweeps),
  R9 (the pair decides whether it can open; the levers decide whether it leaks), and D1–D7
  condensed. The brief's §4 says the judges score sensitivity analysis and
  "emphasise mistakes and things that did not come out as expected" — R8 and the four wrong
  expectations in §7 below are the highest-value content on the whole page for that criterion.
- **Keep as the supplementary page:** the five scatters, the quintile tables, the per-state
  tables, the full assumptions list in D5, the method paragraphs (what "worst OFF" means, what a
  within-cell z-score is and why), and R10. That is most of the current 79 KB, and the page as it
  stands is already close to being that supplementary page.

**Do not** split by topic — one page with the AND-gate results and another with everything else
would put R8's sensitivity analysis outside the page the judges read.

---

## 4. Merge without thinking about it

Nothing here is a judgement call; it is all one repo serving one purpose.

- the four `tools/` files and the test file
- `docs/assets/axes_c8/`
- the `docs/findings-register.md` rows
- the `access_a` orientation fix in `analyse_axes.ORIENTATION` (it was `-1.0` with a comment
  calling it a probability; it is `open_penalty`, p_open as an **energy**, so a cost. Dormant —
  the column is empty on every row of this run — but the next run to fill it would have been
  ranked inverted)

---

## 5. Do not merge

**Do not fold the HTML prose into `docs/igem-model-page.md`.** That file's own header says it is a
mirror of the Claude Doc and that an edit to it is lost on the next refresh. So there are two
honest options and no third: either the earlier chapters move out of the Doc and the repo becomes
the source of truth, or the new chapters go into the Doc and the HTML is generated from it. Pick
one deliberately. Merging into the mirror looks like it works and silently reverts.

**Do not union `axes_c8` with `axes_pfas`.** Different schema (47 vs 162 columns), different ON
ceiling, different gate version. `characterise_axes.py`'s own guards refuse it. `axes_pfas_v2` is
an independent replication check, never extra rows.

---

## 6. Integration mechanics, if the page is grafted into `model.html`

1. **Drop my `<style>` block.** The brief says adopt the wiki's existing visual language from the
   start rather than adding ours later. My CSS is a standalone-document stylesheet: light/dark via
   `prefers-color-scheme`, `overflow-wrap: anywhere` on `code`, scrollable tables and figures for
   phone width. The last three are behaviours worth keeping whatever the host stylesheet does —
   the tables are wide and the identifiers are long.
2. **Renumber, and fix 36 cross-references.** The page uses `R0`–`R10` and `D1`–`D7` and refers to
   them 22 and 14 times. `grep -o "§R[0-9]*\|\bD[1-7]\b"` finds them all. A renumbering that
   misses one produces a reference to a section that no longer exists, which is the one error a
   judge will notice.
3. **The five SVGs must travel with the page** into `wiki/pages/`, or every figure is an empty
   frame. This cost two rounds already. Regenerate with
   `tools/plot_axis_shape.py --out axes_c8 --x <axis> --y <objective> --into <dir>`.
4. **The figures the brief asks for that do not exist yet:** per-step graphical simulations
   through Methods, and the gate-structure figure in the OneDrive style with versions for states
   01 and 10. `tools/figure_and_gate_states.py` and `tools/figure_methods.py` already emit inline
   SVG for the wiki — extend those rather than hand-drawing.

---

## 7. What these results say about chapters already written

This is the part worth reading even if the integration is deferred. Four stated expectations
turned out wrong, and the brief asks for exactly that.

**§1.5, the accessibility sort, is the one that needs revisiting.** It orders pairs by
`min(l_local_A, l_local_B)`. Probe 6 (§R9) measured each trigger separately over all 420 cells:

- `b_site_energy` is predicted by `l_local_b` (ρ +0.304) and **not at all** by `l_local_a`
  (−0.020, p 0.69); `lock_energy` likewise tracks `l_local_b` (+0.320) and not `l_local_a`
  (+0.036, p 0.46). So the two accessibilities are not interchangeable and `min()` destroys
  structure that predicts the design's energies.
- Holding each trigger's own GC fixed collapses the A-side link from +0.283 to +0.041 and it
  changes sign between strata. **The part of accessibility that predicts a stem energy is almost
  all its GC part.** Accessibility and GC are not two independent screens on a window.
- `l_local_min` correlates with the cell's best achievable ON-state openness (ρ −0.191) and with
  **no contrast at all** (|ρ| ≤ 0.14). The sort selects for "this pair can turn on", not for
  "this pair will discriminate". §1.5's own closing line — accessibility is not the binding
  constraint at this step — survives; what changes is what the sort is *for*.

**Three more expectations that did not hold:**

- **The secondary hairpin is mixed in function and single-sided in sequence.** We expected neither
  trigger's accessibility alone to account for `lock_energy`, because both triggers' sequences are
  in that structure. It is trigger B's alone, because the arm is the `x*` side and `x*` is read out
  of gene B.
- **Kim 2019's extended secondary arm buys nothing measurable here.** 140,256 matched design pairs
  over 195 trigger pairs: nothing significant on any of the four contrasts (p 0.15–0.42), median
  paired difference exactly 0.000 on all four, the four disagreeing in direction, 72 of 195 pairs
  exactly tied on the opening contrasts.
- **Trigger A's grip on the secondary arm is a cost with no detectable benefit.** The architecture's
  rationale is that A needs the help. Every ON-state term is flat against it (|ρ| ≤ 0.05) while it
  is the largest single driver of the state-10 leak (ρ 0.70). Stated carefully in D2: all four
  ON-state observables are equilibrium properties, and the one kinetic observable we have
  (`barrier`) is the switch strand alone, so this is a negative result about what we measure.

**And the one that is a hazard rather than a finding:** a metric's reference state is a design
decision. The same folded data gives ρ −0.075, +0.651 and +0.620 for the ensemble-defect contrast
depending on whether the OFF state means 00, the worst of 01 and 10, or the worst of all three.
The engine is inconsistent about this — `ied_off_worst` excludes state 00 while the `A_M`, `aug`
and `meanW` worst-OFF terms include it. That should be resolved deliberately, across every family.

---

## 8. Still open

1. **The ceiling this population was filtered on is not the one the engine now applies.** The run
   used `open_11 ≤ 8.0` (the main stem's 15-nt arms); Green's criterion as the engine evaluates it
   is `dG_open_11 ≤ 7.2` over the 31-nt window. §R8 re-applies the latter as a counterfactual and
   the lever conclusions hold — but a design the older ceiling rejected was never folded in its
   OFF states, so no sweep can recover it. A re-run would fix this and nothing else will.
2. **A barrier along the invasion path in state 11.** `FoldEngine.saddle` takes one strand, so it
   cannot do the switch&A&B path. Until it can, D2's negative result is about equilibrium
   observables plus one switch-only barrier.
3. **`access_*` versus `l_local_*`:** one property, two names, one of them empty on every row.
   Decide which is canonical and retire the other rather than filling in the empty one.
4. **The mediation test on the outcome, not the energy:** `l_local_min` against the cell's best
   `A_M_11` with GC held fixed. It is the one link in §R9 not taken apart, and on the evidence it
   is probably composition at one remove.
5. **No measured two-input performance exists for any construct we can score.** Green and VISTA
   are single-input (370 constructs); Kim 2019 is two-input but qualitative. Everything in R3–R9
   is internal consistency, and D4 says so rather than burying it.

---

## 9. How to check this handoff rather than trust it

```
uv run pytest tests/engine -q                       # 1,557 pass
uv run ruff check . && uv run ruff format --check .
uv run python tools\analyse_axes.py        --out axes_c8 --into docs\assets\axes_c8
uv run python tools\sensitivity_filters.py --out axes_c8 --into docs\assets\axes_c8
uv run python tools\probe_axes.py          --out axes_c8
```

Every table and figure on the page is derived from the files those write. If a number on the page
disagrees with a freshly generated one, the generated one is right and the page is stale — say so
rather than reconciling quietly.
