# Remediation status

Updated 8 October 2026. The [dated audit](SOFTWARE_STATUS_REVIEW_2026-10-08.md)
remains the immutable before-state evidence. This ledger records product/client changes;
integrated engine/platform/runtime acceptance is recorded in the
[main QA ledger](QA_REMEDIATION_2026-10-08.md).

| Audit IDs | Software changes | Verification and remaining acceptance |
|---|---|---|
| PD-01 | UI consumes authoritative production host/family/output capabilities and prevents unsupported submission | Browser fixtures cover all four hosts × three input modes, marker/backbone host restrictions and optional codon optimization; reviewed multi-input chemistry remains ENG-09/GAP-01 |
| PD-02 | Run/candidate warning details, frozen configuration/seed/engine, reference/design provenance, honest proxy/off-target/release labels | Browser fixtures expose unique warnings and unmeasured values; scientific calibration remains GAP-03 |
| PD-03 | Server-side output/min-score filters; 50-row pagination with last-page navigation and stable detail selection; history offset | Synthetic API/browser tests navigate candidate 201 and 7907; history remains ownership-filtered |
| PD-04 | Plain/single FASTA parsing preserves text and rejects invalid bases/multiple headers; shared trigger/payload UI parsing | Browser ambiguity/header test; server/engine equivalent contract comes from platform/engine branches |
| PD-05 | Visible errors/retry for session, submit, history, candidates/detail, artifacts, public comparisons and keys; terminal empty results | Browser offline/history/empty fixtures; submission HTTP401/403/404/422/429/500 and review persistence fixtures passed; external service failures remain deployment acceptance |
| PD-06 | Current-route smoke and isolated HTTP-fixture browser contracts replace obsolete projects routes | Fast contracts run built SPA; real isolated SQLite + worker + LocalEngine browser passed locally and in hosted CI |
| PD-07/08; PLAT-12 | All SDK handles retain result options; transport timeout covers bounded server wait; best chooses accepted rank | Python live/contract tests passed; R raw/table/live HTTP suite passed hosted Ubuntu CI; MATLAB runtime remains unexecuted |
| PD-09 | Raw JSON vs flattened tables separated; R array serialization and MATLAB Nx2 headers/null metrics repaired | R hosted runtime suite passed; MATLAB runtime coverage remains open |
| PD-10; PLAT-16 | Current docs and operative instructions corrected; old design narratives explicitly archived | Current status points to source/capabilities and dated verification; generated API surface refreshed at integration |
| PD-11 | Research note/tag persistence shown through existing owned APIs and attributed JSON bulk export; synthesis ordering labeled unavailable | Annotation ownership remains server-enforced; funded external integration is not implemented |
| PD-12 | Synthetic example/source installation labels corrected; decision/owner ledger written | Names, consent, governance, publishing and institutional approvals remain human decisions, not completed by code |
| GAP-04 | Verified selected arthritis contrast from primary Atlas XML/GEO metadata; conditions/common context normalized; retained CSV digests/statistic counts/subset status shown; future sync retains full analysis rows | Primary evidence and deterministic parser/checksum/full-row tests; all fifteen bundled comparisons completed real bounded DE smoke (14 productive/1 valid empty/0 errors); broader reference coverage and biological review remain open |
| GAP-05 | Productive fixture checks engine success/accepted results; clean generation order and browser CI lanes | Hosted Python/frontend/browser/R jobs passed; dependency advisories remediated and rechecked; full backend/final-head jobs, MATLAB/Windows/deployment acceptance remain distinct |

Local product verification: TypeScript, ESLint, server-render/help checks and production
build passed. Isolated Playwright HTTP-fixture contracts passed for paste integrity,
capability rejection, offline submission retry, catalog empty state, warnings/proxies,
candidate 201/7907, global output filtering, custom-vector boundary validation,
four-host/three-mode readiness, HTTP failure matrix, review save/delete, empty
completion and history failures.
Python client suite passed 19 tests through a real localhost API (real LocalEngine
precompleted fixture; this is not a worker-queue test). R runtime conformance subsequently passed in [hosted Ubuntu CI](https://github.com/zivbental/cernal_software/actions/runs/37802426550/job/113397823314).
MATLAB runtime remains unavailable. Engine test totals and main-suite claims are recorded
only from commands actually run after integration.

Detailed real catalog evidence and the source-homopolymer eligibility policy change
are recorded in [catalog pipeline smoke](catalog-pipeline-smoke.md). The bounded
15-comparison rerun took 52.6 seconds initially and 68.7 seconds with a concurrent
old-engine diagnostic. Those observations are not calibrated runtime predictions.
Known dependency advisories and the read-only after checks are recorded in
[the dependency evidence](evidence/dependency-advisories-2026-10-08.json).
