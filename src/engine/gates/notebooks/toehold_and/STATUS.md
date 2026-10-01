# A0 AND gate — state, open problems, proposed solutions

Written 2026-09-16. Code lives in `ToeholdAndGate` (`src/engine/gates/toehold.py`) with
runnable drivers beside this file. Design documents are in the separate
`Prokaryotic-And-Gate` repo and are reference-only.

## Run it

```
# whole pipeline, one command, minutes
uv run python src/engine/gates/notebooks/toehold_and/design_panel.py \
    --fasta ".../mCherry original.txt" --quick --out panel

# the real panel: 2 pairs x 3 stem families x 2 designs, plus 4 controls per pair
uv run python src/engine/gates/notebooks/toehold_and/design_panel.py \
    --fasta ".../mCherry original.txt" --out panel
```

Other drivers: `find_candidates.py` (stage 1 + controls), `rank_candidates.py` (gates and
the two-pass score), `kim2019_benchmark.py` (the validation against published constructs),
`strength_window.py` (the sweep that tested and falsified the main-hairpin fix),
`strand_occupancy.py` (where each strand goes in each tube -- the audit behind problem 1).

The plain-language write-up of the state-10 investigation, English and Hebrew, is
[`state10_leak_summary.md`](state10_leak_summary.md).

## Pipeline status

| # | Stage | Status |
|---|---|---|
| — | `FoldEngine`: `p_open`, `ensemble_defect`, `structure_energy` | **done** |
| — | `binding`: fixed-alignment energy, wobble-aware runs | **done** |
| 1 | Trigger-pair discovery — geometry, motifs, control feasibility | **done**, reproduces 1443/1036/867/169 |
| 1b | `Q_A`/`Q_B` accessibility, three sub-measures each | **not built** anywhere |
| 2 | Secondary stem, scheme C + Pareto front + family labels | **done** |
| 3 | Switch assembly + intended OFF structure | **done**, 161 nt, coordinates asserted |
| 4 | Four-tube evaluation | **done** |
| — | Pair pre-filter (one fold per pair, before stems) | **done**, but see problem 2 |
| 5 | τ gates, two-pass score, λ | **done**; nothing passes, see problem 1 |
| 5b | `Q_pair` / `Φ` | **blocked** on 1b and the §5.2 margins |
| 6 | Bench constructs, four states on one background | **done** |
| 7 | Output / ranking | **partial** — ranks on `J`, not `Φ` |

695 engine tests, 284 house-rule assertions, ruff clean.

---

## Problem 1 — the state-10 leak. Blocking, and audited as not a code defect

**Audited 2026-09-16, because two results looked too clean to trust.** Verified from three
independent directions, and the conclusion held:

1. **`p_open` against answers known without folding.** A poly-A window returns exactly
   1.0; a 10-bp stem returns 25.3 kcal/mol; that stem's own loop returns 0.0; and moving
   the window changes the answer. Pinned as regression tests.
2. **`A_M` against a raw reimplementation** that reads ViennaRNA's 1-indexed
   upper-triangular output directly instead of the shared matrix: agreement to
   **0.0×10⁰**, so the matrix conversion carries no off-by-one.
3. **`dG_open` against an independent re-derivation** with no `FoldEngine` involved:
   agreement to **0.01 kcal/mol** on a ~70 kcal/mol quantity, which is ViennaRNA's own
   partition-function scaling noise, four orders below the model's ~1.5 kcal/mol error.

**Both suspicious coincidences have physical causes.** Kim's four constructs return
identical `dG_open(10)` because **the ribosome window's sequence is identical in all
four** — `AACAGAGGAGAUAUAGAAUGAGACAAUGGA`; they differ only in *upstream* spacing, and
trigger A opens the primary hairpin in every one, so the window's local ensemble is the
same. Their absolute energies differ correctly (−70.53 / −69.07 / −67.61 / −57.35, tracking
length); only the difference over a shared window converges, and it converges to the fifth
decimal rather than exactly.

And `A_M(10)` versus `A_M(11)` are **not** identical: 0.5220967774815423 against
0.5221042962957555, a difference of 7.5×10⁻⁶, non-uniform per base, with one base moving
the *other* way — which is what a real ensemble does and a caching fault could not. An
earlier version of this file claimed "identical to five decimals, max difference 0.00000";
that was an artifact of printing three decimals, and is corrected above. The conclusion is
unchanged, since 10⁻⁵ cannot move a gate thresholded at 0.2, but the precision was
overstated.

The reason the two tubes agree so closely is visible in the matrices: trigger A pairs the
main arm at probability **1.0000** in both states, so that arm's local ensemble really is
the same. Where the tubes differ hugely — max |ΔP| = 0.9999 — is the *secondary* hairpin,
which is where trigger B acts.

