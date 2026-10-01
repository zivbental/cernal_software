# Gate-agnostic RNA off-target analysis

Status: revised proposal for `ziv/global-rna-off-target-scanner`; implementation is gated by the feasibility spike in Section 4

## 1. Scope

CERNAL should provide one reusable RNA–RNA interaction-search engine that accepts any RNA query sequence and any declared RNA reference collection. The engine returns candidate interactions and the evidence behind them. It does not predict translation, leakage, protein output, or a universal gate-success probability.

Two biological questions use the same interaction engine but remain distinct analyses:

- **Cross-activation candidate discovery:** which non-cognate RNAs could bind a gate recognition region?
- **Trigger-sequestration candidate discovery:** which RNAs could bind the intended trigger and reduce its free concentration?

The engine must not claim that binding necessarily activates a gate or materially sequesters a trigger. Those interpretations require gate architecture, concentration, localization, and experimental context and therefore belong to gate or circuit integrations.

Out of scope:

- translation-initiation or expression prediction;
- gate leakage or dynamic-range prediction;
- a calibrated probability of biological failure;
- CRISPR spacer/genomic off-target analysis;
- organism-specific assumptions inside the search primitive.

## 2. What is wrong with the current interface

The current `src/engine/stages/off_target.py` is a stub: every non-empty search raises `NotImplementedError`. More importantly, its documented trigger-sponging orientation is incorrect.

Let `T` be a trigger RNA in its physical 5′→3′ orientation and `B = reverse_complement(T)` be a toehold gate's recognition region.

- An RNA resembling `T` can bind `B`; it is a **cross-activation candidate**.
- An RNA complementary to `T` can bind `T`; it is a **sequestration candidate**.

The current `scan_trigger(T)` documentation proposes finding copies of `T` and calling them trigger sponges. That conflates the two failure modes. A global engine should instead search for antiparallel RNA–RNA interactions and never require callers to manually reverse-complement sequences to satisfy an index convention.

Other current limitations:

- `Hit` lacks end coordinates, aligned sequence, pairing pattern, G–U pairs, bulges, energy components, strand semantics, and reference provenance.
- `OffTargetReport.penalty == 0.0` can mean either “not measured” or “measured and clean.”
- `scan_trigger` cannot identify the intended source interval because it receives only a sequence.
- The bundled “transcriptomes” are CDS-only, one record per gene, and therefore omit UTR and isoform interactions.
- `TriggerScorer` calls the scanner inside dense sliding-window generation. Launching a transcriptome-wide biophysical search for every surviving window would be prohibitively wasteful.
- `SwitchValidator` receives an `OffTargetScanner` but never calls it.

## 3. The global primitive

The reusable primitive is conceptually:

```text
scan_interactions(
    query_molecule,
    allowed_interaction_region,
    reference,
    search_profile,
) -> InteractionAnalysis
```

It answers only:

> Which segments in this declared RNA reference can form a modeled antiparallel interaction with this supplied RNA query, and what evidence supports each candidate?

### Inputs

- Query ID, biological role, and the **complete molecular RNA context** in its actual 5′→3′ orientation.
- One 0-based half-open region within that molecule in which intermolecular pairing is allowed. The whole molecule is the default only when the whole molecule is genuinely interaction-competent.
- Optional source record ID and 0-based half-open source interval.
- Reference FASTA containing uniquely identified RNA molecules, each stored 5′→3′.
- Reference manifest: content digest, source/build/release, record scope such as full transcript or CDS-only, and retrieval provenance.
- Explicit search/scoring parameters: backend and version, temperature, seed policy, G–U policy, loop/bulge limits, accessibility settings, candidate/output limits, and resource limits.
- Optional contextual annotations such as abundance and localization, each with units and provenance.

The script must accept arbitrary FASTA identifiers and must not require an organism enum. Curated CERNAL references can be convenience inputs to the same contract.

### Orientation rule

