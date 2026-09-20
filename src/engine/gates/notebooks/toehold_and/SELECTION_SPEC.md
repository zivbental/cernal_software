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

**What `a_site_energy` actually measures, since the name hides it.** It is
`fixed_alignment_energy(x + ext, secondary_z + x*)` — trigger A's overlap **plus its
extension** against the nucleation site **plus the inhibitory stem's descending arm**. So it
is not "does trigger A bind its site"; it is **how far past its site trigger A can reach into
the inhibitory hairpin**. `x` is fixed by the trigger pair, so the only variable part is
`ext` against `secondary_z` — and `secondary_z` is a domain scheme C designs. The metric
exists because that design choice directly controls trigger A's over-reach.

Under the original premise (trigger A needs help), more reach was better. Under what we have
measured it is the mechanism of the leak, one domain over from the main hairpin: `locked(00)`
is 0.982–0.999 and `locked(10)` collapses to **0.000 on 12 of 14 stems** — trigger A tears
the lock open, and a stronger `a_site` is exactly what lets it. It is the same phenomenon as
`engaged_A(10)`, priced before folding.

**It stays an objective, with the direction flipped, rather than being dropped** — because
there is a floor. Trigger A must still bind `x*` firmly enough in state 11 to open the main
hairpin. Minimising its reach and keeping its grip are in genuine tension, which is what a
Pareto axis is for.

**Also to relax, to report-only:**

- **R6** (`ddG_pref = lock − b_site ≥ 0`). It caps lock strength so trigger B can displace
  the lock — but B has a 32-nt toehold measured 31–53 % exposed in the OFF state and does not
  need a weak lock, while lock strength is the axis that matters. Keep the invasion-stall cap,
  which guards the real failure.
- **Scheme C's excluded fourth per-position option** ("serve neither trigger"). Excluded as
  "dominated" under the same inverted premise. Re-enable and let the front decide.

**Hard cut, new:** `lock_energy > 0` is not folded. A positive lock is not a lock.

---

## 3b. Two selection problems, not one front

VISTA's findings are about **which trigger site to pick on the transcript**; the scheme C
front is about **which stem to build once the pair is fixed**. Putting the first into the
second would be a category error — once a pair is chosen, its accessibility and GC gradient
are constants and cannot discriminate between stem builds. So there are two rankings at two
stages:

**Pair-level front (stage 1b), a new Pareto over three cheap objectives:**

1. **proximal accessibility** — SED at ±10 and ±25 nt, *minimise* (less paired = more
   reachable). VISTA: *"proximal occlusion of the binding site rather than global folding of
   the full transcript more strongly determines accessibility and functional response"*, and
   only ±10 and ±25 were significant.
2. **GC gradient** — `gc_bottom3 − gc_top3`, *maximise*.
3. **`dG_RBS-Linker`** — *maximise* (less structured), ρ = +0.334 on 168 measured switches.

Codon usage and the 3′/5′ sub-window pairedness are **reported alongside**, not on the front,
because their published effects are weaker (r ≈ 0.30 and −0.33) and adding weak axes to a
front mostly widens it.

**Stem-level front (stage 2):** `lock_energy`, `b_site_energy`, `a_site_energy` as in §3.

> **A caution we should not design past.** VISTA's own conclusion is that *"moderate stem
> stability — rather than extreme single-strandedness or rigid base pairing — enable robust
> strand invasion"*, and that high performers carry **balanced** GC/AU. Our measurement says
> stronger lock is monotonically better (ρ = −0.707 against separation-after-closure), but we
> sampled `lock_energy` only from −0.2 to −23.1 and may simply not have reached the turn. So
> **rank on lock strength, but carry the extremes into the panel rather than only the
> maximum** — if the relationship turns, that is where it turns.

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
- **Secondary loop — measured, and it does not need sweeping.** Ours is already 15 nt,
  **identical to Kim's**. Its pairing probability over 8 pairs:

  | state | mean ± sd | range |
  |---|---|---|
  | 00 | **0.031 ± 0.010** | 0.026 – 0.055 |
  | 01 | 0.147 ± 0.138 | 0.019 – 0.398 |
  | 11 | 0.163 ± 0.135 | 0.012 – 0.451 |

  It pairs `r2*` at **0.0000** in every design and the triggers at 0.001–0.064, so it is not
  interfering with either toehold. In the OFF state — the one state where the loop's own
  sequence is the only thing acting on it — it is **flat across pairs** (sd 0.010), which is
  what a well-behaved constant looks like. The 20-fold spread appears only in 01 and 11,
  *after* trigger binding frees the arms around it, so that variation is a **consequence of
  the trigger pair, not of the loop**.

  **So: do not sweep it. Report it, and let it discriminate between pairs.** Redesigning a
  constant per pair multiplies the design space to fix something the constant is not causing.
  The general rule this is an instance of: **measure first; if a quantity is flat where the
  design controls it, it is a selection criterion, not a design knob.**
