# Pending-feature audit

> Historical snapshot: PRs 68/69/81/82 have since merged. See [current status](../status.md) for accepted scope and CI receipts; original findings below are preserved.

Snapshot: 2026-10-16 04:50 UTC. Read-only GitHub connector inspection. Baseline main: c1bb92cc085a6bad272298b81bda28c22b1d57f5. No tests were run by this audit and no remote state changed.

## Executive findings

- Four open PRs: #68, #69 (draft), #81, #82. GitHub search_prs returned only #69; direct REST pulls collection returned all four. Prefer the collection snapshot for completeness.
- Current main documentation describes supported single-input toehold workflows. Do not promote branch-only eukaryotic AND or IBBIS deployment to current application capability.
- IBBIS backend branch is implemented but not merged, operationally provisioned, biologically validated or production-approved. Its software tests and parser timings are not screening-performance evidence.
- PR82 implements a corrected path-maximum barrier calculation, but the canonical corrected barrier CSV folder is missing from its complete head tree. Numerical summaries cannot be independently regenerated from that missing data in the current checkout.
- NucSyn release/publication and CERNAL integration are separate milestones. This audit did not independently inspect NucSyn release metadata; no integration claim follows from a release. PR81 explicitly generates switches through the engine rather than a NucSyn CSV.

## Open PR snapshot