All callers pass real molecular sequences 5′→3′. The interaction backend finds antiparallel complementarity. Callers do not reverse-complement a query merely to match a search implementation.

- **Cross-activation mode:** the gate adapter supplies the complete gate RNA plus the coordinates of the recognition region `B`. Hits are reference RNAs able to pair with `B`. For a standard toehold, these will resemble `T`. Accessibility of `B` is evaluated in the complete gate scaffold, not by folding an isolated substring and pretending it is the gate.
- **Sequestration mode:** the caller supplies trigger `T`. Hits are reference RNAs able to pair with `T`, and therefore resemble `B` rather than `T`.

The mode changes labels, intended-target annotation, and downstream ownership. It does not change the physical definition of an RNA–RNA interaction.

### Gate boundary

A gate integration owns the mapping from a complete design to one or more interaction-competent query regions. This is necessary because gate geometries differ: a toehold may expose one contiguous recognition domain, whereas an antisense design can use multiple separated arms.

The shared engine returns interaction evidence. The gate integration decides whether a specific interaction covers the domains, order, and structural transition required for activation or inhibition. Gate implementations must not construct their own transcriptome scanners.

If a caller has only an isolated recognition sequence and not the full molecular context, it must choose an explicit approximation: treat the supplied query as unstructured, provide externally computed accessibility, or label accessibility as unavailable. The engine must not silently fold the isolated region and report that opening cost as though it came from the complete gate.

## 4. Feasibility-gated backend choice

**IntaRNA 3.4.1 is the candidate MVP backend, not yet an unconditional production choice.** IntaRNA models RNA–RNA interaction energy together with interaction-site accessibility, supports configurable seed constraints, provides heuristic and exact modes, accepts multiple FASTA sequences, and emits machine-readable CSV.[1][4] This is a stronger starting point than a custom mismatch counter because equal mismatch counts can hide different pairing energetics, G–U pairs, bulges, and opening costs.

IntaRNA still produces model-based thermodynamic evidence, not a probability that a cell or gate will fail. Its heuristic mode does not guarantee the minimum-energy interaction under the model, while exact mode is practical only for more limited pairwise work; every report must identify which mode produced it.[4]

### Phase 0: time-boxed executable and performance spike

Before production contracts, caching, batching, or pipeline migration are implemented, install a reproducible external environment containing exactly:

- IntaRNA `3.4.1`;
- ViennaRNA `2.7.2`;
- the resolved package/build identifiers and an environment lock or container digest.

The supported acquisition path for development and dedicated CI is a pinned Bioconda environment created with micromamba. The wrapper verifies `IntaRNA --version` before a scientific run and records both IntaRNA and ViennaRNA provenance. A missing or mismatched executable fails explicitly; it never produces an empty result.

Run an implementation spike—not production code—over 1, 10, and 100 representative 30–36 nt interaction regions against:

- the bundled *E. coli* CDS reference: 4,308 records and 4,013,090 nt;
- the bundled yeast CDS reference: 6,027 records and 8,825,064 nt;
- at least one declared full-transcript/UTR-inclusive reference before calling the backend transcriptome-ready.

Record the complete parameter file, query-length distribution, reference digest and scope, wall time, peak RSS, number of query-reference pairs, reported hits, failures, IntaRNA thread count, CPU allocation, timeout, and whether each measurement used a cold or warm filesystem cache. The provisional engineering gate for direct IntaRNA screening is **100 queries against the *E. coli* reference in at most 10 minutes and at most 8 GiB peak RSS on `ziv-gaming-pc`**. This is an operational budget, not a biological threshold. If the gate fails, direct transcriptome-wide IntaRNA is rejected for the MVP and an indexed candidate generator is required before IntaRNA re-scoring.

### Provisional screening profile

The spike must use a checked-in, fully resolved profile rather than IntaRNA defaults. The initial profile to test is:

