# QA remediation: implementation, PRs, evidence and remaining work

This is the implementation follow-up to [the comprehensive audit](SOFTWARE_STATUS_REVIEW_2026-10-08.md).
The original audit is historical evidence; this document records what changed afterward.
Three GPT-6.1 Sol agents with high reasoning worked concurrently on engine, platform and
product tasks. The coordinating agent handled recovery, deployment, integration and QA.

**This is not a claim that all 47 audit tasks are closed.** Software corrections, added
features, actual test results and external scientific/operational acceptance are separate.
Rejecting an unsupported molecular mechanism fixes misleading behavior; it does not
implement that mechanism. The scientific limitations are detailed in
[the engine implementation record](https://github.com/zivbental/cernal_software/blob/0ba41d290851b8c0cae787d9c5a0a683d6f6650d/docs/SCIENTIFIC_QA_IMPLEMENTATION_2026-10-08.md).

## Branch and review organization

Work was isolated under `/tmp/cernal-qa-20261008/`; the original working tree, its
uncommitted implementation, user database and media were preserved. The baseline PR
captures the previously uncommitted four-host implementation and audit. Each subsequent
PR is based on the preceding branch to keep its diff reviewable. Nothing was merged.
The PRs remain drafts while integrated verification and human review are completed.

| Order | PR | Scope |
|---|---|---|
| 1 | [#47](https://github.com/zivbental/cernal_software/pull/47) | Audited four-host/reference baseline and evidence |
| 2 | [#48](https://github.com/zivbental/cernal_software/pull/48) | Owner isolation, idempotency, scopes, quotas, auth and immutable admin records |
| 3 | [#49](https://github.com/zivbental/cernal_software/pull/49) | Scientific input validation, statistical completeness and bounded cache lifetimes |
| 4 | [#50](https://github.com/zivbental/cernal_software/pull/50) | Complete result-manifest validation and zero-preserving exports |
| 5 | [#51](https://github.com/zivbental/cernal_software/pull/51) | Asynchronous SDK options, timeouts and ranking |
| 6 | [#52](https://github.com/zivbental/cernal_software/pull/52) | Durable dispatch, worker leases/heartbeats, recovery and portable supervision |
| 7 | [#53](https://github.com/zivbental/cernal_software/pull/53) | VM service templates, readiness and operations runbook |
| 8 | [#54](https://github.com/zivbental/cernal_software/pull/54) | Physical/scoring semantics, actual payload contexts, provenance, budgets and reports |
| 9 | [#55](https://github.com/zivbental/cernal_software/pull/55) | Shared upload/preview/submission/dry-run validation and capabilities |
| 10 | [#56](https://github.com/zivbental/cernal_software/pull/56) | Recoverable imports, complete archives, backup/restore and storage lifecycle |
| 11 | [#57](https://github.com/zivbental/cernal_software/pull/57) | Compile/result/research-review UI and further SDK corrections |
| 12 | [#58](https://github.com/zivbental/cernal_software/pull/58) | Browser-to-real-queue CI, runtime lanes and current documentation |
| 13 | [#59](https://github.com/zivbental/cernal_software/pull/59) | Cross-layer integration, cancellation races, canonical host submission and verified arthritis metadata |
| 14 | [#60](https://github.com/zivbental/cernal_software/pull/60) | Annotated custom-vector insertion, reporter CDSs and optional codon optimization |
| 15 | [#61](https://github.com/zivbental/cernal_software/pull/61) | Exact gene-selection optimization, independent parity tests and benchmark evidence |
| 16 | [#62](https://github.com/zivbental/cernal_software/pull/62) | Resistance CDSs, authoritative host maps, proxy identity, dependency fixes and final integrated QA |

Integration follow-ups on `qa/integration-20261008` include the canonical-host browser
fix, cancellation races, conservative staging retention, atomic auth admission,
inline-upload cleanup, stricter SDK terminal states, catalog metadata and expanded
browser coverage. Construct/payload work and final verification follow in PRs #60–62.

Merge/review in dependency order. Intermediate branches are development checkpoints;
their individual CI results do not certify the final combined tree. The complete tree
must pass verification before the stack is approved. Do not replace the original local
working tree with a reset: use a separate checkout of the final review branch.
Do not deploy an intermediate checkpoint. After merging a parent PR, retarget the next
PR as appropriate and verify its diff and CI; resolving conflicts requires fresh checks.

## The reported user problems

### Runs remaining at 0%

Submission now persists enqueue state and can republish a dispatch that failed. A worker
claims a run with an atomic execution token. Duplicate delivery cannot repeat live work.
An unclaimed run expires with a clear queue-wait error after the configured deadline
(two hours by default); republishing cannot keep it waiting indefinitely.
Independent heartbeats and a reconciler terminate abandoned/deadline-exceeded runs;
late results cannot overwrite terminal state. Cancellation and result finalization are
serialized. Import failure retains successful scientific output for an operator retry
into a new immutable run. A real worker-kill subprocess test exercises recovery.

This addresses observed failure modes; it cannot guarantee that no future run will fail.
Native folding is cooperative only between calls. Production requires the reconciler,
shared local heartbeat storage and appropriate resource/time limits. See
[operations.md](https://github.com/zivbental/cernal_software/blob/0ba41d290851b8c0cae787d9c5a0a683d6f6650d/docs/operations.md) for actual commands, defaults and residual deployment tests.

### The disabled arthritis-study submission

Host/family/output applicability and invalid input now produce explicit validation
messages. A real browser/queue test exposed a separate UI defect: the form sent a display
name at the top level and a canonical organism key inside its frozen parameters. The
form now submits the canonical key consistently.

The exact Human public-dataset browser flow subsequently passed: select
`E-GEOD-103501 / g3_g1`, load the expression profile, and click **Compile & Optimize**.
The API returned 202 and a separate worker completed with 20 accepted candidates in
66.31s for the whole browser harness. This used an ordinary UI-selected short custom
CDS and permissive visible scoring settings, with no request rewriting. The submission,
terminal response and screenshots are retained in the final evidence archive.

The bundled selected arthritis contrast was checked against primary provider metadata:
it is Growth Medium versus no treatment in normal samples, with four test and five
reference samples. Disease-versus-normal is a different contrast. The UI now preserves
the exact groups, shared context, raw/adjusted-statistic distinction, retained subset
status and source digest. The study title alone is not a disease-classifier input label.
See [catalog-governance.md](https://github.com/zivbental/cernal_software/blob/0ba41d290851b8c0cae787d9c5a0a683d6f6650d/docs/catalog-governance.md) for source links and retained evidence.

### Human construct construction

Human reference lookup, transcript-based inputs, eukaryotic single-input gate generation
and computational expression-cassette/custom-backbone assembly are part of the review
stack. The supplied bacterial catalog backbones currently have E. coli support only;
other hosts use an expression cassette or a supplied custom vector. This is the current
implementation scope, not a universal biological impossibility. Payload-dependent
folding and the exact switch-initiated coding fusion are now evaluated and recorded;
no-backbone cassette topology is linear. These are computational designs. Their
functional performance and deployment screening are not established by software tests.

### Current supported combinations

The following is the runnable computational scope after these PRs. Three input modes
are implemented for each host: a differential-expression table, one reference gene,
or a direct RNA trigger. CSV/TSV/TXT/XLSX are table formats; plain RNA/DNA and single-record
FASTA are direct-trigger formats. A gene input is one reference gene, not an arbitrary
multi-gene list. Multi-output requests evaluate independent payload alternatives.

| Host | Runnable gate | Catalog output alternatives | Vector construction |
|---|---|---|---|
| E. coli | Single activating prokaryotic toehold | GFP, mCherry, firefly luciferase, AmpR, KanR, custom CDS | Catalog vector, annotated custom vector, or linear cassette |
| Yeast | Single activating eukaryotic toehold | GFP, mCherry, firefly luciferase, custom CDS | Annotated custom vector or linear cassette |
| C. acnes | Single activating prokaryotic toehold | GFP, mCherry, firefly luciferase, custom CDS | Annotated custom vector or linear cassette |
| Human | Single activating eukaryotic toehold | GFP, mCherry, firefly luciferase, custom CDS | Annotated custom vector or linear cassette |

API `output_hosts` and `backbone_hosts` are authoritative and the UI consumes them.
Opt-in codon optimization is available for all four hosts and checks protein
preservation; it is disabled by default. Uploaded vector replication/selection and
the biological function of every constructed fusion remain unverified.

The supported-input matrix includes negative assertions for unavailable families;
a useful rejection is not counted as successful implementation of that chemistry.
Input/host coverage is bounded regression coverage, not enumeration of every possible
sequence, numeric parameter, vector feature, or environmental failure.

### Performance and dependency corrections

An exact Stage 1 optimization screened the same 1,192 transcripts / 1,161,495 bases,
selected the same genes with identical scores/yields/warnings, and reduced one
3,000-row catalog comparison from 58.524 to 0.640 seconds (91.45×). This is a measured
gene-selection improvement on one input, not a total-run or folding guarantee.
The independent original algorithm remains the benchmark oracle; see
[the performance evidence](https://github.com/zivbental/cernal_software/blob/0ba41d290851b8c0cae787d9c5a0a683d6f6650d/docs/qa/2026-10-08-gene-selection-performance.md).

The dependency review removed the unused browser XLSX package and updated compatible
JavaScript patches plus locked urllib3 2.8.0. The recorded rescan found zero published
advisories in the frontend lock graph and zero across 52 evaluated production Python
requirements. This is a dated advisory result, not proof of absence of vulnerabilities;
see [the dependency inventory](https://github.com/zivbental/cernal_software/blob/0ba41d290851b8c0cae787d9c5a0a683d6f6650d/docs/evidence/dependency-advisories-2026-10-08.json).

## Every audit task: delivered change and remaining acceptance

“Implemented” below means code and targeted regression evidence exist. “Partial” means
the audit's full acceptance criteria extend beyond that code. Read the original task
card for detailed acceptance; no task is silently removed.

| Task | Implementation state | Remaining work / acceptance |
|---|---|---|
| PLAT-01 | Owner-scoped keys, normalized conflict detection, retry-before-quota, inline-input cleanup | Review retention policy and final concurrency/integration results |
| PLAT-02 | Durable enqueue timestamps, execution leases, heartbeats, reconciliation, cancellation/import rollback | Real deployment crash/reboot/timeout acceptance; native calls cannot be interrupted cooperatively mid-call |
| PLAT-03 | Shared complete-table parser for upload/preview/engine, first-sheet XLSX, strict numerics and identifiers | Full provider refresh is a separate data task; preserve explicit preview/canonical-column contract |
| PLAT-04 | CSV preserves numeric zero separately from missing | Closed for the tested API/export contract; integrated regressions pass |
| PLAT-05 | Shared strict effective configuration and truthful dry-run; bounded max_designs; backbone parity | Runtime seconds are null and runtime_calibrated=false; unavailable mechanisms remain rejected |
| PLAT-06 | Immutable submitted datasets/runs and imported metrics/artifacts in admin | Review allowed repair workflow; research notes remain intentionally mutable |
| PLAT-07 | Reserved nonprivileged reviewer identity; collision fails safely | Shared reviewer history versus disposable workspaces remains a product policy choice |
| PLAT-08 | Read/design/annotation scope enforcement and atomic account quota | Maintainer review of chosen account limit and full endpoint policy; distributed scale is not certified |
| PLAT-09 | Origin/CSRF protection for session entry, shared atomic auth rate admission, no raw DEBUG media serving | Production proxy/security and distributed-load acceptance |
| PLAT-10 | Schema/status/config/checksum/finite-value/identity validation and contained nonsymlink artifact paths | Production storage-adapter verification if moving beyond local filesystem |
| PLAT-11 | Cleanup-aware import finalization, retained reimport, explicit incomplete ZIP failure, spooled ZIP, backup/restore, dry-run cleanup | Operator backup schedule/retention/RPO/RTO and production-sized restore/memory measurements |
| PLAT-12 | SDK result options, wait budgets, CSV/raw tables, rank selection and terminal-state fixes; Python/R runtime conformance passed | MATLAB runtime and broader all-language fresh queued-job conformance; see PD-09 |
| PLAT-13 | POSIX/Windows locking/process adapters and manual CI lane; 48 tests passed on Windows Server 2025 | Actual native process crash/restart/tree-shutdown evidence still required; launch/shutdown unit cases use mocks |
| PLAT-14 | Gunicorn/worker/reconciler/Caddy templates, environment example, readiness, runbook | Clean-VM HTTPS, restart, disk-full, restore, alerts, resource limits and incident-owner acceptance |
| PLAT-15 | Expired-key regeneration refusal, expiry display, parameter validation and collision retries | Maintainer policy choice for explicit renewal; no false active secret on expiry |
| PLAT-16 | Current-status pointers, corrected instructions/roadmap, generated API surface | Continued documentation review as scientific decisions land |
| ENG-01 | Physical single-gate constraint; prevents false compiled Boolean labels | Approved molecular AND/OR/NOT architecture and actual physical compiler remain open |
| ENG-02 | Preserves signed DE; no activating toehold is substituted for required DOWN inversion | Implement reviewed repressive/inverting chemistry |
| ENG-03 | BH only for explicitly complete tested hypotheses; partial/raw statistics labeled | Acquire/verify provider-complete tables and completeness provenance |
| ENG-04 | Bounded per-instance folding caches and collection tests; no-count ranking fast path | Repeated native-worker memory plateau/soak benchmark |
| ENG-05 | Accepted constraint bounds/types/motifs affect actual tools; unavailable settings rejected | New constraints require independent behavior tests |
| ENG-06 | Dot-bracket validation, pairing comparison and stored normalized ensemble defect | Functional structural thresholds need independent biological evidence |
| ENG-07 | Versioned metric descriptions and explicit binding/accessibility proxy labels; finite scoring | Functional direction review, independent calibration and uncertainty/rank sensitivity evidence |
| ENG-08 | Scores exact attached payload context; removes duplicate head/start; validates fused ORF; optional synonymous codon optimization with mutation/source provenance | Functional consequences of the N-terminal fusion require independent assays |
| ENG-09 | One authoritative production capability source; early rejection of unintegrated families | Integrate approved antisense/AND/CRISPR mechanisms with their real state semantics |
| ENG-10 | Truthful cassette/vector topology; explicit 0-based custom insertion; preserved/shifted annotations, strands, compound locations and qualifiers; feature-disrupting insertion rejected | Host function of uploaded vectors is unverified; no assembly-orderability claim without a specified method |
| ENG-11 | Strict independent engine parsing, finite/range/shape validation | Closed for the tested supported-format/API contract; new formats require new acceptance |
| ENG-12 | Stable gene/transcript IDs, reference/model/family versions, architecture/digests and diagnostic snapshots | Full discarded-stage provenance and immutable reference refresh governance |
| ENG-13 | Deterministic explicit design budget, configured ties, arity pruning, length rejection and cancellation checkpoints | Maximum-size latency/RSS/cancellation measurement; Pareto remains component scope |
| ENG-14 | Sequence-free HTML report, standalone diagnostic SVG helpers, actual host release context | SVG/PDF production export integration and a provisioned, validated operational screening adapter |
| PD-01 | UI/API consume runnable host/family/output/mode combinations | Positive tests for every newly enabled payload/mechanism; hidden chemistry is not implemented |
| PD-02 | Visible warnings, configuration/provenance and unmeasured/proxy labels | Scientific calibration remains ENG-07/GAP-03 |
| PD-03 | Global output/score filtering, stable 50-row pages, last page and history offsets | Large synthetic pagination verified; production-scale query benchmarking remains useful |
| PD-04 | Preserves raw paste; explicit plain/single-FASTA parsing and invalid-base rejection | New formats require an explicit parser contract |
| PD-05 | Visible network/authorization/input/run/detail/artifact/empty-state handling | Continued browser failure matrix for new routes |
| PD-06 | Current browser contracts, four-host/mode cases, error/review cases, real queued browser lane | Broader supported-runtime/environment matrix beyond the executed lanes |
| PD-07 | Async handles retain result-shaping options across waits | Final all-language queued/inline equivalence |
| PD-08 | Remaining-budget transport timeouts, accepted-rank best selection, strict terminal state | Long real waits and all-language runtime verification |
| PD-09 | R raw/table and array fixes; MATLAB headers/arrays/null/terminal handling; real hosted R conformance passed | MATLAB runtime remains unavailable; native execution is still required |
| PD-10 | Current product/science status reconciled; stale plans marked historical | Human review of remaining design decisions |
| PD-11 | Owned research annotations, decision UI and attributed JSON review export | External synthesis ordering requires vendor/workflow scope; not implemented |
| PD-12 | Attribution/source labels and release decision ledger | Maintainers must assign consenting people and approve release/attribution decisions |
| GAP-01 | GFP, pinned mCherry and firefly luciferase, distinct AmpR/KanR, and custom CDS; exact output-host maps, native folding and translation tests | Context-specific apoptosis remains unspecified; reporter/fusion/resistance function is not experimentally established |
| GAP-02 | Missing off-target/orthogonality measurements made explicit | Background/isoform/interaction specification, backend benchmark and production subsystem remain open |
| GAP-03 | Computational versus biological evidence clearly separated; confusion/QC helpers implemented | Independent assays, held-out calibration, controls and named scientific approval cannot be supplied by software QA |
| GAP-04 | Primary arthritis contrast evidence, normalization, checksums/statistical completeness, full-row future sync; all 15 bundled comparisons completed without engine errors | Full refresh, alias/isoform policy and suitable C. acnes public data remain open |
| GAP-05 | Productive and empty fixtures separated; integrated backend/browser/Python/R checks, native Windows selected tests, generated-source checks and complete production dependency audit passed | MATLAB, actual Windows process drills, worst-case soak and live deployment acceptance remain open |

## Verification record

Test counts below refer to individual commands, not a sum of overlapping suites. Tests
which enable sequence exports through an explicit test seam exercise serialization and
download behavior; they do not establish operational screening or biological efficacy.
The native payload and real browser runs used the unchanged release policy.

| Verification | Observed result | Revision / scope |
|---|---|---|
| Full backend regression after queue deadline | **2,042 passed in 661.85s** | `e6508f9`; freshly installed locked Python environment; the eight advisory-helper cases added afterward ran separately |
| Corrected API expectations and submission routes | 145 passed in 52.73s | `941e233`; includes the two obsolete assertions identified in the preceding full run |
| Queue deadline, worker death, cancellation, import retry, readiness and supervision | 52 passed in 18.29s | `e6508f9`; includes six new queue-expiry cases and a real subprocess-kill test |
| Advisory coverage guard | 8 passed in 0.05s | `dc41b0e`; empty, incomplete, wrong-version, partly/all-skipped and unpinned reports rejected |
| Native folding subprocess clean-environment regression | 86 scientific/advisory tests passed in 0.78s with PYTHONPATH removed | `3da3189`; includes source checkout, foreign working directory and installed layout with spaces/apostrophe; original ViennaRNA parity/count/time bounds retained |
| Native host × mode × payload alternatives | 12/12 jobs, 54/54 accepted alternatives, zero failures/empty jobs; 322.345s | `24280ec`; real ViennaRNA, budget 1, default hard filters, standard none, no vector, codon optimization off |
| Real retained public catalog | 15/15 succeeded, 14 productive, one valid empty; 68.7s detailed rerun | `f899e67`; real CSV/digests, three-gene and one-design budget, short custom CDS |
| Browser contract matrix | Passed in 8.63s | `24280ec`; four hosts × three modes, errors, review edits, global filters and candidate 7907 |
| Browser → real queue → separate worker | Completed with three accepted candidates in 20.54s | `24280ec`; actual login, HTTP submission, SQLite queue and LocalEngine; isolated QA storage |
| Human arthritis-study browser submission | HTTP 202 → COMPLETED, 20 accepted candidates in 66.31s | Application `e6508f9`, checkout `dc41b0e`; actual Human selector and bundled g3_g1 table, short custom CDS, visible permissive scoring |
| Python SDK | 19 passed in 25.71s | `24280ec`; live localhost API plus contracts, distinct from queue acceptance |
| Frontend | TypeScript, ESLint, render/help checks and production build passed | Fresh isolated npm install; Node 24.19 locally and Node 22 in hosted CI |
| Final frontend wording adjustment | Check, production build and browser contracts passed in 31.13s combined | `0ba41d2`; copy now describes host applicability accurately |
| Static/backend configuration | Ruff lint/format (305 files), Django check, migration drift and API-surface checks passed | `dc41b0e`; all five commands exited zero |
| Python production dependency audit | 52 expected, 52 audited, zero skipped/missing/wrong-version packages and zero advisories | Repaired pinned-requirement audit and explicit coverage verification |
| JavaScript dependency audit | Zero published vulnerabilities in the lock graph | Local rescan and hosted artifact; historical unused XLSX and compatible patch findings remediated |
| Hosted R | Passed live HTTP/raw/table conformance | [PR #62 R job](https://github.com/zivbental/cernal_software/actions/runs/37807903563/job/113416906473), `24280ec`, 4m03s |
| Hosted native Windows | 51 selected tests passed in 35.20s, including three actual native folding subprocess cases | [release run](https://github.com/zivbental/cernal_software/actions/runs/37812568608), `d485d20`, Windows Server 2025; process launch/shutdown adapters include mocks |

The hosted [real-queue browser job](https://github.com/zivbental/cernal_software/actions/runs/37807903563/job/113416906724)
also passed at `24280ec`: Chromium provisioning took 303s; actual application acceptance
took 25s and returned three candidates. Provisioning delay was not an application hang.
The same hosted run passed frontend and Python client checks.

Native matrix details, every payload's source/construct/metric records, 108 held release
audits and checksum verification are retained in
[the matrix evidence](https://github.com/zivbental/cernal_software/blob/0ba41d290851b8c0cae787d9c5a0a683d6f6650d/docs/evidence/final-payload-matrix-2026-10-08.md). All fifteen catalog
results and the matched source-homopolymer eligibility comparison are retained in
[catalog-pipeline-smoke.md](https://github.com/zivbental/cernal_software/blob/0ba41d290851b8c0cae787d9c5a0a683d6f6650d/docs/catalog-pipeline-smoke.md). Empty results, rejected
candidates and exceptions are separately recorded.

The preceding full run at `24280ec` finished with **2,034 passed and two failed** in
522.72s. Both failures were obsolete assertions: AmpR was still expected to be unavailable,
and the normalized default insertion coordinate was omitted from the expected snapshot.
The corrected API lane passed; the final full rerun includes both fixes. Earlier
integration failures (canonical host mismatch, generated API documentation, R native
package installation, result/cancellation cases) were fixed and rerun, not counted as
passing tests.

Review also caught an invalid hosted Python audit: `pip-audit --local` in a uv tool
overlay produced an empty dependency list while exiting zero. That artifact is **not**
security acceptance. CI now exports the locked production requirements, audits those
pins explicitly and fails when required packages are missing, skipped or mismatched.
The repaired local scan covered all 52 applicable packages. The earlier empty report
is retained as superseded evidence.

A subsequent hosted backend run at `dc41b0e` had **2,049 passed and one failed**:
the bounded suboptimal folding child could not import `engine` without an inherited
PYTHONPATH. The exact failure was reproduced locally with the environment variable
removed. Commit `3da3189` bootstraps the child's owning package root explicitly, without
changing the caller's environment or weakening native limits. Both source-checkout and
installed-layout regressions pass. The final full hosted check, including these new
cases, is the required gate on [PR #62](https://github.com/zivbental/cernal_software/pull/62/checks);
check its result for the current PR head rather than treating an earlier green subset
as approval of a later change. The final PR description records the handoff result.

The final hosted release run at `d485d20` independently confirmed 52/52 Python
packages, zero skipped/missing/version-mismatched packages and zero advisories; its
JavaScript artifact reported 426 dependencies and zero advisories. Three inherited
broken `.claude/worktrees` gitlinks were subsequently removed from the distributable
review branch and ignored, resolving checkout cleanup warnings. Original local agent
worktrees were preserved. A final UI wording correction describes a disabled payload
as unsupported for the selected organism rather than globally unimplemented.

The local final environment is Python 3.13.15, Django 5.2.17, ViennaRNA 2.7.2,
BioPython 1.88, NumPy 2.5.3, SciPy 1.18.1, pandas 3.0.6 and urllib3 2.8.0. Package
versions and tested revisions are captured in the
[final evidence archive](qa/2026-10-08-remediation-evidence.zip), including per-test
outcomes, command logs, hosted artifacts and the Human browser screenshots. MATLAB and a real
production VM were unavailable; no passing claim is made for those environments.

## Remaining tasks that require decisions or external evidence

1. **Scientific lead:** approve the physical architecture, transcription units and truth
   tables for multi-input AND/OR/NOT; specify CRISPR effector and activation/repression
   polarity. Acceptance is a real constructor, complete state evaluation and correct
   physical assembly, followed by independent functional evidence.
2. **Payload owner:** name exact context-specific apoptosis molecule/host behavior;
   approve the implemented reporter/resistance source, protein and junction expectations.
   No arbitrary sequence should be presented as an unspecified biological outcome.
3. **Evaluation owner:** provide independent positive/negative assays, held-out cohorts,
   intended ON/OFF definitions and calibration criteria. Proxy scores cannot become
   success probabilities by renaming or unit tests.
4. **Specificity owner:** approve intended/off-target interactions, background reference
   universe/isoforms, model, benchmark controls and runtime limits before the proposed
   transcriptome scan is advertised as a measured property.
5. **Operations owner:** provision a target VM and approved secrets/DNS, execute the
   documented restore/reboot/disk-full/HTTPS drills, configure external alerts and
   retention, and record ownership/RPO/RTO.
6. **Release owner:** supply the actual screening adapter, operational policy and failure
   handling; resolve computational JSON sequence disclosure versus artifact-release
   scope. Existing release controls remain in place.
7. **Runtime/QA owner:** execute actual Windows process drills and MATLAB runtime
   checks. Hosted R conformance and 51 selected native Windows tests have passed.

These are delegatable acceptance tasks, not undocumented TODOs or implied approvals.
See [release-decisions.md](https://github.com/zivbental/cernal_software/blob/0ba41d290851b8c0cae787d9c5a0a683d6f6650d/docs/release-decisions.md) for the human decision ledger.

## Explicit implementation follow-ups still open

These are code/data tasks that remain after the delivered fixes; they are not all
blocked on a human approval. Keep them open when delegating the original audit cards.

| Next task | Original IDs | Concrete deliverable and acceptance |
|---|---|---|
| Native memory and worst-case compute characterization | ENG-04/13, GAP-05 | Repeated same-worker workloads and maximum accepted inputs; retain peak/plateau RSS, latency, time-to-cancellation and deadline recovery. Use the measurements to choose documented limits; current cache bounds alone do not establish a plateau. |
| Complete rejected-stage provenance | ENG-12 | Versioned, bounded records for candidates discarded at each stage, with stable input/reference IDs and explicit rejection reasons. Verify deterministic replay and cap diagnostic storage without exposing sequence content through reports. |
| Production report exports | ENG-14 | Wire the existing diagnostic SVG helpers into actual report artifacts; decide PDF dependency/renderer support and add a reproducible PDF export if required. Test empty and rejected-only results, escaping, pagination and sequence-disclosure boundaries. HTML is already implemented. |
| Full reference/data refresh | ENG-03/12, GAP-04 | Acquire checksum-pinned provider-complete contrasts and appropriate C. acnes data; document isoform/alias and tested-hypothesis policies, validate identifiers and metadata, rerun the catalog inventory. Current retained subsets remain explicitly incomplete. |
| Additional runtime and deployment acceptance | PLAT-13/14, PD-09, GAP-05 | Record native Windows process ownership/restart/shutdown, licensed MATLAB API conformance, and the VM drills in operations.md. A CI job running mocked process adapters on Windows is only partial evidence. |
| Physical multi-input and off-target implementations | ENG-01/02/09, GAP-02 | After the specifications above are supplied, implement the real molecular state constructors and background scan through the existing interfaces, with independent positive/negative fixtures. Do not satisfy these tasks by enabling capability flags. |

Priority order: review the delivered security/recovery/input fixes first; complete
runtime/deployment and scientific decision ownership before release; then extend
capabilities using the explicit remaining specifications and acceptance tests.
