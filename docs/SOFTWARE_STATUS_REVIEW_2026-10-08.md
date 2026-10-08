# CERNAL: complete software status review and QA findings

**Audit date:** 8 October 2026. **Basis:** the current working tree on branch `ziv/remove-mock-engine`, HEAD `ca91177c224d18f58c4c5b148cd7699e2616cfb0`, including the existing uncommitted Human/reference-input, upload-format and worker-supervision changes. This is not an assessment of HEAD alone.

**Purpose:** establish what exists, what works under the tests actually run, what remains incomplete or scientifically unresolved, and what another agent can implement next. No product fixes were made during this audit. Existing user runs and database records were preserved; new API fault probes used isolated test databases and temporary media. The frontend production assets were rebuilt for QA.

**Assessment:** CERNAL is a substantial, functioning computational design prototype. It has a real engine, four reference organisms, three submitting input modes, real folding calculations, candidate ranking, construct composition, persistence, APIs and a usable frontend. It is **not yet a complete, reliable implementation of all advertised combinations**, and successful execution currently permits materially misleading scientific outputs. There are also confirmed privacy, input-integrity and recovery defects. It should not be described as fully QA-passed, production-ready, or experimentally validated.

The existing regression suite passed **1,655 tests in 828.99 seconds**, but targeted QA reproduced defects those tests do not cover. The separate Python-client conformance suite has **one failure and three passes**, and the Python formatter check fails. These are current results, not historical claims from the roadmap.

## How to use this document

1. Read the immediate findings and capability matrices first.
2. Use the feature inventories and decision ledger to distinguish implementation work from scientific decisions.
3. Assign the task cards by ID. Each card states evidence, scope and acceptance criteria. Related cards are grouped in the delegation plan to prevent overlapping edits.
4. Close tasks only with the specified desired-behavior tests and a recorded statement of remaining limits. The diagnostic probes deliberately asserting current defects must be inverted into regression tests when a fix is implemented.

This is a dated audit, not a replacement for the living roadmap. Reconcile accepted tasks into `docs/ROADMAP.md`; retain this document as the evidence of the before state.

Contents:

