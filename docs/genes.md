# Gene selection — assessment and design

**Status:** Built, and now wired into `run_pipeline` for a first, scoped `de` path
(`engine.pipeline._de_trigger`) — a real compile against a differential-expression
table now produces real toehold candidates and a real plasmid, verified against real
data for both bundled hosts end to end: *E. coli* (730 accepted candidates from
`apps/expression/catalog/ecoli/88048__42635036.csv`, 34 s) and yeast (110 accepted
candidates from real genes in the bundled catalog). `GeneSelector.select` implements
§4–§6 below, tested in `tests/engine/test_genes.py` against real rows from the public
catalog (§1's own worked example); `engine.inputs.parse_dge_table` (§6 G3) parses the
table; `engine.transcriptome.load_transcriptome` (new, `tools/sync_transcriptome.py`)
answers **Q1 for E. coli and yeast** — real bundled NCBI RefSeq references (K-12
MG1655, 4,308 real CDS; S288C, 6,027 real CDS across 16 chromosomes + the
mitochondrial genome), fetched live and checked in. **Q12 (promoter/terminator)
answered for the same two hosts too** — real iGEM Registry parts for yeast
(`BBa_K124002`/`BBa_K1486025`), verified the same way the *E. coli* parts were.
Decisions D1–D6 in §5 were resolved as implemented, not left open — see each axis's
own section for what was chosen and why.

**What "wired in" does not yet mean.** This is single-gene circuits only — every
selected gene becomes its own one-gene circuit, the same trivial construction the
`direct` path already used, never a `CircuitDesigner`-built multi-gene Boolean
expression. No real off-target scanning — `OffTargetScanner`'s matching is still a
stub, so its transcriptome stays deliberately empty even here. No `InputQualityCheck`
— there is no count matrix in this product to check (§3 G-a is still open). No bundled
yeast plasmid backbone (D7) — a real, verifiable one was not found in time; a yeast
run supplies its own vector or omits a backbone entirely. No human at all — Q1 needs a
different, bigger fetch strategy for a spliced genome, and Q12 needs an actual
assembly-standard decision for a mammalian vector, not a parts lookup (D7). See
`engine/pipeline.py`'s own module docstring and docs/ROADMAP.md E2 for the exact scope
line.
**Question it answers:** *given one differential-expression table and nothing else, which
handful of genes is worth building a circuit around?*
**Companion documents:** [`ROADMAP.md`](ROADMAP.md) Q1/Q2 and [`integration.md`](integration.md)
GAP-1 are the blockers this plan works around rather than solves;
[`triggers.md`](triggers.md) is the stage below, and supplies the measured evidence in §5.2;
[`public-datasets.md`](public-datasets.md) is where the input data in §2 comes from;
[`modalities.md`](modalities.md) §A1 is the `de` path this stage sits on.

---

## 1. The naive rule, and why this document exists

With one control group and one condition group, the obvious rule is *take the most
up- or down-regulated genes*. That rule is a sort on `|log2FoldChange|`, it is one line,
and it is what `SelectedGene.score` will collapse to if nobody decides otherwise.

Here is that one line, run against a real comparison already shipped in this repo —
`E-CURD-149`, human, bacterial disease vs normal, top 8 by `|log2FC|`:

| Rank | Symbol | log2FC | p-value |
|---|---|---|---|
| 1 | `MAPK8IP1P2` | −23.1 | 0.0061 |
| 2 | `LINC01242` | −21.8 | **0.063** |
| 3 | `MTCO3P12` | −20.9 | **(none)** |
| 4 | `MMP8` | 10.0 | 8.4e−08 |
| 5 | `CYP19A1` | 9.3 | 0.00016 |
| 6 | `OLFM4` | 9.1 | 8.4e−06 |
| 7 | `PCOLCE2` | 9.0 | 0.00016 |
| 8 | *(blank symbol)* | 8.2 | 0.0020 |

Rank 1 and rank 3 carry the HGNC `P<n>` suffix that names a **pseudogene**; rank 2 is a
lncRNA that is not significant even at a nominal 0.05, uncorrected; rank 3 has no p-value
at all; rank 8 has no symbol. A log2FC of −23.1 is an 8.9-million-fold change, which is
not a regulatory event — it is a near-zero denominator. The first row a synthetic biologist
would recognise as a plausible circuit input is **rank 4**.

So the naive rule does not merely rank imperfectly. On real data it puts three artifacts
above the first real gene, and the run that follows spends its entire folding budget on
them. Everything below is about the other four filters that have to run first.

---

## 2. What the input actually looks like — measured, not assumed

Three input shapes reach this stage, and they carry different columns. This was measured
by reading the files in `src/apps/expression/catalog/` and
`src/apps/datasets/examples/`, not inferred from the ingestion code.

| Source | Columns present | Rows |
|---|---|---|
| Researcher upload (DESeq2 export) | whatever they exported — `gene_id`, `log2fc`, `baseMean`, `pvalue`, `padj` typical | theirs |
| Bundled example (`ecoli_oxidative_stress.csv`) | `gene_id, log2FoldChange, baseMean, pvalue, padj` — **no symbol** | 50 |
| **Public catalog, all 15 comparisons** | `gene_id, gene_symbol, log2fc, pvalue, padj` — **no abundance column** | 3,000 each |

And the public catalog's two p-value columns are mostly empty:

```
45,000 rows across 15 curated comparisons
    with an adjusted p-value : 0        (zero, in every file)
    with a raw p-value       : 25,556   (0 in all five E. coli files; 1,030 of 3,000 in E-CURD-149)
```

Three consequences follow directly, and each of them breaks a filter the current
`GeneSelector` docstring specifies:

**(a) The significance filter, implemented literally, returns nothing.**
`stages/genes.py` says *"`p_adj <= constraints.max_p_adj`. Drop rows with a null `p_adj`."*
Applied to the catalog, that drops 45,000 of 45,000 rows. Every public dataset — the
feature Phase D just shipped — would select zero genes and report an empty result with no
error. The rule is correct for a DESeq2 upload and catastrophic for everything else,
and nothing currently distinguishes the two cases.

**(b) The abundance filter cannot run at all on public data.** The docstring calls filter 3
*"the criterion the pipeline map calls out and the one most easily forgotten"* — expression
must sit in a usable window **in both states**, because too low in the ON state is a false
negative and too high in the OFF state is leakage. No catalog file has any abundance
column. There is nothing to filter on.

**(c) The catalog is pre-sorted by `|log2FC|` and truncated to 3,000 genes**
([public-datasets.md](public-datasets.md) §3). So the head of every public dataset is
*enriched* for the low-count artifact in §1, and the tail that would let us calibrate
against it has been cut off. This is the input we get; it is not going to improve.

---

## 3. Five gaps in the repo, not in the science

These are things the code cannot currently express, independent of any scientific decision.

### G-a · `select(counts, dge)` asks for a file the product never collects

`GeneSelector.select(self, counts: CountMatrix, dge: DgeTable)`. Nothing in
`src/apps/` accepts a count matrix: `Dataset` is one file, the wizard uploads one file,
`AnalysisRun` holds one `dataset` FK, and `apps/datasets/services.py` validates a DE table.
Grepped: `CountMatrix` is referenced only by `stages/genes.py`, `stages/quality.py` and
`stages/circuits.py` — three stubs and nothing else.

So `control_percentile` and `condition_percentile` have **no source today**, and
`InputQualityCheck.check(counts, metadata)` — which is specified to run *before* this stage
and to check sample clustering — has no input either.

This is bigger than gene selection: `ConfusionEvaluator.evaluate(expression, counts, threshold)`
needs it too, and the confusion matrix is what [engine.md](engine.md) §3.2 calls *"the most
honest number the pipeline produces"*. **A one-file product cannot produce a confusion
matrix.** Worth deciding deliberately rather than discovering at stage 4.

### G-b · `p_adj` is non-optional in the record, and absent in most real data

```python
class DgeRow:
    p_adj: float  # not float | None


class SelectedGene:
    p_adj: float  # not float | None
```

The parser cannot build a `DgeRow` for a catalog row without inventing a number, and the
repo's own rule ([CLAUDE.md](../CLAUDE.md) §3) is that an unmeasured quantity is `None`,
never a placeholder. `1.0` would read as "tested, not significant"; `0.0` as "perfect".
Both are wrong and both get persisted.

### G-c · Nothing parses the input file

[integration.md](integration.md) GAP-1. `JobRequest.input_path` is a path; no module in
`src/engine/` turns it into a `DgeTable`. Gene selection cannot be tested end to end until
it exists, and if it does not exist by then it gets written *inside* `GeneSelector`, which
is how a pandas DataFrame ends up crossing a stage boundary.

### G-d · A selected gene with no transcript sequence crashes the next stage

`TriggerScorer.score` opens with `transcript = sequences[gene.gene_id]` — a bare
`KeyError`, mid-iteration, with no gene named. Whatever answers Q1, the join key matters:
the human catalog uses Ensembl IDs (`ENSG00000263503`), E. coli uses locus tags (`b2094`),
and the bundled example uses bare symbols (`katG`). A systematic namespace mismatch drops
**every** gene, and must surface as a named error rather than an empty shortlist.

### G-e · Every threshold this stage needs is missing from `Constraints`

`Constraints` carries `min_separation` and `max_p_adj` and nothing else relevant. There is
no shortlist size, no abundance window, no implausible-fold-change cap. `CLAUDE.md` §3
forbids putting them in module constants — *"an undeclared numeric cutoff is an invisible
per-family filter"* — and `pipeline._build_constraints` rejects any key not on the
dataclass, so the platform cannot pass them until the record gains them.

---

## 4. What gene selection actually is

Not a sort. **A budget allocation.** The shortlist decides what the rest of the run is
allowed to look at: stage 2 folds every window of every selected transcript, stage 4
enumerates Boolean expressions over the selected set, and nothing downstream can recover a
gene that stage 1 dropped. Ten wrong genes cost a ten-minute run and produce a confident
report about the wrong biology.

That reframes the job as five independent questions, of which effect size is one:

| # | Question | Answerable from | Today |
|---|---|---|---|
| 1 | Does the gene **separate the two states**? | log2FC, p | always (p sometimes missing) |
| 2 | Is it **expressed in a usable range** in both states? | baseMean / per-group means | uploads only |
| 3 | Can a **trigger be built** from its transcript at all? | the sequence | blocked on Q1 — §5.2 |
| 4 | Does it say something the **other selected genes don't**? | co-expression, similarity | §5.3 |
| 5 | Is it **constructible** with the chemistry this run has? | direction × gate families | §5.4 |

Questions 3, 4 and 5 appear nowhere in the current docstring. They are the difference
between a shortlist and a ranking.

### 4.1 · Axis 1 — separation, done properly

Three refinements to "big fold change, small p":

**Floor *and* ceiling on effect size.** `min_separation` is a floor. §1 shows the top of a
real dataset is artifacts, so there must also be a ceiling: an implausible `|log2FC|`
is evidence of a near-zero group mean, not of strong regulation. Propose
`max_separation`, defaulting to something like 12 (≈4,000-fold) — above that, flag and
drop rather than rank first. This is a judgement call and should be recorded as one.

**Use the standard error when it exists.** `DgeRow.lfc_se` and `DgeRow.stat` are already
fields. Where a DESeq2 upload provides them, rank on a shrunken estimate
(`|log2FC|` penalised by `lfc_se`) or on `stat` — that is precisely what `lfcShrink` is
for, and it dissolves the §1 problem at the source. Public data has neither, so this is an
upgrade for uploads, not a general solution.

**Tier the significance rule instead of applying one rule to three data shapes:**

| What the table has | What this stage does | What it reports |
|---|---|---|
| `p_adj` | filter on `max_p_adj`; drop null-`p_adj` rows as *not tested* | nothing special |
| `p_value` only, table complete | compute Benjamini–Hochberg over the table, filter on that | run warning: *"FDR computed by CERNAL from raw p-values"* |
| `p_value` only, table **truncated** (every public dataset) | **do not fabricate an FDR** — filter on raw p at a stated, stricter threshold, or not at all | run warning naming the limitation |
| neither (all E. coli catalog entries) | no significance filter; effect size and axes 2–5 carry the whole decision | prominent warning: *"significance was not assessed"* |

BH over a table that has been pre-truncated by `|log2FC|` is anti-conservative — the
denominator is wrong and the result would look like an FDR without being one. That is the
same invented-precision the ingestion layer already refuses ([public-datasets.md](public-datasets.md)
§2.1), and it should be refused here for the same reason.

### 4.2 · Axis 3 — trigger yield: how many usable triggers a gene actually has

This is the axis this design exists for, and it is affordable.

[triggers.md](triggers.md) §4 measured, on a real mCherry CDS: of 676 scanned windows,
**337 are unusable** at switch level — and the dominant rejection, by an order of
magnitude, is the AUG count:

```
1026  expected exactly one AUG
  99  restriction site 'PstI' (CTGCAG)
  51  homopolymer 'Gx6'
  38  in-frame stop codon(s)
```

The critical property is that **this rejection needs no folding**. `SwitchValidator`
rejects a switch whose sequence contains anything other than exactly one AUG
([`switches.py:280`](../src/engine/stages/switches.py#L280)), and the switch contains
`reverse_complement(trigger)` plus segments reverse-complemented back — so an unwanted AUG
arises from an `AUG` in the window **or** from a `CAU` in it. Both are `str.count`.

So a per-gene **trigger yield** — the fraction of a transcript's windows that survive a
screen costing no ViennaRNA call at all — is computable at stage 1:

```
for each window of each length in constraints.trigger_lengths:
    reject if screener.violations(window)          # S7, already built, already injected
    reject if window.count("AUG") + window.count("CAU") > 0
    reject if gc_content(window) outside a stated band
trigger_yield = surviving / scanned          (0.0 – 1.0, None if no sequence)
```

Every call is either `engine.sequences` (S6) or `MotifScreener` (S7) — both legal imports
from `stages/genes.py`, `MotifScreener` being one of the three modules
[`test_house_rules.py`](../tests/engine/test_house_rules.py)'s `STAGE_TOOL_MODULES` permits
sideways. `stages/triggers.py` is **not** importable from here and must not be reached for.

Two things this buys:

- A gene whose transcript yields **zero** usable windows is dead. It should never be
  selected, however clean its statistics, and today it would be — and would then produce
  no designs, silently, and be indistinguishable in the report from a gene that folded badly.
- Between two genes with similar separation, the one with 200 usable windows gives stage 2
  a real search and the one with 3 gives it a formality.

**What stays in stage 2:** accessibility, MFE, off-target load, segment specificity. Those
need folding or a transcriptome index, they are stage 2's declared job, and computing them
here would be the two-numbers-for-one-quantity failure [CLAUDE.md](../CLAUDE.md) §5 names.
Stage 1 asks *"can anything be built here?"*; stage 2 asks *"which window is best?"*.

**Cost.** One `str.count` pass and one motif scan per window, over tens of transcripts —
milliseconds, against a folding stage measured in minutes. It is affordable precisely
because it refuses to fold.

**Degradation.** With Q1 unanswered there are no sequences, so `trigger_yield` is `None`,
the axis drops out of the score (§4.5), and the run warns that constructibility was not
assessed. It is never `0.0`.

### 4.3 · Axis 4 — the shortlist is a set, not a list

Ranking genes independently and taking the top *K* selects **K copies of the same signal**.
Two genes in one operon, or one pathway, move together; an `A AND B` circuit over them is
no more discriminative than `A` alone, needs twice the parts, and leaks twice as much.
Worse, if their transcripts are similar enough to cross-hybridise, each one's switch is
activated by the other's trigger — cross-talk that stage 4 will measure and penalise after
the whole folding budget has been spent on it.

So selection should be **greedy with a redundancy penalty**, not a sort: take the best
gene, then repeatedly take the best remaining gene *discounted by its similarity to what
is already chosen*. Deterministic, cheap, and it changes the answer.

The similarity term depends on what is available:

| Available | Redundancy signal |
|---|---|
| count matrix | correlation of the two genes' profiles across samples — the real answer |
| transcript sequences | `OffTargetScanner.find_similar` — direct cross-hybridisation risk (stub today, and Q1) |
| neither | E. coli only: adjacent locus tags (`b2094`/`b2095`) are usually one operon — a weak, honest proxy |
| nothing | skip the axis and say so |

This axis is the one most likely to be dropped for time. It should be the one kept, because
it is the only one that makes a **two**-gene circuit better than a one-gene circuit.

### 4.4 · Axis 5 — a DOWN gene cannot be built today

`SelectedGene.regulation` is data, not design: an UP gene is an activator input, a DOWN gene
reaches the circuit through a **NOT** gate. Which means a DOWN gene needs an antisense
family — and `pipeline._UNBUILDABLE_FAMILIES` skips `antisense` at run time (no payload
library, Q11), skips `toehold_and`, and skips both host-specific AND variants.

**Today the constructible surface is a single-input toehold on a single UP gene.** Every
DOWN gene in a shortlist is dead weight that will produce no designs.

Measured, taking the naive top 20 by `|log2FC|` from each public comparison:

```
human/E-MTAB-2580        UP= 1  DOWN=19     <- 1 constructible gene out of 20
human/E-GEOD-103501      UP=18  DOWN= 2
ecoli/92117__44313016    UP= 2  DOWN=18     <- 2 out of 20
yeast/E-MTAB-5313        UP=17  DOWN= 3
```

Two things follow. First, the shortlist needs **direction balance** as a declared choice —
selecting top-*K* per direction rather than top-*K* overall, so a circuit that wants
`A AND NOT B` has a B to use. Second, since the balance that is *useful* depends on which
gate families a run can actually build, and `GeneSelector` has no business knowing about
gate families ([CLAUDE.md](../CLAUDE.md) §4 — nothing imports upward), **the pipeline
warns**: *"N of the M selected genes are down-regulated and no NOT-capable gate family is
available in this run."* One line, at the right layer, turning a silent empty result into
a stated limitation.

### 4.5 · The score, and what happens when an axis is missing

`SelectedGene.score` is stage 1's own ranking. It is **not** one of the nine metrics in
`DEFAULT_V1` — those are per-*design* and this is per-*gene* — so it does not go through
`engine.scoring`, and it must not be given one of the nine names.

The discipline still applies. Normalise each axis to 0–1, declare the weights in one
readable place, and — the part that matters — **combine only the axes that were actually
measured, renormalising their weights over what is present.**

```
score = Σ(wᵢ · normᵢ) / Σ(wᵢ)   over the axes that are not None
```

Substituting `0.0` for a missing axis is the exact failure [CLAUDE.md](../CLAUDE.md) §3
describes, one layer up: with no atlas, every gene's `condition_specificity` becomes 0.0,
the axis contributes a constant, and the weighting silently stops meaning what it says.
Renormalising is honest — a run with three of five axes is a run with three of five axes,
and the report should say which three.

Proposed starting weights, explicitly provisional and belonging to the scientific team:

| Axis | Weight | Missing when |
|---|---|---|
| separation (effect size, significance-aware) | 3.0 | never |
| abundance window | 2.0 | no abundance column — all public data |
| trigger yield | 2.0 | no transcript sequences — Q1 |
| non-redundancy | 1.5 | no counts, no sequences |
| condition specificity | 1.0 | no atlas — always, today |

---

## 5. Decisions this needs

Each has a recommendation. None of them blocks starting; all of them get harder to change
later.

**D1 — the signature.** `select(counts, dge)` cannot run on the product's own inputs (§3 G-a).
*Recommend:* `select(self, dge: DgeTable, *, counts: CountMatrix | None = None,
sequences: dict[str, str] | None = None) -> list[SelectedGene]`. The DE table is the one
required input; counts and sequences are optional and their absence removes axes rather
than failing. Updates needed in the same PR: [engine.md](engine.md) §3.1,
[api-surface.md](api-surface.md), [integration.md](integration.md).

**D2 — is a count matrix a product feature?** Separately from D1: do we ask for a second
upload? It is the only way to get per-group percentiles, sample clustering (S15), the
co-expression redundancy signal, **and the confusion matrix**. *Recommend:* yes, optional,
but as its own phase — and state plainly in the meantime that a one-file run cannot produce
a confusion matrix.

**D3 — no p-value at all.** Five of fifteen public comparisons have none. *Recommend:* run,
rank on the other axes, warn loudly. Refusing would make the E. coli catalog undesignable;
silently proceeding would present an unassessed ranking as an assessed one.

**D4 — shortlist size.** *Recommend:* `max_genes: int = 20`, as a `Constraints` field.
Stage 4 enumerates over these, so it is a compute-budget knob, and the docstring's "tens,
not thousands" should be a number the run records, not a constant in a file.

**D5 — does DE stay out of scope?** [integration.md](integration.md) flags the PyDESeq2
conflict. *Recommend:* keep it out — `stages/genes.py`'s docstring is right that CERNAL
filters and ranks DE results rather than producing them. But it makes D3 permanent: we will
keep receiving tables with no FDR and must handle them, not fix them.

**D6 — Q1, decided for one host.** A real `de` compile hitting the still-open Q1 blocker
(a user tried one and got the documented `InputValidationError`) forced this decision
rather than leaving it for later. *Decided:* bundle a real reference transcriptome —
fetched once, offline, checked into the repo (the same shape already established for
the plasmid backbone catalog and the public dataset catalog), starting with *E. coli*
K-12 MG1655 from NCBI RefSeq, over a live accession lookup at compile time (an
external dependency and failure mode on every `de` run, the opposite of this repo's own
stated provider philosophy) or requiring a second upload from the researcher (shifts
real effort onto them, and only works for organisms they can already source
themselves). Scope alongside it: single-gene circuits only for this pass — every
selected gene becomes its own one-gene circuit via the same construction the `direct`
path already used, not a `CircuitDesigner`-built multi-gene expression — deferring the
larger, still-mostly-stubbed remainder of `de` mode (`InputQualityCheck`,
`CircuitDesigner`, `ConfusionEvaluator`, real off-target scanning, `CodonOptimizer`,
stage 6) rather than attempting all of it at once. See §6 G8/G10 for what actually
landed.

**D7 — extending D6 to yeast and human, decided the same way.** Asked directly
("what about yeast and human?"), rather than assumed. *Decided, yeast:* extend the
transcriptome the same way (real NCBI RefSeq S288C, mechanically similar to *E. coli*
— yeast has almost no introns) and extend the promoter/terminator table with real,
iGEM-Registry-verified parts (`BBa_K124002`, `BBa_K1486025`) — but explicitly **not**
a bundled yeast backbone: yeast's real assembly grammar (the "Lim standard") could not
be fully verified from public sources in the time spent, and CLAUDE.md §1's rule — an
almost-right part is worse than a missing one — applies exactly as much to a backbone
as to a payload CDS. A yeast run relies on `params["backbone"]["custom_genbank"]` (a
real lab vector) or no backbone at all, both already-legal `_resolve_backbone` paths
requiring zero new code. *Decided, human:* stop, deliberately, rather than force a fit.
Two separate reasons, not one: Q1 needs actual mRNA/CDS transcript records for a
heavily-spliced genome (a different, bigger fetch than "another genome accession"),
and Q12 has no defined target at all — a mammalian expression plasmid is not
assembled via BioBrick-style restriction-site avoidance, so there is no "compliant
promoter" to pick without first deciding what compliance even means for that host.
That is a real architectural question for the scientific team, and is recorded as its
own open item rather than answered by default. See §6 G11–G13 for what actually
landed.

---

## 6. The plan

Ordered so that each step is testable when it lands. G1–G3 are prerequisites owned by
whoever is nearest; G4–G7 are the stage itself.

| # | Task | File | Depends on | Status |
|---|---|---|---|---|
| **G1** | `DgeRow.p_adj` → `float \| None` (`p_value` already is); add `base_expression`/`target_expression: float \| None` (the platform already recognises those column aliases; `DgeRow` has nowhere to put them). `SelectedGene`: `p_adj`, `control_percentile`, `condition_percentile`, `condition_specificity` → `\| None`; add `trigger_yield: float \| None` and `usable_windows: int \| None` | `engine/domain.py` | D1 | ✅ (named `control_mean`/`target_mean`, not `base_expression`/`target_expression` — a clearer domain name than the CSV column it's parsed from; docstring cross-references it) |
| **G2** | `Constraints` gains `max_genes: int = 20`, `max_separation: float \| None = None`, `min_base_expression`/`max_base_expression: float \| None = None`, `direction_balance: bool = True`. Nothing else needed — `_build_constraints` picks them up from the dataclass automatically | `engine/domain.py` | D4 | ✅ (plus `trigger_gc_range: tuple[float, float] = (30.0, 70.0)` for §4.2's screen, not anticipated when this table was first written) |
| **G3** | The parser (GAP-1): `input_path` → `DgeTable`, honouring `COLUMN_ALIASES`, emitting `None` for absent columns, never returning a DataFrame. Decide its module first — `engine/inputs.py` is the obvious answer | *new* | GAP-1 | ✅ `engine/inputs.py`, `parse_dge_table(raw: bytes, filename: str) -> DgeTable` — takes bytes rather than a path, so the platform decides how the file reaches it; unranked in the layer graph, like `store.py`/`artifacts.py` |
| **G4** | `GeneSelector.select` — axes 1 and 2, the tiered significance rule (§4.1), the abundance window, the effect-size floor and ceiling, deterministic sort with `gene_id` as final tiebreak | `engine/stages/genes.py` | G1, G2 | ✅ |
| **G5** | Trigger yield (§4.2). `MotifScreener` injected via `__init__`, built in `pipeline.build_tools` and shared with `TriggerScorer` — never constructed here. Drop genes with yield 0; drop genes absent from `sequences` and **count them**, so a namespace mismatch (G-d) is a named error not an empty list | `engine/stages/genes.py` | G4, Q1 | ✅ — `MotifScreener` injected, and now genuinely shared with a live `TriggerScorer` via `_de_trigger` (G8) |
| **G6** | Greedy non-redundant selection (§4.3), with whichever similarity signal is available and a clean skip when none is | `engine/stages/genes.py` | G4 | ✅ — implemented with the one signal that does not crash on a stub: a count matrix's per-sample correlation. The sequence-based (`OffTargetScanner.find_similar`) and locus-tag-adjacency signals from the table in §4.3 are not wired in — the first is itself an unimplemented stub, and calling it would crash the run outright rather than degrade gracefully |
| **G7** | The score (§4.5): weights in one table, renormalised over present axes, and the list of contributing axes reported | `engine/stages/genes.py` | G4–G6 | ✅ — reported via an `on_warning` callback (the same idiom `SwitchDesigner.design`'s `on_incompatible`/`on_invalid` already use), added during implementation since `select`'s return type has no room for warnings of its own |
| **G8** | Pipeline wiring: parse → `InputQualityCheck` → `GeneSelector` → `TriggerScorer`; the direction/constructibility warning (§4.4); every "axis not measured" warning surfaced on the run, not swallowed | `engine/pipeline.py` | G3–G7 | **Partially done**, scoped deliberately (a real decision, not a shortcut — see D6). `run_pipeline` now has a real `de` branch (`_de_trigger`): parse → `GeneSelector` → `TriggerScorer` → the same `SwitchDesigner`/`PlasmidBuilder` `direct` mode already uses, one gene's designs at a time rather than through a `CircuitDesigner`. **Still not done:** `InputQualityCheck` is not called (no count matrix exists to check, §3 G-a), and the gate-family-aware direction warning in §4.4 has no home yet — nothing today requests a NOT-capable family for a `de` run to warn about, since `antisense` is unconditionally skipped (`_UNBUILDABLE_FAMILIES`, Q11) regardless of input mode. Every "axis not measured" warning from `GeneSelector.select` **is** surfaced, via `on_warning` into `JobResult.warnings` |
| **G10** *(new)* | **Q1's first real answer, for one host.** A bundled reference transcriptome, not a live lookup — `tools/sync_transcriptome.py` fetches NCBI RefSeq accession `NC_000913.3` (*E. coli* K-12 MG1655, the same strain `stages/plasmids.py`'s promoter/terminator/backbone defaults already target) live, extracts every annotated CDS by locus tag, and writes `engine/data/transcriptomes/ecoli.fasta` (4,308 real genes, ~4 MB). `engine.transcriptome.load_transcriptome(host)` reads and caches it. CDS only, not a full transcript with UTRs — *E. coli* GenBank annotation carries no separate UTR features, so the CDS is the practical unit available; a stated limitation, not a hidden one | `tools/sync_transcriptome.py`, `engine/transcriptome.py`, `engine/data/transcriptomes/ecoli.fasta` | — | ✅ |
| **G11** *(new)* | **Q1, extended to yeast.** The same tool, extended to a multi-accession host: `tools/sync_transcriptome.py` fetches all 16 nuclear chromosomes (`NC_001133.9`–`NC_001148.4`) plus the mitochondrial genome (`NC_001224.1`) for *S. cerevisiae* S288C — every accession looked up live via NCBI esearch/esummary, not typed from memory — merges their CDS by locus tag (SGD's systematic ORF name, e.g. `YAL037C-A`, which is also what the public yeast catalog already uses as `gene_id`), and writes `engine/data/transcriptomes/yeast.fasta` (6,027 real genes, ~9 MB) | `tools/sync_transcriptome.py`, `engine/transcriptome.py`, `engine/data/transcriptomes/yeast.fasta` | G10 | ✅ |
| **G12** *(new)* | **Q12, extended to yeast.** Real promoter and terminator parts for yeast, verified against the same iGEM Registry API used for the *E. coli* parts — `BBa_K124002` (yeast GPD/TDH3 promoter, 681 bp, Mumberg/Muller/Funk 1995) and `BBa_K1486025` (ADH1 terminator, 188 bp) — byte-for-byte diffed against the raw API response before landing, not retyped by hand. Real biology, not a defect: both carry long homopolymer runs (yeast regulatory DNA is AT-rich) that `MotifScreener` correctly flags as informational, non-fatal compliance notes on every yeast plasmid — the same "report, never silently drop" behaviour the screener already gives every other host | `stages/plasmids.py` (`PROMOTERS`, `TERMINATORS`) | — | ✅ |
| **G13** *(new)* | **Q13 for yeast: deliberately not answered with a bundled default.** Yeast's real BioBrick-family assembly grammar (the "Lim standard", pRS-series vectors) could not be fully verified from public sources in the time spent — no new `BACKBONES` entry, no new `AssemblyStandard` member. `_resolve_backbone` already supports a lab's own real vector (`params["backbone"]["custom_genbank"]`, pre-existing `parse_custom_backbone`) or no backbone at all (its own documented "fully legal choice") — a yeast run uses one of those two paths today, requiring zero new code | — | — | **Not done, deliberately** (D7) |
| **G9** | Docs in the same PR: this file's status, [engine.md](engine.md) §3.1's signature, [ROADMAP.md](ROADMAP.md) E2 and Q2, [api-surface.md](api-surface.md) | `docs/` | all | ✅ (Q2 in ROADMAP.md is stage 2/3's own threshold question, not stage 1's — left alone) |

### Test plan — ✅ built

`tests/engine/test_genes.py` (24 tests) and `tests/engine/test_inputs.py` (17 tests),
both matching `tests/engine`'s no-Django, sub-second budget — every case below is
covered, plus the significance tiers (§4.1: `padj`/computed BH/raw fallback/none) and
the direction-balance behaviour (§4.4), which this original test-plan draft did not yet
list:

- **The §1 regression.** A fixture shaped like the `E-CURD-149` head — a huge-|log2FC| row
  with no p-value, one with p=0.06, one modest and clean — asserts the clean gene outranks
  all three.
- **A table with no `p_adj` selects genes anyway**, and the result carries the warning.
  This is the one that would have caught the empty-result failure in §2(a).
- **A missing axis is `None`, never `0.0`**, on every optional field — the same rule
  `test_house_rules.py` enforces for `evaluate_design`, asserted here by hand since
  `select` is not in `MEASURING_FUNCTIONS`.
- **Determinism:** shuffle the input rows, assert an identical shortlist. Ties, equal
  scores and `set` iteration all break this if the sort is not total.
- **Zero-yield genes are dropped**, and a gene missing from `sequences` is reported rather
  than crashing stage 2 (G-d).
- **Redundancy:** two perfectly correlated genes do not both appear in a shortlist of 2.
- **`max_genes` is honoured**, and no threshold appears as a module-level literal.

---

## 7. What this does not solve

- **Q1 stands for human.** Axis 3 and half of axis 4 are dark for any host with no
  bundled transcript sequences — *E. coli* and yeast now have one (D6, D7); human does
  not, and needs a different, bigger fetch (real mRNA/CDS records, an isoform choice)
  than "another genome accession". The design degrades to axes 1, 2 and 5 for human
  today — worth building, and honestly weaker.
- **No atlas, so no condition specificity.** `GeneSelector(atlas=...)` stays `None`, and
  "expressed in the target state but also everywhere in the body" remains unchecked.
- **No confusion matrix on a one-file run** (D2). The product's headline claim — *"is this
  a good circuit for telling these two cell states apart?"* — is not measurable from a DE
  table alone. Only §4's axes 1–5 are, and they are all predictions.
- **Contrast direction is unverifiable.** If a user's table is built the other way round,
  every UP/DOWN flips and the circuit fires in the wrong state. Nothing in the engine can
  detect this; the wizard already states the convention
  ([public-datasets.md](public-datasets.md) §5) and the report must repeat it.
- **The weights in §4.5 are provisional**, exactly as `DEFAULT_V1`'s are (Q6). They are
  written down so they can be argued with, which is the whole point of writing them down.
