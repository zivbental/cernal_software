# Real public-catalog pipeline smoke — 8 October 2026

All fifteen bundled comparisons ran through `LocalEngine` using their real retained
CSV files and matching source SHA-256 digests. The recorded current snapshot is
`f899e674e8dd17e989088fba429b30b449d92509` / `local-0.11.0-scientific-qa`.
The parameters use default scientific filters, seed 42, `constraints.max_genes=3`,
`budget.max_designs=1`, a short valid synthetic custom CDS, and no backbone.

The [current detailed inventory](evidence/catalog-pipeline-smoke-2026-10-08.json)
records terminal status/error, mapped/unmapped/statistical row counts, the
pre-inversion stage-1 shortlist, candidate/accepted/rejected counts, warnings,
effective request parameters, candidate metrics and construct digests, tool/profile
versions, source provenance, stage timings and source checksums. All fifteen
computations succeeded: fourteen had one accepted computational candidate;
`yeast__E-GEOD-59814__g1_g2` completed with an empty result. An empty successful
result is distinct from an engine error. Historical catalog subsets with unknown
source hypothesis universes are explicitly declared incomplete; no new BH correction
is inferred from retained raw p-values.

This tests source ingestion, reference matching and bounded computation. It does not
establish full default-budget behavior, disease selectivity, wet-lab efficacy,
physical multi-input implementation, or sequence-release eligibility. The selected
arthritis contrast is a healthy-monocyte culture comparison, as documented in
[catalog governance](catalog-governance.md). No C. acnes public comparison is bundled.

The [earlier complete inventory](evidence/catalog-pipeline-smoke-before-stage1-optimization-2026-10-08.json)
preserves exact per-comparison snapshots and had five productive / ten empty outcomes.
The recorded shortlist gene IDs, symbols, effects and directions agree for all
fifteen comparisons before and after the exact stage-1 scan optimization. In one
3000-row E. coli comparison, the earlier real pipeline spent 77.5 seconds selecting
genes, 0.57 seconds scoring shortlisted triggers and about 0.06 seconds designing and
reporting. The separate stage-1 inventory added 63.7 seconds. The current full
inventory took 52.6 seconds initially and 68.7 seconds while a legacy diagnostic ran
concurrently; these timings are observations, not a calibrated estimate.

The accepted-count change is explained by assembly eligibility policy in engine
commit `75755e4`, independently of stage-1 performance. A fresh matched
[old-engine diagnostic](evidence/catalog-assembly-eligibility-before-2026-10-08.json)
and [current diagnostic](evidence/catalog-assembly-eligibility-after-2026-10-08.json)
for Human `E-CURD-149 / g3_g1` produced the identical construct digest and all nine
identical raw metrics. The old candidate was rejected for source-part homopolymers
`Gx6@905` and `Tx7@1105`; the new candidate retains these exact caveat warnings and
is computationally eligible. Default scoring-profile source is unchanged. Effective
request parameters differ only by newly normalized `payload.optimize_codons=false`;
the identical construct digest confirms the sequence did not change.

Frame failures, user-forbidden motifs and newly generated assembly restriction sites
remain hard exclusions. Source homopolymers and pre-existing vector sites remain
visible assembly caveats. Acceptance does not authorize release or provide a cloning
protocol; screening/release holds remain separate.

Reproduce from the reviewed checkout using an isolated output location:

```sh
UV_CACHE_DIR=/tmp/cernal-qa-uv PYTHONPATH=$PWD/src \
  uv run --offline --no-sync python tools/catalog_pipeline_smoke.py \
  --output /tmp/cernal-catalog-smoke.json
```

The manual tool writes only temporary engine artifacts and the requested JSON report;
it does not access Django or change database/media records. `--catalog-key` can be
repeated to partition work. Give each process a distinct report path; merge with
`tools/merge_catalog_smoke.py REPORT... --output MERGED.json`, which rejects duplicate
comparisons and inconsistent parameters/catalog digests and preserves source
revisions per comparison. The earlier three-process run used eight available CPUs,
about 5.2 GB available memory and measured about 300–336 MB RSS per worker.
