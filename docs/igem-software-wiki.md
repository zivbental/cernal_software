# CERNAL — From RNA signals to inspectable toehold candidates

> **Research prototype.** CERNAL turns a direct RNA sequence or a scoped differential-expression signal into inspectable, ranked single-input toehold-switch and plasmid design candidates. It preserves inputs, assumptions, metric decompositions, rejected candidates, warnings, and artifact checksums so that a result can be reviewed rather than accepted as a black-box answer.
>
> **Evidence boundary.** This page describes merged `main` at commit `417f8385725a99f2d7d4bc835eeedeb5903d399f` unless a feature is explicitly labelled **unmerged**, **uncommitted**, or **planned**. CERNAL has software-test and computational evidence, but no wet-lab validation of its current candidates, scores, or biological performance.
>
> **Editorial status — 28 September 2026.** This is a competition-page draft for team review. Team members must verify every claim, rewrite and approve the substantive narrative, complete the official Attributions Form and responsible-AI disclosure, and replace every `TODO` before publication.

<!-- ASSET PLAN — HERO
Proposed filename: assets/software/cernal-hero-pipeline.svg
Alt text: "A three-part workflow: RNA sequence or differential-expression table enters CERNAL, a traceable pipeline ranks single-input toehold designs, and the user receives candidate records plus FASTA and GenBank artifacts with checksums."
Caption: "CERNAL connects a bounded biological input to reviewable computational candidates and build artifacts; the diagram does not imply experimental efficacy."
Production notes: Team-authored SVG; use text labels and arrows in addition to color; include a static PNG fallback; keep labels legible at 320 px; do not animate unless motion can be paused and respects prefers-reduced-motion.
Evidence source: merged main at 417f838; architecture and output claims listed in the Source notes.
-->

## Five-minute judge path