- heuristic prediction mode (`mode=H`) with the single-site loop-based interaction model (`model=X`);
- ViennaRNA nearest-neighbor energy evaluation (`energy=V`) with the explicit Turner 2004 parameter set (`energyVRNA=Turner04`);
- seed disabled (`noSeed=true`), because no gate-independent biological seed is assumed;
- canonical Watson–Crick and G–U pairs allowed throughout (`allowGU=true`, `outNoGUend=false`); with no seed, seed-specific G–U flags are inapplicable;
- lonely intermolecular pairs and dangling-end contributions left enabled (`outNoLP=false`, `energyNoDangles=false`);
- computed accessibility for both molecules;
- full-molecule accessibility context for the query (`qAccW=0`, `qAccL=0`);
- local reference accessibility (`tAccW=200`, `tAccL=150`), explicitly labeled as a computational approximation;
- query interaction restricted to the adapter-supplied region;
- `intLenMax` equal to the allowed interaction-region length and `intLoopMax=8` as recorded search-budget limits;
- temperature `37 °C`;
- one best reported interaction per query-reference pair (`outNumber=1`);
- maximal reportable interaction energy `0 kcal/mol` (`outMaxE=0`);
- CSV output containing IDs, both coordinate intervals, interaction structure, total energy, hybridization energy, and both accessibility/opening contributions when supported.

These are testable starting settings, not universal biological constants. `model=X`, `energy=V`, `Turner04`, the optional G–U-end exclusion, `outMaxE`, and per-pair `outNumber` are documented IntaRNA 3.4.1 controls.[6] The JSON profile stores booleans explicitly even when `false` is represented by omitting a CLI flag; the fully resolved command is copied into provenance. The spike must confirm that IntaRNA 3.4.1 accepts every setting together and that every requested CSV field is actually emitted. If a setting is unsupported, the profile is versioned and revised explicitly rather than silently dropped.

The gate-agnostic contract permits a seed-free profile; a gate adapter may add an experimentally justified seed requirement and position. IntaRNA's bacterial-sRNA benchmark showed that a stricter seed constraint improved that benchmark's ranking while also losing at least one verified interaction. It does not validate a universal synthetic-gate seed rule, so every seed constraint remains an explicit sensitivity boundary.[1]

### Accessibility semantics

Both molecules receive accessibility treatment when their full structural contexts are available. In cross-activation mode, the query is the complete gate molecule with pairing restricted to its recognition region. In sequestration mode, the query is the complete trigger molecule. This estimates opening costs in the supplied molecular contexts without predicting whether the gate subsequently opens or produces output.

RNAup normally treats only the longer molecule as structured unless `-b`/`--include_both` is used.[3] It may be used later as an alternative calculation under matched assumptions, but agreement between RNAup and IntaRNA is model agreement—not independent experimental validation.

### When RIsearch2 enters

RIsearch2 creates a reusable suffix-array index, finds configurable complementary seeds, and extends them with a simplified interaction-energy model.[2][5] It is the preferred candidate generator if the Phase-0 budget fails, but it does not replace IntaRNA's accessibility-aware re-scoring. Its seed requirement becomes a recorded sensitivity boundary.

RIsearch2 indexes reverse-complement copies internally. CERNAL must retain only hits mapped to RNA molecules actually declared in the reference; an automatically indexed opposite strand is not a biological transcript unless that molecule exists as its own reference record.

## 5. First shippable standalone interface

The first production milestone is deliberately narrow: one query molecule, one allowed interaction region, and one multi-record reference FASTA. It is uncached and does not modify the existing pipeline.

Expose the same contract through Python and a thin CLI with a checked-in `[project.scripts]` entry. The CLI imports the pipeline-level factory; it never constructs a stage tool itself.

```text
cernal-offtargets scan \
  --query query.fasta \
  --query-region 12:48 \
  --reference transcripts.fasta \
  --mode cross-activation|sequestration \
  --profile intarna-screen-v1.json \
  --source-record-id optional-transcript-id \
  --source-interval 100:136 \
  --max-hits 100 \
  --output report.json
```

