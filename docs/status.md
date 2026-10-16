# Capability and branch status

Snapshot: **16 October 2026, 04:50 UTC**. Current documentation describes main
[`c1bb92cc085a6bad272298b81bda28c22b1d57f5`](https://github.com/zivbental/cernal_software/commit/c1bb92cc085a6bad272298b81bda28c22b1d57f5).
PR 80 merged the October 12 remediation, including PRs 70–79. Status is a snapshot,
not a promise about later branch heads. Query `/api/version` on the installed build.

## Implemented on main

| Area | Supported behavior | Boundary |
|---|---|---|
| Inputs | Direct sequence, named reference gene, differential-expression table; E. coli, yeast, Human, C. acnes | No raw-count differential-expression inference |
| Scientific application | LocalEngine, real ViennaRNA, trigger discovery, single-input toeholds, scoring and assembly | One input and one gate; not a general multi-input compiler |
| Outputs | GFP/custom coding sequences, run records, diagnostics and artifact provenance | Computational candidates; not calibrated efficacy or synthesis authorization |
| Release controls | Fail-closed release/disclosure policy | Unconfigured screening holds sequences; IBBIS branch is not on main |
| Interfaces | React, HTTP API, Python/R/MATLAB source clients | Native MATLAB runtime verification and package publication remain separate |
| Research | Offline gate/CRISPR/accessibility workbenches and preserved results | Presence in source does not make a production capability |

[Methods and interpretation](scientific-interpretation.md), [API](public-api.md),
[testing](testing.md) and [evidence](evidence/README.md) explain what each statement means.

## Open work, not merged capabilities

| Work | Exact inspected head | Meaning and remaining work |
|---|---|---|
| [PR 68: eukaryotic stem-opening reports](https://github.com/zivbental/cernal_software/pull/68) | `55272c5ef50ea04d32098465ad9b1e31dd0c59e8` | Notebook/report and folding-helper work; no application selection on main |
| [PR 81: selectable eukaryotic AND](https://github.com/zivbental/cernal_software/pull/81) | `64a29c24bfd020d75952ecfde6adf6ec486a9764` | Stacked on PR 68, not main. Exactly one two-input Human/yeast AND in DE mode; app integration pending |
| [PR 69: screening UI](https://github.com/zivbental/cernal_software/pull/69) | `2d50e23cc75c3fee151ccb0524ab36e389dc8069` | Draft evidence UI/contract; does not invoke Common Mechanism |
| [PR 82: prokaryotic AND/model work](https://github.com/zivbental/cernal_software/pull/82) | `78d988757c42f57948f82dc3a595bccf2f1cc78e` | Separate research branch; conflicts reported. Corrected barrier code, incomplete canonical result tables |
| [IBBIS final-output adapter](https://github.com/zivbental/cernal_software/tree/a2d6503c09d927e48f4c90f9c7af3953921e529e) | `a2d6503c09d927e48f4c90f9c7af3953921e529e` | Two commits ahead of main; no open PR. Synthetic software checks, no real-tool/database benchmark or production activation |
| [AND wiki overview](https://github.com/zivbental/cernal_software/tree/680bab6dcbe81a742555b5314b94fe6685027066) | `680bab6dcbe81a742555b5314b94fe6685027066` | Separate publication material, not implementation acceptance |

The [full audit](evidence/branch-audit-2026-10-16.md) records all four open PRs, all 43
visible branch heads, compared branches, source links and verification limits. Old provenance,
visualizer and CRISPR branches already contained in main are not counted as pending features.

## Scientific cautions for pending work

**Eukaryotic AND:** PR 81 app ranking uses the engine's weighted profile, not only ON−OFF;
app controls and notebook controls differ. Its folding context includes the first 30 payload
nucleotides, not the whole payload. Structural leakage/dynamic-range values are proxies,
not measured translation. Do not promise numeric equivalence with notebook runs or NucSyn.
A NucSyn release is not evidence of CERNAL integration.

**Barriers:** PR 82's corrected estimate is the maximum evaluated energy along the
searched path minus the starting energy. The endpoint difference is not a barrier.
The corrected canonical `docs/assets/barrier/` row CSVs are absent at the inspected head;
reported ranges/correlations have not been independently reproduced from those rows.
Other CSV files do not establish equivalent provenance. Do not promote its summaries to
verified results. A path-search estimate is not an experimental kinetic rate.

**IBBIS:** Branch checks cover adapter and release-policy behavior using synthetic inputs.
Parser timings exclude actual executable/database search. Full approximately 40 GB database
benchmarking remains unmeasured. Database licensing, provisioning, exact-head broad verification,
operator policy and frontend/backend contract reconciliation remain acceptance work.
No production manifest should be inferred from this status page.

## Publication and acceptance

Main integration, public deployment, screening activation, registry publication, wiki publication
and biological validation are distinct outcomes. This documentation branch changes none of
those runtime or external states. [Release decisions](release-decisions.md) retains required
human decisions; [roadmap](ROADMAP.md) captures unresolved outcomes.
