# Selection specification — what the pipeline ranks on, and what it refuses to rank on

Written 2026-09-20, for review before the full sweep is built. Every number quoted is
measured and reproducible from the drivers beside this file; nothing here is fitted.

---

## 1. Two objectives, not one

We have two live hypotheses about why the gate does or does not work, and **measurement says
they are independent**. Over 12 baseline designs, the kinetic nucleation advantage spans
10¹·⁰ to 10⁴·⁵ — a 30,000-fold range — and its rank correlation with every equilibrium
quantity we compute is:

| against | ρ | | against | ρ |
|---|---|---|---|---|
| `separation` | +0.340 | | `A_M(11)` | −0.091 |
| `mean_separation` | +0.077 | | `lock_energy` | −0.112 |
| `A_M(10)` | −0.091 | | `toehold_dG` | +0.087 |

None reaches significance at n = 12 (best |z| = 1.13). **A quantity that varies 30,000-fold
is invisible to everything we currently rank on.**

Combining them into one score would require weights, and there is no data to set those
weights — the standing instruction on this project is that no weight is fitted to data. So:

> **Two arms. Two rankings. No combination. The panel carries both, and the bench decides
> which arm was right.**

**Arm E — equilibrium.** Ranks on `mean_separation`. Selects designs whose end states
differ.
**Arm K — kinetic.** Ranks on `log10_rate_advantage`. Selects designs where trigger B
genuinely unlocks trigger A's site.

A design may appear in both. Designs that appear in **neither** are not ordered.

---

## 2. The funnel, cheapest first

Folding dominates cost, so every stage exists to avoid the next one. Costs are per
candidate.

| # | Stage | Cost | Kept |
|---|---|---|---|
| 1 | Geometry: overlap ≥ 4 nt, window gap, arm lengths | free | 1036 of 1239 |
| 2 | Motif / sequence validity, no out-of-frame AUG in the UTR | free | — |
| 3 | **GC-gradient score** (§4.1) | free | rank, no cut |
| 4 | **`dG_RBS-Linker`** (§4.2) | 1 MFE of ~50 nt | rank, no cut |
| 5 | **Trigger accessibility** SED at ±10 / ±25 (§4.3) | 1 bppm of the transcript, shared | rank, no cut |
| 6 | Scheme C front, **direction corrected** (§3) | fixed-alignment energies only | ~50 builds/pair |
| 7 | `lock_energy > 0` excluded | free | see §3 |
| 8 | Four tubes → all equilibrium observables | ~25 s | top few hundred |
| 9 | **Kinetic foothold proxy** (§4.5) | 2 folds | same set |
| 10 | **findpath barriers** (§4.6) | ~2 min | top ~20 only |

Stage 10 is why kinetics cannot run on everything, and stage 9 is why it does not have to:
the cheap proxy and the expensive barrier put the same design top by a wide margin.

---

## 3. The Pareto front — and the sign error to fix

The front is currently taken over `(lock_energy, a_site_energy, b_site_energy)`, all
minimised. **`a_site_energy` rewards trigger A binding the secondary stem**, which was
correct under the original premise that trigger A needs help and is wrong under everything
we have since measured. Keeping it biases the front toward exactly the builds that leak.

**Corrected front, three objectives:**

1. `lock_energy` — **minimise** (more negative = stronger lock). The axis that predicts
   whether closing the AUG produces a gate at all (ρ = −0.707 against separation-after-closure).
2. `b_site_energy` — **minimise**. Trigger B must still bind.
3. `a_site_energy` — **maximise** (weaker A binding is better). *Direction inverted.*

**Also to relax, to report-only:**

- **R6** (`ddG_pref = lock − b_site ≥ 0`). It caps lock strength so trigger B can displace
  the lock — but B has a 32-nt toehold measured 31–53 % exposed in the OFF state and does not
  need a weak lock, while lock strength is the axis that matters. Keep the invasion-stall cap,
  which guards the real failure.
- **Scheme C's excluded fourth per-position option** ("serve neither trigger"). Excluded as
  "dominated" under the same inverted premise. Re-enable and let the front decide.

**Hard cut, new:** `lock_energy > 0` is not folded. A positive lock is not a lock.

---

## 4. Metric definitions

Every metric below is **reported** for every design that reaches stage 8. Only the two named
in §1 are **ranked** on. Nothing else gates.

### 4.1 GC gradient — free, pre-fold
`gc_bottom3 − gc_top3`, as fractions over the 3 bp at the base of the main stem and the 3 bp
nearest the loop. Green's enrichment analysis: high-performing switches carry G·C at the
bottom and A·U at the top. Higher is better. **No folding, so it can sort all 1036 pairs
before anything expensive runs.**

### 4.2 `dG_RBS-Linker` — 1 MFE, the best cheap predictor
MFE of the switch from the first base of the RBS loop to the last base of the 21-nt linker.
A **single-state** folding energy of a subsequence — how structured that region is — and not
a two-state difference, which is what makes it a different quantity from `dG_open` rather
than a rewording of it. Measured on Green's 168 switches: **ρ = +0.334, |z| = 4.32**, the
highest of any single metric we have tested, marginally ahead of our own `A_M_gain` (+0.320).

