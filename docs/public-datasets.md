# Public transcriptomics dataset selection

**Status:** Built (Phase D, [ROADMAP.md §11](ROADMAP.md)). Every endpoint and file path
below was fetched and verified live against the real provider during development —
nothing here is assumed from documentation alone.
**Question it answers:** *can a researcher start CERNAL from a real, published
biological transcriptional state, not only their own upload?*
**Companion documents:** [`ROADMAP.md` §11](ROADMAP.md) is the task list this is a
subset of; [`ROADMAP.md` Q1](ROADMAP.md) is the *different* open question this
deliberately does not answer (see §7); [`architecture.md` §3](architecture.md) is the
Platform⇄Engine boundary this stays entirely on the Platform side of.

---

## 1. What this is, in one sentence

A curated catalog of 15 real public differential-expression comparisons (5 per
organism), each of which a researcher can browse — organism → experiment → comparison —
and load into the wizard exactly the way the existing bundled example dataset already
works: it materializes into a real, checksummed, validated `apps.datasets.Dataset` row,
indistinguishable from an upload from that point on.

```
EMBL-EBI Expression Atlas ──┐
                             ├──► sync_expression_catalog (offline, by a maintainer)
BV-BRC ──────────────────────┘         │
                                        ▼
                          apps/expression/catalog/  (checked into the repo)
                                        │  read-only, at request time
                                        ▼
                          apps/expression/services.py
                                        │  reuses apps.datasets.services.create_dataset
                                        ▼
                          apps.datasets.Dataset  ← the same row an upload produces
```

**The one architectural decision worth stating up front:** the running application
never calls a provider. `apps/expression/providers/` is imported by exactly one thing —
`manage.py sync_expression_catalog` — which a maintainer runs offline, ahead of time.
This is stronger than a live-query design on every axis the task brief asked about:
a provider being down, slow, or rate-limited can never affect a researcher using the
app (§8's error-handling requirement is satisfied by construction, not by a retry
loop), CI needs zero live network access, and the catalog stays exactly as small and
curated as whoever runs the sync command chooses to make it.

---

## 2. The three providers — what's real, what's verified

### 2.1 EMBL-EBI Expression Atlas (human, and yeast's actual backend)

`ExpressionAtlasProvider` (`apps/expression/providers/expression_atlas.py`) reads the
documented FTP mirror, never the HTML UI:

```
http://ftp.ebi.ac.uk/pub/databases/microarray/data/atlas/experiments/{accession}/
    {accession}-analytics.tsv          # Gene ID, Gene Name, {contrast}.p-value, {contrast}.log2foldchange
    {accession}-configuration.xml      # <contrast id="..."><name>'A' vs 'B'</name></contrast>
```

Experiment listing is `https://www.ebi.ac.uk/gxa/json/experiments`, filtered
**client-side** to `rawExperimentType == "RNASEQ_MRNA_DIFFERENTIAL"` for the requested
species.

**Two things discovered by testing, not assumed from the docs:**

- **`?species=`/`?experimentType=` on the JSON endpoint are silently ignored.** A
  request with those query parameters returns the entire cross-species, cross-type
  catalog regardless. Filtering happens in Python after the fetch.
