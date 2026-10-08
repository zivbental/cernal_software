# Public catalog governance and contrast verification

Recorded 8 October 2026. A study title describes a whole experiment; the selected
contrast determines each bundled DE table's biological interpretation and log2FC
direction. Software execution does not establish a disease classifier.

The retained table checksums, row counts, raw/adjusted p-value counts, normalization
version and subset status live in `apps/expression/catalog/manifest.json` and are
shown before loading a public profile. The original 15 tables were historically
limited to up to 3,000 rows ranked by absolute log2FC. Their original tested-row totals
were not recorded, so current metadata explicitly reports an historical subset with
unknown source total. No existing CSV values or gene identifiers were changed during
this remediation. A future catalog sync retains all provider-tested rows; preview
limits remain display limits. Source-tested rows exclude provider rows with missing
log2FC and do not imply every gene was experimentally measured.

## Verified selected arthritis-study contrast

The [primary Expression Atlas configuration](https://ftp.ebi.ac.uk/pub/databases/microarray/data/atlas/experiments/E-GEOD-103501/E-GEOD-103501-configuration.xml)
was retrieved on 8 October. Its complete source snapshot and checksum are retained
under [evidence](evidence/expression-atlas/E-GEOD-103501-configuration.xml).

| Selected item | Exact provider meaning |
|---|---|
| Accession and contrast | E-GEOD-103501, g3_g1 |
| Experimental/test group | g1, normal; Growth Medium, four SRR assays |
| Reference group | g3, normal; none, five SRR assays |
| Shared sample context | normal, applying to both sides |
| Fold-change direction | Positive means higher in the Growth Medium test group than the none reference group |
| Interpretation | Healthy/normal monocyte culture-medium condition compared with ex vivo/none; not arthritis versus healthy and not LPS stimulation |
| Separate disease contrast | g1_g4 compares disease versus normal within Growth Medium; it is not the selected bundled table |

The GEO [series metadata](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE103501)
describes healthy and disease samples, cultured and ex vivo groups, and LPS treatments.
The [healthy medium sample record](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSM2772484)
identifies cultured monocytes at six hours. These primary records support the context;
the contrast's exact assay grouping/direction comes from Atlas configuration. Atlas
reanalysis metadata and the original study's analysis methods must not be treated as
interchangeable provenance. No missing adjusted p-values were inferred or synthesized.

The parser now separates the common context from each contrasted condition, and
preserves time qualifiers without stray quote fragments. The raw comparison label
remains available unchanged. Regression tests pin this selected contrast to its exact
reference/test groups and distinguish the separate disease comparison.

## Refresh and review requirements

A data steward still needs appointment and biological interpretation review remains
pending. Refreshes require source accessions, download/checksums, sample/strain/tissue
context, contrast direction, row/statistic completeness and pinned reference versions.
Existing run snapshots must continue to identify their exact stored input bytes;
new catalog files must never rewrite historical user datasets or run metadata.

Mapping coverage, unresolved IDs and alias/isoform decisions are separate from CSV
integrity. Preserve unresolved and ambiguous IDs; reference availability is not complete
mapping and must not silently select another species. Duplicate aliases need a
non-inflating policy reviewed with the engine's selection logic. Every catalog entry
still needs a real integration smoke and scientific contrast review; the deterministic
metadata tests alone do not satisfy those biological acceptance criteria.

C. acnes has no curated public profile in the current catalog. The interface explicitly
points users to upload, direct sequence or reference lookup. No new organism dataset
or phenotype label was invented. Further non-Human UTR and user-reference import
support needs its own approved scope.