Rules for the first milestone:

- `query.fasta` contains exactly one uniquely identified record.
- `--query-region` is 0-based and half-open and must fall within the query molecule; omitting it means the entire query molecule is allowed to pair.
- `--source-record-id` and `--source-interval` are either both absent or both present. They are a caller-declared intended/cognate reference interval, always interpreted on the stored 5′→3′ reference. The record must exist and the interval must be in range. The engine does not require sequence identity because the declaration has different meanings in the two modes; it records `relationship_validation=caller_declared` and reports full, partial, or no overlap for each hit rather than silently excluding one.
- `--max-hits` is optional. If omitted, every parsed pair-level hit is returned; values must be positive integers.
- The mode is required so reports cannot lose biological context, but it does not alter the physical interaction calculation.
- Multi-query FASTA and a per-query source-mapping sidecar are later milestones, after the single-query contract is stable.

## 6. Output contract

### Run-level fields

- schema and engine versions;
- mode and query role;
- normalized query, reference, and parameter digests;
- backend executable/build, prediction mode, interaction model, and thermodynamic parameter provenance;
- reference manifest and declared sequence scope;
- records/nucleotides searched, query-reference pairs attempted, pair-level outputs parsed, and hits returned;
- `search_exhaustiveness`, such as `heuristic_under_profile` or `exact_within_profile`;
- `backend_enumeration`, initially `best_reported_interaction_per_query_reference_pair`;
- success/failure state, warnings, and presentation-limit metadata.

Run states are:

- `success_reported_hits`;
- `success_no_reported_hits_under_profile`;
- `not_evaluated`;
- `failed`.

The no-hit state means only that the configured backend completed without reporting an interaction under the recorded model, heuristic, accessibility assumptions, energy cutoff, and enumeration policy. It never means that no modeled or biological interaction exists. An absent or empty reference is `not_evaluated`, not a zero-risk result.

The first schema does not claim an exact count of interactions omitted by IntaRNA's heuristic search or per-pair enumeration. If a later presentation limit is applied after parsing, `reported_hits_before_presentation_limit` and `presentation_omitted_hits` are exact; backend-unknown omissions remain explicitly unknown.

### Per-hit fields

- stable hit ID and reference record ID;
- query and reference 0-based half-open coordinates;
- stored reference segment in 5′→3′ orientation;
- antiparallel duplex/alignment representation;
- canonical-pair, G–U, mismatch, query-bulge, and reference-bulge counts when derivable from backend output;
- total interaction energy and units;
- hybridization energy, query opening cost, and reference opening cost when emitted;
- backend-native seed evidence and whether the search was seed-limited;
- intended-source overlap flag;
- optional abundance/localization annotations with units and provenance;
- deterministic rank and ranking components;
- null-with-reason for unavailable evidence.

No field is named `probability`, `activation`, `sequestration`, or `failure` unless a separately trained and validated calibration model is added later.

## 7. Ranking and limit semantics

For the first milestone:

1. Request one best reported interaction per query-reference pair.
2. Preserve every native energy component emitted by IntaRNA.
3. Rank parsed hits by accessibility-adjusted interaction energy, more favorable modeled energy first.
4. Break ties by normalized reference ID, reference start, reference end, query start, query end, and stable hit ID.
5. Apply any user-facing hit limit only after all pair-level outputs are parsed and canonically sorted. The limit is global because the first milestone has exactly one query.
6. Return at most `min(max_hits, reported_hits_before_presentation_limit)` when a limit is set; deterministic tie-breakers—not input order—resolve a tie at the cutoff.
7. Keep abundance as a separate annotation, not part of the universal score.
8. Apply no biological pass/fail threshold.

A future context-specific occupancy model may combine interaction energy with measured concentrations, competition, and stoichiometry, but it must be separately named and state its equilibrium or kinetic assumptions. Bulk transcript abundance is condition-, isoform-, compartment-, and time-dependent and is not itself free local concentration.