- **A microarray experiment's analytics file is platform-suffixed**
  (`{accession}_{array-design}-analytics.tsv`, e.g.
  `E-GEOD-17367_A-AFFY-47-analytics.tsv`), discovered by listing the real FTP directory
  of an accession that 404'd on the plain filename. Filtering to
  `RNASEQ_MRNA_DIFFERENTIAL` (RNA-seq only, matching the task's own "RNA-seq
  differential expression" requirement) sidesteps this entirely rather than trying to
  discover the array-design suffix per accession.

**A real limitation, priced in rather than hidden:** the analytics TSV has **no
adjusted-p-value column at all** — only a raw p-value per contrast. Every row this
provider emits has `adjusted_p_value=None`. Reporting the raw value as if it were
already FDR-corrected would be exactly the kind of invented precision CLAUDE.md §3
warns against for the engine, applied here to a data-ingestion adapter instead.

### 2.2 BV-BRC (*E. coli*)

`BVBRCProvider` (`apps/expression/providers/bvbrc.py`) talks to the real, unauthenticated
JSON REST API directly — no FTP mirror exists here the way Atlas has one.

```
GET https://www.bv-brc.org/api/bioset/?keyword(Escherichia coli)&limit(500)
GET https://www.bv-brc.org/api/bioset_result/?eq(bioset_id,{id})&limit({page},{offset})
```

**Three things discovered by testing:**

- **The documented example query uses a value that does not exist.** `bv-brc.org/api/doc/bioset`
  shows `eq(bioset_type,differential_expression)`; the real, observed values are
  `"Differential"` and `"RNA-seq Differential Expression"`. Filtering here matches
  reality, not the doc.
- **RQL query parentheses must stay unencoded.** `requests`' `params=` dict
  percent-encodes `(`/`)` into `%28`/`%29`, which the API rejects with a 400. The query
  string is built and passed as a literal URL instead.
- **The comparison's real `"X / Y"` direction lives in `bioset_name`, not
  `treatment_name`.** `treatment_name` is frequently a single word (`"Ampicillin"`,
  `"pH"`) with no direction at all; `bioset_name` consistently reads e.g. `"0 min after
  Ampicillin (100 ug/ml) / 0 min before treatment"`. Found by fetching one real bioset
  record and reading every field, not by trusting either field's name.
- **The API truncates an overly large single response** rather than erroring —
  `limit(10000,0)` came back as invalid, cut-off JSON. Paging uses a conservative page
  size (500) and stops via the `Content-Range` response header's total count.

**A real limitation:** not every bioset carries a p-value at all — some report only
`log2_fc` and a `z_score`. All five curated *E. coli* comparisons in this catalog happen
to have **no p-value**; every row honestly reports `p_value=None` rather than a
fabricated one.

### 2.3 Yeast — yStreX confirmed unreachable, Expression Atlas used instead

yStreX (`ystrex.riken.jp`, `www.ystrex.org`) failed DNS resolution on every attempt this
session — not a timeout, not a 403, the domain simply does not resolve. Per the task's
own explicit fallback instruction ("reliability is more important than provider
purity"), `YeastExpressionProvider` (`apps/expression/providers/yeast.py`) wraps
`ExpressionAtlasProvider` scoped to *Saccharomyces cerevisiae*.

Verified: only **13 of Atlas's yeast experiments** are RNA-seq differential (the same
`RNASEQ_MRNA_DIFFERENTIAL` filter as §2.1) — the rest are older microarray studies the
same filename gotcha excludes. A real, small, working pool, not a workaround dressed up
as one. Nothing outside `yeast.py` imports `ExpressionAtlasProvider` for anything
yeast-related — if a working yStreX endpoint appears later, only this one file changes.

---

## 3. The curated catalog

Exactly the 15 entries `apps/expression/catalog/manifest.json` records, one comparison
per experiment (the first contrast an experiment's configuration lists — enumeration
order, not a significance ranking). Every accession is real and citable at its
`source_url`.

| Organism | Category (task brief §8) | Accession | Comparison |
|---|---|---|---|
| Human | Inflammatory response | `E-CURD-149` | bacterial disease vs normal |
| Human | Cancer vs normal | `E-CURD-45` | neoplasm vs adjacent normal tissue |
| Human | Immune activation | `E-GEOD-103501` | growth medium stimulation vs none |
| Human | Differentiation | `E-GEOD-54112` | ZNF804A knockdown vs control (neural progenitor) |
| Human | Hypoxia | `E-MTAB-2580` | hypoxic vs normoxic condition |
| Yeast | Osmotic stress | `E-MTAB-5313` | 0.4 M NaCl, 15 min vs 0 min |
| Yeast | ER stress / UPR | `E-MTAB-10511` | isw1Δ vs wild type, unfolded protein response |
| Yeast | Nutrient depletion / growth phase | `E-MTAB-7657` | 14 h vs 6 h glucose consumption |
| Yeast | Nitrogen source / nutrient response | `E-MTAB-4651` | DAL81 deletion vs wild type |
| Yeast | Metabolic engineering | `E-GEOD-59814` | acetyl-CoA synthetase-deficient vs wild type |
| *E. coli* | Heat shock | bioset `67644164` | heat-shocked 15 min vs recombinant T0 |
| *E. coli* | Oxidative stress | bioset `44313016` | aerobic pH 8.7 vs pH 7.0 |
| *E. coli* | Antibiotic treatment | bioset `42635036` | ampicillin (100 µg/mL) vs untreated |
| *E. coli* | Nutrient limitation | bioset `68952326` | thymineless vs control |
| *E. coli* | Growth-condition change | bioset `44541816` | anaerobic vs 15 min oxygen exposure |

**A discovered gap worth being honest about:** yeast's real, working RNA-seq pool
(§2.3) skews toward genetic/mutant studies rather than classic environmental-stress
panels — no working "heat shock" or "drug response" (doxorubicin, imatinib, metformin)
experiment exists in Atlas's RNA-seq-only set; every candidate tried for those two
categories 404'd for the reason in §2.1. Labels above describe what each entry actually
is rather than forcing a mismatched category name onto it.

Each comparison's stored CSV is capped at **3,000 genes, ranked by |log2FC|** — a
comparison can hold a whole transcriptome (human: ~58,000 measured; *E. coli*: ~4,000
genes), and the API's own preview endpoint (§4) already caps what it renders at 2,000,
so storing much past that buys nothing and works against "keep the catalog
intentionally small."

---

## 4. The normalized schema and the API surface

Every provider's raw response becomes one shape
(`apps/expression/providers/normalize.py:NormalizedDeRow`) whose field names are the
exact canonical columns `apps.datasets.services.COLUMN_ALIASES` already recognises:
`gene_id, gene_symbol, log2fc, pvalue, padj`. A materialized public dataset is
byte-for-byte a CSV in this shape — it goes through `create_dataset` unchanged, so it
gets the same checksum, validation, and storage guarantees an upload gets.

```
GET  /api/public-datasets/organisms
GET  /api/public-datasets/experiments?organism=ecoli
GET  /api/public-datasets/comparisons?experiment=ecoli__88048
GET  /api/public-datasets/{comparison_key}          # the info card
POST /api/public-datasets/materialize {comparison_key}  -> {201: Dataset}
GET  /api/datasets/{id}/preview                     # shared with uploaded datasets
```

`DatasetOut.provenance` is `null` for a plain upload and a full
`DatasetProvenance` object (provider, accession, comparison, source URL, retrieval
date, gene/p-value counts) for anything materialized from the catalog — one response
shape either way, one optional field telling them apart.

---

## 5. The wizard

`compile.tsx`'s Input Mode has three top-level routes — **Differential Expression**
(unchanged, now with a **Public Dataset** / **Upload Your Own** sub-choice),
**Direct Trigger mRNA** (unchanged), and **Specific Gene** (new, informational).

The public-dataset picker is scoped to the wizard's own top-level organism selector —
there is no second organism dropdown inside it, so a human public dataset can never sit
next to an *E. coli* design organism. Selecting a comparison shows the info card
(§12 of the original brief) including the explicit direction callout — *"positive log2FC
= higher in \<experimental condition\>"* — since that is, per the brief, one of the
easiest and most dangerous mistakes in differential-expression interpretation.

Once any dataset is selected — public or uploaded — an expression-profile preview
appears: "Loaded N genes," a volcano plot (log2FC vs −log10 FDR, genes with neither a
p-value nor an FDR left off the plot rather than plotted at a fabricated y=0), and a
searchable, sortable, direction-filterable table.

---

## 6. Specific Gene — deliberately informational

Selecting a gene records `{organism, geneId, geneSymbol}` and hands the researcher to
Direct Trigger mRNA to paste the actual sequence, with a pinned banner showing which
gene the pasted sequence is for. **No gene→sequence lookup exists.** This was a
deliberate scope decision, not an oversight — see ROADMAP.md's Phase D, task D6, for
why: even with a resolved sequence, only *E. coli* has real promoters, terminators,
payloads and a backbone catalog today (Q11–Q13 are still open for human and yeast), so
a resolved human or yeast gene would still dead-end at plasmid construction. Revisit
alongside those questions, not in isolation.

---

## 7. What this does *not* change

**Q1 is still open.** [`ROADMAP.md`](ROADMAP.md)'s Q1 asks where *trigger sequences*
come from — a reference transcriptome, an accession lookup, user-supplied FASTA. This
phase answers a different, upstream question: where a **differential-expression
table** comes from. A public dataset materializes into the exact same `Dataset` row an
upload produces, which still hits `engine/pipeline.py`'s unconditional
`InputValidationError` for anything but `input_mode == "direct"` — confirmed by reading
that check before writing anything here. Submitting a `de`-mode run against a public
dataset behaves under `LocalEngine` exactly as it does today against an uploaded one:
it fails cleanly, for the same documented reason. Under `MockEngine` (the default
everywhere in dev, test and CI), both run to completion identically, since `MockEngine`
never reads `input_mode` at all.

---

## 8. How to add another organism or provider

1. Write `apps/expression/providers/<name>.py` exposing whatever shape is natural for
   that source, and a `normalize_*` function producing `NormalizedDeRow`/
   `NormalizedComparison`/`NormalizedExperiment` (`providers/normalize.py`). Test it
   against a captured real response first — see `tests/test_expression_providers.py`
   for the pattern (fixture responses, no live network in the test itself).
2. Add entries to `CURATED_EXPERIMENTS` in
   `apps/expression/management/commands/sync_expression_catalog.py` and run
   `uv run python manage.py sync_expression_catalog --only <organism>`. Inspect the
   generated `manifest.json`/CSVs before committing them — every entry must trace to a
   real, fetched accession.
3. If it's a genuinely new organism (not human/yeast/*E. coli*), add it to
   `apps/expression/services.py:ORGANISMS` and to the wizard's own `ORGANISMS` array in
   `frontend/src/components/compile/Steps.tsx` — these are intentionally two small,
   explicit lists (task brief §3: "do not build a universal organism system yet"), not
   one shared config, because the wizard's organism also drives gate-family
   availability and plasmid parts that have nothing to do with this catalog.

Nothing else changes. `apps/expression/services.py`, the API router, and the frontend
components all read the catalog generically — none of them branch on provider identity
(CLAUDE.md's "CERNAL core should never contain `if source == "BV-BRC"`", satisfied by
construction: that branch exists exactly once, in the sync command, which is not core).