1. **Understand the claim (1 minute):** read [CERNAL in one minute](#cernal-in-one-minute) and the [current capability matrix](#current-capability-matrix).
2. **Follow one real software path (1 minute):** scan the [worked regression-fixture workflow](#worked-workflow-a-real-test-fixture-not-a-biological-result), including accepted/rejected candidates and checksummed artifacts.
3. **Check the evidence boundary (1 minute):** review [what was actually verified](#validation-and-evidence) and what has no wet-lab or calibrated-performance evidence.
4. **Reproduce the judged configuration (1 minute):** use [installation and engine verification](#installation-and-demo), then confirm that `/api/version` and the downloaded run manifest report the same engine version.
5. **Assess responsibility and continuity (1 minute):** read [safety](#safety-security-and-responsible-use), [limitations](#limitations-and-future-work), and [attribution/AI TODOs](#attribution-licensing-and-ai-disclosure-todos).

**Optional deep dives:** expand the implementation sections for [architecture](#architecture-from-click-to-artifact), [inputs/outputs](#inputs-outputs-and-interoperability), [algorithms](#algorithms-and-assumptions), [reuse](#reuse-contribution-and-continuity), and the [media production plan](#media-and-asset-production-plan).

**Competition record:** the official 2026 iGEM rules require software work to be preserved in the team’s official iGEM Software Tools repository, with reproducible instructions, pinned dependencies, an OSI-approved license, and appropriate AI/model disclosures. The judged wiki record must remain understandable without an external live application. See [Official iGEM 2026 Team Wiki Requirements][igem-wiki-requirements] and [Official iGEM 2026 Project Software Requirements][igem-software-requirements].

<!-- TODO (team): Add the official iGEM Software Tools GitLab URL when assigned and make it the primary source link. Keep the GitHub repository clearly labelled as a development mirror if it remains public. -->
<!-- TODO (team): Confirm the team’s 2026 Village and selected judging criteria. If the team is in the Software & AI Village, state clearly in the final judging map that this page is the software record and not a Best Software submission, because Software & AI Village teams are not eligible for that award. -->

## CERNAL in one minute

| Question | Answer grounded in the audited release |
|---|---|
| **Who is it for?** | Synthetic-biology researchers and iGEM teams who can evaluate RNA-switch assumptions, host context, transcriptomic contrasts, plasmid assembly constraints, and biosafety requirements. |
| **What goes in?** | Either a direct RNA sequence or a normalized differential-expression table. The real end-to-end path is currently scoped to *E. coli* and yeast. |
| **What happens?** | CERNAL validates the request, sources candidate triggers, performs [ViennaRNA][vienna-paper]/[RNAplfold][rnaplfold-paper] calculations, generates single-input toehold candidates, applies a provisional scoring profile, and constructs sequence artifacts for accepted candidates. |
| **What comes out?** | Ranked and rejected candidate records, raw and normalized metrics, warnings, stable rejection reasons, a candidate table, FASTA and GenBank artifacts, resolved parameters, and SHA-256 checksums. |
| **What is the strongest evidence?** | Current-main tests exercise direct RNA and *E. coli*/yeast differential-expression paths, deterministic ranking behavior, rejected-candidate retention, artifact checksums, and GenBank parse-back. The simulated web lifecycle is exercised through the HTTP API with the worker task function invoked inline, not through a live qcluster. |
| **What is not established?** | Biological efficacy, calibrated specificity, wet-lab performance, human end-to-end support, production AND/NOT/antisense/CRISPR design, a provisioned hazard database, or a validated genome-wide off-target screen. |

CERNAL is best understood as a **compiler-like design workflow**. It freezes a request into a versioned `JobRequest`, runs either a real local scientific engine or a clearly simulated engine through the same contract, and returns a versioned `JobResult`. The output is a set of design hypotheses and their provenance—not a construction authorization or a claim that the top-ranked candidate will work in a cell.

## The design problem

### Disconnected tools hide consequential decisions

A team may begin with an RNA sequence or with evidence that genes separate two biological states. Turning that starting point into a candidate RNA switch requires several different decisions: which signal to use, where a trigger window lies, whether local RNA structure is accessible under recorded settings, which switch architecture is compatible, how candidates are filtered and ranked, and how an accepted design is represented as a plasmid artifact.

When those decisions are made across spreadsheets, scripts, websites, and manual copy-paste, it becomes difficult to answer basic review questions:

- Which exact input bytes produced this candidate?
- Which parameters, references, and software versions were used?
- Why was one design ranked above another?
- Which alternatives were rejected, and why?
- Does a downloadable sequence correspond to the candidate shown on screen?
- Which measurements are real calculations, which are provisional scores, and which are still placeholders?

CERNAL’s present contribution is to connect a deliberately narrow slice of that workflow through one inspectable contract. It does not remove the need for scientific judgment; it makes the computational hand-offs easier to audit.

<!-- ASSET PLAN — PROBLEM / BEFORE-AFTER
Proposed filename: assets/software/cernal-before-after-workflow.svg
Alt text: "Two horizontal lanes compare a manual workflow with CERNAL. The manual lane passes data among separate spreadsheets, folding tools, ranking notes, and sequence files. The CERNAL lane records the same stages in one versioned run with warnings, rejected candidates, and checksums."
Caption: "CERNAL’s value is traceability across a bounded workflow, not replacement of expert biological review."
Production notes: Use identical stage names in both lanes; mark manual hand-offs with a broken-chain symbol and CERNAL records with document/checksum symbols; do not communicate the comparison through color alone.
-->

### One user, one decision, one traceable run

Consider an iGEM researcher who has identified a candidate RNA signal in *E. coli* and wants to explore a single-input toehold switch controlling GFP. The researcher needs a computational starting point, but also needs enough information to challenge that starting point before synthesis.

With CERNAL, the researcher can:

1. choose direct-RNA input or a supported differential-expression path;
2. select only capabilities exposed by the running engine;
3. submit a request whose input checksum and resolved parameters are frozen;
4. inspect progress, warnings, accepted candidates, rejected candidates, and score components;
5. download candidate tables and current FASTA/GenBank artifacts; and
6. retain artifact checksums so that the reviewed bytes can be identified later.

The researcher must still review the biological context, off-target risk, host assumptions, assembly constraints, institutional requirements, and wet-lab evidence. CERNAL currently supports that review with provenance and visible limitations; it does not complete the review automatically.

## Current capability matrix

The labels in this table are textual so that status is not conveyed by color alone.

| Capability | Status on merged `main@417f838` | What the status means |
|---|---|---|
| Account registration, staff approval, sign-in, queued runs, cancellation, results browsing, annotations, and downloads | **Current** | The web product supports the workflow. A separate worker is required to execute queued runs. |
| Default `MockEngine` | **Current — simulated** | Deterministic simulated results exercise the complete product contract. Screenshots and demos must say **SIMULATED** inside the visible frame. |
| `LocalEngine` direct RNA path | **Current — bounded** | Valid RNA can produce real single-input toehold candidates through the current scientific pipeline. |
| `LocalEngine` differential-expression path | **Current — bounded** | Normalized differential-expression input can be joined to bundled *E. coli* or yeast transcript references and then use the same trigger/toehold path. |
| Human end-to-end design | **Not available** | Human lacks the bundled transcriptome and host assembly parts needed by the current pipeline. |
| Single-input toehold design | **Current** | This is the production scientific gate path on merged main. |
| Multi-input AND logic | **Not production-ready** | `ToeholdAndGate.generate_designs` and circuit-enumeration functions are incomplete; AND families are skipped by the real pipeline. |
| Antisense/NOT design | **Not production-ready** | Antisense code and tests exist, but the pipeline skips the family because the construction path is not supported by a payload sequence library. |
| CRISPR logic | **Not production-ready** | Generation and evaluation methods remain stubs. |
| GFP payload | **Current** | GFP is a configured buildable output. |
| Reviewed custom coding sequence | **Current — bounded** | A custom CDS can be supplied and validated; CERNAL emits it verbatim. |
| Codon optimization | **Not available** | No codon optimization is performed. |
| *E. coli* plasmid construction | **Current — bounded** | Promoter, switch, payload, terminator, and an optional supported backbone can be assembled and exported. |
| Yeast plasmid construction | **Limited** | Yeast promoter/terminator parts exist, but no verified first-party yeast backbone is bundled; a reviewed circular custom GenBank backbone or an allowed backbone-free route is required. |
| ViennaRNA/RNAplfold structural calculations | **Current** | Calculations use the separately licensed [ViennaRNA package][vienna-paper] and its [RNAplfold method][rnaplfold-paper]; they are computational predictions under recorded settings, not probabilities of biological success. |
| Validated biological off-target specificity | **Not available** | The current `OffTargetScanner` has no populated index; off-target and segment-specificity values are placeholders/unmeasured. |
| Hazard/pathogen/AMR screening database | **Not available** | No validated database or real screening adapter is provisioned on merged main. [PR #35][pr-35] proposes a fail-closed release policy but remains open and unmerged. |
| Candidate CSV, FASTA, GenBank, checksums | **Current** | Candidate and sequence artifacts are written on merged main; sequence artifacts correspond to accepted candidates. |
| Scientific PDF report or rendered structure/circuit report | **Not available** | `ReportBuilder` rendering/build methods remain stubbed. |
| In-product FAQ/help route and expanded accessibility tests | **Not shipped** | Draft changes were observed without a commit or pull request, so they are excluded from judged evidence. |

<!-- ASSET PLAN — CAPABILITY MATRIX
Proposed filename: assets/software/cernal-capability-matrix-export.csv
Alt text: Not applicable; this is the machine-readable alternative to the HTML table.
Caption: "Machine-readable capability status for the judged commit."
Production notes: Export the visible matrix to CSV; keep the HTML table as the primary accessible representation; if icons are added, pair each icon with the status word Current, Limited, Unmerged, or Not available.
-->

## Worked workflow: a real test fixture, not a biological result

This walkthrough follows the current-main direct-RNA regression fixture in [`tests/engine/test_pipeline.py`][test-pipeline]. It demonstrates software behavior with an intentionally selected test sequence. It is **not** an experimentally validated trigger and must not be presented as a safe, effective, or application-specific design.

### Step 1 — define the bounded request

The fixture supplies this RNA sequence:

```text
AACUUGUUGGCCCAGUGUGAAUCGCUUAAGGGUUAA
```

The request selects:

- input mode: direct RNA;
- host: *E. coli*;
- gate family: single-input toehold;
- output: the configured GFP payload;
- engine: `LocalEngine`; and
- scoring profile: the current default profile unless explicitly overridden.

CERNAL also records the request schema version, run identifier, idempotency key, output directory, parameters, and input checksum in the `JobRequest` boundary.

<!-- ASSET PLAN — WORKED EXAMPLE INPUT
Proposed filename: assets/software/example-01-direct-rna-input.webp
Alt text: "CERNAL New Circuit screen with direct RNA selected, the regression-test RNA visible, E. coli selected, single-input toehold selected, and an on-screen label stating TEST FIXTURE — NOT BIOLOGICAL VALIDATION."
Caption: "The worked example begins with the same direct-RNA fixture used by current-main pipeline tests."
Production notes: Capture from the judged commit; crop to the form and capability labels; remove usernames, tokens, local paths, and timestamps; include the test-fixture warning inside the screenshot rather than only in the caption.
-->

### Step 2 — validate before computing

The pipeline checks the input mode, RNA alphabet and length guards, organism, requested family, payload/backbone configuration, and checksum. Unsupported combinations should fail with an actionable error rather than silently produce an empty or misleading result.

For direct RNA:

- RNA is normalized to uppercase A/C/G/U;
- the minimum accepted length is 20 nucleotides;
- the direct-input guard is 10,000 nucleotides;
- short input is treated as a trigger, while longer input is scanned as a transcript; and
- engine coordinates are zero-indexed, start-inclusive, and end-exclusive.

### Step 3 — source and evaluate trigger evidence

`TriggerScorer` profiles the sequence and records structural evidence used by the current ranking path. For transcript scanning, the implemented footprints are 30, 33, and 36 nucleotides, corresponding to 12-, 15-, and 18-nucleotide toehold variants. Motif-violating windows are removed before more expensive stages. The local-opening calculation is implemented through the [RNAplfold method][rnaplfold-paper] in the [commit-pinned folding adapter][source-folding-stage].

Recorded fields include mean openness, minimum per-base accessibility, minimum free energy, GC content, AUG/stop positions, and provenance for the selection method. Gate-aware ranking also uses an 8-nucleotide seed joint-opening calculation and terminal-window measurements. These are mechanistic structural hypotheses under the recorded ViennaRNA/RNAplfold settings, not calibrated success probabilities.

<!-- ASSET PLAN — TRIGGER WINDOW
Proposed filename: assets/software/cernal-trigger-window-method.svg
Alt text: "An RNA transcript is scanned with overlapping 30-, 33-, and 36-nucleotide windows. A selected window shows an 8-nucleotide seed and a terminal 20-nucleotide region, with labels for mean marginal openness, minimum accessibility, joint seed opening, and opening free energy."
Caption: "CERNAL compares overlapping trigger footprints using recorded structural measurements; none of these values alone predicts cellular efficacy."
Production notes: Define every coordinate convention in the figure; use patterns or line styles in addition to color; label marginal and joint quantities distinctly; cite the judged commit and method settings in the caption metadata.
-->

### Step 4 — generate and score toehold candidates

`ToeholdGate` constructs a computational hairpin architecture containing a leader, complementary toehold, split stem, RBS context, start-codon sequestration, and linker. This mechanism follows the original single-input toehold-switch work of [Green et al. (2014)][green-toehold-paper], while the exact implemented construction is recorded in the [commit-pinned gate source][source-toehold]. The current implementation sweeps the supported toehold lengths and validates generated designs before scoring.

The scoring layer exposes raw values, normalization direction, weights, hard-filter outcomes, and ranking. Missing measurements follow the scoring profile’s declared default behavior rather than being invented. The profile is explicitly provisional, so the score is useful for comparing the current candidate set under one recorded configuration—not for claiming an absolute success rate.

<!-- ASSET PLAN — TOEHOLD ANATOMY
Proposed filename: assets/software/cernal-toehold-anatomy.svg
Alt text: "A labelled schematic of the computational toehold switch architecture showing leader, complementary toehold, ascending stem, RBS-containing loop, descending stem with start-codon sequestration, linker, and downstream payload."
Caption: "The implemented single-input toehold architecture. The schematic represents a computational design, not an experimentally verified structure."
Production notes: Team-drawn schematic based on the implemented source; avoid copying a journal figure; distinguish paired regions with bracket symbols as well as color; include sequence direction labels.
-->

### Step 5 — preserve accepted and rejected candidates

The current-main regression tests establish the expected software behavior for this fixture:

- the run succeeds and returns a non-empty set of toehold candidates;
- accepted candidates receive contiguous ranks;
- rejected candidates remain inspectable, have no rank/overall score, and carry a rejection reason;
- repeating the same scientific request produces byte-identical candidate identity/rank/score/sequence fields under the tested conditions; and
- the candidate table contains one row per candidate.

A judge or user should therefore be able to inspect not only the winner, but also the alternatives and the reason a design failed a hard filter.

<!-- ASSET PLAN — RESULTS REVIEW
Proposed filename: assets/software/example-02-candidate-review.webp
Alt text: "CERNAL results view with separate accepted and rejected candidate rows, rank and score columns, expandable metric details, warnings, and visible rejection reasons. The screen is labelled COMPUTATIONAL TEST FIXTURE."
Caption: "Accepted and rejected candidates remain visible so that ranking and filtering decisions can be audited."
Production notes: Use an actual current-main LocalEngine fixture run; do not substitute MockEngine output; blur no scientific fields; remove account identity; crop closely enough that headers and rejection reasons remain readable.
-->

### Step 6 — construct and verify artifacts

For each accepted candidate, `PlasmidBuilder` assembles promoter, switch, payload, terminator, and an optional backbone. Current-main tests verify that:

- every artifact path resolves to a real file;
- each file’s SHA-256 matches the checksum returned in `ArtifactRef`;
- FASTA artifacts are written for accepted candidates and not rejected candidates;
- a GenBank artifact is written for every accepted candidate; and
- the tested GenBank file parses back with circular topology and exactly four features. That regression does **not** assert the names or types of those four features; segment-kind assertions are covered separately.

The checksum proves byte identity. It does not prove biological correctness, safety, manufacturability, or efficacy.

<!-- ASSET PLAN — ARTIFACTS
Proposed filename: assets/software/example-03-artifacts-and-checksums.webp
Alt text: "CERNAL artifact list showing a candidate table, FASTA and GenBank files, candidate references, media types, and SHA-256 checksums."
Caption: "Artifacts are tied to candidate references and checksums so reviewers can identify the exact exported bytes."
Production notes: Use a judged-commit fixture; make the full checksum available as selectable text near the image; never expose a local absolute path or authentication token.
-->

### Step 7 — interpret the result honestly

This worked workflow supports the claim that current-main code can move a valid direct-RNA request through structural calculations, single-input toehold generation, provisional scoring, candidate retention, plasmid assembly, and checksummed artifact export.

It does **not** support a claim that the generated switch will function in vivo, discriminate the intended biological state, avoid biologically relevant off-targets, pass a hazard screen, or be safe to synthesize. Those questions require additional validated computational methods, expert review, institutional oversight, and wet-lab evidence.

<details>
<summary><strong>Optional deep dive: implementation, architecture, inputs, outputs, and algorithms</strong></summary>

## How CERNAL works

### Five stages, one reviewable contract

1. **Define context.** The user selects direct RNA or differential-expression input, organism, gate family, payload, backbone, constraints, and scoring options from the running capability document.
2. **Source candidate triggers.** Direct input is validated/scanned; differential-expression input is parsed, genes are ranked, bundled *E. coli* or yeast transcripts are loaded, and the same trigger scorer is applied.
3. **Generate compatible designs.** The current production path dispatches supported triggers to the single-input toehold family and validates generated switch designs.
4. **Measure, filter, and rank.** Raw measurements become typed metric records, hard filters are applied, and accepted candidates are ranked while rejected candidates remain visible.
5. **Assemble and export.** Accepted single-switch designs are wrapped as one-gene circuit candidates, assembled into plasmid representations, and written as candidate/sequence artifacts with checksums.

<!-- ASSET PLAN — FIVE-STAGE WORKFLOW
Proposed filename: assets/software/cernal-five-stage-workflow.svg
Alt text: "Five numbered stages: define context, source triggers, generate a single-input toehold, measure and rank candidates, then assemble and export artifacts. Each stage lists its input, method, output, and evidence link."
Caption: "The merged-main scientific path. Grey dashed boxes mark circuit enumeration, validated off-target scanning, hazard screening, and report rendering as unavailable or unmerged."
Production notes: Make unavailable stages visually distinct with both dashed outlines and explicit text; link each stage in the final wiki to the relevant section; provide the same information as nearby HTML text.
-->

## Architecture: from click to artifact

### Product/data flow

```text
Browser
  │
  ▼
Django Ninja API ── capability document at GET /api/version
  │
  ▼
Platform services ── accounts, datasets, runs, results
  │
  ▼
django-q2 task queue / worker
  │
  ▼
JobRequest contract
  ├── MockEngine  ── deterministic simulated science
  └── LocalEngine ── current bounded scientific pipeline
          │
          ▼
JobResult contract ── candidates, warnings, parameters, artifacts
  │
  ▼
Result import ── browser review and downloads
```

### Layer responsibilities

| Layer | Responsibility | Current source |
|---|---|---|
| React frontend | Wizard, status, candidate inspection, downloads, settings, API documentation | [`frontend/`][source-frontend] |
| HTTP/API | Typed schemas, authentication, capability discovery, run/result endpoints | [`src/api/`][source-api] |
| Platform/domain services | Accounts, datasets, analyses, results, lifecycle and persistence | [`src/apps/`][source-apps] |
| Task execution | Queue submission and separate worker execution | [`tasks.py`][source-tasks] and [`services.py`][source-analysis-services] |
| Engine boundary | Framework-free request/result/capability contracts | [`contract.py`][source-contract] and [`client.py`][source-client] |
| Scientific engine | Input, trigger, folding, gate, scoring, plasmid, artifact stages | [`src/engine/`][source-engine] |
| Runtime state | SQLite database, uploads, artifacts, and logs | `var/` at runtime; not source-controlled |

### The boundary that protects scientific code

[`src/engine/`][source-engine] must not import Django, `apps`, or `api`. Platform code may import [`engine.contract`][source-contract] and [`engine.client`][source-client], but not engine internals. [`tests/test_boundary.py`][test-boundary] enforces this rule.

This separation matters because it keeps scientific stages testable without the web framework. It also means a future out-of-process engine could preserve the same serialized contract instead of rewriting the scientific pipeline around deployment concerns.

<!-- ASSET PLAN — ARCHITECTURE
Proposed filename: assets/software/cernal-user-data-flow.svg
Alt text: "Browser requests pass through the Django Ninja API, platform services, a task queue and worker, then a versioned JobRequest reaches either MockEngine or LocalEngine. A JobResult returns candidates and checksummed artifacts for import and download. User uploads and mutable runtime storage are marked as a trust boundary."
Caption: "Product architecture and trust boundaries from browser action to downloadable artifact."
Production notes: Show MockEngine and LocalEngine as separate branches; label MockEngine SIMULATED; mark user uploads, mutable storage, and any external dataset acquisition as trust boundaries; link boxes to source directories.
-->

<!-- ASSET PLAN — ENGINE PIPELINE
Proposed filename: assets/software/cernal-engine-pipeline.svg
Alt text: "Typed input moves through validation, optional gene selection, trigger scoring, toehold design, metric normalization and ranking, one-gene circuit wrapping, plasmid assembly, and artifact writing. Off-target scanning, multi-gene circuit design, and report rendering are labelled incomplete."
Caption: "The current engine pipeline and the stages that remain incomplete."
Production notes: Keep this separate from the product/data-flow diagram; use solid borders for implemented stages, dotted borders plus text for incomplete stages; include source paths below each implemented box.
-->

## Inputs, outputs, and interoperability

### Direct RNA input

- Alphabet: RNA A/C/G/U after uppercase normalization.
- Minimum accepted length: 20 nucleotides.
- Direct-input maximum guard: 10,000 nucleotides.
- Short input is treated as a trigger; longer input is scanned as a transcript.
- Internal engine coordinates are zero-indexed, start-inclusive, and end-exclusive.
- Invalid or unsupported input must fail rather than be silently converted into a different biological sequence.

### Differential-expression input

The web upload surface accepts CSV, TSV/TXT, and XLSX, but the scientific parser consumes normalized UTF-8 CSV/TSV. Required concepts are a gene identifier and an effect-size column. Common aliases are supported for gene identifiers and log2-fold-change-like fields; optional symbol, significance, abundance, and contrast fields may also be present.

A current integration defect must remain visible: XLSX and semicolon-delimited files can pass platform validation and then fail the scientific parser. In addition, aliases such as `FC` or `fold_change` populate a log2 field, so the uploader must verify the units and contrast direction rather than assuming that a header proves the scale.

A current-main differential-expression regression fixture is:

```csv
gene_id,gene_symbol,log2fc,padj
b3908,sodA,3.2,0.001
b0033,carA,-2.8,0.002
```

This fixture demonstrates the software path against bundled references. It is not presented here as a biological dataset or experimental result.

The bundled CDS FASTA files are generated by the [commit-pinned transcriptome sync script][source-sync-transcriptome] from NCBI RefSeq records. The exact audited inputs are *E. coli* K-12 MG1655 `NC_000913.3` ([NCBI record][ncbi-ecoli]) and *S. cerevisiae* S288C chromosomes `NC_001133.9`, `NC_001134.8`, `NC_001135.5`, `NC_001136.10`, `NC_001137.3`, `NC_001138.5`, `NC_001139.9`, `NC_001140.6`, `NC_001141.2`, `NC_001142.9`, `NC_001143.9`, `NC_001144.5`, `NC_001145.3`, `NC_001146.8`, `NC_001147.6`, `NC_001148.4`, plus mitochondrial `NC_001224.1` ([NCBI S288C assembly][ncbi-yeast]). The script extracts annotated CDS by `locus_tag`; these are CDS references, not complete mature transcriptomes with UTRs.

### Host, payload, and backbone assumptions

- Bundled CDS reference sets are available for *E. coli* and yeast from the versioned NCBI accessions above.
- Human is deliberately unavailable end to end.
- GFP is the configured catalog payload on merged main, sourced as Registry part [BBa_E0040][registry-e0040].
- A reviewed custom coding sequence can be supplied; it is emitted verbatim because codon optimization is not implemented.
- The current parts table declares Registry records [BBa_J23119][registry-j23119], [BBa_K124002][registry-k124002], [BBa_B0015][registry-b0015], and [BBa_K1486025][registry-k1486025] as promoter/terminator sources; the exact sequences used are visible in the [commit-pinned plasmid source][source-plasmids].
- Catalog backbones and reviewed circular custom GenBank input are supported by the plasmid stage. The ten catalog backbones are the cited Registry pSB records listed in the bibliography.
- No verified first-party yeast backbone is bundled.

### Outputs

| User need | Current output | Important boundary |
|---|---|---|
| Compare candidates | Ranked and rejected `CandidateResult` records | Rank is relative to the current candidate set and provisional profile. |
| Understand scores | Raw/normalized values, direction, weight, hard-filter outcome | Several profile metrics may be absent or placeholders; missing values follow declared defaults. |
| Review failures | Warnings and stable rejection reasons | A failed filter is useful evidence, not a hidden row. |
| Build from accepted candidates | FASTA and GenBank artifacts | Export does not authorize synthesis or establish safety. |
| Reproduce bytes | Input checksum, resolved parameters, artifact SHA-256 | Checksums establish byte identity only. |
| Automate | Versioned request/result objects and HTTP API surfaces | Capability metadata currently over-advertises some class-level combinations; clients must still handle clean failures. |
| Produce a scientific report | **No implemented report on merged main** | `ReportBuilder` remains incomplete. |

CERNAL currently exports FASTA, GenBank, CSV, and JSON-shaped API records. It does not claim SBOL support or standards compliance beyond the formats actually implemented.

<!-- ASSET PLAN — ARTIFACT BUNDLE
Proposed filename: assets/software/cernal-artifact-bundle.svg
Alt text: "An annotated file tree groups candidates.csv and warnings for inspection, FASTA and GenBank files for build review, and parameters plus checksums for reproducibility. A missing scientific PDF is explicitly marked not implemented."
Caption: "Current artifact groups and the report output that is not yet implemented."
Production notes: Generate the tree from an actual judged-commit output directory; do not invent filenames; include a downloadable text version; remove runtime absolute paths.
-->

## Algorithms and assumptions

### Gene selection

`GeneSelector.select` deduplicates gene identifiers, applies absolute log2-separation bounds, uses the best available significance tier, applies optional directional abundance limits, can compute control/condition percentiles, evaluates trigger yield when transcript sequences are available, balances regulation direction, and returns at most the configured number of genes.

The stage-level provisional weights are separation 3.0, abundance 2.0, trigger yield 2.0, non-redundancy 1.5, and condition specificity 1.0. Condition-specificity atlas evidence is currently unmeasured because no producer supplies it. These numbers are design heuristics, not calibrated biological coefficients.

### Trigger selection and accessibility

`TriggerScorer` scans the supported footprints, removes motif-violating windows, and records structural/sequence evidence. Every transcript is profiled once, then windows slice the resulting profile. Candidates are compared within length buckets and allocated round-robin, with a cap of 50 candidates per gene.

The implemented evidence includes:

- mean marginal unpaired probability across a window;
- minimum per-base accessibility;
- window minimum free energy;
- GC content and AUG/stop positions;
- an 8-nucleotide seed joint-opening calculation;
- terminal-window opening free energy per nucleotide; and
- terminal-window mean marginal openness.

The current off-target fields do not represent a validated genome-wide screen. `OffTargetScanner` has no populated index in the merged pipeline.

### RNA folding

`FoldProfiler` wraps the local-opening algorithm published with [RNAplfold][rnaplfold-paper], while `FoldEngine` centralizes folding through the [ViennaRNA package][vienna-paper]. Provenance records should include the effective ViennaRNA/RNAplfold versions and settings. A shared tool instance reduces the risk that different stages silently use inconsistent temperatures or caches.

Predicted structures and opening values describe an equilibrium computational model for the supplied sequence/context. They do not model all kinetic, cellular, concentration, interaction, or expression effects.

### Single-input toehold construction

The implemented `ToeholdGate` follows the single-input architecture reported by [Green et al. (2014)][green-toehold-paper] and is described in source as a ViennaRNA-based port of an earlier NUPACK generator. The public file matching the named `prokaryotic_switch_generator.py` is available at a [commit-pinned project source][nupack-generator-source]. That repository exposes no license file, and GitHub reported no license metadata when checked on 28 September 2026; a closely related packaged implementation, [ToeGen][toegen-source], carries an [MIT license][toegen-license]. Because the audited CERNAL repository does not document which public copy supplied the reused code, the team must verify the exact origin and retain the correct copyright/license notice before publication. NUPACK `tube_design`, sequence optimization, and the generator’s ensemble-defect/concentration outputs were not ported; the current real pipeline uses the single-input CERNAL family only.

<!-- TODO (team): Confirm the exact reused generator repository/commit and copyright holder, then add the required license/attribution text to NOTICE and the official iGEM Attributions Form. Do not infer that the exact `prokaryotic_switch_generator.py` snapshot is MIT-licensed from the separate ToeGen package. -->

### Scoring and filtering

The `DEFAULT_V1` profile is explicitly provisional. It names nine metrics:

1. state separation;
2. trigger accessibility;
3. gate folding energy;
4. predicted leakage;
5. orthogonality;
6. GC content;
7. dynamic range;
8. predicted success rate; and
9. circuit complexity.

Not every metric is currently measured. Missing metrics follow the profile’s declared behavior, generally a worst-case default. The names `orthogonality` and `predicted_success_rate` must not be interpreted as calibrated specificity or success evidence.

Current hard filters require predicted leakage no greater than 0.85 and state separation at least 0.5. Tie-breakers use state separation and then predicted leakage. Units must remain visible: GC is percent from 0–100, probability-like values are fractions from 0–1, state separation is log2 fold, dynamic range is linear fold, and energy is kcal/mol.

<!-- ASSET PLAN — SCORE DECOMPOSITION
Proposed filename: assets/software/cernal-score-decomposition.svg
Alt text: "A candidate’s raw metrics pass through direction-aware normalization, provisional weights, hard filters, and deterministic tie-breakers to produce a relative rank. Unmeasured orthogonality and predicted-success fields are marked unavailable rather than shown as data."
Caption: "CERNAL exposes how a relative rank is assembled and which measurements are missing."
Production notes: Populate only with a test fixture from the judged commit; label raw units and normalization direction; use hatching plus text for missing values; include the underlying CSV/JSON beside the figure.
-->

### Plasmid construction

`PlasmidBuilder.build` assembles the host promoter, switch, payload, terminator, and optional backbone, then checks assembly-standard and motif constraints. `to_genbank` and `parse_custom_backbone` are the isolated Biopython-touching functions. No codon optimization occurs, and no complete human host-parts path exists.

</details>

## Installation and demo

### Requirements

- Python `>=3.13,<3.14`;
- [`uv`](https://docs.astral.sh/uv/);
- Node.js 22 or newer for the frontend;
- Git; and
- network access for the first dependency installation.

[`pyproject.toml`][source-pyproject] declares `viennarna>=2.7.2`, and the audited [`uv.lock`][source-uv-lock] resolves ViennaRNA `2.7.2` from PyPI. `./do install` runs `uv sync --extra dev`, so ViennaRNA is retrieved as part of the normal Python environment installation—**not** as a separate manual installation step. ViennaRNA remains separately licensed under its [upstream terms][vienna-license] and is not vendored or relicensed as CERNAL code. Frontend packages are installed from [`frontend/package-lock.json`][source-frontend-lock] by `./do install-frontend`.

### Local installation

Run these commands from the official CERNAL source checkout:

```bash
./do install
./do install-frontend
./do migrate
./do superuser
./do build-frontend
```

### Choose one engine for both processes

The web server and task worker are separate processes. They must receive the **same** `CERNAL_ENGINE` value or `/api/version` can describe one engine while queued jobs execute another.

For the real bounded scientific pipeline, run:

```bash
# Terminal 1 — web server
CERNAL_ENGINE=engine.client.LocalEngine ./do dev
```

```bash
# Terminal 2 — task worker
CERNAL_ENGINE=engine.client.LocalEngine ./do worker
```

For a deterministic simulated demonstration, replace `LocalEngine` with `MockEngine` in **both** terminals:

```bash
CERNAL_ENGINE=engine.client.MockEngine ./do dev
CERNAL_ENGINE=engine.client.MockEngine ./do worker
```

Run those two MockEngine commands in separate terminals. Without the worker, submitted runs remain queued. A MockEngine demonstration must say **simulated** in the UI, screenshot, video, and caption.

### Verify the API and result manifest agree

First record the active capability document:

```bash
curl --fail --silent http://127.0.0.1:8000/api/version > version.json
python3 -m json.tool version.json
```

Then complete a run and download its `run_manifest` artifact as `manifest.json`. Compare the version advertised by [`GET /api/version`][source-api-meta] with the version written from the actual `JobResult` into the [run manifest][source-results-services]:

```bash
python3 - <<'PY'
import json

version = json.load(open("version.json", encoding="utf-8"))
manifest = json.load(open("manifest.json", encoding="utf-8"))

expected_engine = "LocalEngine"
version_prefix = {"LocalEngine": "local-", "MockEngine": "mock-"}[expected_engine]
assert version["engine"] == expected_engine, version
assert manifest["engine_version"].startswith(version_prefix), manifest
assert version["engine_version"] == manifest["engine_version"], (version, manifest)
print(version["engine"], version["engine_version"], "matches manifest")
PY
```

For a simulated run, change `expected_engine` to `MockEngine`. The API identifies the configured engine class and version; the manifest’s version prefix identifies the engine family and its full `engine_version` must exactly match the API. Do not use a screenshot or artifact as judged evidence unless this comparison passes.

### Verify a checkout

```bash
./do check
./do lint
./do test
./do build-frontend
```

When the web server and worker are running with the same engine selection, `./do smoke` drives a browser flow. The final judging release should publish the exact commands, operating system/container details, dependency lockfiles, and expected fixture artifacts.

### Demo availability

**No public deployment URL was established by the audited repository evidence.** Deployment documentation is planning material and must not be treated as proof that a production service exists.

<!-- TODO (team): Add either (1) a verified iGEM-hosted/static demonstration path plus a separately linked live service, or (2) a clearly labelled “No public live service” statement. The judged wiki must retain a captioned recording, static screenshot walkthrough, example input, and expected artifact bundle even if an external service is unavailable. -->

<!-- ASSET PLAN — DEMO VIDEO
Proposed filename: video-universe/cernal-75-second-walkthrough.mp4
Alt text: Not applicable to video; provide captions and a full transcript.
Caption: "A release-pinned walkthrough from input selection to candidate and artifact review. Demo data and engine mode remain visible throughout."
Production notes: Host on iGEM Video Universe; 60–90 seconds; no autoplay audio; burned-in release/commit label; human-edited captions; transcript directly below the player; include a static fallback sequence; never use a fabricated successful result.
-->

## Validation and evidence

### What has been verified

| Evidence type | Verified behavior | Scope boundary |
|---|---|---|
| Direct `LocalEngine` regression path | A valid direct-RNA fixture completes with non-empty toehold candidates through the real current pipeline. | Software/computational behavior only; no wet-lab claim. |
| Differential-expression regression paths | Real bundled *E. coli* and yeast identifiers can reach accepted toehold candidates. Human fails cleanly. | Test fixtures and bundled references; not a claim of generalization to all datasets. |
| Candidate auditability | Accepted candidates are ranked contiguously; rejected candidates keep reasons and no misleading rank. | Ranking remains relative and uses a provisional profile. |
| Determinism | Repeated tested requests preserve candidate identity/rank/score/sequence fields. | Applies to the tested configuration, not every future dependency/platform. |
| Artifact integrity | Files exist and their SHA-256 values match `ArtifactRef`; candidate table row counts match candidate records. | Hashes prove identity, not biological validity. |
| Sequence export | FASTA is limited to accepted candidates; GenBank is produced per accepted candidate. The parse-back regression asserts circular topology and `len(record.features) == 4`—not four named feature types. | Does not prove synthesis, assembly, expression, or safety. |
| Engine/platform boundary | [`tests/test_boundary.py`][test-boundary] enforces the allowed dependency direction. | Architectural test, not scientific validation. |
| Web lifecycle | [`tests/e2e/test_full_workflow.py`][test-e2e] covers authentication, capability discovery, upload, queueing, candidate review, rejection reasons, download, annotation, export, and idempotency with simulated engine output. | It invokes `apps.analyses.tasks.run_analysis(run_id)` inline through the worker task function; it does **not** launch or prove a live qcluster worker. |

### What has not been verified

- No wet-lab validation was found for current candidates, scoring, leakage, dynamic range, specificity, or efficacy.
- No calibrated relationship has been established between rank and experimental success.
- No validated genome-wide off-target scan is implemented.
- No real hazard database/tool adapter is provisioned.
- No human end-to-end workflow is supported.
- No independent usability study or accessibility conformance audit was found.
- No production deployment, service-level objective, retention policy, or public-demo uptime was established by the audited evidence.

### Required evidence bundle for every wiki result

Before a result is shown as evidence, preserve:

- exact Git commit/tag and engine/schema/application versions;
- a captured `/api/version` document plus a downloaded result manifest whose `engine_version` matches it;
- original input bytes and SHA-256;
- input mode, host, gate, payload, and backbone;
- resolved constraints and scoring profile/overrides;
- seed and idempotency information where applicable;
- ViennaRNA/RNAplfold and reference-data versions;
- warnings and rejected candidates;
- result manifest and artifact checksums; and
- exact UI route, command, or API payload used to reproduce it.

`CandidateStore` supports audit-oriented records, but `snapshot` and `load_snapshot` remain unimplemented on merged main. Do not claim complete per-stage replayability.

<!-- ASSET PLAN — VALIDATION SUMMARY
Proposed filename: assets/software/cernal-validation-evidence.svg
Alt text: "A four-column evidence map separates software tests, analytical computations, user evidence, and wet-lab evidence. Software tests and analytical computations contain documented items; user evidence is limited; wet-lab evidence is marked not completed."
Caption: "Evidence types are separated so computational checks cannot be mistaken for experimental validation."
Production notes: Do not use a green-to-red color scale alone; print the labels Verified, Limited, and Not completed; link every verified item to a test, artifact, or Results/Engineering page.
-->

## Safety, security, and responsible use

### Intended-use boundary

CERNAL is research and design-support software. Its output is a computational hypothesis. It is not:

- clinical, diagnostic, or therapeutic advice;
- automated biosafety or biosecurity approval;
- authorization to synthesize or construct a sequence;
- evidence that a candidate is non-hazardous, specific, effective, or manufacturable; or
- a substitute for institutional, legal, ethical, host-context, assembly, and experimental review.

Users must independently review every candidate and follow the current [iGEM Safety and Security Requirements][igem-safety-requirements], [iGEM Safety Policies][igem-safety-policies], local institutional rules, and applicable law.

### Current merged-main safeguards and gaps

Merged main performs motif/restriction and structural checks during design and assembly. It does **not** contain a validated hazard database or a validated biological off-target screen. `build_tools` constructs `OffTargetScanner({})`; current off-target and segment-specificity fields are unmeasured placeholders, and the result includes warnings rather than pretending they are evidence.

The product also handles accounts and uploaded files. Any public deployment therefore needs explicit ownership for access control, retention, deletion, incident response, logs, backups, post-competition account handling, and restrictions on confidential or controlled data. Those operational policies were not established by the audited evidence.

### PR #35 is open and unmerged

[Pull request #35 — fail-closed output sequence release gate][pr-35] is **open, unmerged, and not part of current main**. Its head is `8347e8aeff0a255cb6a0931cc377008bc52a56dc` on `feat/output-sequence-safety-screening`.

The branch proposes:

- an offline-first local screening-adapter contract;
- fail-closed sequence-release decisions;
- audit manifests and signed review tokens; and
- withholding FASTA/GenBank while preserving non-sequence metadata when screening evidence is unavailable.

It does **not** provision or validate a real hazard database/tool adapter. Until such an adapter, evidence base, operating procedure, and validation are established, PR #35 is a release-policy prototype that holds output—not a hazard-identification service. Screenshots or prose must label it **UNMERGED PROTOTYPE**.

### Before any build or synthesis decision

1. Confirm the exact input, parameters, engine version, warnings, and artifact checksum.
2. Review whether the organism, payload, backbone, and biological context are actually supported.
3. Treat all current specificity/off-target fields as unvalidated unless separately supported by reviewed evidence.
4. Perform independent biological, biosafety, biosecurity, ethics, and assembly review.
5. Obtain all required iGEM, institutional, national, supplier, and other approvals before beginning regulated work.
6. Design and document appropriate experimental controls; do not infer efficacy from rank or visualization.
7. Do not upload restricted, confidential, patient-derived, or otherwise sensitive data without an approved lawful basis and deployment policy.

<!-- ASSET PLAN — SAFETY BOUNDARY
Proposed filename: assets/software/cernal-safety-boundary.svg
Alt text: "Current main performs input, motif, structural, and assembly checks, but validated biological off-target and hazard screening are absent. A separate box labelled PR #35 — OPEN, UNMERGED PROTOTYPE shows a fail-closed sequence-release policy without a provisioned database."
Caption: "Current safeguards, missing biological screens, and the exact boundary of unmerged PR #35."
Production notes: Put OPEN and UNMERGED inside the figure; do not use a shield/checkmark that implies safety certification; link the PR box to the exact pull request and commit.
-->

## Accessibility and user support

### Evidence on merged main

Inspected frontend routes include labelled form fields, `role="alert"` and `role="status"` regions, image `alt` attributes, and visible `focus-visible` rings in several controls. These are useful implementation details, but they do not establish comprehensive accessibility or WCAG conformance.

### Uncommitted FAQ/help work is not shipped

An evidence audit observed uncommitted FAQ, usage-guide, help-route, component, and browser-test changes, including proposed semantic controls, keyboard behavior, focus styling, landmarks, headings, labelled search, table captions, stable IDs, an `aria-live` result count, and named mobile controls.

Because no commit or pull request provides a stable judge-facing record, this page treats that material only as editorial/accessibility work in progress. It is not current-main evidence and must not be shown as shipped until reviewed and merged.

### Publication accessibility checklist

The final wiki implementation should target WCAG 2.2 AA as a practical baseline without claiming conformance until it is tested. At minimum:

- keep one page-level H1 and a logical heading hierarchy;
- add a skip link and keyboard-visible focus;
- make every interactive control reachable and operable without a pointer;
- provide meaningful alt text for informative images and empty alt text for decoration;
- provide nearby tables/text alternatives for complex figures;
- caption videos and publish transcripts;
- avoid autoplay audio and respect reduced-motion settings;
- meet text/control contrast requirements;
- never use color alone for status, ranking, warnings, or data series;
- make tables responsive while preserving header associations;
- verify 200% zoom, narrow-width reflow, keyboard order, visible errors, and screen-reader names; and
- test with users outside the implementation team where possible.

<!-- ASSET PLAN — ACCESSIBLE SCREENSHOT ANNOTATION
Proposed filename: assets/software/cernal-accessibility-callouts.webp
Alt text: "A CERNAL form screenshot annotated with labelled fields, keyboard focus, error summary, status announcement, and descriptive button names."
Caption: "Examples of semantic and keyboard-visible behavior to verify before the wiki freeze."
Production notes: Capture only after the relevant behavior is merged; annotations must identify real DOM behavior, not design intentions; publish a text checklist beside the image.
-->

## Reuse, contribution, and continuity

### What a future team can reuse now

A future team can inspect and extend:

- the versioned `JobRequest`, `EngineCapabilities`, `CandidateResult`, `ArtifactRef`, and `JobResult` contracts;
- the framework-free scientific-engine boundary;
- the direct and scoped differential-expression paths;
- trigger/folding/toehold/scoring/plasmid stages;
- regression fixtures and architectural boundary tests;
- API/web product patterns for asynchronous scientific jobs; and
- provenance patterns for candidate, warning, rejection, and artifact records.

The development source currently lives in the [CERNAL GitHub repository][cernal-github]. For iGEM evaluation, the official iGEM Software Tools repository must become the authoritative competition source.

### License and dependency boundary

CERNAL code is licensed under Apache-2.0. ViennaRNA `2.7.2` is a separately licensed dependency resolved in [`uv.lock`][source-uv-lock] and retrieved by `./do install`; it is not manually installed as an extra standard step, vendored in the CERNAL repository, or covered by CERNAL’s Apache-2.0 license. The upstream [ViennaRNA license][vienna-license] permits use and modification under conditions that are not represented as an OSI-approved license here. The final publication must also verify and state the applicable Biopython and all other third-party notices accurately.

The reused toehold-generator provenance also needs closure: cite the exact [generator source][nupack-generator-source], confirm its applicable copyright/license, and do not substitute the separate [ToeGen MIT license][toegen-license] unless the team verifies that ToeGen is the actual source of the reused code.

Do not describe the entire runnable stack as “fully open source” without this dependency boundary. Preserve `LICENSE`, `NOTICE`, lockfiles, and a generated third-party license report in the official repository.

### Contributor handoff

A useful continuation package should include:

- the official iGEM repository and exact judging tag/commit;
- an OSI-approved project license and third-party notices;
- clean-environment installation and verification commands;
- the test-fixture input and expected artifact manifest;
- system requirements and measured runtime/memory for the judged example;
- API and Python-client status, including unsupported combinations;
- architecture and engine-boundary documentation;
- test commands and contribution conventions;
- changelog/migration notes;
- issue, security, and contact routes; and
- a completed `CITATION.cff` with individual citation authors.

<!-- TODO (team): Add official repository URL, judging tag, release date, archive/DOI if available, measured example runtime/memory, issue URL, security contact, maintainer/contact after the competition, and support expectations. -->

<!-- ASSET PLAN — REUSE CARD
Proposed filename: assets/software/cernal-reuse-map.svg
Alt text: "A future team can start from the versioned contract, replace or extend a scientific stage behind the engine boundary, run regression tests, and produce the same candidate and artifact record types."
Caption: "Reuse path for extending CERNAL without coupling scientific stages to the web framework."
Production notes: Link each step to a source directory or documentation page; include the Apache-2.0 label and a separate ViennaRNA dependency/licensing note; do not imply that unfinished stages are reusable production modules.
-->

## Limitations and future work

### Limitations visible to users now

| Limitation | User impact | Current mitigation | Evidence needed before a stronger claim |
|---|---|---|---|
| `MockEngine` is the default | A complete-looking run may be simulated | Persistent simulated label and explicit engine selection | Verified public demo configuration and screenshot audit |
| Real pipeline is single-gene/single-input toehold only | Users cannot build production multi-input logic | Capability-driven selection and clean failure | Implemented circuit enumeration plus tests and biological validation |
| Human path is unavailable | Human datasets cannot run end to end | Fail cleanly; expose supported hosts | Curated transcript references, host parts, privacy review, tests, validation |
| No validated off-target scanner | Specificity cannot be claimed | Warnings and unmeasured placeholders | Reference index, algorithm validation, benchmarks, reviewed thresholds |
| No provisioned hazard screen | “Safe” output cannot be claimed | Independent review; PR #35 proposes fail-closed withholding | Validated local adapter/database, governance, audit procedure, test cases |
| Provisional scoring profile | Rank is not a calibrated outcome probability | Show components, units, directions, and missing values | Pre-specified benchmark and wet-lab comparison with uncertainty |
| Incomplete codon/translation methods | Payload manufacturability/expression is not optimized | Emit reviewed payload verbatim | Implemented methods, host-specific validation, explicit output contract |
| No verified bundled yeast backbone | Yeast assembly choices require extra work | Reviewed custom circular GenBank or permitted omission | First-party backbone provenance and assembly validation |
| File-format mismatch | Some uploads validate but fail scientific parsing | Prefer normalized UTF-8 CSV/TSV; show clear errors | One canonical normalization layer plus contract tests |
| Capability metadata over-advertises combinations | UI/API may expose combinations that later fail | Treat `/api/version` as necessary but not sufficient; preserve clean errors | Mode × host × gate × payload × reference capability matrix generated from executable probes |
| No scientific PDF/structure renderer | Users must inspect tables and sequence artifacts directly | Export current machine-readable artifacts | Implemented renderer, tests, accessible alternatives, provenance |
| No complete stage snapshot/replay | Full per-stage replay cannot be claimed | Preserve request/result/artifact checksums and parameters | Implement and test `CandidateStore.snapshot/load_snapshot` |
| No wet-lab evidence | Biological performance is unknown | Label outputs computational and require experiments | Pre-registered experiments, controls, raw data, analysis, negative results |
| No proven production deployment | Availability, privacy, retention, and operations are unknown | Local reproducible operation; archive the wiki record | Deployment verification, owner, policies, monitoring, incident process |
| No comprehensive accessibility audit | Some users may encounter barriers | Semantic implementation checklist and testing plan | Keyboard, zoom, contrast, screen-reader, caption, user testing evidence |

### Work outside merged main

| Work surface | Exact state | What exists | How the wiki may describe it |
|---|---|---|---|
| [PR #35][pr-35] | Open and unmerged on 28 September 2026; head `8347e8aeff0a255cb6a0931cc377008bc52a56dc` | Fail-closed release policy, local-adapter contract, audit manifests, sequence withholding | **Under review; no real adapter/database provisioned.** |
| [PR #32][pr-32] | Open and unmerged on 28 September 2026; head `2e8af637c6a3509c27d2d41dbe7bfad25477600b` | Experimental eukaryotic/trailing layout, payload-aware work, notebooks/report generation, AND-fusion research | **Experimental pull request only; not current product support.** |
| [PR #15][pr-15] | Open with a conflicting/dirty merge state on 28 September 2026; head `04bbe394fe0307a4c40da8d090ed9eeba5896f17` | Alternative parallel toehold implementation | Do not feature as a capability; resolve or close independently. |

Branch-only analyses and uncommitted work without a stable pull request or commit link are intentionally omitted from this judge-facing table; they are not evidence for merged capabilities.

Future work should be ordered by evidence and risk: first make capability reporting executable and exact; resolve input normalization; finish and validate safety/off-target boundaries; calibrate or replace provisional scoring; complete accessible user support; then expand hosts, gates, reporting, and deployment. New modalities should not be presented as production features merely because a class, notebook, or pull request exists.

## Attribution, licensing, and AI disclosure TODOs

### People and institutions

The official 2026 Attributions Form—not a custom prose page—is the authoritative record of who did what. Before publication, the team must supply and verify:

- individual authors for architecture/backend/API, scientific engine, frontend, scientific direction, validation, documentation, visual design, and wiki implementation;
- instructors, advisors, PIs, and outside contributors with their exact contributions;
- former members or contributors outside the frozen roster in the correct external-contribution fields;
- the timing of major project phases;
- use or non-use of iGEM and partner offers; and
- the owner of public-deployment privacy, retention, deletion, and post-competition account handling.

<!-- TODO (team): Replace collective authorship in CITATION.cff with individual citation authors and add the official repository-code URL. -->
<!-- TODO (team): Add example-dataset accession/publication or consistently label the data synthetic/test-only. -->
<!-- TODO (team): Record logo origin/license, permission for team photographs, and source/license for every icon, font, image, diagram, and video asset. -->
<!-- TODO (team): Credit the Lovable design origin and preserved design reference accurately. AI systems are tools, not team members. -->

### Responsible AI disclosure for this draft

This document was prepared with drafting assistance from **Hermes Agent by Nous Research using OpenAI Codex `gpt-5.6-sol` on 28 September 2026**, based on the evidence sources listed below. This statement documents the drafting event; it does not make model-authored scientific narrative acceptable for the final competition submission.

Before publication, human team members must:

1. review every sentence against primary code, tests, artifacts, official iGEM rules, and cited literature;
2. rewrite and take responsibility for the substantive scientific/project narrative in accordance with the 2026 iGEM responsible-AI boundary;
3. verify every link, number, caption, alt text, and capability status;
4. identify all other AI systems and versions used in coding, research, translation, design, administration, or media work;
5. describe the purpose and scope of each use; and
6. document human review, fact-checking, code review, testing, and scientific validation in the official Attributions Form and visible wiki disclosure.

<!-- TODO (team): Replace this draft disclosure with the team-approved complete AI-use record. Do not delete the drafting event if any of this draft is retained. -->

### Wiki and software licensing

- Team-authored wiki text, figures, and photographs must be released under CC BY 4.0 with the required footer link.
- CERNAL source code is Apache-2.0 and must retain `LICENSE` and `NOTICE`.
- Third-party assets require licenses that permit the intended reuse, redistribution, and modification, with inline credit.
- ViennaRNA must be described as a separately licensed dependency retrieved by the environment installer, with its actual upstream redistribution conditions—not as manually installed CERNAL code.
- Biopython and all other dependencies require accurate notice/licensing review.
- Decorative AI-generated images, if any, require model credit and must not be used as scientific evidence.

## Judge evidence map

| Judge question | Fastest evidence on this page | Deeper record to link before freeze |
|---|---|---|
| What problem does CERNAL address? | [The design problem](#the-design-problem) | Project Description and Human Practices TODO links |
| Who is the user and what decision do they make? | [One user, one decision, one traceable run](#one-user-one-decision-one-traceable-run) | User interviews/testing TODO links |
| What works now? | [Current capability matrix](#current-capability-matrix) | Judged-commit release notes and `/api/version` artifact |
| Can I follow one workflow? | [Worked workflow](#worked-workflow-a-real-test-fixture-not-a-biological-result) | Captioned video and downloadable fixture bundle |
| Is the system understandable? | [Architecture](#architecture-from-click-to-artifact) and [Algorithms](#algorithms-and-assumptions) | Model and Engineering page anchors |
| Was it validated? | [Validation and evidence](#validation-and-evidence) | Results page, test logs, benchmark artifacts, wet-lab status |
| Is it safe and responsible? | [Safety, security, and responsible use](#safety-security-and-responsible-use) | Safety and Security page plus official Safety Form |
| Can another team run and extend it? | [Installation and demo](#installation-and-demo) and [Reuse](#reuse-contribution-and-continuity) | Official iGEM repository, judging tag, release/archive |
| Are limitations visible? | [Limitations and future work](#limitations-and-future-work) | Roadmap, issues, open PRs, engineering cycles |
| Are contributions credited? | [Attribution and AI disclosure TODOs](#attribution-licensing-and-ai-disclosure-todos) | Official Attributions Form and completed `CITATION.cff` |

<!-- TODO (team): Replace all “TODO links” with canonical lowercase 2026 wiki paths, including /description, /engineering, /model, /results, /safety-and-security, /contribution, /human-practices, and dated notebook anchors where applicable. -->

<details>
<summary><strong>Optional deep dive: media and asset production plan</strong></summary>

## Media and asset production plan

All substantive wiki content must remain on iGEM infrastructure. Images/documents/fonts belong in the iGEM CDN workflow; video/audio belong on iGEM Video Universe. External source, literature, and live-service links may supplement the record, but no external runtime dependency or embed may be required to understand the page.

| ID | Proposed asset | Format | Evidence/status rule | Accessibility and caption requirement |
|---|---|---|---|---|
| M1 | `assets/software/cernal-hero-pipeline.svg` | SVG + PNG fallback | Merged-main capabilities only | One-sentence alt; legible at mobile width; caption states computational boundary |
| M2 | `assets/software/cernal-before-after-workflow.svg` | SVG | Team-authored comparison, no invented timings | Same stage labels in both lanes; no color-only meaning |
| M3 | `video-universe/cernal-75-second-walkthrough.mp4` | MP4/WebM + VTT + transcript | Pin commit, fixture, run ID, and engine mode | Captions, transcript, no autoplay, static fallback |
| M4 | `assets/software/cernal-five-stage-workflow.svg` | SVG | Implemented stages solid; unavailable/unmerged stages explicit | Nearby text duplicate; linked stage labels |
| M5 | `assets/software/example-01-direct-rna-input.webp` | WebP/PNG | Current-main test fixture; not biological evidence | Visible test-fixture label; descriptive alt and takeaway caption |
| M6 | `assets/software/example-02-candidate-review.webp` | WebP/PNG | LocalEngine result only; no MockEngine substitution | Accepted/rejected distinction in text and symbols |
| M7 | `assets/software/example-03-artifacts-and-checksums.webp` | WebP/PNG | Actual current-main artifact list | Full checksums available as text; no local paths/tokens |
| M8 | `assets/software/cernal-trigger-window-method.svg` | SVG | Exact implemented footprints and metric semantics | Marginal vs joint measurements distinguished in words/patterns |
| M9 | `assets/software/cernal-toehold-anatomy.svg` | SVG | Team drawing from implemented source | Direction labels; paired regions not color-only; computational caption |
| M10 | `assets/software/cernal-user-data-flow.svg` | SVG | Product architecture and trust boundaries | Logical reading order; source links; plain-text alternative |
| M11 | `assets/software/cernal-engine-pipeline.svg` | SVG | Grey/dotted incomplete stages | Explicit Not implemented/Unmerged text |
| M12 | `assets/software/cernal-score-decomposition.svg` | SVG + CSV/JSON | Populate from test fixture only | Units/direction/missing values visible; accessible data alternative |
| M13 | `assets/software/cernal-validation-evidence.svg` | SVG + HTML table | Separate software, analytical, user, and wet-lab evidence | Status words printed; every item links to evidence |
| M14 | `assets/software/cernal-safety-boundary.svg` | SVG | PR #35 labelled open/unmerged; no safety certification symbol | Text equivalent and exact PR/commit link |
| M15 | `assets/software/cernal-artifact-bundle.svg` | SVG + text tree | Generate from actual judged-release bundle | File roles explained; missing PDF marked absent |
| M16 | `assets/software/cernal-reuse-map.svg` | SVG | Current interfaces only | Source paths as link text; license boundary visible |
| M17 | `assets/software/cernal-accessibility-callouts.webp` | WebP/PNG | Capture only after behavior is merged | Text checklist beside image; callouts describe real behavior |
| M18 | `assets/software/cernal-capability-matrix-export.csv` | CSV | Generated from final visible matrix | Machine-readable alternative; version/commit columns |

### Screenshot and figure rules

- Capture every screenshot against one pinned judging release and record commit/tag, viewport, dataset or fixture, engine mode, and run ID.
- Remove personal data, secrets, tokens, local paths, and non-reproducible timestamps.
- Keep UI text readable at page width; prefer focused crops over full-browser screenshots.
- Put **SIMULATED** inside every MockEngine image and **UNMERGED PROTOTYPE** inside every PR #35 image.
- Do not stage UI states or scientific results the software cannot produce.
- Label mockups **CONCEPT — NOT IMPLEMENTED**.
- For every scientific plot, state commit, input, method, units, sample size, and whether values are observed, simulated, or predicted.
- Make each caption answer “What should the reader notice?” rather than repeat the alt text.
- Credit every third-party source and license inline; prefer team-authored diagrams derived from primary code and data.

</details>

## References and source notes

### Official iGEM requirements and design references

1. [Official iGEM 2026 Team Wiki Requirements][igem-wiki-requirements] — hosting/runtime constraints, CI/CD build, licensing, fixed judging paths, scientific integrity, responsible AI, and repository footer link.
2. [Official iGEM 2026 Team Wiki Recommendations][igem-wiki-recommendations] — content-first design, honest iteration, compressed media, descriptive commits, and early build testing.
3. [Official iGEM 2026 Project Software Requirements][igem-software-requirements] — official software repository, README, OSI license, reproducible instructions, pinned dependencies, repository size, and AI-software disclosures.
4. [Official iGEM 2026 Medal Criteria][igem-medals] and [Special Awards][igem-special-awards] — 2026 judging structure and award eligibility.
5. [Official iGEM 2026 Attributions Requirements][igem-attributions] — standardized attribution record and AI-use disclosure.
6. [Official iGEM Safety and Security Requirements][igem-safety-requirements] and [Safety Policies][igem-safety-policies].
7. [WCAG 2.2][wcag-22] — practical accessibility baseline proposed for implementation/testing; no conformance claim is made here.
8. [TAU-Israel 2025 Software page][tau-2025-software] — studied for judge-first navigation, audience/workflow/FAQ structure, and explicit limitations; no prose copied.
9. [Munich 2025 Software page][munich-2025-software], [Marburg 2025 Software page][marburg-2025-software], [Vilnius-Lithuania 2024 Software page][vilnius-2024-software], and [Fudan 2023 Software page][fudan-2023-software] — studied for workflow-first explanation, architecture, validation, screenshots, installation, and reuse patterns; no prose copied.

### Scientific methods, reused software, reference data, and parts

- **Original toehold-switch method:** Green, Silver, Collins, and Yin, “Toehold Switches: De-Novo-Designed Regulators of Gene Expression,” *Cell* 159(4), 925–939 (2014), [doi:10.1016/j.cell.2014.10.002][green-toehold-paper].
- **ViennaRNA:** Lorenz *et al.*, “ViennaRNA Package 2.0,” *Algorithms for Molecular Biology* 6 (2011), [doi:10.1186/1748-7188-6-26][vienna-paper]. The installed `2.7.2` dependency remains subject to the [upstream ViennaRNA license][vienna-license].
- **RNAplfold:** Bernhart, Hofacker, and Stadler, “Local RNA base pairing probabilities in large sequences,” *Bioinformatics* 22(5), 614–615 (2006), [doi:10.1093/bioinformatics/btk014][rnaplfold-paper].
- **Reused NUPACK-generator provenance:** the public file matching the source comment’s `prokaryotic_switch_generator.py` is the [commit-pinned generator source][nupack-generator-source]. The cited repository has no license file, and GitHub reported no license metadata when checked on 28 September 2026. The closely related [ToeGen source][toegen-source] has a separate [MIT license][toegen-license]; this is evidence for ToeGen only, not proof of the exact generator snapshot’s license.
- **Bundled CDS references:** NCBI RefSeq [`NC_000913.3`][ncbi-ecoli] for *E. coli* K-12 MG1655 and the [S288C reference assembly][ncbi-yeast] whose exact chromosome/mitochondrial accession versions are enumerated in the [sync script][source-sync-transcriptome].
- **Registry expression parts:** [BBa_J23119][registry-j23119], [BBa_K124002][registry-k124002], [BBa_B0015][registry-b0015], [BBa_K1486025][registry-k1486025], and GFP payload [BBa_E0040][registry-e0040].
- **Registry backbones:** [pSB1A3][registry-psb1a3], [pSB1C3][registry-psb1c3], [pSB1K3][registry-psb1k3], [pSB1T3][registry-psb1t3], [pSB1AK3][registry-psb1ak3], [pSB1AT3][registry-psb1at3], [pSB3C5][registry-psb3c5], [pSB3K3][registry-psb3k3], [pSB3T5][registry-psb3t5], and [pSB4C5][registry-psb4c5]. The [commit-pinned plasmid table][source-plasmids] is the exact record of sequences used by the audited code.

### CERNAL source-of-truth notes

- **Audited merged baseline:** [`417f8385725a99f2d7d4bc835eeedeb5903d399f`][cernal-audited-commit] on `main`.
- **Current development repository:** [CERNAL on GitHub][cernal-github]. The final iGEM Software Tools repository URL remains a team TODO.
- **Installation behavior:** [`do`][source-do], [`pyproject.toml`][source-pyproject], and [`uv.lock`][source-uv-lock] at the audited commit.
- **Primary request/result boundary:** [`src/engine/contract.py`][source-contract].
- **Engine selection and pipeline:** [`src/engine/client.py`][source-client] and [`src/engine/pipeline.py`][source-pipeline].
- **Algorithms:** [`genes.py`][source-genes], [`triggers.py`][source-triggers], [`folding.py`][source-folding-stage], [`switches.py`][source-switches], [`plasmids.py`][source-plasmids], [`toehold.py`][source-toehold], and [`src/engine/scoring/`][source-scoring].
- **Regression evidence:** [`tests/engine/test_pipeline.py`][test-pipeline], [`tests/test_boundary.py`][test-boundary], and [`tests/e2e/test_full_workflow.py`][test-e2e].
- **Open pull requests:** [PR #15][pr-15], [PR #32][pr-32], and [PR #35][pr-35], with status verified on 28 September 2026.
- **Evidence precedence:** claims phrased as “CERNAL does” refer only to the audited merged commit. Open pull requests and uncommitted work are labelled separately and are not merged-product evidence.

[igem-wiki-requirements]: https://teams.igem.org/go/deliverables/wiki/requirements
[igem-wiki-recommendations]: https://teams.igem.org/go/deliverables/wiki/recommendations
[igem-software-requirements]: https://teams.igem.org/go/deliverables/software/requirements
[igem-medals]: https://competition.igem.org/judging/awards/medals
[igem-special-awards]: https://competition.igem.org/judging/awards/special
[igem-attributions]: https://teams.igem.org/go/deliverables/attributions/requirements
[igem-safety-requirements]: https://teams.igem.org/go/safety/requirements
[igem-safety-policies]: https://responsibility.igem.org/safety-policies
[wcag-22]: https://www.w3.org/TR/WCAG22/
[tau-2025-software]: https://2025.igem.wiki/tau-israel/software
[munich-2025-software]: https://2025.igem.wiki/munich/software
[marburg-2025-software]: https://2025.igem.wiki/marburg/software
[vilnius-2024-software]: https://2024.igem.wiki/vilnius-lithuania/software
[fudan-2023-software]: https://2023.igem.wiki/fudan/software
[cernal-github]: https://github.com/zivbental/cernal_software
[cernal-audited-commit]: https://github.com/zivbental/cernal_software/tree/417f8385725a99f2d7d4bc835eeedeb5903d399f
[source-do]: https://github.com/zivbental/cernal_software/blob/417f8385725a99f2d7d4bc835eeedeb5903d399f/do
[source-pyproject]: https://github.com/zivbental/cernal_software/blob/417f8385725a99f2d7d4bc835eeedeb5903d399f/pyproject.toml
[source-uv-lock]: https://github.com/zivbental/cernal_software/blob/417f8385725a99f2d7d4bc835eeedeb5903d399f/uv.lock#L458-L465
[source-frontend]: https://github.com/zivbental/cernal_software/tree/417f8385725a99f2d7d4bc835eeedeb5903d399f/frontend
[source-frontend-lock]: https://github.com/zivbental/cernal_software/blob/417f8385725a99f2d7d4bc835eeedeb5903d399f/frontend/package-lock.json
[source-api]: https://github.com/zivbental/cernal_software/tree/417f8385725a99f2d7d4bc835eeedeb5903d399f/src/api
[source-apps]: https://github.com/zivbental/cernal_software/tree/417f8385725a99f2d7d4bc835eeedeb5903d399f/src/apps
[source-tasks]: https://github.com/zivbental/cernal_software/blob/417f8385725a99f2d7d4bc835eeedeb5903d399f/src/apps/analyses/tasks.py
[source-analysis-services]: https://github.com/zivbental/cernal_software/blob/417f8385725a99f2d7d4bc835eeedeb5903d399f/src/apps/analyses/services.py
[source-api-meta]: https://github.com/zivbental/cernal_software/blob/417f8385725a99f2d7d4bc835eeedeb5903d399f/src/api/routers/meta.py#L27-L42
[source-results-services]: https://github.com/zivbental/cernal_software/blob/417f8385725a99f2d7d4bc835eeedeb5903d399f/src/apps/results/services.py#L256-L284
[source-contract]: https://github.com/zivbental/cernal_software/blob/417f8385725a99f2d7d4bc835eeedeb5903d399f/src/engine/contract.py
[source-client]: https://github.com/zivbental/cernal_software/blob/417f8385725a99f2d7d4bc835eeedeb5903d399f/src/engine/client.py#L170-L225
[source-pipeline]: https://github.com/zivbental/cernal_software/blob/417f8385725a99f2d7d4bc835eeedeb5903d399f/src/engine/pipeline.py
[source-engine]: https://github.com/zivbental/cernal_software/tree/417f8385725a99f2d7d4bc835eeedeb5903d399f/src/engine
[source-genes]: https://github.com/zivbental/cernal_software/blob/417f8385725a99f2d7d4bc835eeedeb5903d399f/src/engine/stages/genes.py
[source-triggers]: https://github.com/zivbental/cernal_software/blob/417f8385725a99f2d7d4bc835eeedeb5903d399f/src/engine/stages/triggers.py
[source-folding-stage]: https://github.com/zivbental/cernal_software/blob/417f8385725a99f2d7d4bc835eeedeb5903d399f/src/engine/stages/folding.py
[source-switches]: https://github.com/zivbental/cernal_software/blob/417f8385725a99f2d7d4bc835eeedeb5903d399f/src/engine/stages/switches.py
[source-plasmids]: https://github.com/zivbental/cernal_software/blob/417f8385725a99f2d7d4bc835eeedeb5903d399f/src/engine/stages/plasmids.py#L56-L209
[source-toehold]: https://github.com/zivbental/cernal_software/blob/417f8385725a99f2d7d4bc835eeedeb5903d399f/src/engine/gates/toehold.py#L1-L151
[source-scoring]: https://github.com/zivbental/cernal_software/tree/417f8385725a99f2d7d4bc835eeedeb5903d399f/src/engine/scoring
[source-sync-transcriptome]: https://github.com/zivbental/cernal_software/blob/417f8385725a99f2d7d4bc835eeedeb5903d399f/tools/sync_transcriptome.py#L45-L80
[test-pipeline]: https://github.com/zivbental/cernal_software/blob/417f8385725a99f2d7d4bc835eeedeb5903d399f/tests/engine/test_pipeline.py
[test-boundary]: https://github.com/zivbental/cernal_software/blob/417f8385725a99f2d7d4bc835eeedeb5903d399f/tests/test_boundary.py
[test-e2e]: https://github.com/zivbental/cernal_software/blob/417f8385725a99f2d7d4bc835eeedeb5903d399f/tests/e2e/test_full_workflow.py#L1-L93
[green-toehold-paper]: https://doi.org/10.1016/j.cell.2014.10.002
[vienna-paper]: https://doi.org/10.1186/1748-7188-6-26
[rnaplfold-paper]: https://doi.org/10.1093/bioinformatics/btk014
[vienna-license]: https://github.com/ViennaRNA/ViennaRNA/blob/v2.7.2/COPYING
[nupack-generator-source]: https://github.com/Talshem/software/blob/c5e327a49324e6e6010a4972c71915ec4e6b75e8/tool/prokaryotic_switch_generator.py
[toegen-source]: https://github.com/Orezbm/toegen/blob/b4983ca1da03c752fe88626f30a4162f3a0eaf80/toegen/switch_generator.py
[toegen-license]: https://github.com/Orezbm/toegen/blob/b4983ca1da03c752fe88626f30a4162f3a0eaf80/LICENSE.md
[ncbi-ecoli]: https://www.ncbi.nlm.nih.gov/nuccore/NC_000913.3
[ncbi-yeast]: https://www.ncbi.nlm.nih.gov/datasets/genome/GCF_000146045.2/
[registry-j23119]: https://registry.igem.org/parts/bba-j23119
[registry-k124002]: https://registry.igem.org/parts/bba-k124002
[registry-b0015]: https://registry.igem.org/parts/BBa_B0015
[registry-k1486025]: https://registry.igem.org/parts/bba-k1486025
[registry-e0040]: https://registry.igem.org/parts/BBa_E0040
[registry-psb1a3]: https://registry.igem.org/parts/psb1a3
[registry-psb1c3]: https://registry.igem.org/parts/psb1c3
[registry-psb1k3]: https://registry.igem.org/parts/psb1k3
[registry-psb1t3]: https://registry.igem.org/parts/psb1t3
[registry-psb1ak3]: https://registry.igem.org/parts/psb1ak3
[registry-psb1at3]: https://registry.igem.org/parts/psb1at3
[registry-psb3c5]: https://registry.igem.org/parts/psb3c5
[registry-psb3k3]: https://registry.igem.org/parts/psb3k3
[registry-psb3t5]: https://registry.igem.org/parts/psb3t5
[registry-psb4c5]: https://registry.igem.org/parts/psb4c5
[pr-15]: https://github.com/zivbental/cernal_software/pull/15
[pr-32]: https://github.com/zivbental/cernal_software/pull/32
[pr-35]: https://github.com/zivbental/cernal_software/pull/35