| PR | State | Head | Base | Documentation scope |
|---|---|---|---|---|
| [#82](https://github.com/zivbental/cernal_software/pull/82) | open | offer/a0-to-cernal at 78d988757c42f57948f82dc3a595bccf2f1cc78e | main at c1bb92cc085a6bad272298b81bda28c22b1d57f5 | Offer/a0 to cernal |
| [#81](https://github.com/zivbental/cernal_software/pull/81) | open | zeev/eu-and-gate-integration at 64a29c24bfd020d75952ecfde6adf6ec486a9764 | zeev/toehold-and-creation-euk at 55272c5ef50ea04d32098465ad9b1e31dd0c59e8 | Make the eukaryotic AND gate (eu_and_v3) selectable, runnable and saved in the app |
| [#69](https://github.com/zivbental/cernal_software/pull/69) | open, draft | codex/sequence-screening-ui at 2d50e23cc75c3fee151ccb0524ab36e389dc8069 | main at 2baa75a7f0dc89f9aafac58dad50da5982f3f56a | Add conservative sequence-screening results UI and backend contract |
| [#68](https://github.com/zivbental/cernal_software/pull/68) | open | zeev/toehold-and-creation-euk at 55272c5ef50ea04d32098465ad9b1e31dd0c59e8 | main at c1bb92cc085a6bad272298b81bda28c22b1d57f5 | Eukaryotic toehold: single and AND stem-opening reports (eu_and_v3) |

### #68: eukaryotic single/AND research reports

Branch-only notebook/report work, not selectable application integration. Adds eu_and_v3, helper modules and shared FoldEngine sample_structures/constrained_probability functionality. Changes API FoldingConfig salt_molar (library default 1.021 M; notebook selects 0.1 M). Documentation requiring coordinated changes: docs/api.md, docs/public-api.md, generated docs/api-surface.md and eu_and_v3_spec.md.

PR author reports 2,515 tests on latest push and a small end-to-end notebook run. These are author-reported software results, not re-executed or independent biological validation. Existing comments document fixes to model consistency, complementarity/wobble sub-runs, zero-standard-deviation verification, empty/singleton candidate sets and control-count reporting. Rank meaning must remain explicit: joint stem opening ON_min − OFF, indicative sum-based fields separate. Sampling may disagree with exact-matrix marginals in mismatched controls; high controls can be sampler artefacts. Report renderer commit is not necessarily the original compute commit when re-rendering saved results.

### #81: selectable eukaryotic AND app integration

Stacked on #68, four commits beyond that branch (69 commits ahead of main including dependency), head 64a29c24bfd020d75952ecfde6adf6ec486a9764. Fresh PR metadata says mergeable against its current feature-branch base; this does not establish main merge readiness. Needs #68 landing and base retargeting first.

Implements selection, execution, save/reopen and exports for exactly one two-input eukaryotic AND gate in Human/yeast DE mode. Mixed families, unsupported host/input combinations and multiple gates are rejected. Capability fields include family_hosts, family_inputs, family_input_modes and limits.max_gate_inputs. Per-state diagnostics, warnings, rejection reasons and folding provenance are saved; and_* CSV columns appear for AND runs only. Sequence-release rules remain independent.

Scientific/documentation cautions from PR body:
- Single switches use the engine generator, not NucSyn CSVs; do not promise numerical agreement with notebook inputs.
- App controls default to exact-matrix upper bounds while notebook defaults to sampling. Persist and display the selected control mode.
- App ranks via weighted engine.scoring, not ON−OFF alone; tied group is evidence alongside ranking, not a reorder.
- predicted_leakage=OFF/100 is a structural proxy, not measured translation leak; dynamic_range=ON/max(OFF,1%) is linear; state_separation is log2; energy is kcal/mol; failures are None.
- gate_folding_energy saturation below the profile's −60 floor prevents discrimination among approximately −80 kcal/mol AND hairpins. Profile change remains a decision, not a documentation fix.
- Evaluation uses switch plus first 30 payload nucleotides, not full payload; effect of the remaining payload on ranks is untested.
- Salt default 0.1 M for AND, with provenance; control triggers use seeded other host-reference transcript windows.
- No experimental validation or default sensitivity analysis.

Author-reported evidence: 2,665 passed/1 skipped, 22 API integration tests, 36 gate tests and browser flow. Example eight-candidate run with ON 100%/OFF 0.89% is computational, configuration-specific and not transferable as a performance guarantee. Exact-head tests were not rerun here.

Documentation footprint to reconcile on merge: README.md; docs/ROADMAP.md; docs/and-gate.md plus screenshots; docs/api.md; docs/public-api.md; generated docs/api-surface.md; frontend API-doc route and help/capability descriptions. Current main must label these pending, rather than replacing current one-input facts before merge.

### #69: conservative sequence-screening UI contract

Draft at 2d50e23cc75c3fee151ccb0524ab36e389dc8069. Optional candidate-detail envelope, runtime validation, saved-switch SHA-256 matching, timestamp validity/provenance checks, pending polling and conservative copy. Does not implement/invoke Common Mechanism. Full construct/artifact evidence and operational release integration remain outside its scope. Existing main release controls are unchanged.

Preserve wording “No concerns detected by this screening,” never “safe.” Synthetic fixtures prove UI behavior only. Author reports 38 contract/17 browser tests and CI at https://github.com/zivbental/cernal_software/actions/runs/38244675476. This audit did not independently verify that historical run or current compatibility with main. New IBBIS backend does not merge/duplicate this UI branch; adapter integration and reconciled contract are still needed.

### #82: prokaryotic AND research/model publication

Head 78d988757c42f57948f82dc3a595bccf2f1cc78e, base main, fresh metadata dirty/unmergeable. 132 commits / 488 changed files, author PR body is an unfilled template, so do not treat it as acceptance evidence. No review comments returned. This is distinct from #68/#81's eukaryotic serial-switch/app work.

Corrected barrier implementation in tools/barrier_designs.py computes max(compound.eval_structure(step.s) for step in compound.path_findpath(start,end,width)) − compound.eval_structure(start). Search width is not an energy ceiling. The path result is a model/path-search estimate, not a measured kinetic rate or guaranteed global minimum barrier. Endpoint E(end)−E(start) is not an activation barrier. Re-evaluating visited structures avoids the initial step energy sentinel. Preserve nonnegative/self-path-zero checks.

The superseded README reports corrected range 4.50–25.20 kcal/mol, median 10.60 and rho=0.528 versus endpoint range −1.70–5.50, median 1.50 and rho=−0.035. These are repository author claims, not independently reproduced here. Complete recursive head tree (truncated=false) contains no docs/assets/barrier directory and only docs/assets/barrier_superseded/README.md in that superseded directory. tools/barrier_compare.py requires best*.csv in both folders. Do not publish these numbers as independently verified or imply the cited canonical tables are present. Some other barriers.csv/panel_barrier3.csv files exist elsewhere, but no evidence establishes them as replacements for the missing paired canonical rows.

Broader findings-register warnings should travel with derived model writing: modest/cross-dataset sign-changing correlations, no established biological predictive validity, equilibrium proxies on a kinetic system, incomplete transcript context (CDS-only research input), pilot results versus full-grid conclusions, within-cell matched comparisons rather than selected-survivor comparisons, historical mixed-column schema recovery and incomplete per-cell grids. Do not silently fuse incomparable populations or stale metrics.

Source ownership also needs care: docs/igem-model-page.md declares itself a mirror of an external live document and warns direct edits are overwritten. docs/wiki-page-brief.md describes an external wiki destination; these are source metadata, not authorization to edit external sites. Its code links to main can mislead for branch-only methods; pin branch/commit links until merge. tools/figure_flow.py matches latest flow title; change generator and generated presentation together.

## IBBIS final-output screening branch

Head a2d6503c09d927e48f4c90f9c7af3953921e529e; two commits ahead of current main, no open PR found. Changes backend safety/pipeline/disclosure, new engine/common_mechanism.py, tests, benchmark tool, API surface and three documentation/evidence files.

Implemented scope (branch-only): final switch and fully assembled plasmid both screened after assembly/optimization; complete linear FASTA molecules, fail-closed evidence binding, operator manifest/software/database identity and time window; both molecules require valid matching release records. Active manifest changes invalidate old grants at disclosure. Internal batches cap 64 records/one million bases. No permissive fallback, skipped searches, reduced database or reusable successful-verdict cache. Circular-origin-spanning detection is not established.

Declared pinned deployment: Common Mechanism 2.1.0 upstream 24fe0390978eb66d13db4f91c18f122d051b1a65, JSON output version 0.6, draft policy commec-exact-pass-v1. Policy/operator approval and full actual tool validation are still needed. Manifest must remain unset until acceptance. Code MIT does not establish database redistribution rights; database licence is explicitly unverified.

Evidence boundaries:
- No real executable/database provisioned; no real biological sensitivity/specificity measured; no production activation or deployment authorized.
- 77 focused checks, 762 gate/API/boundary checks, 178 coverage checks overlap and must not be added.
- Broad suite 2,601 passed, one skip, 110 subtests, two failures; ran while implementation was still being edited, not an exact-final-tree pass. Frozen-dataclass exception mismatch reproduced on untouched main; auth-rate-limit failure intermittent and not claimed fixed.
- Statement coverage 466/491 (94.91%); branches 135/162 (83.33%). Combined coverage display is not a biological detection rate.
- Branch publication returned no hosted CI runs in its verification record; no exact-head hosted success claimed.
- Benchmark is JSON decoder/parser/policy overhead on harmless repetitive synthetic inputs, no CLI, database search or mocked CLI execution. “Fresh adapter” is not OS/database cold. Includes 112 size/batch/status/mode combinations at 20 repeats; 100,000×64 skipped due cap.
- Reported millisecond timings cannot be extrapolated to real screening runtime. Full pre/post database inventories would entail roughly 80 GB logical reads at reported 40 GB extraction, excluding searches. Real full-tool protocol is unexecuted.
- Recorded workspace had 31.45 GiB total / 28.80 GiB free and no commec, insufficient for cited full database. Native Windows not enabled; POSIX subprocess cleanup tested.

Documentation needs: pending-feature/status entry and links; do not duplicate an unreviewed manifest/how-to into current deployment instructions. When integrated, reconcile main release-decisions/audit-f2-release-disclosure, operations/deployment, API disclosure and #69 UI contract. Keep synthetic test results, executed evidence and proposed real-tool protocol visibly separate.

## Relevant other branch classification

Comparisons against current main establish these are ancestors, not pending unique feature work: dot/clarify-evaluation-result-limits (behind 45); dot/folding-model-provenance (behind 41); dot/integrate-rna-gate-visualizer (behind 34); tal/endogenous-crispr-model (behind 52); ziv/host-c-acnes (behind 140); ziv/host-track-explicit (behind 149). Main CRISPR documentation still explicitly calls it a separate research workbench, not selectable app integration.

zeev/wiki-and-gate-page at 680bab6dcbe81a742555b5314b94fe6685027066 is one commit ahead of main: docs/wiki/and-gate-model-overview.html and docs/wiki/static/and-gate/trigger-positions.png. No open PR in the collection snapshot. Keep it as pending publication material, separate from implementation readiness.

## Main-doc drift visible already

README.md still contains October 12 baseline 2baa75a status and integration-order instructions to merge PR70/76 before F5. These are historical audit dependencies, not accurate ongoing instructions for fresh c1bb92c main. Main docs/ROADMAP.md calls itself the single future-work source but mixes a current section dated October 8, historical implementation claims, old MockEngine/client claims and later CRISPR workbench additions. The overhaul should separate current supported capability, pending work, research methods and dated evidence, retaining provenance rather than erasing history.

## Sources

- [Open PR collection](https://api.github.com/repos/zivbental/cernal_software/pulls?state=open&per_page=100)
- [Branch collection](https://api.github.com/repos/zivbental/cernal_software/branches?per_page=100)
- [Current main README](https://github.com/zivbental/cernal_software/blob/c1bb92cc085a6bad272298b81bda28c22b1d57f5/README.md)
- [IBBIS deployment contract](https://github.com/zivbental/cernal_software/blob/a2d6503c09d927e48f4c90f9c7af3953921e529e/docs/ibbis-final-output-screening.md)
- [IBBIS verification](https://github.com/zivbental/cernal_software/blob/a2d6503c09d927e48f4c90f9c7af3953921e529e/docs/evidence/ibbis-verification-2026-10-15.md)
- [IBBIS benchmark boundaries](https://github.com/zivbental/cernal_software/blob/a2d6503c09d927e48f4c90f9c7af3953921e529e/docs/ibbis-final-screening-benchmarks.md)
- [Corrected barrier implementation](https://github.com/zivbental/cernal_software/blob/78d988757c42f57948f82dc3a595bccf2f1cc78e/tools/barrier_designs.py)
- [Superseded barrier warning](https://github.com/zivbental/cernal_software/blob/78d988757c42f57948f82dc3a595bccf2f1cc78e/docs/assets/barrier_superseded/README.md)
- [PR82 complete tree evidence](https://api.github.com/repos/zivbental/cernal_software/git/trees/78d988757c42f57948f82dc3a595bccf2f1cc78e?recursive=1)

## Full visible branch-head inventory

This inventory alone does not classify merge status for every historical QA/fix branch. Only comparisons explicitly discussed above were performed. All 43 branches returned in the single collection page are listed.

- codex/audit-f2-release-disclosure: 4014b70865a4813851e9fb2f9d8ac5b48d1d975f
- codex/audit-f5-current-docs: fd24c77de940855018eb47af802de289be26ec9f
- codex/audit-f6-report-diagnostics: ac626238e768146a1956c65560d241da811f82f6
- codex/f1-wsl-worker: 3bd084f13fdcf1f91c1d247b22203cff69faafac
- codex/f7-close-backup-sqlite: e8b3b3dd8881f0ec9a8601e63d5761999edf24cb
- codex/sequence-screening-ui: 2d50e23cc75c3fee151ccb0524ab36e389dc8069
- dot/clarify-evaluation-result-limits: 1f943c158702f9dc625ffdfee8552fea5e79e956
- dot/folding-model-provenance: 595dec1b8e827007a9dd8b020ce5ad95e6b12010
- dot/ibbis-final-output-screening: a2d6503c09d927e48f4c90f9c7af3953921e529e
- dot/integrate-rna-gate-visualizer: a4c4917732456d6dfb933213a9f324e59d61c678
- fix/audit-f3-clean-frontend-build: 98433ffc2a7fc0f7e6e4b012a2a8f1c99f04117f
- fix/audit-f4-portable-rna-assets: 46c5295e6fcce0fc6ae10271b467ee9ea65f2984
- integration/oct12-all-fixes: e4e62ac65090b0131176bb118bb75f76db5c8392
- main: c1bb92cc085a6bad272298b81bda28c22b1d57f5
- offer/a0-to-cernal: 78d988757c42f57948f82dc3a595bccf2f1cc78e
- qa/api-ingestion-20261008: 89c16639e4ce5a5f951cab93ead448e47474f3a9
- qa/audit-baseline-20261008: fcf0061e8c946a246b287e7fdd4c908a23b937dd
- qa/construct-validation-20261008: 4f03f2a8dfa3b18533a810836ddb88c9d0e5fea0
- qa/delivery-20261008: 5cfb6c91f2ca7be28b773bdf4ba2384a71cce6a9
- qa/engine-integrity-20261008: d7721844fc0d043f6f4aab56e44fd7d889630cb4
- qa/gene-selection-performance-20261008: 01678995b00efa2bb419208e1ad21a6332a910e2
- qa/integration-20261008: 8b03adb8c24c8ccac2f7b01c49ab322907f344fc
- qa/operations-20261008: 366b4f55551075caa0cb5c405485f113fb12c09d
- qa/product-ui-20261008: e4265c7c36b53769ba699f748bb282389a335cf7
- qa/release-verification-20261008: 5763c80d2ff0b186082205a4fbea8191f161bb86
- qa/result-integrity-20261008: 206e688458a9f7abb0da7be4aa20d4fe0ddfb2c9
- qa/run-recovery-20261008: 5625fafe70e8e10b57e7a68c56ccb76ea95520ba
- qa/scientific-semantics-20261008: f035253a4549ee19d5ed08161b1364cfd7dbe794
- qa/sdk-contracts-20261008: a7d98577acc7d076ba52e189ac7c1b0626cb0e9d
- qa/security-20261008: 17eaed9c6841c4d08d027db2ee4951596d8f2c30
- qa/storage-lifecycle-20261008: 3e4572ae48b4b7ddc6250ac7e796b1a4d1d6bd5f
- tal/endogenous-crispr-model: 251b75e14419f20ce9e9746cc7b0b8001d1aa62f
- zeev/eu-and-gate-integration: 64a29c24bfd020d75952ecfde6adf6ec486a9764
- zeev/toehold-and-creation-euk: 55272c5ef50ea04d32098465ad9b1e31dd0c59e8
- zeev/wiki-and-gate-page: 680bab6dcbe81a742555b5314b94fe6685027066
- ziv/aisc-submodule: c9aed9d87a9e27c8234e047dfe2fa50002e6ef21
- ziv/codon-optimizer-eso: 0df6352af2711625b472cf09e8fcba460059ca6a
- ziv/f8-catalog-checkout-bytes: 3efde4b48e06700bf5a84970b523062dc22cbdcf
- ziv/f9-vendor-hash-order: b5be08b58a644659da915918e280cac8bf56d27b
- ziv/f10-matrix-input-bytes: eaa6e79cd449388891f7533b5cf628dcad86fbf2
- ziv/host-c-acnes: 646c98eb47ca1c6767819256ef4aea6d82938a3e
- ziv/host-track-explicit: 706cb433e7c1fc08f8c410c8bec25425b0939b21
- ziv/vendor-aisc-no-submodule: 7518270e2234ea772e08cf9f6379f407affc6a8b

