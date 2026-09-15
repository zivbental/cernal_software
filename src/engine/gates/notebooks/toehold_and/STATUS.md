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
the two-pass score), `kim2019_benchmark.py` (the validation against published constructs).

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

668 engine tests, 259 house-rule assertions, ruff clean.

---

## Problem 1 — the state-10 leak. Blocking, and not a code defect

**Measured.** On 142 candidates, `A_M(10) < 0.2` passes **0/142**, and `A_M(10)` equals
`A_M(11)` to five decimals on **142/142** (max difference 0.00000). `dG_bind_A` against the
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

**Proposed solutions, for Offer and the supervisor.**

1. **Stop gating on τ4a; rank on `separation` over {00, 01}.** What `design_panel.py` does
   today. Honest and unblocking, but it stops claiming the AND is verified.
2. **Invert R6 on the main stem.** The most promising, and it follows from a symmetry Offer
   identified. R6 requires the switch's own copy to be the *weaker* binder so the trigger
   can displace — which is precisely what lets trigger A displace *unaided*. If instead the
   switch's `main_pre`/`mainZ` bind the ascending arm *more* strongly than trigger A does,
   then trigger A cannot open the hairpin on the 18-nt arm alone, and needs the extra
   `len_x` base pairs from `x*` — available only once B has acted. **That is a true AND at
   equilibrium.** Note it makes `main_pre` a design variable, which costs 3 residues of
   N-terminal extension on the reporter, and it reopens R6.
3. **Add the kinetic refinement** §4.5 anticipates, reopening §6's equilibrium-only
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