### 4.3 Trigger accessibility — on the transcript, not the switch
SED (mean base-pairing probability) over the trigger window plus L nt each side, L ∈
{0, 10, 25, 50, 100}, folded as a literal slice of **mCherry**. VISTA found ±10 and ±25 the
only significant windows — proximal occlusion dominates. Plus the 5′ and 3′ 3/6/18-nt
sub-window pairedness from the whole-transcript matrix.

> **Local windows are correct for the transcript and wrong for the switch.** The switch's
> structure is dominated by *designed long-range* pairs — `sw_x` pairs `sw_xs` 40 nt away —
> so a ±25 nt window around `r2*` would omit the very stem that sequesters it. The switch is
> always folded whole (161 nt). The transcript is folded locally. They are different objects
> and get different treatment.

### 4.4 Equilibrium observables — all three forms, always
For each of the four tubes: `P_open` (joint), `dG_open` = −RT ln P (its energy conversion),
and the **mean** per-base unpaired probability over both `W_rank` and the main stem.
`separation` in joint and mean form. `ddG_AND`, `dG_bind_B`, `dG_bind_A|B`, `d_off`.

**`A_S` is replaced** by the three-way decomposition of `x*`: `locked` (paired to `sw_x`),
`engaged` (paired to a trigger), `free`. An unpaired probability cannot distinguish the lock
holding from the lock being torn open, and τ6 (`A_S(11) > 0.5`) is unsatisfiable because `x*`
is *supposed* to be paired in state 11.

### 4.5 Kinetic foothold proxy — 2 folds
`free(x*)` in configuration **00** and in **01** — what trigger A finds *on arrival*, before
it binds, on each path. Converted at ~1 decade per nucleotide to a 6-nt saturation.
**Constants borrowed from Zhang & Winfree 2009: DNA, 25 °C, 1 M Na⁺, against our RNA at
37 °C.** Ratios are defensible; absolute rates are not.

### 4.6 findpath barriers — top ~20 only
Saddle height on a direct refolding path, in kcal/mol. Two separate barriers:
**nucleation** (opening `x*`, from 00 and from 01 — what B buys) and **completion** (opening
`W_rank`, from 00/10/11 — what A buys). Rate ≈ nucleation × completion. findpath is a
heuristic that can only over-estimate a saddle, so these are conservative bounds.

### 4.7 Codon usage — free
Relative synonymous codon fraction (E. coli) for the two in-frame codons after the AUG, and
for the n codons flanking the trigger window, n = 4…10. Green/VISTA: frequent codons
immediately after the start codon correlate with higher ON fluorescence; slow codons just
downstream of a binding site park the ribosome over it.

---

## 5. Thresholds — what survives

**Feasibility only.** Nothing thresholds on a scored quantity, because no τ has been
calibrated against a two-input AND gate and the one published AND gate that works fails our
τ4a with the same numbers as a switch that does not gate.

| Keep | Why |
|---|---|
| assembly length / coordinate assertions | a violated one is a bug, not a bad design |
| forbidden motifs, restriction sites, homopolymers | synthesis and cloning |
| no out-of-frame AUG in the 5′ UTR | it is a second start codon |
| invasion-stall cap (`MAX_INVASION_STALL`) | guards trigger B genuinely stalling |
| `lock_energy > 0` excluded | a positive lock is not a lock |
| control constructibility (R13) | **opt-in only**, `--lab-filter` |

Everything else — all twelve τ gates, R6, R7 — is **computed and reported, never enforced**.

---

## 6. Choosing what goes to the bench

The panel has to discriminate between the two hypotheses, not assume one.

1. **Top N from Arm E** (`mean_separation`), filtered on `A_M(11)` and start-codon
   accessibility so we never order a design that turns off without turning on.
2. **Top N from Arm K** (`log10_rate_advantage`), *regardless of equilibrium rank* — these
   are the designs our equilibrium model rejects and the kinetic reading favours. Without a
   fixed quota they never appear, because they are not on the front.
3. **Matched contrast pairs**: for each chosen trigger pair, build **baseline** and
   **AUG-closed** on the *same* pair and the *same* stem. If they perform the same at the
   bench, the metric was the problem; if the closure wins, the leak was real. This is the
   single most informative comparison available.
4. **Negative controls** per pair: the four-state constructs (00/01/10/11) by minimal
   synonymous knockout.
5. **`a = 4` variants of the finalists only** — not swept through the pipeline. Kim's AND
   works at `a` = 4 and degenerates at `a` = 10; we sit at `a` = 0, outside anyone's tested
   range, and this is the cheapest way to find out whether that matters.

---

## 7. Open, and deliberately not in this spec

- **Green's intermediate / refolding complex** (2014 Fig. 4, carried into VISTA). Changes the
  intended OFF structure and therefore `d_off` and every constrained quantity. Next cycle.
- **Endogenous off-target search**, for both triggers and the switch. `OffTargetScanner` is a
  stage-2 stub. Separate workstream.
- **5′ stabilising hairpin.** Decision recorded: **GGG prefix only** for now. Green optimises
  a stabiliser per design against its toehold; Kim froze one from his best construct. Our
  wet-lab route is a plasmid into BL21 and prior work needed only the GGG. Revisit if
  transcript stability becomes the suspected bottleneck.
- **Secondary loop.** Ours is already 15 nt, **identical to Kim's**. Whether to optimise it
  per trigger pair is open; its pairing probability should be reported first.
