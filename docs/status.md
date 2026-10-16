# Capability and branch status

Current documentation baseline: main
[`66a6d265577810e8943709f3e5bb21bffdab212c`](https://github.com/zivbental/cernal_software/commit/66a6d265577810e8943709f3e5bb21bffdab212c),
16 October 2026, after PRs 68, 69, 81 and 82 merged. Query `/api/version` on the
installed build; a merge does not imply deployment or biological validation.

## Implemented on main

| Area | Supported behavior | Boundary |
|---|---|---|
| Inputs | Direct sequence, reference gene and DE table; E. coli, yeast, Human, C. acnes | No raw-count DE inference |
| Single-input design | Real ViennaRNA, trigger discovery, toehold design, scoring and assembly | Computational proxies, not calibrated efficacy |
| Eukaryotic AND | One two-input gate for Human/yeast DE runs, selected up-regulated genes, saved AND diagnostics | No mixed families or general multi-gate compiler; see [AND guide](and-gate.md) |
| Reports and provenance | Replay identities bind inputs, folding model, sampling and jobs; original saved provenance is retained | Legacy or mismatched replay files are rejected |
| Screening UI | Optional evidence/status panel, identity/expiry checks and preserved download guards | Main backend omits the proposed operational evidence envelope; Not screened is expected |
| Release controls | Fail-closed release/disclosure policy | Unconfigured screening holds sequences; operational IBBIS adapter remains branch-only |
| Interfaces | React, HTTP API, Python/R/MATLAB source clients | MATLAB runtime verification and package publication remain separate |
| Research | Offline prokaryotic/generic AND, CRISPR and other workbenches | Source presence does not advertise application support |

Engine provenance is `local-0.13.0-scientific-qa-trigger-footprints`, reflecting explicit
50-nt trigger support. Default single-input windows remain unchanged. Public constraints
exclude `closure_set`, `stem_order` and `stems_per_pair`; `closure_set` is rejected even
with `strict=false`. [NucSyn](nucsyn.md) remains an external research-data source, not a
bundled runtime or production adapter.

## Merge and validation receipts

| PR | Merge commit | Backend CI |
|---|---|---|
| [68](https://github.com/zivbental/cernal_software/pull/68) | `bf76916f18366f20780589d388facf0276e76adb` | [2,603 passed](https://github.com/zivbental/cernal_software/actions/runs/38859864837) |
| [69](https://github.com/zivbental/cernal_software/pull/69) | `907a359ee4d7c17f009d254225d289e5cb37be60` | [2,501 passed](https://github.com/zivbental/cernal_software/actions/runs/38858389322) |
| [81](https://github.com/zivbental/cernal_software/pull/81) | `a907d28d621c3469604d47dd93b1d6c8a420f855` | [2,671 passed](https://github.com/zivbental/cernal_software/actions/runs/38859925891) |
| [82](https://github.com/zivbental/cernal_software/pull/82) | `66a6d265577810e8943709f3e5bb21bffdab212c` | [2,993 passed](https://github.com/zivbental/cernal_software/actions/runs/38862117957) |

Each backend run also passed 110 subtests with one platform-specific skip. Active
frontend/browser, Python/R client and auxiliary workflows passed. Manual/scheduled
Windows-supervisor and dependency-advisory lanes were not exercised by these PR runs.
Independent reviews covered the fixes and integration. The former frozen-dataclass test
mismatch was corrected by testing an actual field; its older recorded failure is historical.

## Remaining research and operational acceptance

**Eukaryotic AND:** application ranking uses the weighted engine profile, not only
ON-OFF. Application and notebook controls differ; AND folding uses the first 30 payload
nucleotides. Structural leakage/dynamic-range values are proxies, not measured translation.
Shared measurement code does not promise numerical equivalence between different runs.

**Model evidence:** corrected barrier CSVs and `docs/assets/axes_c8/rows.csv` are not
versioned at this baseline. The [accepted model snapshot](wiki/and-gate-model.html)
explicitly withholds quantitative figures/correlations pending those inputs and producer,
model/sampling and checksum provenance. Historical summaries are preserved, not endorsed
as independently reproduced results. Path-search energies are not experimental kinetic rates.

**IBBIS:** `dot/ibbis-final-output-screening` remains a separate operational adapter
branch, not part of this main baseline. Its earlier [dated audit](evidence/branch-audit-2026-10-16.md)
is historical. Real-tool benchmarking is a separate ongoing task; this documentation
update does not establish final benchmark acceptance, complete construct coverage,
contract reconciliation, production provisioning or activation. The merged UI is not
proof that Common Mechanism ran. No production manifest is inferred here.

## Historical records and publication boundary

The [04:50 branch audit](evidence/branch-audit-2026-10-16.md), original documentation
checks and [archive](archive/README.md) retain their original observations. Their
then-open PRs and old test failures are not current blockers. This page supersedes
those snapshots for current merge/capability status.

Deployment, screening activation, registry publication, wiki publication and biological
validation are distinct outcomes. This separate documentation branch performs none of
them. [Release decisions](release-decisions.md) and [roadmap](ROADMAP.md) retain remaining
acceptance work. Scientific data and NucSyn citation/license qualifications are preserved.
