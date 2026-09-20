# Our A0 gate against Kim 2019, Green 2014 and Green 2026 (VISTA)

Written 2026-09-17, from the papers and the VISTA source in
`Prokaryotic-And-Gate/Docs` and `vista/toehold-VISTA`. Every sequence-level claim was
re-derived from the published sequence tables with ViennaRNA rather than taken from prose.

---

## The one finding that matters most

**Every published design leaves the top of the ascending arm un-invaded by the trigger, and
ours does not.**

| design | ascending arm | how much the trigger is complementary to | left free |
|---|---|---|---|
| **Ours (A0)** | 18 nt | **18 nt — all of it** | **0 nt** |
| Kim 2019, primary | 18 nt (11 + 1×1 loop + 6) | 15 nt | **3 nt**, the 3 bp next to the RBS loop |
| Kim 2019, inhibitory | 20 nt (1×1 bulge at 12) | 17 nt | **3 nt**, filled with `AUA` |
| Green 2014, 1st gen | 18 nt (9 + 3×3 + 6) | 18 nt — all of it | 0 nt |
| Green 2014, forward-engineered | 18 nt | 15 nt | **3 nt**, hard-coded to the weak A-U ladder `AUA` |
| Green 2026 VISTA | 9 + 3×3 + 6 | 6 nt only | **everything above 6 bp**, an invariant cassette |

Green's first generation shares our rule and reached a mean ON/OFF of **43**. Their
forward-engineered generation pulled the trigger 3 nt back from the RBS — listed in Fig. 3A
as one of four deliberate changes, annotated *"3 nt shift"* — and reached a mean ON/OFF of
**406**, a ten-fold improvement. Kim's constructs follow the same rule via an explicit
design constraint (SI p.1: *"The toehold domain was restricted to 15 nucleotides"*, and
*"The trigger RNA was restricted to total 30 nucleotides"*, which leaves 15 nt for an 18-nt
arm). VISTA goes furthest and freezes the entire top of the hairpin.

**We adopted the rule that the field moved away from.** This is the difference Offer was
pointing at when he asked about the last 6 nt of the ascending stem — the literature says
3 nt, adjacent to the loop, and says to make them *weak* rather than merely different.

---

## The second finding: our ON-state observable may be asking for the wrong thing

VISTA's specified **ON-state** structure, from SI Table S2, is
`D36 + U6 D6 U11 U3 D6 U6 U30`. Decoded: the trigger pairs the first 36 nt; then **the 6-bp
upper stem stays paired**, the RBS stays inside its 11-nt loop, and only the `AUG` becomes
unpaired.

So in the architecture with the best published data, *the ON state never opens the upper
stem at all*. Translation initiates because the RBS sits in a loop and the start codon is
freed — not because the hairpin melts.

Our `dG_open` / `p_open` over `W_rank` (−17…+13, 30 nt) asks for the joint probability that
**all thirty** nucleotides are simultaneously unpaired. That is a state VISTA's own working
design is not built to reach, which is consistent with our measurement that `P_open` is only
4.5 × 10⁻⁶ even in state 11. **The metric may be demanding something a working switch does
not do.** This is a hypothesis, not a proven defect, and it is testable: score Green's
forward-engineered switches — which have ON/OFF data for 13 constructs — with our
`dG_open` and see whether it ranks them at all.

---

## Full comparison

| feature | **Ours (A0)** | **Kim 2019** | **Green 2014** | **Green 2026 VISTA** |
|---|---|---|---|---|
| Inputs | 2 triggers | 2 (Fig. 1 AND) | 1 (its 4-input AND is *transcriptional*, layered) | 1 |
| Hairpins on the switch | 2 | 2 | 1 | 1 + a small 3′ refold hairpin |
| Exposed toehold `a` on the main hairpin | **0** | 10, 7, **4** (AND works at 4); 15 for the one-hairpin control | 12 (1st gen), 15 (fwd-eng), 24–30 (mRNA sensors) | 30 |
| Main stem | 9 bp + 3×3 loop + 6 bp, arm **18 nt** | 11 bp + **1×1** loop + 6 bp = 17 paired, arm **18 nt** | 9 + 3×3 + 6, arm 18 nt | 9 + 3×3 + 6 |
| Inhibitory hairpin arm | 18 nt (= ARM_LEN) | **20 nt**, 1×1 bulge at position 12, `AUA` on top | — | — |
| Two stems equal length? | yes, by construction | **no** — primary arm 18 nt, inhibitory arm 20 nt | — | — |
| Trigger invasion into the inhibitory arm | n/a (trigger B binds `k2*` fully) | **17 of 20 nt**, stopping 3 short, with `AUA` filling the top | — | — |
| Where the `AUG` sits | 3×3 internal loop, descending arm | **1×1 bulge**; only the A is unpaired, U and G are G·U wobbles | 3×3 internal loop | 3×3 internal loop |
| RBS → AUG spacing | 6 nt | 6 nt | 6 nt | 6 nt |
| Terminal loop | RBS flank + RBS | 15 nt | 11 nt (1st gen), 15 (fwd-eng) | 11 nt |
| Linker | 21 nt | 21 nt, `AACCTGGCGGCAGCGCAAAAG` | same 21 nt | same 21 nt |
| Triggers from one transcript? | **yes** (mCherry, both windows) | **no** — de-novo, separate promoters | no | no |
| Objective function / thresholds | 12 τ gates + Φ | **none** — domain-level NUPACK, then build and measure | φ = 5·l_mRNA + 4·l_toehold + 3·n_sensor | 66 features → RFE → PLS-DA |
| Thermodynamic engine | ViennaRNA 2.7.2 | NUPACK | NUPACK, Mathews 1999 for analysis | NUPACK 4.0 `stacking`; ViennaRNA only for the transcript bppm |
| Bench data available to us | none yet | ON/OFF per construct | **168 + 13 constructs with ON/OFF** | **189 constructs with ON/OFF** |

