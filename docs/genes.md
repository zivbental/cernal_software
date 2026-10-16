# Gene selection and reference resolution

Source baseline: `66a6d265577810e8943709f3e5bb21bffdab212c` (16 October 2026).
See [status](status.md) for release evidence and pending work.

CERNAL consumes differential-expression results; it does not calculate DE from raw read
counts in the application workflow. A shortlist allocates a finite downstream design
budget and must preserve evidence about what was and was not measured.

## Input and significance

[`inputs.parse_dge_table`](../src/engine/inputs.py) normalizes supported table columns and
preserves missing values. The pipeline verifies the stored input checksum, resolves IDs
against the chosen host, and supplies the table and bundled sequences to
[`GeneSelector.select`](../src/engine/stages/genes.py).

The implemented significance tiers are:

1. Use supplied adjusted p-values when available; a missing per-row value remains missing.
2. Compute Benjamini–Hochberg correction from raw p-values only when the tested hypothesis
   universe is explicitly complete and raw p-value coverage is 100%.
3. Otherwise use raw, uncorrected p-values with an explicit warning that selection is not
   FDR controlled.
4. If no p-values exist, warn that significance was not assessed.

Do not claim FDR control for historical top-fold-change subsets. The
`statistics.hypothesis_universe_complete` declaration must describe the actual tested
universe, not merely a syntactically complete CSV. See [catalog governance](catalog-governance.md).

## Selection and limits

The selector applies configured separation/significance and sequence-related criteria,
then ranks a deterministic shortlist. Duplicate canonical gene IDs use first occurrence
with a warning; unmatched references are reported. Cheap trigger-yield screening estimates
the fraction of windows compatible with motifs, start-codon and GC constraints before
expensive folding. It is not a complete switch validator.

The selector has optional count/atlas-based axes, but the production DE route supplies
neither a sample count matrix nor a cell atlas. It cannot infer sample-wise discrimination,
absolute expression suitability or redundancy from fold change alone. Missing axes remain
unmeasured rather than passing by default.

After statistical selection, the pipeline excludes DOWN-regulated genes with an explicit
warning: an activating toehold cannot invert that signature and no production NOT compiler
exists. Selected transcripts over the 10,000 nt compute limit are reported and not folded.
Survivors use the same [trigger scorer](triggers.md) as direct/named-gene input.

## Bundled references

Reference sequence and metadata files live under
[`src/engine/data/transcriptomes`](../src/engine/data/transcriptomes).
[`transcriptome.py`](../src/engine/transcriptome.py) owns loading, identifier resolution,
reference lookup and provenance.

| Host | Reference | Selection scope |
|---|---|---|
| E. coli | K-12 MG1655, `NC_000913.3` | Bundled reference CDS |
| C. acnes | ATCC 6919, `NZ_CP044255.1` | Bundled reference CDS; ambiguous aliases retained explicitly |
| Yeast | S288C nuclear chromosomes and mitochondrial record | Bundled reference CDS; exact versioned accessions in `yeast.json` |
| Human | Ensembl release 116, GRCh38.p14 | Mature transcript selection: MANE Select, then Ensembl canonical, then longest transcript, then transcript ID |

Human reference metadata pins sequence SHA-256
`8087a33315c23e8267a975bd5abe3cea354830d6e50e76eb7d441d7de18913d1`.
Non-Human CDS references do not include full UTR/isoform biology. A deterministic Human
representative does not prove that isoform is expressed in the user's sample.

All four hosts support `direct`, `gene` and `de` application modes. Named-gene lookup
checks a frozen sequence against the reference and records transcript ID, accession,
selection method and sequence digest. It supplies no observed expression contrast.
Changing a reference must not silently rewrite a previous run's scientific identity.

## Checks and interpretation

Relevant coverage includes `tests/engine/test_genes.py`,
`test_gene_selection_performance.py`, and reference/input integration tests. Numerical
regression tests verify selection logic; experimental specificity and observed confusion
matrices require appropriate biological data. [Public datasets](public-datasets.md)
explains catalog provenance; [scientific interpretation](scientific-interpretation.md)
explains downstream scores.

## Historical evidence

The [preserved design and development record](archive/scientific-design/genes.md)
contains earlier measurements, alternatives and decisions. It is historical evidence,
not current implementation guidance.