## 8. Dependency and CI isolation

IntaRNA is an external executable, not a Python dependency in `pyproject.toml`. The first milestone keeps existing MockEngine and LocalEngine behavior unchanged.

- Unit tests use checked-in golden IntaRNA CSV to test validation, command construction, coordinate conversion, parsing, sorting, and JSON serialization without the executable.
- One external integration test invokes real IntaRNA on a synthetic fixture.
- The real test is marked `intarna_external`; it skips in ordinary local/default CI when the external environment is absent.
- A dedicated GitHub CI job creates the pinned micromamba/Bioconda environment, sets `CERNAL_REQUIRE_INTARNA=1`, and runs the external test. In that lane, missing or wrong-version IntaRNA is a failure, never a skip.
- The wrapper uses a temporary directory, a bounded timeout, bounded captured output, process-group cleanup, and explicit mappings for nonzero exit, timeout, malformed CSV, and partial output.
- A report is published only after complete parse and schema validation; partial output never becomes a successful report.

## 9. Migration boundary

The repository already assigns off-target measurement to `OffTargetScanner` in `src/engine/stages/off_target.py`; the first milestone **fills that existing tool rather than creating a parallel implementation**. Rich versioned request/result records are added to `engine.domain`, and the scanner gains one neutral interaction-analysis method used by the standalone path. Existing `Hit`, `OffTargetReport`, `scan_trigger`, `scan_switch`, `TriggerCandidate`, `GateDesign`, `TriggerScorer`, `CandidateResult`, and public API/client payload behavior remain byte-compatible during this milestone.

`pipeline.py` remains the only place that constructs `OffTargetScanner`. A new pipeline-level factory accepts an explicit reference and profile; both `build_tools()` and the thin `src/engine/off_target_cli.py` entry point obtain the scanner through that factory. This preserves the one-tool/one-configuration rule and gives the repository one underlying off-target measurement, not two. The standalone CLI does not route through `TriggerScorer` or mutate current jobs.

Pipeline integration is a later coordinated schema migration:

1. batch a deliberately broader structurally ranked candidate pool rather than invoking IntaRNA inside every sliding-window iteration;
2. add a versioned rich interaction-analysis attachment to candidate results;
3. represent measured, not evaluated, and failed states explicitly;
4. deprecate mandatory legacy scalars only under a declared schema-version change;
5. prove MockEngine output, Python-client conformance, and LocalEngine runs with off-target analysis disabled remain compatible or migrate them together;
6. keep gate families from constructing or invoking the shared scanner, preserving repository house rules.

No universal formula will map rich evidence to `off_target_penalty`, `segment_specificity`, or `binding_site_off_target` until a separately reviewed calibration exists.

## 10. Determinism and later caching

The uncached first milestone must:

- normalize case and whitespace and explicitly convert `T` to `U`;
- accept only `A`, `C`, `G`, and `U` after normalization;
- reject empty sequences, duplicate IDs, invalid regions, and checksum mismatches before invoking IntaRNA;
- parse a FASTA record ID as the first non-whitespace token after `>`; preserve the full original header separately and reject collisions after ID normalization;
- digest the canonical normalized FASTA, query region, and complete resolved profile;
- canonically sort output independent of FASTA record order;
- serialize floats with one documented JSON policy.

Caching is deliberately not part of the first shippable milestone. A later cache may key immutable reference preparation by reference and tool/profile digests, and interaction evidence by query, region, reference, backend, and thermodynamic digests. Cold and warm scientific payloads must then match exactly apart from cache/timing metadata, and corrupt entries must trigger safe recomputation.

## 11. Test-first delivery slices

Every production slice follows red–green–refactor.