- [Immediate findings and the earlier reported problems](#immediate-findings)
- [Fresh QA results and limits](#qa-results)
- [Actual support matrices](#support-matrices)
- [Feature-by-feature implementation inventory](#feature-inventory)
- [Closed decisions, open questions and roadmap reconciliation](#decisions)
- [Delegation plan and task index](#delegation)
- [Detailed task cards](#task-cards)
- [Release acceptance and reproduction](#release-acceptance)

<a id="immediate-findings"></a>
## 1. Immediate findings

| Priority | Finding | Practical consequence | Task |
|---|---|---|---|
| P0 | An authenticated caller reusing a known/guessed foreign idempotency key receives that user's run and private parameters | Account isolation can be bypassed through submission | [PLAT-01](#PLAT-01) |
| P0, conditional | Reviewer login can enter an existing privileged account named `reviewer` when the feature is enabled | Anonymous privilege escalation in that configuration | [PLAT-07](#PLAT-07) |
| P0 | Displayed AND/NOT logic does not control physical assembly; changing AND/OR/NOT can produce identical DNA | A ranked “circuit” can fail to represent the claimed logic | [ENG-01](#ENG-01), [ENG-02](#ENG-02) |
| P1 | Queue publication failure and interrupted RUNNING jobs can leave permanent nonterminal rows; stale transitions can undo cancellation | The original stuck-run problem can recur | [PLAT-02](#PLAT-02) |
| P1 | XLSX preview reads the first sheet; execution reads the active sheet | The software can run different genes from the ones the user previewed | [PLAT-03](#PLAT-03) |
| P0/P1 | Pasted FASTA text/ambiguous bases are silently altered; warnings and release holds are hidden | Users can submit changed biological input or misread results | [PD-02](#PD-02), [PD-04](#PD-04) |
| P1 | Truncated catalog raw-p tables receive a computed FDR claim without full-hypothesis evidence | Statistical significance is overstated | [ENG-03](#ENG-03) |
| P1 | Unbounded method caches retain completed folding-tool instances | A long-lived worker can accumulate memory across runs | [ENG-04](#ENG-04) |
| P1 | Antisense/AND and four absent payloads are offered as available | Selectable configurations fail or silently skip requested work | [PD-01](#PD-01), [ENG-09](#ENG-09), [GAP-01](#GAP-01) |
| P1 | High “success rate” can accompany predicted ON/OFF response below one; off-target scanning is absent | Scores are not calibrated efficacy or specificity evidence | [ENG-07](#ENG-07), [GAP-02](#GAP-02), [GAP-03](#GAP-03) |
| P1/P2 | Sequence exports are held by an unconfigured adapter, and result UI only loads 200 candidates | A completed run does not necessarily deliver usable exports or show all results | [ENG-14](#ENG-14), [PD-03](#PD-03) |

P0 means resolve before exposing the affected path or relying on its claims. P1 means core correctness, availability or advertised behavior is broken. P2 means a significant completeness, scalability or delivery gap. P3 means lower-impact behavior. Some task cards use a conditional priority because the risk depends on deployment or intended product scope; this is stated explicitly.

### 1.1 The run stuck at 0%

The recent changes do solve part of the problem: the Unix development server starts/supervises a worker, worker status uses a separate file cache, and expensive gene/trigger/switch stages publish incremental progress. The ordinary run path now has regression coverage.

They do **not** justify a promise that the problem cannot happen again. Fresh isolated probes showed all of the following:

- Enqueue failure after the database transaction leaves a QUEUED run without a published task.
- A fatal worker exit leaves RUNNING; redelivery cannot restart or fail it and returns without recovery.
- A stale worker's in-memory QUEUED record can overwrite a cancellation with RUNNING.
- Long folding operations, circuit enumeration and final export/import still need bounded cancellation, compute and memory behavior.

The exact original incident cannot be retrospectively diagnosed from a progress percentage alone. Fixing the reproducible mechanisms above, with kill/timeout/publication/race tests, is the concrete route to preventing indefinite stuck states. Do not mask them with a moving progress animation.

### 1.2 The arthritis dataset and disabled submit

The earlier lack of a Human reference/input path is no longer the current state. Human DE and gene submissions now resolve against a bundled mature-transcript reference, and the current code routes all three input modes. A retained live run of the named dataset completed earlier on the same day: run `4ec8cbcf-b5bd-41a8-818f-6464ec02b80a`, 7,907 candidates, 7,577 accepted, 15,157 recorded artifacts. That is **historical evidence from the preceding implementation work**, not a fresh full default-size rerun in this audit.

Fresh checks independently establish that its 3,000-row file parses, **2,894 IDs resolve and 106 do not**, and its statistics are 2,996 raw p-values with zero adjusted p-values. It is a selected/truncated catalog table; current BH handling is therefore a correctness issue. The bundled catalog labels its chosen comparison “Growth Medium” versus “none” in “normal”; the study title alone does not establish that this is a disease-versus-control classifier. The experimental/reference label is also imperfectly normalized. The relevant comparison must be verified against source metadata before interpreting a disease circuit (GAP-04).

The current browser correctly enables a resolved gene and invalidates it after editing, but still enables other incompatible mechanism/output choices. The UI also shows only the first 200 results, hides warnings and can leave a spinner on a completed zero-candidate run. Those are separate defects, not evidence that Human is wholly unsupported.

### 1.3 Human plasmid construction

Implemented: Human eukaryotic-toehold computational design, CMV promoter/hGH polyadenylation cassette composition, no restriction-standard default, and a custom circular GenBank backbone ingestion path. Bundled bacterial backbone choices are rejected for Human by the engine. Fresh GFP and custom-payload runs complete.

Still incomplete: no first-party mammalian backbone, no verified insertion-site/cloning plan, custom backbone annotation retention, payload-context evaluation, calibrated Human response model, or experimental validation. Without a backbone the product is a cassette, although GenBank currently labels it circular and the UI renders a plasmid ring. The existing Human export test uses a deliberately synthetic 100-nt backbone and a test-only release override; it verifies plumbing, not a functional mammalian vector or operational screening service.

### 1.4 What “all combinations” should mean

All **declared biologically applicable** combinations should have real implementations and acceptance tests. It is not meaningful to turn every Cartesian combination into success—for example, an E. coli-only vector must not be advertised as a suitable Human expression vector, and an apoptosis label is not a generic bacterial output specification. Unsupported choices need an explicit reason before queuing, while applicable missing features need real implementation tasks. A clean terminal error is valuable robustness evidence, but it does not count as support.

The shared capability contract must express organism, mechanism, input, output, vector/assembly and validation maturity together. Mechanism/payload integration tasks below are necessary to satisfy the earlier feature request; disabling inaccurate UI options is an immediate correctness measure, not completion of that request.

<a id="qa-results"></a>
## 2. Fresh QA results and limits

### 2.1 Executed checks

| Check | Fresh result | Interpretation |
|---|---|---|
| Main Python regression suite | **1,655 passed**, 828.99 s | Existing assertions pass on the current working tree |
| Host × mode × gate-family engine matrix within that suite | **96 cases pass their assertions** | 24 expect success; 72 expect clean failure. It does not establish 96 supported combinations |
| Additional host × payload direct executions | **24 runs:** 8 succeed, 16 fail cleanly | GFP/custom for each of four hosts succeed; four missing built-in outputs fail for every host |
| Additional host × table-format executions | **16/16 succeed**, progress monotonic to 100 | One genuine reference gene per fixture; CSV/TSV/TXT/XLSX for each host. Does not cover all workbook structures |
| Host × optional catalog backbone preflight | **44 combinations inspected:** 34 accepted, 10 Human catalog choices rejected | Tool-construction preflight only; acceptance for yeast/C. acnes does not establish vector compatibility |
| Bundled public catalog parse/reference audit | **15/15 parse**, all 45,000 retained rows checked for resolution | Coverage varies; full default-size pipeline reruns of all 15 were not performed |
| Scientific adversarial probes | Multiple defects reproduced, with exact outputs below | Logic, signed DE, FDR, motifs, malformed structures, nonfinite numbers, cache lifetime and Human metrics |
| Platform adversarial probes | **27 observations reproduced**, 9.04 s | These tests deliberately assert the existing defects, not desired acceptance behavior |
| Browser QA | **13 scenario probes** against real built UI with mocked APIs | Submission state, errors, input normalization, gene invalidation, results scale/warnings; no claim of a live backend in these probes |
| Python client edge probes | Timeout/filter/best/CSV/dry-run defects reproduced | Fake sessions and isolated API tests; no external server involved |
| Python client live-server conformance | **1 failed, 3 passed**, 1.78 s | Shared biological fixture yields no valid candidates; the conformance expectation requires candidates |
| Frontend `npm run check` | Pass | TypeScript, ESLint, seven logic render cases, help content: 3 pages/37 links/7 negative controls |
| Frontend production build | Pass, 3.45 s | Current browser bundle compiles; not an end-to-end UI certification |
| Ruff lint | Pass | Style/static rule checks only |
| Ruff format check | **Fail:** `src/config/settings/base.py:111` missing trailing comma | One file needs formatting; 1,021 already formatted. Existing product file intentionally not changed by audit |
| Django development system check | Pass | No reported configuration issues |
| Django production `check --deploy` | Pass with audit-only secret/localhost hosts | Static settings check, not proof of deployed TLS/proxy/storage/worker operation |
| Migration drift check | Pass, no changes detected | Existing migration definitions match current models |
| Generated API-surface check | Pass: 63 modules, 331 public callables | AST classification: 307 BUILT, 16 STUB, 5 ABSTRACT, 3 PROTOCOL; BUILT does not mean integrated or correct |

The client conformance failure was investigated rather than attributed to networking. Its 42-nt fixture scans 30 windows, generates 34 designs, and rejects all of them: 30 for extra AUGs and four for in-frame stops. The engine returns a successful empty result, which setup persists as COMPLETED; the test then requires a nonempty result. Use a known productive fixture and explicitly retain an empty-result test. Do not weaken the biological validator to restore a test count. Initial client socket errors were sandbox restrictions; after permitted localhost execution the real failure above was observable.

Installed versions checked locally: Python 3.13.15; Django 5.2.17; django-ninja 1.6.3; django-q2 1.11.0; ViennaRNA 2.7.2; Biopython 1.88; openpyxl 3.1.5; pytest 9.1.1; Ruff 0.16.4; Node v24.19.0. Dependencies came from the installed locked-workspace environment; this audit did not perform a clean network reinstall.

### 2.2 Scope boundaries

The audit combined full regression, source/call-path review, contract inventory, actual engine matrix runs, fault injection and browser probes. This is broad current-state QA, not an exhaustive proof over arbitrary datasets, all numeric settings or future failures. In particular, these were **not completed**:

- Full default-size reruns for every public comparison and every possible combined family/output/backbone/constraint set.
- Real multi-user load/soak, memory-plateau benchmarking, process-kill/OOM/disk-full drills on a deployed instance. Isolated lifecycle failures were tested without killing the user's active worker.
- Clean deployment/container/cloud equivalence, backup restoration, Windows execution or external-provider outage/refresh validation.
- R/MATLAB execution: those runtimes are unavailable. Source defects are identified without claiming runtime certification.
- Formal accessibility, screen-reader, multi-browser or physical mobile-device testing.
- Dependency-advisory scanning, external penetration testing, source licensing/legal sign-off, or live verification of every catalog publication and part record.
- Prospective experimental switching, truth tables, host performance, specificity or calibration studies. No runtime pass closes those scientific questions.

Logs and probe scripts remain under `var/audit-2026-10-08/`. Because `var/` is ignored, a durable companion [evidence archive](qa/2026-10-08-evidence.zip) preserves selected scripts, JSON observations, sanitized logs and source snapshot metadata. The report is self-contained; the archive enables reproduction and deeper inspection. It excludes the user's database/media and generated construct directories.

<a id="support-matrices"></a>
## 3. Actual support matrices

### 3.1 Organism and input routes

“Runnable” below means real pipeline execution exists for compatible single-input toeholds and a supported payload. It does not mean every input yields accepted candidates or that the resulting construct is scientifically validated.

| Host | Direct sequence | Named gene | DE upload | Bundled public comparisons | Reference scope |
|---|---|---|---|---|---|
| E. coli | Runnable | Runnable | Runnable, four formats | 5 | 4,308 CDSs; UTRs absent |
| Yeast | Runnable | Runnable | Runnable, four formats | 5 | 6,027 CDSs; UTRs absent |
| Human | Runnable | Runnable | Runnable, four formats | 5 | 77,902 selected mature transcripts; Ensembl 116; one transcript per gene |
| C. acnes | Runnable | Runnable | Runnable, four formats | 0 | 2,312 reference CDSs; UTRs absent |

These input classes are **not implemented**: FASTQ/BAM processing, raw-count-to-DE analysis, per-sample count matrix plus metadata in the product, arbitrary organism reference import, condition-specific isoform inference. A pasted long transcript is scanned; it is not a substitute for RNA-seq preprocessing. Current plain-sequence/FASTA handling in the browser needs PD-04.

### 3.2 Mechanisms

| Registered family | E. coli | Yeast | Human | C. acnes | Current integration |
|---|---|---|---|---|---|
| `toehold` | Runnable | Runnable | Runnable | Runnable | Generic host-adapting single-input family |
| `prokaryotic_toehold` | Runnable | Incompatible | Incompatible | Runnable | Single-input prokaryotic track |
| `eukaryotic_toehold` | Incompatible | Runnable | Runnable | Incompatible | Single-input eukaryotic track |
| `antisense` | Not integrated | Not integrated | Not integrated | Not integrated | Substantive component implementation; production pipeline skips it |
| `toehold_and` | Not integrated | Not integrated | Not integrated | Not integrated | Research helpers exist; production generation stub |
| `prokaryotic_toehold_and` | Not integrated | Incompatible/unintegrated | Incompatible/unintegrated | Not integrated | Advertised available, skipped in pipeline |
| `eukaryotic_toehold_and` | Incompatible/unintegrated | Not integrated | Not integrated | Incompatible/unintegrated | Advertised available, skipped in pipeline |
| `crispr` | Unimplemented | Unimplemented | Unimplemented | Unimplemented | Correctly advertised unavailable; scientific mode undecided |

The DE stage can enumerate multi-gene logical candidates even when using single-input families. That does **not** close the AND mechanism or physical circuit-compiler tasks.

### 3.3 Outputs and vectors

| Output choice | Actual direct-run result across four hosts | Limit |
|---|---|---|
| GFP | 4/4 succeed | Sequence/model context and host validity still provisional |
| Custom (`other`) with a valid short test CDS | 4/4 succeed | Fixture proves code path; arbitrary CDSs require input/context validation |
| mCherry | 4/4 fail | No configured payload sequence |
| Luciferase | 4/4 fail | No configured payload sequence |
| AmpR | 4/4 fail | No configured payload sequence; UI also confusingly mentions KanR |
| Apoptosis | 4/4 fail | No defined/configured payload; host-specific biological outcome needs specification |

Requesting multiple outputs does not necessarily create every circuit/output combination: current assignment is round-robin across designs, and unavailable outputs may be skipped. Product semantics must specify whether alternatives, exhaustive variants or co-expression are intended (GAP-01).

Ten catalog vectors exist: `psb1a3`, `psb1c3`, `psb1k3`, `psb1t3`, `psb1ak3`, `psb1at3`, `psb3c5`, `psb3k3`, `psb3t5`, `psb4c5`. Human rejects all ten. E. coli, yeast and C. acnes currently accept all ten during tool construction; this exposes missing host-compatibility enforcement for yeast/C. acnes. No-backbone composition is accepted for every host. Custom circular GenBank parsing exists, but successful parsing does not prove a valid vector/insertion design. See ENG-10.

All successful additional payload runs produced **design-table and safety-audit artifact kinds only** under the current release configuration. `accepted`, `COMPLETED`, and `released` are different states:

| Term | Current meaning | What it does not establish |
|---|---|---|
| `COMPLETED` / `succeeded` | Execution returned successfully | Nonempty results, implemented truth table, released sequence files |
| Accepted candidate | Passed implemented scoring filters | Biological function, off-target specificity, valid physical circuit |
| Artifact recorded | A file was created/imported | That it is a sequence, report, or usable orderable construct |
| Released sequence | Separate release policy permits sequence artifacts | Experimental efficacy; also not operationally available with current unconfigured adapter |



**Release scope clarification:** the current HOLD applies to FASTA/GenBank/SBOL artifact creation. `Candidate.design` still contains switch/component sequences and the candidate API exposes that JSON. The implementation therefore does not establish a universal sequence-disclosure barrier. ENG-14 must specify the intended scope and test both file and API serialization paths if policy is meant to cover all sequence disclosure. This audit did not alter the policy or bypass it.

### 3.4 All bundled public datasets: current parse and identifier coverage

Every entry contains 3,000 retained rows; none contains adjusted p-values. “Mapped” means row identifiers resolve to the installed sequence reference, not that all mapped genes survive selection. Alias collisions can reduce distinct mapped genes, especially in yeast. This table was generated from fresh inspection of all files.

| Catalog comparison | Host | Mapped / 3,000 | Unresolved | Raw-p rows | Distinct mapped genes |
|---|---|---:|---:|---:|---:|
| `ecoli__105638__44541816` | ecoli | 2969 | 31 | 0 | 2969 |
| `ecoli__138294__67644164` | ecoli | 2967 | 33 | 0 | 2967 |
| `ecoli__85809__68952326` | ecoli | 2970 | 30 | 0 | 2970 |
| `ecoli__88048__42635036` | ecoli | 2966 | 34 | 0 | 2966 |
| `ecoli__92117__44313016` | ecoli | 2964 | 36 | 0 | 2964 |
| `human__E-CURD-149__g3_g1` | human | 2866 | 134 | 1030 | 2866 |
| `human__E-CURD-45__g2_g1` | human | 2897 | 103 | 3000 | 2897 |
| `human__E-GEOD-103501__g3_g1` | human | 2894 | 106 | 2996 | 2894 |
| `human__E-GEOD-54112__g2_g1` | human | 2935 | 65 | 2567 | 2935 |
| `human__E-MTAB-2580__g1_g2` | human | 2965 | 35 | 2989 | 2965 |
| `yeast__E-GEOD-59814__g1_g2` | yeast | 2662 | 338 | 3000 | 2662 |
| `yeast__E-MTAB-10511__g5_g2` | yeast | 2365 | 635 | 2996 | 2364 |
| `yeast__E-MTAB-4651__g7_g1` | yeast | 2675 | 325 | 2978 | 2674 |
| `yeast__E-MTAB-5313__g1_g2` | yeast | 2646 | 354 | 3000 | 2645 |
| `yeast__E-MTAB-7657__g3_g1` | yeast | 2599 | 401 | 3000 | 2597 |

The five E. coli comparisons have no raw or adjusted p-values; ranking is therefore exploratory effect-size analysis, not demonstrated significance. Several Human/yeast comparisons are missing some raw p-values, and all catalog tables were selected/truncated. Preserve statistical completeness independently of display limits. Missing references and study-condition interpretation need visible warnings and an explicit update policy, not fabricated sequence replacements.

<a id="feature-inventory"></a>
## 4. Feature-by-feature implementation inventory

Maturity definitions: **runtime implemented** is called by the current product; **component implemented** has callable code but may not be integrated; **provisional** runs but has uncalibrated scientific assumptions; **stub** is an unimplemented method; **planned** has no delivered runtime. A feature may be implemented and still have confirmed defects.

### 4.1 Scientific engine

| Area | Current implementation stage | Evidence and practical limit |
|---|---|---|
| Direct sequence input | Runtime implemented | `pipeline.py:732–840`; short paste is one trigger; longer paste scans footprints; 20–10,000 nt accepted as direct input, alphabet enforced |
| Named-gene input | Runtime implemented | `pipeline.py:355–385`, `transcriptome.py:86–122`; resolves/fixes sequence through the reference; this is not measured differential expression |
| DE table input | Runtime implemented | `inputs.py:104–206`, `pipeline.py:912–975`; CSV, TSV, TXT and XLSX parser; consumes supplied DE results rather than computing DE |
| Reference sequences | Runtime implemented; biological coverage differs by host | Four references present: E. coli 4,308 CDSs; yeast 6,027 CDSs; C. acnes 2,312 CDSs; Human 77,902 mature selected transcripts, Ensembl 116. Counts were read from current files. `transcriptome.py:25–55` |
| Reference completeness | Partial by explicit design | E. coli/yeast/C. acnes lack UTRs; one Human transcript per gene cannot model tissue-specific isoform expression; reference selection is deterministic, not evidence that that isoform is expressed in the studied cells |
| Raw-count QC | Stub; absent from product path | `stages/quality.py:27–64`; product does not collect a per-sample count matrix |
| Stage 1 gene filtering | Runtime implemented, provisional ranking | Effect-size, available significance, optional abundance, transcript availability, coarse window-yield and direction balancing are real; `genes.py:401–542` |
| Stage 1 abundance/redundancy/specificity | Partial component behavior; mostly unavailable in runtime | No counts or atlas passed by `pipeline.py:943–953`; count-derived percentiles/correlations and atlas specificity cannot contribute; some abundance values can come from uploaded DE means if constraints are configured |
| Stage 1 significance | Implemented with a correctness gap | P-adjusted/raw/BH/missing tiers exist; completeness decision is insufficient; see ENG-03 |
| Stage 2 transcript folding | Runtime implemented | Real RNAplfold; window 200, max-span 150, unpaired max 20, fixed 37°C; `stages/folding.py:41–78,105–120` |
| Stage 2 trigger selection | Runtime implemented, research heuristic | Exact 30/33/36-nt footprints; selected joint P8, P20-derived opening-energy/nt, mean marginal openness; per-length ranking and round-robin cap 50 per gene; `triggers.py:42–46,65–120,205–223` |
| Trigger/off-target specificity | Absent | No transcriptome-wide sequence/off-target/interaction screen in current pipeline. Motif compliance and RNA folding are not off-target measurements |
| Single-input toeholds | Runtime implemented, provisional biological design | Generic and prokaryotic/eukaryotic aliases; loop and trailing-Kozak layouts; deterministic filler; no guaranteed experimental switch activity. `toehold.py:309–476` |
| Two-input toehold AND | Research helpers substantial; production generator stub | Assembly/screening/knockout/4-state helper methods exist; `generate_designs` still raises at `toehold.py:1979`; pipeline explicitly skips all AND aliases |
| Antisense NOT | Component implemented; unavailable in pipeline | `antisense.py` has construction and evaluation; payload argument is required; `pipeline.py:153–158` unconditionally skips it. “Real end to end” in roadmap is not product integration |
| CRISPR family | Stub | `crispr.py:89,123,141`; unavailable; effector identity/activation vs repression decision still open |
| Structural validation | Sequence rules only | Length, motifs, unique AUG, premature stops; no target-structure conformance or initiation geometry; `switches.py:275–295` |
| Global folding adapter | Mostly component/runtime implemented | MFE, partition, base-pair probabilities, ensemble defect and additional research methods exist; suboptimal structures and `structure_match` remain stubs (`folding.py:542,663`) |
| Translation-initiation tool | Stub, injected but unused | Four methods in `tools/translation.py` raise; toehold evaluator deliberately does not call it (`toehold.py:758–761`) |
| Codon optimizer | Component implemented, not connected to production assembly | Seeded synonymous optimization/scoring and C. acnes AIS-China references exist; `pipeline.py:224–247` builds them; toehold and plasmid builder only store the tool, never call it. Current constructed payloads are not optimized by this pipeline |
| Stage 3 metric calculation | Runtime implemented, provisional proxies | MFE, accessibility, binding-energy sigmoid, supplied DE fold-change, complexity; no calibrated probability of success; dynamic range is an accessibility ratio |
| Stage 4 Boolean enumeration | Runtime implemented | Conjunctions of signed genes; first/best existing design per gene; `circuits.py:112–145,225–255` |
| Stage 4 physical circuit realization | **Incorrectly implied / not implemented** | Logical expressions do not determine construct wiring; see ENG-01/02 |
| Confusion matrix / discrimination | Stub and unmeasured | `ConfusionEvaluator.evaluate` raises at `circuits.py:317`; runtime sends empty count matrix and does not call it; no sensitivity, specificity or measured circuit classification performance |
| Cross-gate orthogonality | Absent, even for multi-gene candidates | Single-gate raw metric omits it; worst-member aggregation cannot create it; profile still SKIPs it on multi-gate constructs (`profiles.py:170–185`) |
| Scoring normalization | Runtime implemented | Shared min-max/clamped normalization, hard filters, weights and ranking; defaults are provisional; declared tie-breakers are not applied |
| Pareto filtering | Component implemented, not connected | `store.py` implements a frontier; no call from pipeline; result list is one scalar ranking |
| Stage 5 parts and assembly | Runtime implemented, limited physical semantics | Registry-associated parts, GFP or custom CDS, ten bacterial backbones or opaque custom GenBank; concatenation, motif warnings and frame checks; no cloning plan or insertion-site model |
| Human construction | Computational cassette assembly implemented | CMV promoter/hGH polyadenylation; standard `none` default; custom vector or no backbone; upstream changes make Human input usable but do not resolve model/physical limitations |
| Full construct evaluation | Absent | Gate scores are calculated before output selection/assembly, without actual downstream payload/backbone context; see ENG-08 |
| GenBank and SBOL writers | Component implemented, runtime release held | Actual annotation writers exist; no successful current production release route; GenBank topology always circular even for backbone-free cassette |
| Stage 6 reports/figures | Stub | `reporting.py:44,62,121`; runtime “Writing report” writes candidates CSV + audit artifacts, not a PDF or scientific report |
| Intermediate provenance snapshots | Stub, not called | `store.py:48–104`; only ID allocation is used |
| Sequence safety/release gate | Policy component implemented; adapter absent | Local release result classes, manifest checks, review-token logic have code/tests; runtime always uses unavailable adapter and unconfigured host (`pipeline.py:1422–1451`, `safety.py:391–419`) |

### 4.2 Platform, API, runtime and delivery

| Capability | Current implementation stage | What exists and works in source/tests | Material qualification |
|---|---|---|---|
| Accounts | Implemented, normal flows tested | Registration creates inactive accounts, admin/CLI approval, session login/logout, pending-account messaging, Django password validation | No automated recovery/password-reset flow; login/registration are not abuse-throttled; login CSRF and reviewer collision defects below |
| Object authorization | Implemented with a serious bypass | Central ownership mapping for datasets, runs, candidates, artifacts, annotations and keys; staff override; non-owner object URLs return404 | Idempotent submission bypasses ownership, exposing another user's run; DEBUG media routes bypass ownership entirely |
| API keys | Implemented, lifecycle partially hardened | Secret shown once; stored SHA256 digest; constant-time digest comparison; indexed prefix; inactive-owner/revoked/expired rejection; issue/revoke/regenerate; session-only key administration | Empty scopes still read; read keys write datasets; expiry/regeneration edge cases; prefix collisions lack retry |
| Rate limits and quotas | Implemented for API-key requests | Shared database cache; rate bucket per key; owner active-run ceiling on submissions | Session/auth endpoints exempt; read/count/create operations not atomic; retries blocked at quota; no job budgets |
| Dataset ingestion | Implemented for CSV/TSV/TXT/XLSX | Size/row limits, checksum, common column aliases, preview, example and public comparison materialization, provenance | First-sheet/active-sheet mismatch, parser/validator divergence, nonfinite numerics, whitespace-header bypass, filename/display-name confusion |
| Input routes | Implemented submission plumbing | DE dataset, direct sequence, reference gene; reference gene is resolved and sequence/reference metadata frozen | API host and params host can disagree; malformed nested constraints/scoring often reach500 or asynchronous failure |
| Run creation and polling | Implemented happy path | Immutable-intent snapshots, queued-on-commit, capability checks, polling/detail, idempotent-intent submission, worker availability on QUEUED runs | Global idempotency key disclosure, non-atomic transitions, enqueue failure leaves0%, no stalled RUNNING health signal |
| Worker startup supervision | Implemented for local Unix development | runserver/devserver starts queue worker, restarts missing/exited/stale-heartbeat worker, shared lock, filesystem heartbeat cache | Process recovery does not reconcile abandoned analysis rows; Unix-only primitives break native Windows; no production supervisor configuration |
| Cancellation | Cooperative implementation | Queued run can cancel immediately, running engine checks callback, completed runs ordinarily unchanged | Stale snapshots can undo terminal state; import/completion window does not re-check cancellation; hard kill has no recovery |
| Result persistence | Implemented atomic SQL import | Candidate and metric rows, rejected-candidate reasons/ranks constrained, checksummed artifact copy, derived summary/manifest | Contract validation incomplete; source path escapes; disk writes outlive transaction rollback; admin can modify scientific records |
| Results explorer API | Implemented | Owner-scoped candidate list/detail, pagination/filter/sort, metrics, artifact list/download, annotations | Large result/detail/artifact responses lack comprehensive bound/streaming strategy |
| Exports | Implemented with correctness defects | CSV table, individual files, selectable ZIP, platform manifest | Numeric zero lost from CSV; missing ZIP files silently omitted; no post-import checksum verification on download; manifest omits some reproduction identifiers |
| Public design API | Implemented basic wrapper, partial contract | One-call submit, optional wait, dry-run estimate, statuses/results, scoped keys | Dry-run skips input validation; budgets accepted but ignored; include_metrics unused; `/design` lacks `/runs` backbone input parity; estimate stale |
| Python client | Implemented, conformance currently fails1/4 | requests client, typed errors, polling, DataFrame conversion, artifact save | wait timeout mismatch, dry-run wait succeeds, CSV decoded as JSON, async result options lost |
| R/MATLAB clients | Implemented wrappers, runtime unverified in this audit | Submission, polling, capability/results/artifacts, language-specific result tables | Their conformance tests are not in current CI; singleton array encoding and error/timeout behavior need language-runtime tests |
| Admin | Implemented inspection/approval tools | Registration queue, runs/candidates/artifacts, key management | Several supposedly immutable fields remain editable; metrics standalone admin fully editable |
| Production | Design/planning stage | prod settings require secret/hosts and configure TLS cookies/HSTS/Whitenoise/logging; CI exists | `deploy/` contains only `.gitkeep`; no executable web/worker deployment, backup/restore, readiness, monitoring or retention runbooks proven |

A passing ordinary workflow establishes that the software can complete that workflow. It does not establish privacy isolation, reliable restart, scientific correctness, all input variations, or production readiness. The defects below explain why those should remain separate acceptance criteria.

### 4.3 User interface and clients

| Feature | Current implementation stage | Evidence and remaining work |
|---|---|---|
| Sign-in, sign-out, protected routes | Implemented and backed by platform tests | Session/CSRF API client, `RequireAuth`, login/logout mutations. Login redirect returns to requested route. Network failure handling is inconsistent across forms. |
| Registration and approval | Implemented | Registration form creates an approval request; staff approves in admin. No self-service password reset, email verification/delivery, or profile editor is present. Whether these are required is a product decision. |
| Reviewer entry | Implemented, deployment-configured | Login shows reviewer button only when `/version` says enabled. Shared account suitability and restrictions need explicit deployment policy. |
| Dashboard | Implemented with a scale/error gap | Fetches latest 50 runs without pagination/search; HTTP 500 currently appears as “No circuits yet”. `routes/dashboard.tsx:21`. |
| Organism selection | Implemented for four organisms | E. coli, yeast, Human, C. acnes. Selection resets dataset/gene and chooses a mechanism/backbone default. Human and yeast use no backbone; C. acnes defaults to bacterial pSB1C3, which needs explicit host suitability review. |
| DE upload | Implemented | CSV, TSV, TXT, XLSX inputs supported in current backend. UI upload/error/validation preview exists. Uploaded datasets have no enforced organism association in the wizard. |
| Public DE catalog | Implemented for three organisms | Experiment/comparison metadata, accession/source links, log2FC direction, materialization and preview. C. acnes has no curated entries and the empty picker gives no explanation or alternate route. |
| Gene lookup | Implemented for four organisms | Stable IDs/symbols resolve against offline reference, with canonical ID returned. Human mature transcript selection is shown. Browser probes passed resolution→enabled submit and edited-gene→disabled submit. Old instruction still says “Record it here, then paste its sequence.” |
| Direct sequence input | Implemented, unsafe input-normalization UX | Lowercase/DNA normalization is useful, but every non-ACGUT character is silently deleted. Ambiguous bases and FASTA headers can change biological meaning without an error. Browser proof below. |
| Gate-family selection | UI and backend capabilities disagree with runnable pipeline | UI enables all `available=true` families, including antisense and AND variants skipped by `pipeline._UNBUILDABLE_FAMILIES`. Host-only variants remain selectable on incompatible hosts. CRISPR is correctly disabled. |
| Leakage/stability/max-gates controls | Implemented | Wizard sends scoring filters and `constraints.max_circuit_gates`. A choice from 1–4 is exposed. Scientific meaning of combined-circuit AND behavior needs separate engine review. No browser budget control is exposed. |
| Payload selection | Partially implemented | GFP and custom coding sequence are runnable. mCherry, luciferase, AmpR, apoptosis are enabled UI options but absent from the built payload library. “AmpR · KanR” is displayed for a single `ampr` enum, not independent alternatives. |
| Custom payload | Implemented at assembly, incomplete early validation | UI strips invalid characters and checks only length≥3. ORF/motif checks occur later. No meaningful sequence/length/translation feedback in the wizard. |
| Vector choice and custom GenBank upload | Implemented composition/export support | Ten catalog entries, custom upload, or none. Human catalog-backbone blocker exists and is useful, but incompatible catalog choices remain visible. No assembly protocol/insertion-position plan is captured by the UI. FileReader errors are not shown. |
| Submission/idempotency | Implemented, requires backend audit fixes | One key is minted for wizard session. Repeated submits can reuse the same key after configuration edits/recovery. Backend ownership and request-equality enforcement must decide safe replay semantics. |
| Run progress and cancel | Implemented | Polling every three seconds; terminal status stops polling; queued offline worker message, failure summary and cooperative cancellation UI. Cancel mutation failures are not shown. A failed polling request is conflated with run-not-found. |
| Ranked results | Implemented but incomplete at real data sizes | Fixed limit 200, no pagination, hidden total. For the historical arthritis run’s 7,907 candidates, the UI cannot browse most candidates. Filtering only the fetched subset can hide valid outcomes elsewhere. |
| Candidate detail and metric decomposition | Implemented, scientific claims need correction | Real design/metric fields drive view; missing raw values render as em dash. UI calls success metric “confidence … in vivo”, orthogonality “Off-target”, and results subtitle says off-target screening despite no integrated scanner. |
| Candidate and run warnings, frozen config/provenance | Stored/API-visible, absent from results UI | Types include warnings and full-run hook exists, but run page never renders them. This hides unavailable measurements and why sequence exports are withheld. The guide explicitly acknowledges the gap. |
| Plasmid/logic visualization | Implemented, interpretation limits | Proportional ring and variable-size logic rendering exist. Ring always depicts a plasmid, including no-backbone constructs; presentation needs explicit cassette/topology status. Logic visualization is not validation that assembled molecular parts execute that truth table. |
| Result filtering | Implemented over first fetched page | Rank/score/family/ref sort, min-score, include-rejected, output filter. Selected detail is not reset when filters hide that candidate. Empty results leave a perpetual detail spinner. |
| Downloads | Implemented with metadata and category grouping | Per artifact, category ZIP, selected ZIP, all ZIP. Actual release depends on backend sequence gate. UI describes PDF/diagrams as categories even though scientific reporting modules remain stubs. No clear explanation of held sequence exports. |
| Candidate annotations/decision tags | Backend/API plus unused hooks | `useAnnotations`, create/delete hooks and typed decision tags exist; no user-facing component calls them. Product scope needs a decision. |
| Synthesis ordering | Explicitly unavailable | Disabled button “Order Plasmid with Our Trusted Partner”; no partner integration. Do not count it as implemented. |
| API-key management | Implemented | Create scoped key, display secret once, copy, revoke, reset, expiry/status. Errors on revoke/reset are not rendered. API-key secret copy should handle clipboard failure accessibly. |
| Guide/FAQ/use cases/API docs/about | Implemented routes and static-render checks | Better disclosure than some result screens, but contradictions remain across engineering and product docs. API docs omit new `gene_id` field from exhaustive field listing. |
| Python client | Implemented, conformance lane, important edge gaps | Thin HTTP client + polling, results, optional DataFrame, artifact download, capabilities. Four committed conformance tests cover precompleted run, capabilities, bad key and typo validation; not real asynchronous queue behavior. |
| R/MATLAB clients | Written, unverified, visible contract defects | See client findings below. Present them as experimental until executable conformance passes. |
| Developer/admin tools | Implemented for local deployment | Django admin, demo seed, API-key issuing, offline source sync, supervisor and worker. Container/cloud production path remains planned. |

<a id="decisions"></a>
## 5. Closed decisions, open questions and roadmap reconciliation

### 5.1 Scientific question ledger: Q1–Q15

“Implemented” closes a software wiring question; it does not establish experimental validity. Scientific decisions should have an accountable human owner and recorded evidence, not only a chosen constant.

| ID | Current disposition | What is implemented / settled | What still needs a decision or proof |
|---|---|---|---|
| Q1 — where trigger sequences come from | **Closed for baseline software coverage; reference policy partially open** | Four bundled references; offline IDs/aliases; Human mature cDNA/ncRNA, MANE/canonical/length policy; gene mode freezes resolved sequence. `transcriptome.py`, sync tools and reference tests. | Arbitrary strains, isoforms, alternate transcripts, UTR completeness in CDS-only organisms, reference refresh cadence, unresolved/ambiguous IDs and gene-table mismatch policy. Coverage is not all possible biological input identifiers. |
| Q2 — trigger/gene thresholds | **Defaults implemented; scientific ratification open** | Constraints include min separation 0.5, max adjusted p 0.05, max genes 20, optional expression/fold-change ceiling, GC band, direction balance; real GeneSelector and TriggerScorer. | Agree thresholds per assay/host; significance availability and truncated-table behavior; abundance requires data current uploaded DE may lack; calibration benchmarks. |
| Q3 — trigger/circuit arity and compute | **Partially implemented; scope open** | Default max_triggers 2, max_circuit_gates 2; circuit enumeration exists; UI allows 1–4 gates. | Distinguish inputs to one molecular gate from multiple transcription units; choose actual supported biological logic and resource ceilings before advertising3/4-input circuits. AND molecular gate generation remains unbuilt. |
| Q4 — toehold construction rules | **Single-input implementation; AND open; validation provisional** | Host-aware ToeholdGate construction and footprint rules, prokaryotic/eukaryotic variants, tests. | Team approval of geometry and allowed variants; eukaryotic expression context; two-input AND construction; wet-lab validation. Roadmap “blocked, no bodies” is stale. |
| Q5 — leakage and dynamic range from folding | **Proxy computation implemented; calibration open** | Toehold/antisense evaluation produces raw metrics with defined thermodynamic conventions. | Validate proxies and units against functional assays; do not convert accessibility correlation or heuristic confidence into in-vivo success probability. |
| Q6 — final metrics and weights | **Provisional, open** | Nine-metric default profile, normalization, custom weights/filters, versioned profile labels. | Agree missing-value behavior, meaningful axes/weights, cross-family comparability and benchmarked confidence; decide unsupported-metric presentation. |
| Q7 — hard disqualifiers | **Mechanism implemented; scientific policy partial** | Sequence checks, score hard filters and a fail-closed artifact gate are implemented; assembly violations are warnings and structural conformance is absent. | Structural conformance remains open; decide which assembly findings are release blockers vs advisory; require scientific evidence for off-target/efficacy gates; align accepted candidate status with released construct status. |
| Q8 — organism effect | **Answered in code at baseline; biological completeness open** | Host selects track, reference, promoters/terminators, codon tables and some geometry. | Host/strain validation, transcription/translation context, appropriate vector and optimization policy; host-capability exposure; integration of TranslationScorer. It is no longer just input labeling. |
| Q9 — antisense trigger acts or drives | **Closed design choice; integration open** | `AntisenseNotGate` acts directly and standalone implementation/tests exist. Amplification via a separate antisense transcription unit is not built. | Wire payload injection, output polarity and pipeline assembly before advertising usable antisense runs; name owner. |
| Q10 — CRISPR activator/repressor | **Open; unimplemented** | Interface and unavailable registry entry exist. | Choose effector, polarity, target/PAM/genomic reference and genomic off-target requirements; name scientific owner before implementation. |
| Q11 — payload sequences | **Partial** | GFP reference and user custom ORF path. | Verified mCherry/luciferase/AmpR/apoptosis identities and host policies; distinguish AmpR/KanR; payload optimization and integration; do not expose absent payloads as working choices. |
| Q12 — promoter/termination | **Part libraries implemented; biological/protocol validation partial** | Ecoli, yeast, Cacnes, Human parts; Human CMV/hGH Registry identifiers and default standardnone. | Expression-context validation, strand/transcription unit design, cloning protocol and tolerances; no claim of validated mammalian switch behavior follows from verified part sequence. |
| Q13 — backbone | **Ecoli catalog/custom parser built; per-host choices open** | Ten BioBrick catalog vectors, circular custom GenBank, explicit no-backbone option. | Compatible Human/yeast/Cacnes vectors and propagation/expression distinction; insert location/removal of existing cassette; full annotation retention; laboratory strain/selection choice. |
| Q14 — RNA class/region rules | **Open** | Generic scanning and class-limited references work. | UTR/CDS/lncRNA/sRNA policy, full-vs-window functional RNAs, isoform/condition choice. Requires sequence annotation/input model work, not just threshold tuning. |
| Q15 — what makes a window good | **Engineering rule closed; predictive validity open** | Exact30/33/36 gate footprints, selected P8/P20/marginal openness and round-robin bucket union documented and implemented. Separate nucleation-ranking utility is explicitly non-production. | Calibrate against functional switching, host and cellular context; determine whether joint-opening hypothesis outperforms simpler metrics. Do not silently substitute utility ranking for production stage. |

### 5.2 Additional unresolved decisions outside Q1–Q15

- **Raw counts and metadata:** current product consumes precomputed DE, direct RNA, or gene lookup. CountMatrix/SampleMetadata types do not make raw-count input implemented. Decide whether raw-count/metadata/QC and external DE preprocessing enter scope, and define organism/condition/schema constraints. `integration.md`’s PyDESeq2 conflict remains a product/science decision.
- **Circuit discrimination:** per-gene thresholds vs global cutoff, held-out validation, bootstrap/leave-one-out, observed-state semantics and boolean minimization remain unresolved (`integration.md` GAP-2). ConfusionEvaluator is still a stub. Preserve missing metrics rather than fabricate accuracy.
- **Two-pass design:** implement cheap pre-switch PassA + post-switch PassB, or formally defer it (`integration.md` GAP-3). Current pipeline is one forward pass.
- **Pareto integration:** utility is implemented but unused. Decide objectives and which stage applies it; name owner.
- **CandidateStore:** typed records already pass between stages. Confirm recorder-only architecture; snapshot/load remain stubs. Source doc recommendation is not a completed team decision.
- **Off-target scope:** detailed `off-target-analysis.md` proposes standalone IntaRNA-first evidence scoring and a 10-minute/8-GiB benchmark gate. It is a plan, not integrated software; it also incorrectly mentions MockEngine CI and all bundled references CDS-only after Human support landed. Decide measured backend feasibility and integration phase.
- **Release gate and intended product:** choose what users can download today, how unresolved scientific validation is represented, and who approves release policy. An accepted/ranked candidate may still have all sequence files held.
- **Ownership:** historical integration table assigns Shir QC, Ze’ev genes/databases, Liran triggers, Aviv generation/validation, Offer circuits, Ziv plasmids/reporting. Treat these as historical suggestions, not confirmed present commitments. Antisense/CRISPR explicitly lacked owners; also assign references, calibration, data stewardship, client releases, UI QA and operations.

### 5.3 Closed architecture decisions and limits

| Decision | Status against current source | Implication |
|---|---|---|
| ADR0001 single repository + in-process engine | Implemented | Engine boundary tests and frozen contract remain; no remote-engine service is built. |
| ADR0002 SQLite WAL + django-q2 ORM queue | Implemented | One configured worker, timeout 3600/retry 3660/max_attempts1. Recent contention makes load/recovery tests necessary; it does not automatically authorize a database replacement. Review operational backup guidance for WAL-consistent backup. |
| ADR0003 same-origin SPA + session auth | Implemented | Central browser API client sends CSRF/session credentials; no JWT/CORS architecture needed. |
| ADR0004 Django Ninja | Implemented | Typed REST/OpenAPI router structure. |
| ADR0005 static SPA rather than TanStack Start | Implemented | Vite emits `src/static/app`; TanStack Router SPA served same origin. |
| ADR0006 API keys as second credential | Implemented | Scopes and key lifecycle share existing API surface. Requires security audit findings to be fixed without replacing architecture. |
| ADR0007 Biopython GenBank handling | Implemented | BioPython used for parsing/export and references; no pydna/OpenCloning assembly service is present. Composition export is not a cloning protocol. |
| ADR0008 native SBOL3 export | Implemented, release-gated | Standardized artifact emitted alongside GenBank/FASTA when release permits; no Registry publishing. |
| Frozen records/functions instead of mutable engine job object | Implemented convention and tests | Python client `Job` is only an HTTP handle; do not confuse it with prohibited engine god-object. |
| Shared injected tools, raw metrics, centralized normalization | Implemented architecture, house-rule checks | Adding another private folding/scoring implementation would violate current design. |
| Host as parameter, explicit track-specific behavior | Implemented with registry convenience subclasses | Do not reopen architecture because host names differ; validate actual differing rules. |
| Python3.13 | Enforced in project metadata | Current dependency compatibility baseline; change requires explicit tested migration. |
| Deployment/repository separation | Settled principle, deployment not built | A future container can build repository subset without splitting repositories. |

### 5.4 Complete ROADMAP reconciliation

Rows below correct status, not priority. “Partial” means some named deliverables exist and others do not; it must not be turned into “done” from a passing test count alone.

#### Platform P

| ID | Current status | Evidence / next action |
|---|---|---|
| P1 organism duplication | Open | Free-text top-level organism plus enum-like params remain; `_resolve_host` prefers params. Choose authoritative field and migrate. |
| P2 host capabilities | Open and broader than original | `/version` globally describes families; add integrated-buildability and payload/backbone compatibility (PD-01). |
| P3 custom sequence validation | Partial | Assembly ORF validation exists; submit/wizard validation weak; early errors and length cap still needed. |
| P4 retention | Open | No artifact/dataset retention command or stated policy. |
| P5 cost-weighted progress | Substantially implemented; stale task | `_pct` consumes STAGE_WEIGHTS; gene/switch progress callbacks exist. Still test long circuit/assembly/export phases and cancellation responsiveness. |
| P6 worker timeout | Current policy unchanged |3600-second timeout and3660 retry. Raise only after measured demand and recovery design; not intrinsically a bug. |
| P7 CI extension | Partial | Backend/frontend/Python-client jobs exist. No real browser, R, container equivalence or cloud failure lane. “Keep MockEngine” instruction obsolete. |
| P8 engine type checker | Open | No mypy/pyright config/dependency in pyproject. |
| P9 AND selectable but unbuilt | Still open at submission/product boundary | Pipeline now skips with named warning rather than directly invoking stub; UI/API available flag remains misleading. |

#### Engine E

| ID | Current status | Evidence / next action |
|---|---|---|
| E0 dependency groups | Open | All platform/science deps remain in main dependencies; dev extra only. Necessary only before separate deployments, not a blocker for local pipeline. |
| E1 tools | Partial | Sequences/motifs/ViennaRNA folding/binding/FoldProfiler/codon optimizer exist. TranslationScorer methods remain stubs; nonempty transcriptome off-target scanning remains absent. |
| E2a direct smoke | Implemented and tested | Now all four hosts; longer direct sequence scanning exists. Old “single short trigger/Ecoli-only” carve-out descriptions historical. |
| E2b direct trigger selection | Implemented, evolved | Gate-aware exact footprints and provenance supersede stated T4/T5 blockers; RNA-region policy Q14 and functional calibration still open. |
| E2 input/genes/triggers | Implemented for DE/gene routes; raw-count QC open | Human/Cacnes no longer blocked by missing reference. InputQualityCheck remains uncalled/stub. |
| E3 combinations/pruning | Partial | Trigger sets, shortlisted genes and circuit gate cap exist. Meaningful combination policy, biological mapping and budget enforcement need review. |
| E4 toehold | Partial, significantly built | Single-input construction/evaluation real; AND gate stub; translation/context/functional calibration unresolved. |
| E5a first construct | Implemented composition, scope expanded | Hosts beyond Ecoli, all input routes and multi-switch assembly supported in code. GFP/custom only; output-release gate limits downloadable sequences. “Orderable” is too strong without protocol/validation. |
| E5b selectable backbone | Implemented, per-host/insertion semantics incomplete | Ten catalog vectors plus custom/no-backbone. Standard fragments and complete vector handling need scientific review. |
| E5 circuits/plasmids/report | Partial | CircuitDesigner and multi-switch assembly exist. ConfusionEvaluator, StructureRenderer and ReportBuilder stub; boolean truth table does not prove physical implementation. |
| E6 switch and measure | Switched; measurement partial | LocalEngine is only concrete engine/default; prior real run timings exist. Formal wall-time/peakRSS/cores benchmark baseline not complete. MockEngine-retention instruction stale. |
| E7 parallelism | Open for production design evaluation | No ProcessPoolExecutor in core pipeline. Parallel offline benchmark tools are a different feature. Profile actual remaining cost first. |
| E8 tests | Large implemented test suite, coverage incomplete | Real folding, deterministic/golden/matrix/reference and boundary tests exist; obsolete sub-second suite goal. Missing end-to-end UI/error/scale/client/functional-validation coverage remains. |
| E9 explanatory reporting | Partial | Warnings/features exist; tool/reference provenance is uneven and UI hides it. Default state/payload polarity and missing measurements need coherent report. |
| E10 CandidateStore | Partial/open decision | mint_id implemented; snapshot/load_snapshot stubs. Typed stage data used; recorder decision should be ratified. |
| E11 Pareto | Utility implemented, integration open | `ParetoFilter.frontier/top_k` implemented; no production caller. |

#### Container/cloud C

| ID | Current status | Next required evidence |
|---|---|---|
| C0 performance sizing | Partial | Representative wall time, peakRAM, disk/artifact volume and concurrent web responsiveness with model/reference version. |
| C1 runner/container | Not built | `deploy/` contains only `.gitkeep`; build/run local contract payload in clean container. |
| C2 equivalence | Not built | Same request local vs container, deterministic result/artifact/hold semantics. |
| C3 cloud IAM/storage | Not built in repository | Named deployment owner and infrastructure evidence; no assertion about external cloud state from absence of code. |
| C4 CloudRunEngineClient | Not built | Only LocalEngine concrete class. |
| C5 upload to bucket | Not built | Authorized storage path, lifecycle and boundary contract. |
| C6 remote progress/cancel/idempotency | Not built | Local support exists; remote failure/retry semantics need design/tests. |
| C7 cloud failure drills | Not built | Kill execution, denied IAM, duplicate request and corrupt artifact tests after remote implementation. Local drills do not close cloud tasks. |

#### External integration X

| ID | Current status | Remaining work |
|---|---|---|
| X1 key model/services/admin | Implemented | Security/owner tests remain release gate. |
| X2 auth/endpoints/whoami | Implemented | Review broad security audit findings separately. |
| X3 scopes/throttle/concurrency | Implemented with operational tests needed | Atomic quota/identity behavior under concurrency. |
| X4 metric metadata | Implemented | Correct overconfident descriptions and missing-measurement semantics. |
| X5 design fast path | Implemented with contract gaps | Default families overpromise; async filters/budget/dry-run consistency need fixes. |
| X6 budgets/dry-run | API estimate implemented; runtime enforcement incomplete | Rough estimate is not a compute ceiling. Roadmap explanation “pipeline does not exist” stale. |
| X7 custom scoring | Implemented | Scientific acceptance of defaults/overrides and safe validation remain review items. |
| X8 Python client | Implemented; CI tests narrow; not established published | PD-07/08, queued conformance, package release verification. |
| X9 R client | Written, unverified, test/shape defects | PD-09; real CI lane. |
| X10 MATLAB client | Written, unverified, request/table defects | PD-09; licensed supported-runtime check. |
| X11 integration docs | Implemented but drifted | New gene field, actual API/client behavior and package availability. |
| X12 webhooks | Deliberately not built | Polling sufficient unless product need changes; no need to invent webhook work now. |

#### Public datasets D and standards S

| ID | Current status | Remaining work |
|---|---|---|
| D1 provenance models/schema aliases | Implemented | Preserve gene identity and source column mapping across normalization. |
| D2 adapters/curated catalog | Implemented for three hosts | Cacnes catalog absent; source refresh/accession/gene mapping/truncation validation ongoing. |
| D3 materialization | Implemented | Owner isolation/idempotency and checksum validation under concurrency. |
| D4 browse/materialize/preview API | Implemented | Pagination/completeness of preview and clear source/uncertainty messaging. |
| D5 wizard | Implemented; outdated status text | Gene is functional now, not informational. Empty/error/race states need PD-05/06. |
| D6 reference resolution | Implemented all four organisms | Q1 reference-policy extensions and refresh governance. |
| S1 SBOL3 export | Implemented and release-gated | Standard compliance/round-trip provenance tests, clarity of held exports. |
| S2 Registry mapping/sync | Implemented | Now17 mapped parts, not historical 15; no network needed at runtime. |
| S3 offline drift tests | Implemented | Keep provenance and byte sequence identity coupled. |
| S4 Registry publishing | Deliberately not built | Requires explicit authorized external publishing and release policy; not part of software QA closure. |

<a id="delegation"></a>
## 6. Delegation plan

There are **47 task cards**: 16 platform, 14 engine, 12 product/client/documentation, and 5 cross-cutting completion tasks. Some cards are deliberately implementation sub-tasks of a wider workstream, not independent competing projects. Suggested owner roles are assignments to make, not claims that a named team member has agreed. Scientific scope/threshold/payload decisions require an accountable domain reviewer; an agent can prepare evidence and implement a chosen specification.

### 6.1 Parallel workstreams and dependencies

| Workstream / suggested owner | Assign together or coordinate | Start condition / dependency |
|---|---|---|
| Account security / backend agent | PLAT-01, PLAT-07, PLAT-08, PLAT-09, PLAT-15 | Start immediately; namespace idempotency before broader submit refactoring |
| Queue and recovery / runtime agent | PLAT-02, PLAT-11; coordinate ENG-04/13 | Start immediately; agree lease/retry semantics and durable artifact handoff |
| Input integrity / parser agent | PLAT-03, ENG-11, PD-04 | Start immediately; define one normalization contract without violating engine/platform boundary |
| Physical circuit correctness / engine + scientific reviewer | ENG-01, ENG-02, ENG-09, GAP-03 | Immediately stop unsupported claims; topology/polarity decisions precede mechanism completion |
| Statistics and reference data / computational-biology agent | ENG-03, GAP-04, Q1/Q2/Q14 | Start completeness/provenance fixes immediately; dataset interpretation needs review |
| Scoring and validation / modelling agent | ENG-05, ENG-06, ENG-07, ENG-13, GAP-02/03 | Preserve existing raw evidence; agree scientific definitions before tuning thresholds |
| Constructs and outputs / assembly agent | ENG-08, ENG-10, GAP-01 | Payload/vector policy and physical circuit contract constrain implementation |
| API/capabilities / contract agent | PLAT-05, PD-01; coordinate ENG-09/GAP-01 | Share capability design with UI; do not independently hardcode another matrix |
| Results integrity and release / results agent | PLAT-04, PLAT-06, PLAT-10, ENG-12, ENG-14 | Zero/admin/path fixes can start now; coordinate manifest and release-state schema |
| Frontend usability and QA / frontend agent | PD-02, PD-03, PD-05, PD-06, PD-11 | Can start now against agreed contract fixtures; release labels depend on results work |
| SDKs / client agent | PLAT-12 plus detailed PD-07, PD-08, PD-09 | Treat PD cards as SDK sub-tasks; first repair productive/empty conformance fixtures |
| Delivery / operations and docs agents | PLAT-13, PLAT-14, PLAT-16, PD-10, PD-12, GAP-05 | Current-status docs and CI repair now; deployment acceptance after recovery/security fixes |

Avoid simultaneous edits to `pipeline.py`, `apps/analyses/services.py`, `api/params.py` and result schema modules by multiple agents without agreed interfaces. Within the same workstream, one agent should own integration. PLAT-16 and PD-10 are one documentation effort; PLAT-12 and PD-07–09 are one SDK effort; ENG-09 is chemistry implementation while PD-01 is honest capability exposure. Their completion criteria differ.

### 6.2 Recommended order

**Wave 1 — protect users and result meaning:** PLAT-01/07, ENG-01/02, PLAT-03/04, PD-02/04; repair the two deterministic CI failures in GAP-05. Restrict unsupported claims while implementation proceeds.

**Wave 2 — reliable execution and truthful contracts:** PLAT-02/05/06/08/09/10/11, ENG-03/04/05/11/12, PD-01/03/05/06. Add failure-mode tests before expanding throughput.

**Wave 3 — complete promised science:** ENG-06–10/13/14, GAP-01–04, missing AND/NOT/CRISPR and reports. Split mechanism work into explicit chemistry sub-deliverables with independent truth-table and validation evidence. Off-target integration depends on measured feasibility and defined applicability, not on a UI toggle.

**Wave 4 — delivery and maintenance:** client conformance, Windows support, measured deployment, retention/restore, documentation/attribution. Docs can run in parallel from Wave 1; cloud services are conditional scale work, not a prerequisite to fixing the local software.

### 6.3 Explicit ownership of remaining public stubs

The generated inventory has 16 public methods classified STUB. Each must be implemented under a defined requirement or deliberately deferred with its capability unavailable; implementing unused methods for a count alone is not a product goal.

| Remaining method group | Count | Owning task / closure requirement |
|---|---:|---|
| Folding `structure_match`, `suboptimal` | 2 | ENG-06: define needed structural validation, implement and independently verify applicable methods, or document deferral |
| `TranslationScorer.score`, `rbs_strength`, `kozak_match`, `ramp_is_unstructured` | 4 | ENG-06/08: scientific initiation/context model and tests before integration; expose unmeasured state if deferred |
| CRISPR `generate_designs`, `evaluate_design` | 2 | ENG-09 plus Q10 decision; real family integration, compatible targets and validation |
| AND `generate_designs` | 1 | ENG-09 and ENG-01; chemistry realization and complete truth-table testing |
| `ConfusionEvaluator.evaluate` | 1 | GAP-03 after per-sample input/objective decision; independent observed-state benchmark or explicit deferral |
| `InputQualityCheck.check` | 1 | GAP-03 after raw-count/metadata input scope decision; counts/QC route or explicit unsupported modality |
| Structure/circuit rendering and report build | 3 | ENG-14: actual diagrams/report artifacts with honest release/provenance labels |
| `CandidateStore.snapshot`, `load_snapshot` | 2 | ENG-12: ratify recorder-only role; implement reproducible audit snapshots or remove unsupported resume claims |

This is syntactic inventory, not a completeness score: a BUILT method may still have an unsupported branch or be unused by the pipeline. Antisense, codon tools and Pareto methods illustrate component code requiring separate integration decisions.

### 6.4 Task index

The detailed cards below retain stable IDs and concrete code/probe evidence. S/M/L estimates, where present, describe relative scope only. They are not elapsed-time promises.

| ID | Task |
|---|---|
| [PLAT-01](#PLAT-01) | Scope idempotency to the caller and make retries reliable |
| [PLAT-02](#PLAT-02) | Recover abandoned QUEUED/RUNNING jobs, and make state transitions atomic |
| [PLAT-03](#PLAT-03) | Unify input interpretation before declaring uploaded data usable |
| [PLAT-04](#PLAT-04) | Preserve zeros and missing values in every CSV representation |
| [PLAT-05](#PLAT-05) | Make API parameters and dry-run claims truthful |
| [PLAT-06](#PLAT-06) | Enforce immutability in administrative interfaces |
| [PLAT-07](#PLAT-07) | Protect the reviewer login from account collisions and privileged sessions |
| [PLAT-08](#PLAT-08) | Apply scopes to every endpoint and decide real account quotas |
| [PLAT-09](#PLAT-09) | Harden authentication entry points and development data serving |
| [PLAT-10](#PLAT-10) | Validate artifact paths and the complete result contract |
| [PLAT-11](#PLAT-11) | Define storage lifecycle, complete downloads, and import recovery |
| [PLAT-12](#PLAT-12) | Finish and test the client contracts |
| [PLAT-13](#PLAT-13) | Make the development supervisor cross-platform |
| [PLAT-14](#PLAT-14) | Turn production deployment into an executable, verified operation |
| [PLAT-15](#PLAT-15) | Fix API-key renewal, expiry display and collision handling |
| [PLAT-16](#PLAT-16) | Refresh status documentation against live code and evidence |
| [ENG-01](#ENG-01) | P0: Stop labeling component concatenation as implemented Boolean circuitry |
| [ENG-02](#ENG-02) | P0: Preserve DE direction and require real inversion for downregulated inputs |
| [ENG-03](#ENG-03) | P1: Correct FDR handling of truncated or filtered DE tables |
| [ENG-04](#ENG-04) | P1: Replace globally retained per-run folding caches with bounded lifetime |
| [ENG-05](#ENG-05) | P1: Apply accepted constraint settings to the actual tools |
| [ENG-06](#ENG-06) | P1: Implement structural validation with explicit maturity and evidence |
| [ENG-07](#ENG-07) | P1: Correct metric semantics and separate proxies from success probabilities |
| [ENG-08](#ENG-08) | P1: Evaluate and validate the assembled payload context |
| [ENG-09](#ENG-09) | P1: Make mechanism availability and integration truthful |
| [ENG-10](#ENG-10) | P1/P2: Complete construct semantics and distinguish cassette from vector |
| [ENG-11](#ENG-11) | P1: Reject invalid numeric data and incomplete input shapes defensively |
| [ENG-12](#ENG-12) | P2: Persist enough scientific provenance to reproduce every candidate |
| [ENG-13](#ENG-13) | P2: Make ranking, pruning and compute budgeting match configuration |
| [ENG-14](#ENG-14) | P2: Finish or clearly delimit reports, release and diagnostic outputs |
| [PD-01](#PD-01) | Make capabilities describe runnable combinations (P0/P1, M) |
| [PD-02](#PD-02) | Show scientific warnings and provenance at the point of use (P0, M) |
| [PD-03](#PD-03) | Implement result pagination and consistent filtering (P1, M) |
| [PD-04](#PD-04) | Reject malformed pasted sequence instead of silently changing it (P0, S/M) |
| [PD-05](#PD-05) | Render errors and genuine empty states consistently (P1, M) |
| [PD-06](#PD-06) | Replace the stale browser smoke suite and add matrix coverage (P1, M/L) |
| [PD-07](#PD-07) | Preserve client result options across asynchronous completion (P1, M) |
| [PD-08](#PD-08) | Fix client timeout and best-candidate contracts (P1, S/M) |
| [PD-09](#PD-09) | Make R/MATLAB clients executable and conformant (P1, M/L) |
| [PD-10](#PD-10) | Reconcile documentation and make status verifiable (P1, M) |
| [PD-11](#PD-11) | Decide annotation, review, and synthesis product scope (P2, S decision; M implementation) |
| [PD-12](#PD-12) | Complete release ownership and attribution decisions (P2 before release, S/M) |
| [GAP-01](#GAP-01) | Complete the payload catalog and specify multiple-output behavior |
| [GAP-02](#GAP-02) | Implement an explicitly scoped off-target/orthogonality subsystem |
| [GAP-03](#GAP-03) | Establish functional validation and calibrated scientific acceptance |
| [GAP-04](#GAP-04) | Govern reference and public-dataset completeness, meaning and refresh |
| [GAP-05](#GAP-05) | Restore green delivery checks and build a meaningful release QA matrix |

<a id="task-cards"></a>
## 7. Detailed task cards

### Platform, security, runtime and data

<a id="PLAT-01"></a>
### PLAT-01 — Scope idempotency to the caller and make retries reliable

**Priority P0; M; owner backend/API.** Current implementation is unsafe, despite ordinary duplicate-submit tests.

- Evidence: `src/apps/analyses/services.py:89` looks up only `idempotency_key`; line 93 returns the existing object without checking `created_by`. `src/api/routers/runs.py:39` serializes it directly. The model's key is globally unique (`src/apps/analyses/models.py:83`).
- Reproduction: userA has a run keyed `private-key` with notes `private patient research`; userB sends their own direct input and the same key to POST `/api/runs`; response 202 contains A's run UUID, full trigger/configuration and private notes. Probe `test_cross_owner_idempotency_discloses_original_submission`.
- Additional defect: a valid retry at the key's active-run ceiling returns 429 because the quota check precedes idempotency lookup (`src/api/routers/runs.py:59`, `src/api/routers/design.py:204`). Inline CSV retry creates a fresh dataset before recognizing the old run.
- Work: namespace keys by owner, migrate the uniqueness rule, resolve retries before quota/storage side effects, compare normalized request fingerprints and reject changed payloads explicitly, handle concurrent inserts deterministically.
- Acceptance: two users can reuse a key without seeing one another; same user/same payload returns same run at quota; different payload produces explicit conflict; parallel identical requests enqueue exactly once; inline retry creates no orphan dataset; ownership tests cover `/runs` and `/design?wait=`.
- Decision: define key retention/expiry and payload-conflict HTTP semantics. No scientific decision blocks the privacy fix.

<a id="PLAT-02"></a>
### PLAT-02 — Recover abandoned QUEUED/RUNNING jobs, and make state transitions atomic

**Priority P1; L; owner runtime/backend.** The recent supervisor repairs a missing worker process, not its orphaned run state.

- Evidence: `src/apps/analyses/services.py:118` publishes in on_commit without recovery. If enqueue raises, a committed QUEUED row survives with no task. `execute_run` at line 170 attempts RUNNING→RUNNING on redelivery and exits on InvalidTransition. `_transition` at line 323 validates an in-memory object's status and saves without compare-and-swap/locking. Worker timeout is3600s with retry 3660s (`src/config/settings/base.py:140`).
- Reproductions: enqueue exception leaves QUEUED; simulated fatal SystemExit after start leaves RUNNING; redelivery leaves it RUNNING again. A stale QUEUED object can write RUNNING after another request cancelled the same row, leaving RUNNING plus a finished timestamp. Probes `test_queue_publish_failure_leaves_unpublished_queued_run`, `test_worker_fatal_exit_leaves_running_then_redelivery_is_noop`, `test_stale_start_can_overwrite_terminal_cancellation`.
- Work: durable publication/reconciliation (e.g. transactional outbox or explicit enqueue state), atomic claim/transition, execution lease/heartbeat, explicit interrupted/failed outcome or safe retry policy, reconcile on supervisor startup and periodically, distinguish queue delay from execution stall in API/UI. Keep retries of expensive science deliberate.
- Acceptance: terminate an isolated worker mid-stage and during import; run becomes terminal or safely resumable within a defined deadline; cancellation cannot be overwritten by a stale start; duplicate delivery does not compute twice; publication failure has actionable state and recoverable task; timeout and OOM exit both reconcile; no test claims recovery solely because a replacement worker PID exists.
- Dependencies: PLAT-01 key/claim semantics; artifact retention in PLAT-11. Decision: when to resume, fail, or require an explicit user retry.

<a id="PLAT-03"></a>
### PLAT-03 — Unify input interpretation before declaring uploaded data usable

**Priority P1; M; owner platform/engine edge.** Several accepted inputs are interpreted differently downstream.

- Most serious: platform validation and preview use `workbook.worksheets[0]` (`src/apps/datasets/services.py:319`); engine uses `workbook.active` (`src/engine/inputs.py:134`). Probe `test_xlsx_active_sheet_differs_between_platform_and_engine` previews b0005 but executes b3908 from the second active worksheet. The whole-file checksum passes, so it cannot catch this wrong-sheet computation.
- `validate_expression_file` permits gene_id+baseMean with no fold-change (`services.py:195`); `parse_dge_table` then drops every row because log2fc is absent (`src/engine/inputs.py:177`). Probe confirms VALID with zero engine rows.
- Header names are stripped for validation's mapping but DictReader's original keys are not (`services.py:297`); ` gene_id , log2fc ` lets `not-number` evade numeric validation. Probe confirms no errors.
- `inf` is accepted as a numeric value and the preview emits literal `Infinity`, which is not valid JSON (`services.py:219`, `:386`). Probe returns 200 with that token; browser JSON decoding fails.
- Preview chooses format from `dataset.name`, a free-form display label, rather than stored file filename (`services.py:360`). An XLSX named `my study.csv` uploads as VALID but preview fails.
- CSV/TSV/TXT delimiter rules are not identical across platform and engine; duplicate/missing identifiers, overlong rows, malformed sheet XML, duplicate normalized headers and nonfinite values need explicit contracts. Extra CSV cells currently upload VALID (an observation, not inherently a bug until policy is chosen).
- Work: put a reusable, framework-independent parsing contract behind the allowed engine client/contract boundary; use the same selected sheet and delimiter for validation, preview, and execution; require sufficient DE evidence or clearly implement a separate expression input route; reject nonfinite numerics; keep display names independent of format.
- Acceptance: multi-sheet active/first mismatch fixture produces identical preview and execution; positive and negative CSV/TSV/TXT/XLSX fixtures share normalized records; whitespace aliases cannot bypass checking; all preview bodies parse with strict JSON; missing log2fc gets an actionable422/INVALID status unless a specified derivation is supported; empty/huge/malformed workbooks fail cleanly; provenance records the selected sheet/format.
- Decision: first sheet, explicitly selected sheet, or reject multi-sheet ambiguity. Decide whether counts/expression-only is an actual supported modality rather than silently accepting it.

<a id="PLAT-04"></a>
### PLAT-04 — Preserve zeros and missing values in every CSV representation

**Priority P1; S; owner results/export.** The scientific table is currently lossy.

- Evidence: `src/apps/results/services.py:245` and247 render raw and normalized values with `value or ""`. Actual 0.0 becomes blank. Probe `test_zero_metrics_export_as_missing` stores raw 0 and normalized 0, then observes both blank CSV cells; overall_score 0 is correctly retained by a separate implementation.
- Work: distinguish `None` from zero in the shared CSV builder, with the same handling in any client table transformation. Review ordering of rejected/null-rank rows.
- Acceptance: values None,0,negative,positive round-trip distinctly; endpoint export and stored `summary.csv` are byte-consistent; raw 0 leakage and normalized 0 poor score remain0; no implementation uses truthiness to decide missingness.

<a id="PLAT-05"></a>
### PLAT-05 — Make API parameters and dry-run claims truthful

**Priority P1 for budgets/validation; M–L; owner API with engine coordination.** A request field being accepted is not evidence it affects the result.

- Evidence: `src/api/routers/design.py:182` dry-run returns before sequence/reference resolution; line 200 hardcodes budget_ok=True. `BUDGET_KEYS` exists (`src/api/params.py:31`) but no execution path reads/enforces max_designs/max_runtime_seconds/on_exceed. `include_metrics` exists only in the schema (`src/api/schemas.py:455`) and does not shape results.
- Reproduction: dry-run `trigger_sequence="not RNA"`, budget max_designs=0/max_runtime_seconds=0 returns 200 and budget_ok=true. A scoring weight string returns 500 from sum at `src/api/params.py:89`. Other free-form nested block types can throw AttributeError/TypeError instead of422.
- Estimate uses stale fixed arithmetic (`src/api/routers/design.py:110`) and describes missing gene selection even though it now exists. `/design` cannot carry custom/catalog backbone configuration although `/runs` can. The two organism fields can disagree, and top-level schema strings do not enforce host enum values before accepting work.
- Work: typed engine-exposed validation schema/capabilities; validate shape, type, range, finite values and host/family compatibility synchronously; share normalization between both submissions and dry-run; implement budgets or reject unsupported budget fields explicitly; echo effective resolved defaults; implement output options or reject them.
- Acceptance: every documented field has a behavior test; invalid sequence/gene/organism/scoring/constraint returns422 in both dry and real submit; no side effects on dry-run; zero/tiny budgets deterministically halt according to documented policy; estimates have measured calibration and clear bounds; backbone choices work in both APIs; conflicting hosts rejected; include_metrics=false actually omits metrics.
- Decisions: budget exceed policy (abort/partial result), supported constraints and bounds, supported organism/family/payload combinations. Coordinate with engine owner rather than duplicating scientific validation in Django.

<a id="PLAT-06"></a>
### PLAT-06 — Enforce immutability in administrative interfaces

**Priority P1; S–M; owner Django/admin.** Admin pages currently contradict the platform's reproducibility contract.

- Evidence: `AnalysisRunAdmin.readonly_fields` (`src/apps/analyses/admin.py:36`) omits new input_mode/trigger_sequence fields. DatasetAdmin (`src/apps/datasets/admin.py:15`) leaves file, validation_status and schema_version editable. CandidateMetricAdmin (`src/apps/results/admin.py:116`) has no readonly restrictions; ArtifactAdmin at line 94 allows file/run/candidate edits.
- Probe `test_admin_forms_allow_mutating_frozen_scientific_inputs` confirms form fields: run=[input_mode,trigger_sequence], dataset includes[file,validation_status], metric includes[raw_value,normalized_value,weight,direction].
- Work: lock submitted source/configuration and imported engine records; allow decisions/annotations as the intended mutable research layer; provide explicit audited repair tools only where justified.
- Acceptance: admin POST cannot change completed/queued run input, underlying dataset bytes, raw metrics, or artifact provenance; legitimate account approval/key revoke/annotations remain usable; any repair creates traceable new revision rather than rewriting history.

<a id="PLAT-07"></a>
### PLAT-07 — Protect the reviewer login from account collisions and privileged sessions

**Priority P0 when reviewer mode is enabled; S; owner auth.** Reviewer mode is enabled by default in development and optionally available in production.

- Evidence: `get_or_create_reviewer_account` (`src/apps/accounts/services.py:106`) uses defaults only on creation and blindly returns an existing username `reviewer`. Login endpoint directly establishes its session (`src/api/routers/auth.py:125`).
- Reproduction: create an existing staff/superuser named reviewer; anonymous reviewer-login returns 200 with is_staff=true. Probe `test_existing_privileged_reviewer_account_is_returned`.
- Work: use a dedicated reserved identity and enforce nonprivileged/active/passwordless invariants; fail safely on a collision without silently demoting a legitimate administrator. Define whether reviewers should share history or receive isolated disposable workspaces.
- Acceptance: existing privileged, inactive, ordinary-password and pending reviewer-name accounts cannot be entered by anonymous users; disabled feature remains404; normal dedicated demo account works; regular registration cannot squat the reserved name.

<a id="PLAT-08"></a>
### PLAT-08 — Apply scopes to every endpoint and decide real account quotas

**Priority P2; M; owner API/security.** Scope support exists, but the endpoint matrix is incomplete.

- Evidence: require_scope only appears on submission/cancel/annotation mutations. Dataset upload/example/materialize omit it (`src/api/routers/datasets.py:31`, `src/api/routers/expression.py:63`). Read endpoints never require READ, while issuance allows scopes=[].
- Reproduction: empty-scope key reads owner run with 200; read-only key uploads dataset with 201 (`test_empty_scope_key_can_read_and_read_key_can_upload`).
- Work: publish and enforce endpoint×credential×scope policy; decide whether upload is DESIGN or a separate write scope; reject meaningless empty scopes or enforce them consistently; apply concurrency ceiling atomically with run creation; make account quotas independent of whichever key happens to be used. Current shared-cache throttle remains a best-effort non-atomic history update, not a strict concurrency control.
- Acceptance: exhaustive key scope tests for all 43 API operations; read-only key cannot mutate persistent resources; empty-scope keys cannot read protected resources; public endpoints remain anonymous; mixed session/key precedence preserved; concurrent submissions cannot exceed chosen active-run quota; ordinary retries do not consume quota again.

<a id="PLAT-09"></a>
### PLAT-09 — Harden authentication entry points and development data serving

**Priority P1 before exposing an instance; M; owner auth/web.** Session write CSRF protection does not cover the unauthenticated login endpoint automatically.

- Evidence: login uses auth=None (`src/api/routers/auth.py:102`); probe with `Client(enforce_csrf_checks=True)` and foreign Origin receives 200 and establishes a session. This confirms server-side login CSRF checks are absent; it does not claim a full browser exploitation chain was demonstrated.
- Authentication/registration endpoints have no effective abuse limit: global ApiKeyRateThrottle returnsTrue without request.api_key (`src/api/security.py:111`). There is no password-reset/self-service recovery flow.
- `src/config/urls.py:22` serves MEDIA_ROOT directly when DEBUG. Probe anonymous `/media/<known dataset path>` returns 200. It is development-only, but development/reviewer instances are often shared, and it contradicts the documented “artifacts are always authorized” guarantee.
- Work: explicit CSRF/origin protection for login/session-creating actions; login/register throttling with shared counters; reserve demo accounts; validate username/email values; serve sensitive media only through ownership checks in every shared configuration; provide a documented manual or automated account-recovery path.
- Acceptance: foreign-origin/no-token login rejected while valid SPA login works; API-key writes remain independently authenticated; login flood limited without revealing account existence; anonymous/non-owner raw media requests denied under DEBUG as well as production; real registration and approval are regression-tested with CSRF enforcement enabled.

<a id="PLAT-10"></a>
### PLAT-10 — Validate artifact paths and the complete result contract

**Priority P2 now, P1 before remote engine execution; M; owner result import.** Current engine is trusted/local, so path escape is a boundary weakness rather than a proven unauthenticated arbitrary-file-read exploit.

- Evidence: importer joins output_dir/ref.path without resolved-path containment (`src/apps/results/services.py:127`). Destination sanitization in model upload_to does not protect the *source read*. `_verify_manifest` at line 105 checks only a nonempty mismatched input checksum; missing checksum, wrong schema_version and mismatched params are accepted.
- Reproduction: manifest with path `../outside.txt`, empty checksum, wrong schema and wrong params successfully imports bytes from outside output_dir. Probe `test_artifact_manifest_traverses_outside_output_directory`.
- Work: reject absolute/traversal/symlink escapes before reading; validate schema, status, expected input/configuration identity and manifest uniqueness; require/verify digests; constrain finite metrics/ranges and referenced candidate identities; include enough provenance in downloaded manifest to independently reproduce input and references.
- Acceptance: traversal/absolute/symlink fixtures rejected atomically; missing/wrong digest, incompatible schema and changed configuration rejected; valid current LocalEngine manifests still import; failed import leaves no reachable partial results; provenance includes dataset checksum/ID, reference release/digest, effective scoring version and configuration identity.
- Existing positive coverage: result import tests already prove known checksum mismatch, missing artifact, candidate ref consistency, transactional rollback and stored checksums. Extend rather than replace those tests.

<a id="PLAT-11"></a>
### PLAT-11 — Define storage lifecycle, complete downloads, and import recovery

**Priority P2; M–L; owner storage/runtime.** Uploaded/result bytes currently grow indefinitely.

- Evidence: `delete_dataset` (`src/apps/datasets/services.py:395`) deletes the database row but not the FileField bytes. Probe confirms the file still exists. SQL rollback can leave artifact bytes; importer docstring acknowledges it. TemporaryDirectory in `_execute` (`src/apps/analyses/services.py:212`) deletes engine output even when result import fails, despite comment suggesting re-import without recomputation.
- ZIP download silently skips missing stored files (`src/api/routers/results.py:159`); probe gets a valid empty ZIP and200 when the selected artifact is gone. ZIP and CSV are assembled wholly in memory; no retention/cleanup management command exists.
- Work: explicit retention/deletion policy; transaction-safe file removal and orphan cleanup; durable result staging until import acknowledged; missing-artifact report/error instead of silent omission; bounded/streamed archives; optional integrity verification on read or scheduled storage checks.
- Acceptance: deleting unused dataset removes its bytes; failed transactions leave no permanent orphan; used-input retention respected; partial/missing archive is explicitly labelled or rejected; import transient failure can be retried without re-running science; restore reproduces artifact digests and owner access; large-archive memory use is measured.
- Decisions: retention period, user deletion rights for completed/failed runs, sensitive-data expectations, whether re-import is automatic/manual.

<a id="PLAT-12"></a>
### PLAT-12 — Finish and test the client contracts

**Priority P1 for failing CI and broken advertised SDK contracts; M; owner SDKs/API.** Main pytest testpaths exclude clients; their evidence must be reported separately.

- **Confirmed CI failure:** authorized Python client conformance produced1failure/3passes. The shared `clients/fixtures/design_request.json` supplies a 42nt sequence that currently yields30candidate trigger windows but **zero gate candidates**: all34generated designs are rejected (30extra-AUG failures,4in-frame-stop failures). The engine correctly returns succeeded with warnings and an empty design table; fixture setup imports it and marks the run COMPLETED, then `test_conformance` fails its at-least-one-candidate assertion. Replace the conformance input with a validated productive fixture; keep the sequence validator intact and preserve a separate empty-result test. Assert the fixture's engine outcome before exercising its HTTP contract. This is not evidence that the client transport failed.

- Python: `Client._request` always uses timeout 30s by default (`clients/python/cernal/client.py:106`), even design(wait=60/300). Probe records wait 60 versus timeout 30. `results(format="csv")` always calls response.json and raises; probe confirms. `Job.wait` returns early whenever candidates key exists (`clients/python/cernal/job.py:47`), so dry-run schema's empty candidates makes wait succeed with no job ID. Async wait calls results(job_id) without preserving submit top_n/include_rejected/options (`:72`).
- R/MATLAB: have analogous30s request default versus up to300s server wait and candidates-field shortcut. R `req_body_json` auto_unbox makes singleton vectors versus arrays a conformance risk; verify explicitly for gate_families, trigger_lengths, outputs, artifacts, hard_filters. No R/MATLAB runtime results claimed here.
- Work: clear separate estimate/submission/result objects or strict checks; server-wait-adjusted timeout; JSON/CSV/bytes handling; preserve result shaping; typed error/Retry-After handling; deterministic mocks plus live tests for each shipped client.
- Acceptance: dry-run wait raises documented “not submitted”; wait 60 succeeds with 60 s server timing; async and inline paths return same selected results; CSV accessible as CSV; singleton arrays survive all languages; R tests run in CI; MATLAB runs in supported-runtime CI or a recorded reproducible pre-release check; each includes a fresh queued job as well as the pre-completed idempotency fixture.
- Existing Python conformance uses a pre-completed seeded run (`clients/python/tests/test_conformance.py:1`), so even a green result does not exercise queue startup/progress/cancellation or long-wait behavior.

<a id="PLAT-13"></a>
### PLAT-13 — Make the development supervisor cross-platform

**Priority P1 for promised native Windows support; M; owner developer tooling.** Source-reviewed, not executed on Windows in this audit.

- Evidence: unconditional `import fcntl` (`src/apps/web/management/commands/devserver.py:3`), `os.killpg` and POSIX process groups at22/29. manage.py transparently redirects runserver to devserver. Native Windows lacks these primitives, while repository instructions explicitly support it.
- Work: choose a supported cross-platform lock/process lifecycle or conditional platform adapters; preserve one-supervisor rule and shutdown semantics; explicitly document supported environments if native Windows is intentionally withdrawn.
- Acceptance: Windows and Linux CI boot the documented runserver entry point, execute a queued run, restart a crashed worker, prevent duplicate supervisor, and shut down all child processes; no Windows-only import failure.

<a id="PLAT-14"></a>
### PLAT-14 — Turn production deployment into an executable, verified operation

**Priority P1 before production; L; owner operations.** This remains a planned phase, not a delivered feature.

- Evidence: `deploy/` contains only `.gitkeep`; `docs/deployment.md:1` says planning/not implemented. prod settings at `src/config/settings/prod.py` configure security but no service/proxy/container/backup exists in deploy. Dependency separation from deployment design is not implemented; pyproject installs platform and engine together.
- Work: first choose measured local-VM versus cloud execution requirements; deliver reproducible web and worker service configuration, database/media backup and restore, writable directories, static build/migrations, readiness/liveness with worker visibility, restart/reconcile behavior, logs/alerts and resource limits. Do not add cloud infrastructure merely to solve defects in local state handling.
- Acceptance: deploy a clean checkout with documented commands; HTTPS/session/CSRF/media isolation verified; restart host during a run; restore database plus media and verify checksums/ownership; monitor failed/queued/stalled runs; demonstrate worker timeout and disk-full handling; run manage.py check --deploy with documented justified exceptions.
- CI detail: GitHub frontend has a build:fast bootstrap for ignored generated route tree; `.gitlab-ci.yml:71` runs npm check before generating it. Reproduce from a clean checkout and synchronize both workflows; GitLab also omits GitHub's locked dependency install flag. Neither current pipeline proves production deployment nor R/MATLAB compatibility.
- Open decisions: hosting target, resources/search bounds, retention, backup RPO/RTO, reviewer mode exposure, support ownership and incident response.

<a id="PLAT-15"></a>
### PLAT-15 — Fix API-key renewal, expiry display and collision handling

**Priority P3; S; owner accounts.** Core issue/revoke/authenticate works, but edge behavior is misleading.

- Evidence: regenerate preserves expires_at (`src/apps/accounts/services.py:211`). Probe regenerates an expired key and obtains a secret that still fails authentication. ApiKeyAdmin labels expiration by expires_at<created_at instead of now (`src/apps/accounts/admin.py:94`). Creation accepts negative expiry days; prefix uniqueness uses only four random characters after cern_live_ with no collision retry.
- Work: define renew versus regenerate semantics, validate expiry/quota ranges, use correct current-time status, handle prefix collision safely.
- Acceptance: expired-key reset either visibly renews according to policy or clearly refuses; never displays inactive key as active; zero/negative/extreme values rejected; forced prefix collision retries without500 or secret disclosure.

<a id="PLAT-16"></a>
### PLAT-16 — Refresh status documentation against live code and evidence

**Priority P2; M; owner documentation with domain reviewers.** Current architecture and roadmap contain mutually incompatible historical claims.

- Evidence: architecture/deployment still describe MockEngine as default and LocalEngine as unimplemented; current `src/config/settings/base.py:155` selects LocalEngine. Roadmap says Step 3 complete/35 endpoints and1116tests, while current router inventory is43 and behavior audit finds gaps. Several sections still say Human/other-host references blocked, CircuitDesigner stub, or suggest manual worker startup; other sections report the newer implementations.
- Work: mark historical decisions/history as historical, separate implemented from validated and production-ready, reconcile open/closed questions with source and quantitative test evidence, update generated API surface, document supported input/host/family/payload/format combinations and unsupported field behavior.
- Acceptance: each advertised option maps to current code and an acceptance test or explicit limitation; no user guide promises all workflows from a passing smoke example; QA date, commit/dirty-tree basis, tested versions and unresolved issues are visible; preserve a durable place for this audit's follow-up tasks (existing ROADMAP is the repository's intended planning source).

### Scientific engine and construct correctness

<a id="ENG-01"></a>
### ENG-01 — P0: Stop labeling component concatenation as implemented Boolean circuitry

**Problem.** `_multi_gate_candidates` enumerates a logical expression, aggregates component metrics, and calls `PlasmidBuilder`. `build` reads `circuit.designs` and ignores `circuit.expression`. It concatenates promoter+switch pairs followed by a single payload and terminator. Changing AND to OR or NOT produces the same sequence. The upstream promoter can produce a longer transcript through downstream regulatory units, while the downstream promoter starts separately; no implemented mechanism makes payload expression depend on the conjunction of the displayed inputs. This is a source-code inference reinforced by the exact-expression-invariance probe, not a wet-lab assertion of one particular alternative truth table.

**Evidence.** `pipeline.py:1039–1115`; `circuits.py:112–145`; `plasmids.py:438–457`; `engine-probes.json.physical_logic`.

**Scope.** Define the distinction between a logical candidate and a physically compiled candidate. Until a chemistry-specific compiler exists, do not present multi-gene concatenations as accepted realizations of that logic. Decide a physical topology with scientific review before implementing it. Preserve component-level exploratory outputs with explicit maturity where useful.

**Acceptance criteria.** Every exported/accepted compiled circuit has an explicit realizability contract; unsupported expressions return an explicit unsupported result; truth-table tests cover every binary input assignment; changing an operator cannot silently retain the same realization without a documented equivalence; per-component transcription units, coding regions and payload connections are explicit; scores distinguish component proxies from circuit response; no experiment-performance claim without experiment evidence.

**Dependencies.** Scientific topology decision; ENG-02; future AND/NOT mechanism integration. Do not simply flip an availability flag.

<a id="ENG-02"></a>
### ENG-02 — P0: Preserve DE direction and require real inversion for downregulated inputs

**Problem.** All `build_trigger_sets` outputs put every trigger in `activators`, regardless of signed log2FC. Single-input candidate output hardcodes `direction: up` and `state: ON`. Meanwhile stage 4 infers `NOT` from a negative fold-change and uses the same activating switch. Scoring applies `abs(log2FC)`, so the inverse biological direction can receive a strong separation score.

**Evidence.** `switches.py:162–189`; `pipeline.py:1124–1147,1336–1343`; `gates/base.py:69–89`. Real probe: two DOWN genes → 31 accepted candidates, one `(NOT b0033 AND NOT b3908)` candidate made from toeholds, with UP labels on its corresponding singles.

**Scope.** Make input-direction requirements travel through trigger sets, family compatibility, construction and result serialization. Decide how unsupported downregulated inputs are handled when no production NOT chemistry is available; retaining them as activation designs for the control condition requires explicit labeling and objective semantics.

**Acceptance criteria.** UP/DOWN/mixed tests establish target-state direction; DOWN-only runs cannot claim target-specific activation using an activating toehold; graph labels match the input and physical gate; repression tests use a true repressor implementation; no hardcoded UP graph for every candidate. Verify positive/negative changes in the same gene produce the appropriate semantic change.

<a id="ENG-03"></a>
### ENG-03 — P1: Correct FDR handling of truncated or filtered DE tables

**Problem.** A raw p-value present for ≥95% of retained rows is treated as sufficient to recompute BH. This does not establish that all tested hypotheses are present. The public catalog intentionally keeps the 3,000 highest absolute fold changes. Arthritis therefore obtains a claimed FDR from a selected subset. The policy is also unsafe for arbitrary user uploads already filtered by significance/effect size.

**Evidence.** `genes.py:41–49,561–591`; catalog writer `sync_expression_catalog.py:294–297`. Probe: arthritis 3,000 rows, 2,996 raw p-values, no adjusted p-values, `mode='bh'` with an FDR warning.

**Scope.** Carry tested-hypothesis completeness/truncation provenance across catalog, upload, parser and selection. Prefer source adjusted p-values computed before truncation. Preserve full statistical tables independently of preview row caps, or explicitly mark subset-only raw-p analysis. Do not invent a corrected p-value where the required hypothesis universe is unavailable.

**Acceptance criteria.** A known truncated raw-p table never receives an FDR-controlled claim; a complete table matches a trusted BH reference; duplicate genes, missing p-values, mixed adjusted-p coverage and prefiltered uploads have documented behavior; manifests distinguish complete input from UI preview; actual arthritis warning/output is corrected.

<a id="ENG-04"></a>
### ENG-04 — P1: Replace globally retained per-run folding caches with bounded lifetime

**Problem.** `@functools.cache` decorating instance methods includes `self` in a class-level function cache. Completed run instances are retained by that cache. `FoldEngine(cache_size=...)` records the value but never enforces it. Cached base-pair matrices grow quadratically with sequence length. `FoldProfiler._matrix` has the same retention pattern. Multiple jobs in a long-lived worker accumulate prior runs' objects and data.

**Evidence.** `tools/folding.py:78–80,106,174,222,505–519`; `stages/folding.py:105–120`; probe shows weak reference remains live after deletion/GC and MFE cache `maxsize=None` despite requested size 1.

**Scope.** Use per-instance bounded caching or an explicitly bounded shared cache with correct model identity and lifecycle. Include every scientific model parameter in any shared key. Release per-run large matrices; avoid cache retention proportional to the lifetime of the worker.

**Acceptance criteria.** Weak-reference/lifecycle test confirms completed tools can be collected; cache limit test is enforced; repeated jobs in one process reach a bounded RSS plateau; results are unchanged for same model/inputs; differing temperatures cannot share results; matrix-return mutation isolation remains intact.

<a id="ENG-05"></a>
### ENG-05 — P1: Apply accepted constraint settings to the actual tools

**Problem.** `Constraints.forbidden_motifs` is accepted and recorded but never passed to `MotifScreener.extra_motifs` in `build_tools`. Thus every stage uses an empty extra motif set.

**Evidence.** `pipeline.py:220–221,614–615`; `motifs.py:58–74`; probe confirms containing sequence has zero extra-motif violations.

**Scope.** Wire normalized motif settings into the single shared screener and validate parameter semantics at the engine boundary; review other accepted settings for “stored but ignored” behavior.

**Acceptance criteria.** A user-supplied motif changes eligibility in direct, gene and DE modes and in final construct checks; DNA/RNA case/orientation policy is documented; repeat-run snapshots reflect effective settings; invalid/empty motifs return understandable input errors. Tests must assert outcome differences, not only that a config field exists.

<a id="ENG-06"></a>
### ENG-06 — P1: Implement structural validation with explicit maturity and evidence

**Problem.** `SwitchValidator` never inspects `dot_bracket`, folds the switch, or checks whether intended hairpin/initiation geometry is present. The source comment says ensemble defect is a stub, but it is now implemented. A target string that is not even dot-bracket syntax passes unchanged.

**Evidence.** `switches.py:244–295`; `tools/folding.py:357–394`; probe's bogus structure passes.

**Scope.** Add basic target structure integrity checks first; define and document chemistry-specific structural/translation rules; integrate available ensemble-defect measurement with calibrated or deliberately provisional thresholds. Do not choose biological cutoffs merely to preserve current acceptance counts.

**Acceptance criteria.** Malformed/unbalanced/wrong-length target structures are rejected; known correct/incorrect hairpins are distinguishable; units are normalized once; defects and rule versions are persisted; missing calculations remain explicit; integration tests exercise real generated designs through validation. Scientific reviewers approve or explicitly mark provisional thresholds.

<a id="ENG-07"></a>
### ENG-07 — P1: Correct metric semantics and separate proxies from success probabilities

**Problem.** `predicted_success_rate` is a logistic transformation of MFE binding ΔG with hardcoded midpoint −15 kcal/mol and slope 2, yet the profile describes in-vivo behavior confidence. `dynamic_range` is a ratio of marginal accessibility, not observed expression fold-change. It can be below one for accepted activating gates. Human rank 1 in the probe has 0.15079 dynamic range and 0.96610 success rate. In trailing-Kozak designs, accessibility is measured across the trigger-binding arm: successful pairing to the trigger can itself make that region paired, so the proxy needs a mechanism-specific review before interpreting “more unpaired ON” as activation.

**Evidence.** `toehold.py:776–827`; `binding.py:164–207`; `profiles.py:195–208`; `eukaryotic-metric-probe.json`.

**Additional inconsistencies.** `trigger_accessibility` is the minimum marginal unpaired probability (`triggers.py:87–89`), while its profile description calls it a fraction of the region free of structure (`profiles.py:146–152`). `gc_content` is measured on the switch, while its profile description says assembled construct (`toehold.py:822`, `profiles.py:186–193`). GC normalization monotonically rewards 70% over 50% while its description says extremes hurt synthesis. Orthogonality is still SKIP even when multiple components are present. Multi-gate metric aggregation takes the worst member metric and adds complexity, so it cannot reward improved combined state discrimination; no such discrimination is actually measured. Global MFE “more negative is always better” also does not express the antisense family’s ON-state preference for low self-structure; integrating that family requires a comparable scientific metric, not merely reusing a name.

**Scope.** Produce a versioned metric specification with biological event, mathematical definition, molecule/context, unit, missing behavior, calibration status and applicable chemistry. Rename or relabel uncalibrated quantities honestly. Review acceptance rules for response direction. Preserve old score interpretability after revisions.

**Acceptance criteria.** UI/API/report definitions match exact calculations; probability/calibration claims require independent validation evidence; ON/OFF tests demonstrate the intended direction for each mechanism; zero/near-zero denominators and missing/nonfinite results are explicit; rank sensitivity to model/weights is reported; profile/family/engine versions change with semantics.

<a id="ENG-08"></a>
### ENG-08 — P1: Evaluate and validate the assembled payload context

**Problem.** Pipeline evaluates a gate before selecting an output. Family constructors receive no payload despite the toehold class having an optional payload-aware path. Plasmid construction attaches the entire CDS later. Custom-payload or output changes therefore do not affect the scored gate’s folding model. `self.codons` is injected but never used for assembly. The full switch→payload junction may add amino acids/duplicate starts and alter folding; only a simple ORF check currently follows assembly. For multi-switch constructs `_frame_violations` checks each switch concatenated directly to payload, although upstream switches are not adjacent to that payload in the actual assembly.

**Evidence.** `pipeline.py:265,447–456`; `toehold.py:208–246,478–503,559–578`; `plasmids.py:438–457,501–541`.

**Scope.** Separate the regulatory sequence used for thermodynamic evaluation from the exact physical ORF; select/resolve payload before payload-dependent evaluation; define junction/fusion rules; evaluate the actual relevant transcript context; make codon optimization an explicit reproducible optional stage instead of assuming tool construction means optimization happened.

**Acceptance criteria.** Two materially different payload contexts are either rescored or clearly marked as unevaluated; no duplicate payload head in assembly; actual coding feature boundaries and translated product are checked; a junction that introduces an early stop is rejected as a nonfunctional construct, not merely offered with a warning; custom/GFP and per-host paths preserve expected protein sequence when optimization is enabled; mutation provenance is retained.

<a id="ENG-09"></a>
### ENG-09 — P1: Make mechanism availability and integration truthful

**Problem.** Registry advertises antisense and all AND families as `available=True`; production pipeline skips them. CRISPR is correctly unavailable. Tests currently consider an explicit clean failure acceptable for these matrix entries, so “matrix passed” does not mean these families work.

**Evidence.** `registry.py:68–115`; `toehold.py:112,839–864,1945–1979`; `antisense.py:107–115`; `pipeline.py:153–170,254–265`; `tests/engine/test_pipeline_matrix.py` hardcodes supported single-input families only.

**Scope.** Introduce a single capability source that distinguishes component/research implementation from production readiness. Integrate each chemistry separately with its constructor, payload semantics, repressor sets, validation, scoring, physical assembly and release policy. Antisense already has a payload argument and substantive code; the current “no payload library” skip reason is incomplete because GFP/custom resolution exists elsewhere.

**Acceptance criteria.** Every advertised selectable host/family combination can run through the current production path; unsupported combinations are identified before queueing; supported-mechanism tests require actual meaningful candidates rather than clean failure; AND integration covers all four input states for two-input AND; NOT integration covers signed DE and direct modes; CRISPR activation/repression choice is explicit before implementation.

<a id="ENG-10"></a>
### ENG-10 — P1/P2: Complete construct semantics and distinguish cassette from vector

**Problem.** No-backbone output is described as a cassette but `to_genbank` always declares it circular. Custom GenBank ingestion extracts an opaque whole sequence and discards origin/marker/insertion-site features. Concatenating a full vector at its file origin is not a documented physical insertion plan. Standard-site screening of an entire BioBrick backbone also needs a distinction between expected assembly sites and prohibited internal insert sites. Invalid frame and standard violations are warnings; `is_rejected` depends only on score hard filters.

**Evidence.** `plasmids.py:438–465,546–585,600–637`; `pipeline.py:1369–1374`; physical probe gives circular no-backbone GenBank and zero violations on expression-invariant multi-gate assembly.

**Scope.** Model topology, cassette vs vector, annotated backbone features, explicit insertion boundaries and assembly method. Review host/backbone compatibility and marker expectations. Treat nonfunctional coding constructs differently from intentionally tolerated assembly constraints. This task should coordinate with the root audit's broader payload/backbone matrix.

**Acceptance criteria.** Cassette exports have truthful topology and artifact labels; custom annotations survive with adjusted coordinates; insertion endpoints and junctions are reproducible; host compatibility is explicit; complete-sequence validation examines actual feature context; sequences and GenBank/SBOL semantics agree. No claim of orderability without an actual assembly definition.

<a id="ENG-11"></a>
### ENG-11 — P1: Reject invalid numeric data and incomplete input shapes defensively

**Problem.** `_as_float` permits `inf` and several NaN spellings; probability bounds and nonnegative means are not checked by the standalone parser. `failed_filter` lets NaN comparisons pass and normalization retains NaN. The platform may reject some of these cases, but `LocalEngine` is a documented independently callable engine and the pipeline says it revalidates inputs. Malformed constraint values are only partly checked and may raise raw Python exceptions.

**Evidence.** `inputs.py:85–101,181–200`; `normalize.py:15–29,82–94`; `pipeline.py:585–627`; preserved numeric probe.

**Scope.** Establish strict data invariants at parsing/constraint boundaries, with explicit missing-value handling and row error policy. Validate p-values within [0,1], finite effect sizes, and semantically valid abundance/ranges. Do not silently treat malformed numeric values as experimentally missing.

**Acceptance criteria.** Nonfinite strings across CSV/TSV/TXT/XLSX and direct engine/API routes receive consistent errors; missing-value spellings stay supported; negative/over-one probabilities cannot influence selection; no NaN/Infinity in result JSON or ranking; booleans and invalid numeric constraint types fail before expensive work.

<a id="ENG-12"></a>
### ENG-12 — P2: Persist enough scientific provenance to reproduce every candidate

**Problem.** `GateDesign.architecture` contains Kozak layout, leader/loop/spacer lengths, payload-head status and footprint-match flag, but `_candidate_result` retains only toehold length and intended structure. It does not persist the family version. `_trigger_feature` stores symbol as `feature_id`, omitting stable gene/transcript ID and selected reference accession. A DE table without symbols therefore produces poorly identified candidates. Multi-component output carries sequences and IDs but loses each component's full architecture and metrics. `CandidateStore.snapshot` and reload are stubs and never called. Tool `.versions()` methods are mostly not recorded on runs; RNAplfold provenance is a useful exception.

**Evidence.** `pipeline.py:1219–1246,1259–1313,1349–1369`; `store.py:48–104`; `toehold.py:450–475,527–538,617–628`; `transcriptome.py:110–122`.

**Scope.** Introduce a versioned provenance manifest for selected and discarded stages, resolved inputs and reference digests, family architecture/versions, model parameters, per-component metrics, actual payload identity and assembly decisions. Preserve scientific audit data within existing release controls.

**Acceptance criteria.** Any candidate can be reconstructed from saved input/config/tool/reference versions; stable gene IDs remain available when symbols are missing or ambiguous; a user can tell intended from predicted structure; selected Human isoform and sequence digest are recorded on DE candidates; reruns produce comparable IDs/content digests; stage snapshots do not become a second execution bus.

<a id="ENG-13"></a>
### ENG-13 — P2: Make ranking, pruning and compute budgeting match configuration

**Problem.** Profile tie-breakers are declared and customizable, but `rank_candidates` only sees `(ref, score)` and sorts equal scores by ID. Gene redundancy ranking does an O(n²) pass even when no counts exist and repeatedly calculates the same score. Stage 2 folds every motif-surviving window before selecting 50; many shortlisted windows can later fail basic AUG compatibility. Pair trigger sets are still enumerated with default max_triggers=2 even when only arity-1 families can run. Stage 4 enumeration and final artifact writes contain no cancellation checkpoints. Named Human genes can be as long as 205,012 nt, much larger than the 10,000-nt direct limit.

**Evidence.** `normalize.py:97–103`; `profiles.py:231`; `genes.py:654–706`; `triggers.py:75–120`; `switches.py:113–139,178–189`; `pipeline.py:475–497,1076–1115,1420–1487`; current reference-size inspection.

**Scope.** Define explicit run budgets and cancellation guarantees for supported maximums; avoid evaluating impossible family arities; preserve exact selection semantics while improving algorithms; implement declared tie-breakers and a documented tie policy; decide whether Pareto output is a promised feature or a component experiment.

**Acceptance criteria.** Ties change according to configured metrics; no-count gene ranking avoids quadratic work; long reference inputs have bounded compute/memory or clear configured limits; cancellation is tested in gene selection, trigger evaluation, circuit enumeration and artifact generation; meaningful load tests use repeated worker jobs and large reference genes, not only short fixtures; candidate counts remain deterministic under optimizations.

<a id="ENG-14"></a>
### ENG-14 — P2: Finish or clearly delimit reports, release and diagnostic outputs

**Problem.** “Writing report” does not call `ReportBuilder`, which is a stub. Successful runs produce design CSV plus HOLD_SYSTEM audit files. GenBank/SBOL writer tests do not establish downloadable production artifacts. Runtime safety calls use `host_context='unconfigured'` and no real adapter; the policy classes do not constitute an operational screening system.

**Evidence.** `pipeline.py:495–497,1378–1490`; `reporting.py:44,62,121`; `safety.py:391–419`; actual artifact-kind counts in probe.

**Scope.** Decide the user-visible completion states of computation, scientific qualification and release. Build an honest human-readable report with metric provenance, caveats and failed checks. Provision/integrate the project’s chosen local screening adapter and operational ownership if sequence release is in scope; retain fail-closed behavior while unconfigured. Never “fix downloads” by bypassing that policy.

**Acceptance criteria.** Report labels reflect actual artifacts; computation completion cannot be mistaken for release; all held outputs carry actionable reasons and correct host/context; malformed/stale/unavailable/timeout adapter paths remain held; release-path tests use a clearly identified test adapter and separately validated deployment integration; no test mocks a PASS and then claims real screening exists.

### Product interface, clients and documentation

<a id="PD-01"></a>
### PD-01 — Make capabilities describe runnable combinations (P0/P1, M)

**Observed:** actual engine capabilities list `antisense`, `toehold_and`, `prokaryotic_toehold_and`, `eukaryotic_toehold_and` as available. `pipeline.py:153` and `build_tools:254` skip them. `Steps.tsx:641` disables only `!family.available`; `compile.tsx:76` has the same incomplete check. Browser probes confirm mCherry-only, AND, and Human+prokaryotic configurations leave Compile enabled.

**Task:** expose host/buildability/payload/backbone constraints in one authoritative capability contract. Distinguish component implemented, integrated pipeline runnable, provisional model, and unavailable. Wire both APIs and UI to it. Implementing missing mechanisms/payloads is a separate scientific task; changing a flag does not implement them.

**Acceptance:** every enabled browser configuration has a runnable integration test; every unsupported combination is rejected before queuing with a specific reason; direct/API/wizard agree; four-host cross-product includes mixed supported/unsupported family requests; unavailable choices never vanish silently from user intent.

**Owner/dependency:** platform+frontend agent, coordinated with mechanism/payload owners. No new biological model is required for honest capability reporting.

<a id="PD-02"></a>
### PD-02 — Show scientific warnings and provenance at the point of use (P0, M)

**Observed:** `runs.$runId.tsx` consumes status but drops its warnings, never calls `useRun`, and drops candidate warnings. Browser seeded a unique warning which never appeared. Result subtitle claims “off-target screening”; `MetricGrid.tsx:61` calls success “Model confidence … in vivo”. Guide/FAQ disclose missing scanner, but user must leave results to find this.

**Task:** render run/candidate warnings, measurement availability, output-release decisions, reference/transcript identity, model/engine versions, resolved constraints and seed. Replace unsupported efficacy/confidence claims with precise model/proxy labels. Show whether design is a bare cassette or assembled vector and whether exports are held.

**Acceptance:** a held Human result explains the hold without API inspection; unmeasured off-target is never displayed as screened/clean; run snapshot is accessible; warning count/detail works for thousands of candidates; accepted-for-ranking and released-for-export are visibly distinct.

<a id="PD-03"></a>
### PD-03 — Implement result pagination and consistent filtering (P1, M)

**Observed:** `Results` fixes `limit: 200` at `runs.$runId.tsx:183`, ignores response total, and reports the fetched length as “candidates returned”. With total 7,907, browser displayed only “200 candidates returned”. Dashboard similarly caps history at50. `selectedId` is only set when null, so selection can refer to a filtered-out candidate.

**Task:** paginate or virtualize API-backed results; make counts and filters global and explicit; keep detail selection consistent; add paginated run history.

**Acceptance:** navigate to candidate201 and7907 in a synthetic large response; output/min-score/rejected filters find matching entries beyond first page; total/fetched/shown counts are accurate; selection clears/reselects after filtering; no large DOM render or giant fetch is necessary.

<a id="PD-04"></a>
### PD-04 — Reject malformed pasted sequence instead of silently changing it (P0, S/M)

**Observed:** `Steps.tsx:161` and custom-payload handler strip every character outside ACGUT. Browser input `>ACTG header\nACGUNNNNACGU` became `ACUGAACGUACGU`: letters from the FASTA title became bases, and four ambiguous N positions vanished.

**Task:** retain entered text, parse explicit FASTA/plain sequence formats, normalize case/T→U transparently, reject ambiguous/invalid characters with positions or an explicit policy. Make both direct and custom payload use the same documented parsing contract.

**Acceptance:** FASTA header never enters sequence; whitespace normalization works; ambiguity never silently deletes coordinates; multiple FASTA records give a precise error/choice; server validates identically; preview length and final frozen RNA agree.

<a id="PD-05"></a>
### PD-05 — Render errors and genuine empty states consistently (P1, M)

**Observed browser cases:** network-aborted submit emitted uncaught `Failed to fetch` and no alert (`compile.tsx:87`, only `ApiError` is displayed); dashboard HTTP500 became “No circuits yet”; completed zero-candidate result kept an animated detail spinner forever; C. acnes empty public catalog had no no-data message. Sources also omit comparison/info errors, artifact-fetch errors and cancel/key-reset/revoke errors.

**Task:** define error/loading/empty states for every query and mutation, catch rejected mutation promises, keep entered config after failures, provide retry and next action. Preserve useful diagnostics without exposing internal stack traces.

**Acceptance:** browser tests inject401/403/404/422/429/500/network-offline into key flows; every state is distinguishable from empty data; no unhandled page errors; zero-candidate run is explained; no public C. acnes data directs user to upload or lookup.

<a id="PD-06"></a>
### PD-06 — Replace the stale browser smoke suite and add matrix coverage (P1, M/L)

**Observed:** `frontend/e2e/smoke.mjs:55` expects login→`/projects`, project list/detail, and old credentials, while product now routes to `/dashboard` and has no projects. `npm run check` executes TypeScript/ESLint and server-render tests only. The render test checks seven logic shapes for `<svg>`; it does not test compiler state, asynchronous behavior, accessibility, or actual API wiring.

**Task:** repair smoke around current routes and fixtures; add isolated browser contract tests plus a small real server/worker integration lane. Seed known safe fixtures without real user data; provision Chromium dependencies in CI.

**Acceptance:** login/register/reviewer, four-host × three-mode wizard, invalid/unsupported combinations, submit retry, progress/offline/cancel/failure, results paging/warnings/exports, key lifecycle all covered; at least one real queued run completes in browser CI; nightly heavier dataset matrix separate from fast checks.

<a id="PD-07"></a>
### PD-07 — Preserve client result options across asynchronous completion (P1, M)

**Observed:** Python `Job.wait()` calls `_client.results(self.job_id)` with no query (`job.py:80`); R and MATLAB do the same. GET results defaults `top_n=25`, `include_rejected=false`, no artifacts (`api/routers/design.py:334`). Submitted `top_n=1`, rejected/artifact choices therefore work if POST returns inline but silently differ after ordinary queued completion. `Job` does not retain submitted fields.

**Task:** persist response-shaping defaults server-side or carry them in all client job handles; document per-call overrides and keep inline/async behavior equivalent.

**Acceptance:** identical requests with immediate completion and queued completion produce the same selected candidates/artifact inclusion; test top_n 1/100, rejected-only, artifact kinds, and resumed job handles in all languages.

<a id="PD-08"></a>
### PD-08 — Fix client timeout and best-candidate contracts (P1, S/M)

**Observed:** fake-session probe shows `Client.design(wait=120)` sends HTTP timeout 30. All three clients default request timeout 30 while server supports wait 300. Python `Job.best()` returns first rejected row although docstring promises None when all rejected; R and MATLAB first-row helpers have the same logic.

**Task:** derive POST request timeout from bounded wait plus transport margin or reject contradictory settings; filter accepted/ranked candidates in best helpers; preserve bounded wall-clock polling behavior and typed transport errors.

**Acceptance:** wait 120 can survive beyond 30 seconds; all-rejected result returns None/NULL/empty table consistently; empty, mixed and shuffled results work; timeout/resume does not resubmit.

<a id="PD-09"></a>
### PD-09 — Make R/MATLAB clients executable and conformant (P1, M/L)

**Source-proven defects:** both flatten raw metrics into table columns and omit `design`, `run_id`, `summary`, `triggers`, `warnings`, while the shared fixture expects the raw candidate JSON column set. R demands exact column equality; MATLAB expects all raw names to be present. These checks cannot pass with current table builders. MATLAB `private/request.m:27` constructs `HeaderFields` as `{'Accept','application/json','X-API-Key',secret}` (1×4) rather than N×2, unlike its own valid2-column download headers. Review this in MATLAB runtime. R's single-element vectors with auto-unboxing also need explicit list-array conformance tests, especially `gate_families`/`include_artifacts` (not executed here).

**Task:** define separate raw-JSON and flattened-table contracts; fix request construction; provision R CI and a reproducible supported MATLAB version test; test null metric values and one/many array encoding. Decide package publication and supported language versions.

**Acceptance:** executable language-specific tests against the same real local API pass; empty/missing metrics retain consistent types; capability/auth/validation/429/async/wait/artifacts round-trip; docs say experimental until verification; publish instructions match actual release availability.

<a id="PD-10"></a>
### PD-10 — Reconcile documentation and make status verifiable (P1, M)

**Observed:** current ROADMAP simultaneously says Q1 answered all hosts and Q1 blocks everything; calls CircuitDesigner/CodonOptimizer stubs although implemented; says MockEngine default although no MockEngine class remains and settings default LocalEngine; says 1,116 tests; says engine.pipeline does not exist under X6. `CLAUDE.md` says 48 stubs, 119 engine tests under 0.5 s, parser missing; `genes.md` says Human unsupported; `integration.md` says repository is in OneDrive and numerous current implementations do not exist. These are operationally harmful instructions to delegated agents.

**Task:** update authoritative current-status sections, mark historical narratives with dates, align user help/API docs and generated surface, record every implemented/open item once. This audit is explicitly requested by user; it should feed ROADMAP rather than become an indefinitely divergent second ledger.

**Acceptance:** no current-status claim references missing MockEngine; Q1 closures consistent; all implemented features have current tests and limits; `gene_id` documented in every “all request fields” table; stale numerical counts replaced by generated evidence or dated snapshots; representative docs examples execute in CI.

<a id="PD-11"></a>
### PD-11 — Decide annotation, review, and synthesis product scope (P2, S decision; M implementation)

**Current:** backend annotations exist; UI hooks unused; synthesis button permanently disabled. No saved shortlist or review workflow in UI despite decision tags existing.

**Decision needed:** should competition release include researcher review/shortlisting? Is ordering an actual funded partner deliverable or a future idea?

**Acceptance:** if in scope, show per-candidate notes/tags, persistence/ownership, auditability and bulk export; if out of scope, label planned features consistently and remove claims implying availability. External ordering needs explicit partner contract and authorization; do not imply it is a small frontend toggle.

<a id="PD-12"></a>
### PD-12 — Complete release ownership and attribution decisions (P2 before release, S/M)

**Current:** `docs/attribution.md` has unresolved contributor/asset/source/consent/data-retention TODOs; example dataset still described as experimental despite its stated illustrative origin; Python README says `pip install cernal` while ROADMAP says not published. Logo permission/HP URL TODO exists in `Steps.tsx`. Docs’ package/repository endpoint counts disagree.

**Task:** name human approvers for data stewardship, deployment, source releases, collaboration branding and package publishing; verify bundled data provenance and license record; test installation from distribution built from clean checkout.

**Acceptance:** every unresolved release TODO has a named responsible person and explicit date; installation instructions use real tested artifact/source; illustrative data clearly labeled; no unverified package publication claim; data retention and post-competition account policy documented.

### Cross-cutting completion tasks


<a id="GAP-01"></a>
### GAP-01 — Complete the payload catalog and specify multiple-output behavior

**Priority P1; owner assembly/product with scientific reviewer; M per approved payload.** The UI advertises six output categories; fresh 24-case execution proves only GFP and valid custom CDS work. Outputs are assigned round-robin across designs rather than exhaustively combined. Existing engine and UI task cards identify this gap but do not by themselves deliver the missing payloads.

**Work:** define the exact supported molecule and version for each named output, permitted host contexts, protein/junction requirements and source provenance. Clarify reporter alternatives versus co-expression. Implement each approved payload as an independently reviewable library/integration change. Distinguish AmpR from KanR. “Apoptosis” is an outcome requiring a concrete context-specific specification, not a missing arbitrary sequence to guess. Expose unavailable/inapplicable combinations honestly until they are implemented.

**Acceptance:** all applicable host/payload/mode combinations pass real integration tests; invalid custom ORFs fail before queueing; changing payload affects payload-dependent validation/scoring; requested outputs are all accounted for explicitly; payload identifiers/protein translations and sequence digests are preserved; no silently skipped outcome; multi-output tests establish exact expected cardinality and meaning. Coordinate ENG-08/10 and PD-01. Domain sign-off is required for the intended biological behavior, beyond software tests.

<a id="GAP-02"></a>
### GAP-02 — Implement an explicitly scoped off-target/orthogonality subsystem

**Priority P1 if specificity is advertised, otherwise P2 feature completion; L; owner computational modelling.** There is no integrated off-target scan. Host reference availability does not make a scan happen, and motif filtering is a different operation. Orthogonality remains unmeasured even in multi-component candidates. `docs/off-target-analysis.md` is a proposal; no fresh feasibility benchmark was executed in this audit.

**Work:** first ratify the intended interactions, background RNA sets, host/isoform context, reference versions and allowed runtime. Benchmark the proposed method using retained positive/negative controls before selecting a backend. Implement as a standalone measured component, then integrate into candidate filtering/ranking with explicit unavailable/timeout/partial states. Define cross-gate interactions separately from transcriptome-wide specificity. Update UI labels immediately so missing measurements are visible.

**Acceptance:** known intended and unintended pairs are distinguished on an independent benchmark; empty or incomplete background never yields a clean-screen claim; stable target coordinates/reference IDs and model versions are recorded; long-input performance and timeout/cancellation are measured; host-specific controls pass; all 2^n input assignments (four for two inputs) and cross-interactions are assessed for supported multi-input mechanisms. Review current off-target plan's stated 10-minute/8-GiB target as a requirement to test, not achieved performance. Depends on ENG-07/12 and GAP-03.

<a id="GAP-03"></a>
### GAP-03 — Establish functional validation and calibrated scientific acceptance

**Priority P1 for scientific claims; L, ongoing; owner scientific lead plus evaluation agent.** Current tests prove numerical/software behavior, not cell-level gate activity. The Human probe produced 15 accepted candidates, 14 with proxy dynamic range ≤1, and rank 1 success 0.96610 with dynamic range 0.15079. Stage 4 has no observed confusion matrix. No functional success probability is calibrated by those calculations.

**Work:** define intended ON/OFF outcome for each supported family/host, independent evaluation cohorts, leakage/dynamic-range measurements, truth tables for combined inputs and negative controls. Separate accessibility benchmarking from switching efficacy. Review existing research artifacts with their exact reference/model versions; prevent tuning and testing on the same data. Rename provisional scores until calibration evidence exists. Raw-count/metadata and measured discrimination should be added only under a documented input specification; otherwise explicitly defer those product claims.

**Acceptance:** a versioned evaluation report describes data provenance, train/tune/test separation, uncertainty, baselines, failure cases and host scope; probabilistic labels require held-out calibration; each claimed molecular logic has functional evidence or an explicit experimental-unvalidated label; analytical tests independently verify equations/units; performance claims can be traced to retained results. New biology decisions have a named human approver. An agent can prepare benchmarks and code, but software QA cannot substitute for missing experiments. Coordinates Q2–Q8/Q14/Q15 and ENG-01/02/06/07/08/09.

<a id="GAP-04"></a>
### GAP-04 — Govern reference and public-dataset completeness, meaning and refresh

**Priority P1 for public data interpretation; M/L; owner reference/data steward.** All 15 tables parse but none maps completely, and yeast includes aliases mapping multiple rows to one stable gene. The arthritis study title differs in meaning from the contrast described as normal-sample stimulation in the bundled catalog; source sample metadata was not verified in this audit. Reference selection is deterministic but does not establish which isoform a tissue expresses. Current catalog contains no C. acnes comparisons.

**Work:** verify and persist exact contrast labels, direction, strain/tissue/condition and statistical completeness against primary provider metadata; repair condition-string normalization; version catalog/reference refreshes together; decide duplicate/alias collapse, unresolved ID reporting and user-selected transcript policy. Keep full analysis data separate from preview caps. Add C. acnes catalog entries only when suitable provenance-verified comparisons exist; otherwise show an explicit empty state. Decide whether non-Human UTR/noncoding support and user reference import are required and document scoped limits.

**Acceptance:** fresh per-comparison checksums/row counts/ID-coverage/statistic tiers and source provenance are retained; no disease-classifier implication from title alone; missing or ambiguous identifiers remain visible and cannot silently change species; every catalog entry gets an appropriate real pipeline smoke plus separate statistical/biological interpretation review; updates reproduce old runs by pinned version; duplicates have a documented non-inflating policy. The current table above is the baseline. Depends on ENG-03/12 and PLAT-03, not on pretending all unknown identifiers resolve.

<a id="GAP-05"></a>
### GAP-05 — Restore green delivery checks and build a meaningful release QA matrix

**Priority P1; M; owner QA/CI.** Fresh main regression is green, but formatting and Python-client conformance are not. Current matrix assertions explicitly accept failure for 72 unsupported configurations, browser smoke is obsolete, and some export tests override release. Those scopes must be visible to maintainers.

**Work:** fix the existing formatting error; replace the stale client biological fixture with a verified productive trigger while retaining an explicit empty-result test; add fixture assertions before seeding COMPLETED. Promote audit probes into desired-behavior regression tests. Maintain separate supported-success and unsupported-rejection matrices, plus failure injection, numeric/parser, scientific-semantic, UI and client lanes. Make heavy datasets/soak tests scheduled or manually reproducible rather than hiding them in every small unit test. Test clean-checkout GitHub/GitLab generation order. Add dependency-advisory review and supported-runtime coverage as release jobs with recorded results.

**Acceptance:** locked clean checkout passes lint/format, migrations, backend, frontend build/check, Python conformance and current browser smoke; every enabled capability has a positive implementation test and every invalid combination has a specific early rejection; zero-candidate results are expected/tested explicitly; API/explorer/export values agree; worker failure recovery and ownership regressions pass; release reports distinguish real screening, test adapter, unavailable feature and untested environment. Archive tested commit/configuration/runtime/reference versions. Do not weaken correctness assertions merely to keep historical candidate counts.


<a id="release-acceptance"></a>
## 8. Release acceptance and reproduction

### 8.1 Definition of done for the requested “all inputs work” milestone

- One versioned capability matrix names applicable hosts, modes, formats, families, outputs, vectors and limits. UI and both submission APIs use it. Every advertised applicable cell has a successful real integration test; omitted work cannot hide behind warning-only skipping.
- Valid inputs are interpreted identically in upload validation, preview, engine and client, including worksheet, normalized identifiers and numeric values. Invalid inputs fail early with an actionable message and no changed sequence.
- A run always reaches a recoverable or terminal state under tested enqueue failure, worker crash/timeout, duplicate delivery, cancellation races and result-import failure. Its progress represents work actually done; long operations have measured bounds.
- Multi-user data stays isolated across every read, write, retry and download path, including reviewer mode, API-key scopes and shared development configuration.
- Candidate labels, signs and displayed logic match a physically specified construct; unsupported chemistry cannot be accepted as if compiled. Scoring definitions and missing measurements are truthful. Experimental validation is tracked separately.
- Every candidate has enough saved provenance to reproduce inputs, models, references and assembly. CSV preserves zero versus missing, strict JSON contains no nonfinite values, and incomplete archives never look complete.
- Completed/empty/failed/cancelled/held/released results have distinct understandable UI states. Results and run history are fully navigable beyond the first page.
- The operational release adapter, if sequence release is in scope, is provisioned and tested without bypassing its policy. GenBank/SBOL/FASTA outputs preserve coordinates, topology and exact sequence identity. PDF/figures are either implemented or explicitly absent.
- Clean installation and supported-runtime CI pass; deployment, backup/restore, storage retention and monitoring are verified for the chosen hosting environment. R/MATLAB and Windows claims require tests on those runtimes.

This milestone can be defined and tested. An absolute guarantee of no future errors cannot be made from any finite QA campaign. The specific target should be no known failures in the declared supported matrix, no indefinite unhandled states in the tested failure modes, and explicit limits for inputs and scientific claims.

### 8.2 Reproduce this audit

Run from the repository root. `UV_CACHE_DIR` here keeps audit cache writes separate. `--offline --no-sync` reuses the installed environment; for a clean-checkout release test first perform the repository's documented locked dependency installation. Python client live-server tests require localhost socket permission. Browser tests require a built frontend, installed Playwright browser and its system libraries.

```bash
UV_CACHE_DIR=/tmp/cernal-audit-uv uv run --offline --no-sync pytest -q --durations=25
UV_CACHE_DIR=/tmp/cernal-audit-uv uv run --offline --no-sync ruff check .
UV_CACHE_DIR=/tmp/cernal-audit-uv uv run --offline --no-sync ruff format --check .
UV_CACHE_DIR=/tmp/cernal-audit-uv uv run --offline --no-sync python manage.py check
UV_CACHE_DIR=/tmp/cernal-audit-uv uv run --offline --no-sync python manage.py makemigrations --check --dry-run
UV_CACHE_DIR=/tmp/cernal-audit-uv uv run --offline --no-sync python tools/gen_api_surface.py --check
UV_CACHE_DIR=/tmp/cernal-audit-uv PYTHONPATH=src:clients/python uv run --offline --no-sync pytest clients/python/tests -c clients/python/tests/pytest.ini -q
npm --prefix frontend run check
npm --prefix frontend run build
```

Restore archived probes to the repository's `var/audit-2026-10-08/` path before using them (archive paths already include that directory). These are audit observations of the before state, not a replacement for committed regression tests:

```bash
UV_CACHE_DIR=/tmp/cernal-audit-uv PYTHONPATH=src uv run --offline --no-sync python var/audit-2026-10-08/engine_probes.py
UV_CACHE_DIR=/tmp/cernal-audit-uv PYTHONPATH=src uv run --offline --no-sync python var/audit-2026-10-08/root_matrix_probes.py
UV_CACHE_DIR=/tmp/cernal-audit-uv PYTHONPATH=src uv run --offline --no-sync python var/audit-2026-10-08/format_pipeline_probes.py
UV_CACHE_DIR=/tmp/cernal-audit-uv uv run --offline --no-sync pytest -q -s var/audit-2026-10-08/test_platform_probes.py
LD_LIBRARY_PATH=/tmp/tau-browser-libs/root/usr/lib/x86_64-linux-gnu node var/audit-2026-10-08/product-browser-probes.mjs
```

The displayed LD_LIBRARY_PATH is specific to the pre-provisioned libraries on the audited machine. Use the supported Playwright dependency installation on another machine. The mocked browser harness loads the real built app while intercepting all HTTP traffic; it does not depend on real user records.

The evidence archive contains selected probe source, observed JSON, sanitized test logs and a content-hash snapshot of relevant source/lockfiles. Run-local sequence artifacts, database files, uploaded user data, virtual environments and installed dependencies are intentionally excluded. Source line references in task cards describe the audited working tree and may move after fixes.

### 8.3 Retained research evidence

`docs/trigger-selection-development-logbook.md` records earlier probing/accessibility comparisons and explicitly separates them from biological gate activation. Those experiments were not rerun here. Its described marginal RNAplfold comparisons and proposed six-tool benchmark must not be presented as calibrated switch success or completed AND validation. Reuse retained research only with its exact input/cohort/model versions and a clear reproduced-versus-historical label.

The historical live arthritis run and earlier all-input report under `var/qa/` are useful execution evidence, but do not override the fresh defects in this report. In particular, candidate/artifact counts do not demonstrate a released sequence, correct physical truth table or measured specificity.

### 8.4 API operation inventory

Fresh source inventory: **43 routed API operations** (27 GET, 13 POST, 3 DELETE), plus framework OpenAPI/docs and Django admin. Endpoint presence does not mean all authorization/validation branches are correct; the task cards identify those gaps.

| Method | Route | Handler source |
|---|---|---|
| GET | `/api/auth/csrf` | `src/api/routers/auth.py:56` |
| POST | `/api/auth/register` | `src/api/routers/auth.py:72` |
| POST | `/api/auth/login` | `src/api/routers/auth.py:103` |
| POST | `/api/auth/reviewer-login` | `src/api/routers/auth.py:125` |
| POST | `/api/auth/logout` | `src/api/routers/auth.py:145` |
| GET | `/api/auth/me` | `src/api/routers/auth.py:151` |
| GET | `/api/auth/keys` | `src/api/routers/auth.py:164` |
| POST | `/api/auth/keys` | `src/api/routers/auth.py:188` |
| DELETE | `/api/auth/keys/{key_id}` | `src/api/routers/auth.py:204` |
| POST | `/api/auth/keys/{key_id}/regenerate` | `src/api/routers/auth.py:212` |
| GET | `/api/auth/whoami` | `src/api/routers/auth.py:222` |
| GET | `/api/datasets` | `src/api/routers/datasets.py:30` |
| POST | `/api/datasets` | `src/api/routers/datasets.py:35` |
| GET | `/api/example-datasets` | `src/api/routers/datasets.py:49` |
| POST | `/api/datasets/example` | `src/api/routers/datasets.py:58` |
| GET | `/api/datasets/{dataset_id}` | `src/api/routers/datasets.py:69` |
| GET | `/api/datasets/{dataset_id}/preview` | `src/api/routers/datasets.py:74` |
| DELETE | `/api/datasets/{dataset_id}` | `src/api/routers/datasets.py:85` |
| POST | `/api/design` | `src/api/routers/design.py:167` |
| GET | `/api/design/{run_id}` | `src/api/routers/design.py:288` |
| GET | `/api/design/{run_id}/results` | `src/api/routers/design.py:328` |
| GET | `/api/reference-genes/resolve` | `src/api/routers/expression.py:32` |
| GET | `/api/public-datasets/organisms` | `src/api/routers/expression.py:40` |
| GET | `/api/public-datasets/experiments` | `src/api/routers/expression.py:45` |
| GET | `/api/public-datasets/comparisons` | `src/api/routers/expression.py:50` |
| POST | `/api/public-datasets/materialize` | `src/api/routers/expression.py:59` |
| GET | `/api/public-datasets/{comparison_key}` | `src/api/routers/expression.py:74` |
| GET | `/api/health` | `src/api/routers/meta.py:23` |
| GET | `/api/version` | `src/api/routers/meta.py:28` |
| GET | `/api/runs/{run_id}/candidates` | `src/api/routers/results.py:53` |
| GET | `/api/candidates/{candidate_id}` | `src/api/routers/results.py:76` |
| GET | `/api/runs/{run_id}/artifacts` | `src/api/routers/results.py:81` |
| GET | `/api/artifacts/{artifact_id}/download` | `src/api/routers/results.py:87` |
| GET | `/api/runs/{run_id}/export.csv` | `src/api/routers/results.py:109` |
| GET | `/api/runs/{run_id}/artifacts/download` | `src/api/routers/results.py:119` |
| GET | `/api/candidates/{candidate_id}/annotations` | `src/api/routers/results.py:190` |
| POST | `/api/candidates/{candidate_id}/annotations` | `src/api/routers/results.py:196` |
| DELETE | `/api/annotations/{annotation_id}` | `src/api/routers/results.py:216` |
| GET | `/api/runs` | `src/api/routers/runs.py:31` |
| POST | `/api/runs` | `src/api/routers/runs.py:39` |
| GET | `/api/runs/{run_id}` | `src/api/routers/runs.py:100` |
| GET | `/api/runs/{run_id}/detail` | `src/api/routers/runs.py:123` |
| POST | `/api/runs/{run_id}/cancel` | `src/api/routers/runs.py:129` |
