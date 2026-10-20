> Historical model draft, exported at revision 52 on 2026-10-05. It is retained
> for research provenance, not as the live page or current compiler specification.
> The live source is in the [Wiki repository](https://gitlab.igem.org/2026/tau-israel/-/blob/main/wiki/pages/and-gate-model.html).
> Start with the [code and reproduction map](prokaryotic-and-reproducibility.md).

# CERNAL — iGEM Model Page

Oct 5, 2026 · @offer simha

CERNAL compiles a transcriptomic signature into an RNA logic circuit on a plasmid. This page documents the computational model: what it does, how to reproduce it, what it produced, and what it got wrong.

**This page is written as the work proceeds.** A section marked as pending is one we have not settled yet, not one we forgot.

## Abstract

A cell exposed to a stressor changes which genes it transcribes. CERNAL takes that change — a transcriptomic signature — and compiles it into an RNA logic circuit that can be carried on a plasmid, so that a cell reports the signature rather than a single marker.

The sensing element is a **toehold switch** ([Green et al., 2014](https://www.sciencedirect.com/science/article/pii/S0092867414012896)). A toehold switch is an mRNA whose own ribosome binding site and start codon are sequestered in a hairpin. A separate **trigger** RNA, complementary to the hairpin's exposed single-stranded toehold, nucleates there and unzips the hairpin by branch migration, freeing the start codon and switching translation on. Because the trigger is recognised by sequence rather than by shape, a switch can be designed for any RNA — which is what makes an endogenous transcript usable as an input.

A one-input switch reports one gene. A signature is a **combination** of genes, so the circuit needs logic. This work builds the **two-input AND gate**: a switch that stays off when either trigger is present alone and turns on only when both are. The design carries two hairpins. The **main hairpin** sequesters the RBS and start codon and is opened by trigger A. The **secondary hairpin** holds a domain that trigger A needs, and is opened by trigger B. Trigger A cannot reach its site until trigger B has released it, so neither input alone produces output.

The two triggers are segments of two different endogenous *E. coli* mRNAs, and the switch is a separate construct. That matters for what the model has to do: the trigger sequences are **not ours to choose**. They are whatever the genes are, so the design problem is to find two windows — one in each gene — that happen to share a short reverse-complementary segment, and then to build a gate around that accident of sequence.

The computational problem has three parts, and the model addresses each:

1. **Which genes.** A published differential-expression analysis of *E. coli* under PFAS exposure supplies the candidate signature.
2. **Which windows.** The two trigger windows must share a reverse-complementary overlap at fixed offsets, be free of sequence features that would destroy the construct or the target, and be accessible rather than buried in the transcript's own structure.
3. **Which design.** For one trigger pair there are hundreds of ways to build the gate — how the start codon is closed, how the stem's top and bottom pairs are set. Each is folded in four states (neither trigger, each alone, both) and the states are compared.

Every threshold in the pipeline is declared and measured rather than assumed, and the sections below give the number behind each one. Where a lever turned out not to work, that is reported too.

## Architecture and notation

&#91;embedded content: the two-input AND switch · 15 domains, 2 triggers, 4 folded states\]

The switch is read 5' to 3'. A domain marked `*` is the reverse complement of the domain it names, so `r2*` in the switch is the complement of `r2` in trigger B. Trigger A's footprint reads `k1 · bulge · main_pre · x · ext`; trigger B's reads `k2 · x* · r2`.

The gate works because the two hairpins share nothing except an ordering constraint. Trigger A pairs with `x``*`, `main_pre*` and `k1*` — but `x``*`, the segment it needs to nucleate on, is held inside the secondary hairpin until trigger B invades it. The secondary hairpin's own lock is the quantity the design has to get right: strong enough that trigger A alone cannot pry it open, weak enough that trigger B can.

State `10` — trigger A alone — is the state that decides whether a design is an AND gate at all. Measured across 400 designs, it is the leakiest OFF state in 400 of 400, so the gate's quality is essentially a question about one tube.

## Methods, Step 1: finding trigger pairs

The inputs are two *E. coli* transcripts. The output is a list of candidate trigger pairs, each a pair of windows — one window in each gene — that share a reverse-complementary segment at the offsets the architecture binds at.

Code: [`ToeholdAndGate.find_cross_gene_pairs`](https://github.com/zivbental/cernal_software/blob/main/src/engine/gates/toehold.py), with `screen_trigger_pair` in the same class.

### 1.1 The cross-gene scan

Every `MIN_OVERLAP`-mer (>=4 nt) of transcript B is indexed. Transcript A is then walked, and at each position the reverse complement of its 4-mer is looked up in that index. Each hit is a seed, and each seed is extended in both directions while the bases keep pairing — extending `x` 3'-ward in A walks its partner 5'-ward in B, because the two strands run antiparallel — up to `SECONDARY_INVASION_LEN`. The run is reported at its **maximal** length only: a truncated overlap is strictly dominated, because both footprints are the same size whatever `len_x`, so a shorter `x` only moves positions out of the conflict-free core.

The scan is `O(n_A + n_B)` per ordered gene pair, and **one scan per unordered pair is enough**. The set of shared runs does not depend on which gene is called A, so both role assignments are emitted from the single scan and a caller enumerating genes needs only `j > i`.

### 1.2 Role assignment

A shared run is symmetric; the gate built on it is not. Around each run, two candidate pairs are defined:

|  | trigger A footprint | trigger B footprint |
| --- | --- | --- |
| assignment 1 | gene A: 18 nt upstream of `x`, then `x`, then the extension | gene B: `invasion − len_x` upstream of `x*`, then `x*`, then 32 nt downstream |
| assignment 2 | the same, with the genes exchanged | the same, with the genes exchanged |

Both footprints are a **constant size whatever `len_x`**, because `len_k2 = invasion − len_x` cancels it: **A is 36 nt and B is 50 nt** in the naive geometry. Kim geometry uses a 17-nt invasion domain instead of 18, with an `AUA` cap above it, so there **A is 35 nt and B is 49 nt** — A loses one base at its 3' end and B loses one at its 5' end.

### 1.3 What step 1 does *not* screen

Step 1 rejects nothing on sequence. A motif screen has to read **the molecule we synthesise**, and that is the switch, not the gene. Most of what reaches the switch is the **reverse complement** of the trigger's bases: `r2_star` is the complement of trigger B's `r2`, and `k1_star` and `main_pre_star` are the complement of trigger A's. Screening the gene window therefore fails in both directions — it misses motifs that do appear in the construct, and it rejects pairs for patterns the construct never contains. Trigger B is the clearest case: none of B appears forward anywhere in the switch.

The screen also cannot be completed at this stage even in principle. Two of the switch's domains, `k2_star` and `secondary_z`, are chosen by the stem solver in step 2, and a motif can straddle a domain junction that exists only once the switch is assembled.

So motif screening happens on the finished switch, in `assembly_violations` — see step 5.

### 1.4 A stop codon is priced, not rejected

One sequence property *is* determined by the windows alone: an in-frame stop codon in `main_pre`, the 9 nt immediately 5' of the overlap in trigger A. Those bases become codons 2 to 4 of the output protein, so a stop there truncates the reporter.

It is reported with its repair cost rather than dropping the pair. `main_pre` pairs with `main_pre_star` in the main stem, so a base can be changed while the pair survives as a G·U wobble. Exactly two moves exist — a base opposite U may go `A→G`, a base opposite G may go `C→U` — and G and U have no alternative:

| codon | repair | substitutions |
| --- | --- | --- |
| `UAG` | `A→G` at position 2 gives `UGG` (Trp) | 1 |
| `UGA` | `A→G` at position 3 gives `UGG` (Trp) | 1 |
| `UAA` | either `A→G` alone gives another stop; both together give `UGG` | 2 |

Measured across the three gene pairs, **58.8% / 62.0% / 67.2%** of stops cost one substitution. Every stop is rescuable; what varies is the price. That matters because the design stage permits at most one broken pair in the stem by default, so a `UAA` costing two may still be declined — but that is a decision made with the number in hand, not a rejection made blindly.

### 1.4 RNase E is counted, not screened

The RNase E cleavage consensus is `RN↓WUU` — purine, any base, the cut, then A-or-U and two uridines ([Chao et al., 2017](https://pmc.ncbi.nlm.nih.gov/articles/PMC5222698), \~22,000 sites mapped in vivo by TIER-seq, described as a 2-nt uridine ruler).

It is **reported on each candidate and never rejects one**, and the reason is a measurement. On real *E. coli* transcripts the consensus fires on **39.7% of 36-nt windows and 51.0% of 50-nt windows**. As a hard filter it would discard half of every trigger B pool, which discriminates nothing.

Weighting it by accessibility is biologically right — RNase E cleaves single-stranded RNA, so a consensus site inside a paired region is not a site — and it helps without rescuing it. On the four PFAS targets (83 sites across the four genes), requiring P(unpaired) at the cut above 0.3 / 0.5 / 0.7 / 0.9 leaves 70 / 60 / 40 / 16 sites, and the per-window rejection rate only falls from 37.6% / 49.0% to 8.1% / 11.5% at the strictest floor.

### 1.5 The accessibility sort

Surviving pairs are ordered by **`min(l_local_A, l_local_B)`** — the less accessible of the two windows, so a pair is only as good as its weaker half. `l_local` is RNAplfold's unpaired probability in a sliding local window (`FoldProfiler.openness`), averaged over the footprint actually built.

This is computed exactly rather than approximated from a neighbouring window, because there is nothing to save by approximating: the RNAplfold pass is **one per transcript** and costs 1.56 s for a 1,716-nt gene, after which each window's accessibility is a slice of the cached profile at **1.5 microseconds**. 238 windows together cost 0.36 ms against 1.56 s for the single pass they all read from.

One limit worth stating: the **joint** opening probability is capped at 20 nt by the profiler's `unpaired` setting, so for a 36-nt or 50-nt footprint no joint probability exists and the honest measure is the mean of per-base marginals.

### 1.6 What it produces

Step 1 rejects nothing, so every run carries forward. Three gene pairs, naive geometry, with `ggt` (b3447) as one half of each:

| gene pair | runs found | carried forward | flagged for a stop | longest `len_x` | best min-accessibility |
| --- | --- | --- | --- | --- | --- |
| ggt + fadB | 24,597 | 24,597 | 2,012 | 13 | 0.6266 |
| ggt + astC | 14,004 | 14,004 | 1,299 | 13 | 0.5441 |
| ggt + aldA | 14,929 | 14,929 | 1,446 | 10 | 0.5766 |

The stop flags break down by repair cost. On ggt + fadB: 1,206 cost one substitution, 719 cost two, and only 87 of 2,012 cost three or four because the window carries more than one stop. The other two pairs are the same shape.

The best available accessibility, 0.54 to 0.63, sits comfortably above the 0.3369 floor the design stage applies, so **accessibility is not the binding constraint at this step**.