**Measured.** On 142 candidates, `A_M(10) < 0.2` passes **0/142**, and `A_M(10)` equals
`A_M(11)` on **142/142** to within **~1×10⁻⁵**. `dG_bind_A` against the
*bare* switch is −38…−44 kcal/mol against −38…−47 conditioned on B — a difference inside
the model's own error. So `separation` is 0.00 for every candidate.

**Cause, and it is structural.** Trigger A's first 18 nt are by construction the exact
reverse complement of the main hairpin's ascending arm (R1), and R7 *intends* those 18
contiguous pairs to beat the hairpin's 15-plus-a-loop — that is the ON mechanism. Nothing
in it requires trigger B. What B supplies is a *nucleation site*, which is kinetic; an
equilibrium model sees only end states. §4.5 of the .docx predicted exactly this.

**Independently confirmed against Kim 2019.** Their `a`=10 (one-input), `a`=7, `a`=4
(working AND) and single-hairpin control all return `dG_open(10)` = **1.61** and
`A_M(10)` = **0.789** from our pipeline — identical. **Our feasible set rejects a
bench-validated AND gate on τ4a with the same numbers it rejects a switch that does not
gate.** Kim attribute the real difference to binding *probability* and *sequential
binding*. Reproduce with `kim2019_benchmark.py`.

**Three dead ends, so nobody re-tries them.** (a) Raising τ from 0.2 to 0.5 cannot work:
since `A_M(10) == A_M(11)`, passing both "10 shut" and "11 open" needs τ_shut > τ_open,
which is incoherent. (b) `engaged(10)` — the probability `x*` is paired to trigger A rather
than locked — looked promising and is not the leak: candidate x@68 has `engaged(10)` =
0.048, i.e. trigger A never takes its nucleation site, and *still* shows
`dG_open(10) = dG_open(11) = 8.25`. Trigger A bypasses the designed pathway entirely.
(c) `len_x` does not predict the leak: `engaged(10)` spans 0.048–0.858 with no relation to
overlap length or lock energy.

**The strength-window fix was tested and it fails. Retracted 2026-09-16.**

Proposal 2 below — make the switch's own copy the stronger binder so trigger A needs `x*`
— was implemented as a sweep and measured. `mainZ` is the only free sequence in the
ascending arm, and `k1*` is its reverse complement, so it is the only lever the layout
offers. `main_stem_energies` prices the three deciding alignments without folding, and
`strength_window.py` sweeps all 4096 spacers per pair, keeps those satisfying
`grip_with_x < stem < grip_alone`, and folds a sample **stratified across the margin
range** so the result is a curve rather than a top-k list.

**Result: 40 variants, 10 trigger pairs, margins 0.1 → 10.7 kcal/mol inside the window,
`separation` 0.00 on every single one, with `dG_open(10) == dG_open(11)` throughout.**
`dG_open(00)` and `dG_open(01)` do differ, so the tubes respond to strand composition; it
is trigger B specifically that stops mattering once trigger A is present.

**Why the window is empty.** The proxy asks trigger A to beat the *whole* 18-bp stem, but
trigger A only has to displace the sub-helix over `main_pre*` — and there its `main_pre` is
the switch's own identical sequence **plus** the 3-nt `bulge` that the descending `AUG`
cannot pair. R7 grants trigger A those three base pairs by design. `mainZ` sits on the far
side of the bulge, so no choice of it takes them back; what `mainZ` controls is the 6-bp
upper stem next to the RBS loop, 6 of `W_rank`'s 30 nt, which is not enough to hold the
window shut once `main_pre` has been peeled. `main_pre` is the reporter's first three
codons and is trigger-derived, so it is inside the ribosome window **and** inside trigger
A's footprint at once.

**`separation +2.97` is retracted.** Recorded earlier as evidence this idea worked, it came
from a throwaway script with a **state-labelling error**: its "state 10" was the
switch-alone tube. Re-measured through `four_tube_observables` on the same pair and spacer
(x@52, `len_x` 8, `mainZ` `GCCGAC`): `separation` −0.00, `A_M(10) = A_M(11) = 0.405`, and
its "`A_M(10)` 0.060" is this pipeline's `A_M(00)`. Decoupling `k1*` does lower `A_M(10)`
from 0.522 to 0.405 — it just never separates 10 from 11.

**Proposed solutions, for Offer and the supervisor.**

1. **Stop gating on τ4a; rank on `separation` over {00, 01}.** What `design_panel.py` does
   today. Honest and unblocking, but it stops claiming the AND is verified.
2. ~~**Invert R6 on the main stem.**~~ **Tested and failed** — see above. The part of the
   idea that survives is its diagnosis: for a thermodynamic AND, the stretch of hairpin
   covering the ribosome window has to be sequence-*independent* of trigger A. Since
   `main_pre` is both the reporter's first three codons and a slice of trigger A, that
   cannot be arranged by choosing `mainZ`.