0. **Feasibility spike:** install and verify the pinned tool environment; validate the provisional profile; benchmark 1, 10, and 100 queries before committing to direct IntaRNA or an RIsearch2 prefilter.
1. **Standalone contract and validation:** define the single-query Python request/result records and JSON Schema; test normalization, digests, query region, source interval, and result-state invariants.
2. **Golden parser:** parse checked-in IntaRNA CSV with exact coordinate and energy assertions, including malformed and partial output failures.
3. **Uncached CLI:** fill the existing `OffTargetScanner` with the neutral analysis path, obtain it through the pipeline-level factory, invoke an injected runner end to end, and publish JSON atomically. Existing pipeline job behavior remains unchanged.
4. **Real external test and CI lane:** run pinned IntaRNA on a deliberately non-self-complementary synthetic fixture containing an exact antiparallel complement, a same-orientation control, one mismatch, one G–U candidate, one bulge candidate, and a decoy.
5. **Mode projection:** verify identical physical evidence can carry different cross-activation versus sequestration roles and intended-source annotations without the engine claiming function.
6. **Batching:** add multi-query FASTA only with a versioned sidecar schema mapping every query ID to zero or more source record/interval pairs; prove batch-size, input-order, and worker-count invariance.
7. **Cache:** add only after the uncached scientific payload is stable.
8. **Pipeline adapter:** start the coordinated schema migration only after performance and standalone contracts pass review.

## 12. Acceptance criteria for the first production milestone

- Accepts one arbitrary RNA query molecule, one allowed interaction region, and one arbitrary multi-record RNA FASTA without hard-coded organism or gate names.
- Evaluates query-region accessibility in full supplied molecular context or records an explicit alternative assumption.
- Correctly identifies antiparallel complementary candidates and does not treat a same-orientation identity match as evidence merely because it is identical.
- Preserves hit-level coordinates, native energies, assumptions, and complete reference/tool/profile provenance in JSON.
- Uses scientifically narrow run states, including `success_no_reported_hits_under_profile`, without claiming exhaustiveness.
- Produces deterministic output for identical normalized inputs and the pinned environment.
- Passes a real IntaRNA integration test in a dedicated provisioned CI lane while ordinary MockEngine CI remains green without IntaRNA.
- Fills the existing `OffTargetScanner`, constructs it only in `pipeline.py`, and leaves existing pipeline job behavior, legacy record fields, API results, and client conformance unchanged.
- Reports ranked interaction evidence, never a calibrated biological-failure probability.
- Contains no translation, leakage, open-state, or protein-expression prediction.

## 13. Recommended decisions

Proceed under these defaults unless the Phase-0 measurements falsify them:

- Treat IntaRNA 3.4.1 plus ViennaRNA 2.7.2 as the candidate backend, subject to the explicit 10-minute/8-GiB benchmark gate.
- If direct screening fails the gate, add RIsearch2 only as a candidate generator and re-score retained candidates with IntaRNA.
- Ship an uncached, single-query standalone interface over the existing `OffTargetScanner` before batching, caching, or integration into current pipeline jobs.
- Support both named biological modes as metadata/projection over one physical interaction primitive.
- Use full query-molecule context plus an allowed interaction region; never fold an isolated gate domain silently.
- Use the declared seed-free heuristic profile for the feasibility test, with all parameters recorded and no claim of exact MFE recovery.
- Retain intended-source hits and flag them in raw evidence.
- Support arbitrary user FASTA immediately; label bundled CERNAL references as CDS-only.
- Keep abundance as annotation only.
- Rank evidence only; apply no hard biological rejection and no universal scalar penalty.

## Sources

[1] https://pmc.ncbi.nlm.nih.gov/articles/PMC5570192
[2] https://pmc.ncbi.nlm.nih.gov/articles/PMC5416843
[3] https://viennarna.readthedocs.io/en/latest/man/RNAup.html
[4] https://github.com/BackofenLab/IntaRNA
[5] https://github.com/RTH-tools/risearch
[6] https://raw.githubusercontent.com/BackofenLab/IntaRNA/v3.4.1/README.md
