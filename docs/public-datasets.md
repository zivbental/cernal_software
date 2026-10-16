# Public transcriptomics catalog

Source baseline: `c1bb92cc085a6bad272298b81bda28c22b1d57f5` (16 October 2026).
See [status](status.md) for release evidence and pending work.

The application loads curated, checked-in DE comparisons. It does not query public
providers while a researcher browses or loads the catalog. Public data provenance and
statistical completeness are separate from downstream reference mapping and efficacy.

## Stored data and runtime path

The [catalog manifest](../src/apps/expression/catalog/manifest.json) identifies 15
comparisons: five each for E. coli, yeast and Human. C. acnes currently has no curated
public profile; upload, direct sequence and reference lookup remain available.

[`apps/expression/services.py`](../src/apps/expression/services.py) loads a selected
comparison through the existing dataset-creation path, preserving the stored bytes,
checksum and validation evidence. The resulting dataset feeds the same `de` pipeline as
an upload. API preview limits are presentation limits, not permission to truncate the
analysis table.

The original catalog CSVs are historical subsets selected by absolute log2 fold change,
up to 3,000 rows. Their original tested-row totals were not recorded. The manifest labels
this `historical_subset_source_total_unknown`, with retained rows, statistic coverage,
checksums and normalization metadata. Do not infer a complete tested universe, invent
adjusted p-values or claim all genes in an experiment are represented.

## Providers and refresh workflow

Offline maintenance uses `manage.py sync_expression_catalog` and provider adapters under
[`apps/expression/providers`](../src/apps/expression/providers):

- Expression Atlas supplies Human and the implemented yeast backend using experiment
  configuration and analytics tables.
- BV-BRC supplies the curated E. coli comparisons.
- The yeast wrapper uses Expression Atlas; historical yStreX connectivity investigations
  are preserved in the archive, not treated as a current live-service outage claim.

Current refresh behavior retains provider-tested rows rather than imposing the historical
3,000-row analysis cap. Preserve source accessions, exact comparison, reference/test
conditions, common context, checksum, retrieval time and missing-statistic counts.
Source-tested rows can exclude missing fold-change values and do not mean every gene
was experimentally measured. A refresh must not rewrite past run inputs or metadata.

## Biological interpretation

A study title is not a contrast. Use the manifest's selected comparison and sample
context, with positive fold change defined relative to its explicit reference/test
conditions. The retained E-GEOD-103501 `g3_g1` comparison concerns normal monocyte Growth
Medium versus none/ex vivo; it is not arthritis versus healthy or LPS stimulation.
[Catalog governance](catalog-governance.md) provides the retained primary evidence and
separate disease-contrast distinction.

The source manifest is the authoritative inventory of accessions and provider links.
Earlier category labels and provider investigations remain available in the historical
record, but must not override exact selected conditions. Biological interpretation review
and real integration smoke coverage remain distinct requirements from metadata tests.

## Statistical and reference limitations

Missing p-values stay missing. A raw p-value is not an adjusted p-value. The historical
subsets cannot establish FDR control merely by applying Benjamini–Hochberg to their
retained rows. See [gene selection](genes.md) for the complete-universe requirement.

Loading a valid CSV does not prove ID mapping or isoform coverage. Unmatched/ambiguous
identifiers and duplicate aliases require explicit reporting and non-inflating handling.
All four hosts have reference routes, but reference scope differs and non-Human bundled
records are CDS-only. No public comparison is a calibrated cellular classifier.

## Historical evidence

The [preserved design and development record](archive/scientific-design/public-datasets.md)
contains earlier measurements, alternatives and decisions. It is historical evidence,
not current implementation guidance.