3. **Move the bulge bonus from trigger A to the switch.** The lever the failure points at.
   If the 3 nt of the ascending arm facing the `AUG` are `CAU` — complementary to the start
   codon rather than to trigger A's `bulge` — the switch's own arm gains the three pairs
   and trigger A loses them, which is the first arrangement in which trigger A can lose
   *locally*. It breaks R1 over 3 nt and removes the 3×3 loop R7 asks for, so it must be
   checked against the ON state before it is believed. Measured with the same script.
4. **Add the kinetic refinement** §4.5 anticipates, reopening §6's equilibrium-only
   instruction. Canonical reference: Zhang & Winfree 2009, toehold-mediated displacement
   rates spanning ~6 orders of magnitude over toehold length 0→6 nt — **unverified from
   here, check before citing.**

---

## Problem 2 — the pair pre-filter conflicts with any fix to problem 1

The pre-filter folds one probe switch per pair and applies only the gates no stem could
rescue, turning ~120 folds per pair into one. It is correct: across four stems spanning the
frontier, the main hairpin's observables move < 0.006 kcal/mol.

But its main gate is τ4a. With τ4a dropped, what remains (`A_M(00)`, `A(r2*|00)`) is a weak
filter. And any *replacement* leak metric built on the lock — `locked`/`engaged` — is
strongly stem-dependent (`locked(00)` is 0.997 with a real stem versus 0.009 with the
probe), so it **cannot** be pre-filtered. Fixing the observable costs the cheap funnel, and
the Pareto front becomes the only reduction.

---

## Problem 3 — `A_S` is mis-specified, independent of problem 1

`A_S` is an *unpaired* probability, so it cannot distinguish "locked shut by the switch"
from "engaged by trigger A" — both are paired. Hence `A_S(10) = A_S(11) = 0.000`, and τ6
(`A_S(11) > 0.5`) is **unsatisfiable**: in state 11 `x*` is *supposed* to be paired, to
trigger A.

**Proposed fix, already measured and working.** Decompose it from the same pair-probability
matrix: `locked(s)` = P(`x*` paired to `sw_x`), `engaged(s)` = P(`x*` paired to trigger A).
On a real strong stem this behaves exactly as the architecture is drawn — 00: locked 0.997;
01: **free 1.000** (B exposes the site); 11: engaged ~1.0. It is a strict improvement over
`A_S` regardless of how problem 1 is resolved.

---

## Problem 4 — control feasibility is a `[lab]` filter applied as if general

R13 marks it `[lab]`: it exists only because *this* validation manufactures both inputs by
recoding one gene. Production triggers are endogenous and cannot be recoded, so the filter
is meaningless there — yet it removes **169 of 1,036** candidates (16%).
`design_panel.py --no-lab-filter` now turns it off. `find_candidates.py` still applies it
unconditionally.

---

## Problem 5 — knockout scope is unresolved

Minimal synonymous substitution, per the supervisor (*"החלפות מינימליות"*). The criterion is
no contiguous pairable run ≥ 4, wobbles counted — the framework's nucleation floor.

Offer asked that the *whole trigger window* be disabled, not just the overlap, and the
reason is sound: an overlap-only knockout leaves trigger A's 18-nt arm intact, and that arm
opens the main hairpin unaided, so state 01 would still fire. **But it is mostly
unachievable.** Synonymous change reaches the codon wobble position and little else — 144
of 196 breakable bases sit at codon position 3 — so breaks come about every 3 nt, exactly
the spacing needed, with no slack. Measured over 80 candidates: overlap **68/80**, trigger
A's 18-nt arm **21/80**, whole 36-nt A window **3/80**, trigger B's arm 24/80, whole 50-nt
B window **0/80**.

**Proposed fix.** Split the criterion by what it protects against: run-of-4 for
**nucleation** (the overlap — can A start?), and `ddG_pref` **inversion** for
**displacement** (the arm — can A win the exchange?), which is Offer's suggestion and is
energetic rather than a base count. The current code uses the overlap scope and builds the
full four-construct panel for 39/40 sampled candidates.

---

## Also open

- **τ12** — measure `flank_penalty` over a real run, then set it. **τ_trig** — needs the
  `Q` saturating map first.
- **`Q_pair` / `Φ`** — needs 1b (six accessibility sub-measures) and the two §5.2 margins.
  The largest piece of remaining work, and the only one needing no decision first.
- **`d(Ω00)` never passes τ9** (0.18–0.32 against 0.1). Either the threshold is wrong or the
  intended OFF structure is not what the molecule adopts; not yet investigated.
- **`A(r2*|00)`** is a genuine discriminator but usually fails (0.20–0.63 against 0.5), and
  it is `r2*` **self-structure**, not the LINKER — deleting the LINKER moves it 0.01–0.04.
  `r2*` is `revcomp(r2)`, read from trigger B, so this is a *selection* criterion on the
  pair, not a design knob.
- **`PIPELINE_CONTEXT.md` §5.6** still describes state 00 as "no transcript"; it is now a
  both-triggers-disabled variant on one background, per the supervisor.