---

## Verified against the sources, 2026-09-20

Three numbers in the first draft of this table were loose, and were checked against Kim's
supporting information directly:

* **The primary hairpin's arm is 18 nt, not 17.** 17 is the *paired* count — 11 bp + a
  single bulged nucleotide + 6 bp. The arm is 18 nt long. **So our 18-nt arm already matches
  Kim's**, and the "18 vs 17" framing in the first draft compared two different quantities.
* **The inhibitory arm is 20 nt**, with a 1×1 bulge at position 12, and trigger B invades
  **17 of those 20** — stopping 3 short, exactly as the primary does.
* **`AUA` sits on top of the inhibitory hairpin too**, not only the main one. So the same
  pattern — invade to within 3 nt of the loop, fill the remainder with a weak A·U ladder —
  is applied to *both* hairpins in Kim's design, and we apply it to neither.

The practical consequence is that "19/17 stems" was the wrong way to describe the
difference. **Both of Kim's arms are longer than the invasion and capped with `AUA`;
the asymmetry between his two hairpins (18 vs 20) is secondary to that shared rule.**

## Differences we had not discussed, most consequential first

1. **The 3-nt shift away from the RBS** — above. Sourced, and the single clearest
   actionable difference.
2. **Green's ON state keeps the upper stem paired** — above. Calls our `W_rank` observable
   into question.
3. **Kim's AUG is in a 1×1 bulge, not a 3×3 loop.** Only the adenine is unpaired; the U and
   G are G·U wobbles. Our R7 assumes a 3×3 loop is the norm. Kim's *other* family
   (Sw2Albion, Fig. 2C) does use 3×3, so both exist — but the AND-gate constructs do not.
4. **Kim caps BOTH hairpins with `AUA`, 3 nt short of the loop** — primary arm 18 nt with a
   15-nt invasion, inhibitory arm 20 nt with a 17-nt invasion. One rule, applied twice; we
   apply it to neither. The length asymmetry between his two hairpins (18 vs 20) is real but
   secondary to that shared rule, and our arms already match his primary at 18 nt.
5. **Kim's triggers are de-novo and unrelated; ours are two windows of one transcript.**
   That is forced by our validation design, but it means our two triggers can pair *each
   other* and share sequence context in ways theirs cannot.
6. **Both published designs add a 26-nt stabilising hairpin upstream of the switch** and one
   on each trigger transcript, for RNA stability. We have none.
7. **The top 3 bp are not merely decoupled — they are made weak.** All 13 of Green's
   forward-engineered switches hard-code `AUA`/`UAU` there. Our sweep decoupled `mainZ` but
   ranked candidates by a balanced margin, which is a different and probably wrong target.
8. **kpLogo result, directly portable:** among VISTA's 189 designs, high performers are
   enriched for *balanced* GC/AU at the 6 nt at the base of the descending stem; A-rich
   there gives high OFF (leaky), GC-rich gives low ON (too rigid to open).
9. **Proximal structure beats global.** VISTA found only the ±10 and ±25 nt windows
   statistically significant — *"proximal occlusion of the binding site rather than global
   folding of the full transcript more strongly determines accessibility"*.

---

## Calibration sets we could use, and have not

- **Green 2014 Table S1**: 168 first-generation switches with full switch and trigger
  sequences and measured ON/OFF; Table S3 adds 13 forward-engineered ones.
- **VISTA supplementary data**: 189 mCherry designs with ON, OFF and fold change.

None of these is a two-input AND, so none validates our gate directly. What they *can* do
is test whether our observables have any rank-order relationship with measured performance
on single-input switches — which is the cheapest available check on whether `dG_open`,
`A_M` and `d_off` mean anything at all. Doing that fits the standing instruction not to fit
weights to data: it is a correlation check, not a fit.

---

## Cautions on VISTA's shipped code, if we ever reuse it

Found while reading `Toehold_VISTA.ipynb`, and all three are the kind of thing our own house
rules exist to prevent:

- **Batch-relative normalisation** — `rank_new_designs()` recomputes the scaler from the new
  batch and ignores the saved `scaler_mean`/`scaler_scale`, so a design's score depends on
  which other designs were in the run.
- **Wrong projection at inference** — training uses `x_rotations_` via
  `PLSRegression.transform()`, inference uses `x_loadings_`. Different matrices.
- **Feature-order mismatch** between the training matrix and the design notebook's output.
- **Silent zeros** — `codon_usage_dict.get(codon, 0)` and a window average that returns 0
  when no index is found.

Their *definitions* are sound and worth adopting. Their ranking code is not.
