# Evidence and reproducibility

Return to [documentation](../README.md) · [scientific interpretation](../scientific-interpretation.md) · [status](../status.md).

## Read evidence at the right level

| Level | What it establishes | What it does not establish |
|---|---|---|
| Source and unit/regression tests | Implemented computation and tested contracts at a revision | Biological efficacy, live operations or every environment |
| Controlled computational run | Output for stated inputs, parameters, model and revision | General performance or calibrated success probability |
| Comparison with experimental structure data | Association under the assay/dataset and analysis scope | Validation of completed RNA circuits or therapeutic effect |
| Deployment/real screening acceptance | Behavior in the measured provisioned environment | Other database versions, hosts or untested inputs |
| Wet-lab construct validation | Only the measured biological outcome and conditions | Every computational candidate |

CERNAL does not claim completed wet-lab validation of its generated circuits. Experimental
structure-dataset comparisons in the trigger logbook are narrower evidence and must retain
assay-specific interpretation.

## Evidence map

- [Documentation verification, 16 October](documentation-reorganization-2026-10-16.md): this change's checks and limits
- [Branch audit, 16 October](branch-audit-2026-10-16.md): open PRs, active branches, exact commits and unresolved alignment
- [Documentation source inventory](documentation-inventory.md) and [baseline file manifest](baseline-file-manifest.json): preservation accounting
- [Trigger-selection logbook](../trigger-selection-development-logbook.md): dated experimental structure-data comparisons, assumptions and incomplete benchmark work
- [Logbook assets and result tables](../assets/trigger-selection-logbook/): retained plots, CSV and JSON summaries
- [Software development log](../software-development-log.md): commit-based chronology and dated verification
- [Catalog smoke report](../catalog-pipeline-smoke.md), [machine-readable run](catalog-pipeline-smoke-2026-10-08.json), [pre-optimization run](catalog-pipeline-smoke-before-stage1-optimization-2026-10-08.json)
- [Final payload matrix](final-payload-matrix-2026-10-08.md), [JSON](final-payload-matrix-2026-10-08.json), [preserved harness](final-payload-matrix-harness-2026-10-08.py.txt)
- [Eligibility before](catalog-assembly-eligibility-before-2026-10-08.json) and [after](catalog-assembly-eligibility-after-2026-10-08.json)
- [Dependency advisory snapshot](dependency-advisories-2026-10-08.json) and [remediation verification](remediation-verification-2026-10-08.json)
- [F5 documentation evidence](audit-f5-documentation-2026-10-12.md): historical audit, including unverified dedicated GitLab hosting
- [QA evidence directory](../qa/): dated performance/security reports and original evidence ZIPs
- [Research notebooks](../../src/engine/gates/notebooks/README.md), [vendor provenance](../../vendor/ais-china-codon-optimization-v2/PROVENANCE.md), [datasets](../public-datasets.md)

## Reproduce, then describe

Record input checksums, host/reference release, code commit, dependency lock, model parameters,
seed, mode, thresholds, warnings, failed/rejected candidates and output checksums. Preserve raw
rows and the generating command alongside summaries. Keep compute revision separate from a
later report-render revision. Do not combine overlapping test totals, incomparable populations
or per-assay scales. A missing measurement remains missing, not zero.

Dated artifacts are retained unchanged; their claims remain scoped to their original baseline.
Historical instructions and superseded designs are indexed in the [archive](../archive/README.md).
Missing external datasets/results are identified as missing; their presence is never inferred
from a narrative. The pending barrier and IBBIS limitations are detailed in [status](../status.md).
