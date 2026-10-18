# AND integration revision and PR evidence — 18 October 2026

## PR-readiness integration checkpoint

The author approved updating the engine PR after the Wiki publication. Refinement
commit `2483c91` records the selected defaults and audit export. Merge `5971b8a`
integrates `origin/main` at `ca4e3b0`; the engine branch is no longer behind that
main revision. Engine main itself was not changed.

Two conflicts were resolved: regenerate `docs/api-surface.md` from the combined
source, and retain both the AND candidate-audit export and upstream final-sequence
screening in `pipeline.py`. The upstream screening/release-record block was checked
byte-for-byte against `origin/main`. A regression now verifies that the AND audit
survives a sequence hold while full switch/construct sequences reach screening
and held sequence-bearing exports remain absent. Synthetic observables in that
test exercise the integration contract; they do not establish biological yield.

Full Ruff lint/format, Django system/migration checks, frontend contracts/build,
generated API reference and the 18-quantity Wiki consistency check passed on the
combined source. Combined AND/API/screening regressions and fresh GitHub CI are
reported in [PR #84](https://github.com/zivbental/cernal_software/pull/84).
The native 20-design run below predates this merge and remains the current
search-yield evidence; it was not relabeled as a new merged-branch experiment.

All 12 compact evidence archives pass compressed/uncompressed SHA-256 and byte
length verification. Two older index entries had used uncompressed lengths in
the `bytes` field; the index now distinguishes compressed and uncompressed sizes.
Archive bytes and both digests are unchanged.

The following sections preserve the preceding review checkpoints. Their older
branch, approval and test statements are superseded by this integration record
and the exact final-head checks attached to the PR.

## Previous local refinement checkpoint

At the previous checkpoint, the Wiki changes were on `offer/prokaryotic-and-integration`.
The user subsequently integrated those Wiki
changes; the current local refinement is on `offer/and-search-refinement`.
**Repository status after the author's publication approval:** the Wiki refinement
was committed and pushed to Wiki `main` as `d8b7b88`; GitLab Pages pipeline
`765093` passed. The live AND page was verified byte-for-byte against the local
frozen page (SHA-256 `9dfebf0f24ca4b7fa59580f579373746a35960b6a032e2ce863f80eb875ada28`).
The engine refinement
remains local and uncommitted; no engine push or merge was performed.
Preview: <http://127.0.0.1:8097/and-gate-model#the-algorithm>.

**Current refinement after the author's clarification:** up to three representatives
from occupied cells in the strongest-lock row of the original 3x3 grid; AUA upper3
only; lower3 variants only when they strengthen the lower arm. The five closures
are unchanged: original plus one representative per 0/1/2/3-pair class. The earlier
two-stem/20-point-per-stem configuration, timings, archives and validation below
are historical checkpoint evidence, not measurements of this new profile.

**No terminal action is required from the user.** Commands in this report are
optional developer instructions for manually reproducing a test run. They do not
execute when this Markdown file is opened, and do not need to be run for normal
backend operation. The application invokes the compiler through its existing job
interface; these commands provide a separate manual reproduction route.

The 0.11-family refinement was exercised in a bounded real GFP example under
`var/and-revision/strong-lock-row-final/`: 20 candidates, zero accepted/ranked,
45.592 seconds. All 20 used AUA; 19 retained original lower3 and one had a qualifying
wobble change (lower-arm energy -10.1000 to -12.1000 kcal/mol). Each represented
pair had only two occupied cells in its strongest row, so the original global
grid selected two rather than inventing a third. This configuration does not
guarantee a nonempty feasible shortlist or three occupied cells.
The final record and closure audit are preserved in
`prokaryotic-and/refinement-export-gfp-20.json.gz`. The author explicitly confirmed
keeping the original grid and returning fewer than three when a cell is empty.

Closure centers were independently recomputed with the shared binding/folding tools:
AAC 3.4000 versus class mean 3.4750; AGU 3.2000 versus 3.6250; CGU 1.8000 versus
2.0667 kcal/mol. The external Green source workbook SHA-256 is
`1c47d155ab0cebbd4693544b7db8bfa72059b64213fa422a7f438f2be0dc3fec`.
The measured 168-switch set contains 102 AUG bulges, median measured ON/OFF 18.0.
An old source comment giving median 86.5 was not reproduced and was corrected;
neither that value nor unreproduced pairwise p-values select the production motif.
AUG is the best-represented reference, not an established best performer. The
local numeric check is `var/and-revision/closure-choice-audit.json`.

Visible Wiki release/merge-review narration was removed. The reader sees the
algorithm, evidence and missing reproduction inputs; source-only editorial notes
remain intact.

Current Git checkpoint: engine `offer/a0-to-cernal` remains at `d32703e` with local
changes and is eight commits behind / eleven ahead of updated `origin/main` at
`ca4e3b0`. Those incoming commits concern Ziv's final-output screening and tests, and were
not merged. GitHub reports existing draft PR
[#84](https://github.com/zivbental/cernal_software/pull/84) as conflicting with
current `main`; its passing CI covers `d32703e`, not these uncommitted refinements.
The read-only three-way comparison identifies a generated API-document conflict;
shared pipeline and sequence-release changes also need integration verification.
GitHub authentication works outside the sandbox; no new login is required.
Wiki refinement was published from `offer/and-search-refinement`, based on the
user's clean merged main `b7237af`, to Wiki `main` at `d8b7b88`.
Git states and test totals later in this report
describe the earlier checkpoint unless explicitly superseded here.

Final refinement validation: **1,102 passed** in the relevant AND, pipeline,
house-rule and boundary suite (240.27 s). Python lint/format, frontend typecheck,
generated API-document check and Wiki freeze/render checks pass. Browser checks
find no visible release-review narration, broken internal anchors, duplicate IDs
or unnumbered tables; desktop/mobile/print behavior is preserved. All 53 previous
Jinja comments are intact. Twelve compressed evidence archives verify against
their compressed/uncompressed digests. Generated `docs/api-surface.md` and the
single bacterial-AND API-help row were updated to match the new defaults/version.
No engine commit, push or merge was performed. Wiki publication is recorded above.

## A. Answers to the scientific and engineering questions

### The four execution questions

1. **Which trigger pairs continue?** Search only CERNAL's nominated regions for
   maximal reverse-complementary overlaps of at least four bases. Construct complete
   A/B footprints around those overlaps and rescore them with the shared
   `TriggerScorer.score_window`. Carry the top eight ordered pair/role/geometry
   records by `min(A.score, B.score)` by default. Each score is the gate-aware
   selected joint P8 opening probability. Using the minimum favors pairs whose
   weaker input is still accessible; it is a search heuristic, not a calibrated
   success score. Optional `percentile_sample` uses seeded sampling above a declared
   percentile of the discovered pool. Discovery caps can truncate that pool before
   ordering, so “top” never promises a global optimum over all possible pairs.
2. **How many secondary hairpins?** Up to 2,187 assignment indices per carried
   record are inspected by default, exhaustive only when that covers the assignment
   space. Construction checks and three-energy Pareto pruning produce a front;
   up to **three stems** are carried from its strongest-lock row, one from each
   occupied A-site tertile of the original global grid, nearest the cell mean.
   Empty cells stay empty. The 2,187 cap equals 3^7 and was a temporary computation
   budget, not an experimentally justified choice or an assumption of seven conflicts.
3. **Which levers?** Default closure writes: trigger-derived, AUG, AAC, AGU, CGU;
   upper3: `WWW_AUA` only; lower3: trigger-derived plus an eligible strengthening
   `wobble_GU`. This is at most **10 points per selected stem**, 30 per record and
   240 across eight records before invalid assemblies/budgets. The default limit
   of **20 evaluated designs**, alongside 160 attempted assemblies, prevents a
   full sweep. Rotation/interleaving spread that finite budget. Geometry defaults
   to naive, with Kim/both configurable. Full axes give 16 closures and three
   upper3 choices for explicit comparisons. Reduced production wobble only adds
   eligible AU-to-GC conversions below the 2S1W target, retaining G-U pairing with A,
   and requires a strictly lower modeled energy of the complete lower arm.
   No qualifying conversion means the original design only, with no duplicate.
4. **What ranks candidates?** The existing shared profile
   `default-v3-computational-proxies`, after structural/construct eligibility.
   Its declared ranges normalize/clamp raw values to 0–1; lower-is-better terms
   are inverted; a weighted mean determines rank. Tie-breakers are separation,
   leakage, then stable candidate ID. AND supplies the common schema, but
   cross-family biological comparability is not established.

| Shared term | AND definition | Weight; direction; normalization range |
|---|---|---|
| `state_separation` | Opening-energy gain divided by RT ln 2; log2 of ON/worst-OFF opening | 3; higher; 0–10 |
| `trigger_accessibility` | Lower minimum per-base marginal accessibility of the two adjusted triggers; distinct from the P8 pair-selection score | 2; higher; 0–1 |
| `gate_folding_energy` | MFE of the switch through its linker, excluding output CDS | 2; lower; -60–0 kcal/mol |
| `predicted_leakage` | max(P00, P10, P01), joint opening of the 30-nt initiation footprint | 2.5; lower; 0–1 |
| `gc_content` | Switch GC percent; the shared linear preference, not a target-GC optimum | 0.5; higher; 30–70 |
| `dynamic_range` | P11/max(P00,P10,P01), without a denominator floor | 2; higher; 1–500 |
| `orthogonality` | Unmeasured (`None`) | 1.5; skipped when missing |
| `predicted_success_rate` | Uncalibrated for AND (`None`) | 1; missing treated as worst |
| `circuit_complexity` | Not emitted by this family (`None`) | 1; missing treated as worst |

The shared profile also applies leakage <= 0.85 and separation >= 0.5. These
**existing additional eligibility filters** mean passing the 22 structural checks
alone does not guarantee acceptance by CERNAL. They were neither added nor changed
in this revision. If the intended contract is strictly “22 checks, then rank only,”
the shared-profile policy requires an explicit decision with its owner.

Single-input gates use different opening events, other families use gene-level
separation or sampled stem measures, and missing metrics are penalized differently.
The schema is technically consumable; the total score is not a calibrated
cross-architecture protein-output comparison. No common-score redesign was made.

### The nine attached topics

| Topic | Established; change made | Uncertainty / further evidence |
|---|---|---|
| 1. Usable CERNAL output | Existing frozen records already carry full sequences and shared rank. Added inspectable check-by-check JSON, resolved profile and raw metrics in CSV. Rejected candidates remain visible. | Current real bounded searches have zero accepted designs. A nonempty current upstream-search shortlist is still needed; historical checks-pass rows are not substituted for it. General physical multi-gate assembly is outside this integration. |
| 2. Compensation for stronger A binding | New matched 2x2 historical analysis fixes genes/windows, overlap, geometry, stem and closure in 37,488 quadruplets. Combined AUA+wobble lowers mean state-10 x* engagement by 0.0862 and main-arm engagement by 0.1737. Among 23,289 quadruplets with all four recorded ON costs, mean ON cost rises by 0.2178 kcal/mol. Post-hoc 22-check passes: baseline 527; AUA 495; wobble 530; both 485, each /37,488. | Some OFF improvement is supported; preserved feasibility or compensation for a longer effective A toehold is not. Includes no-op edits and conditioned historical data. No significant interaction, causal biological effect or protein-leakage result is claimed. |
| 3. Difference/ratio and correlations | §8.3 now separates feasibility/ranking, gives arithmetic examples, keeps raw ratios unfloored, and proposes ON/worst-OFF Pareto comparison alongside shared rank. Original unexplained rho triple is withheld; explicit recomputation gives median within-cell rho -0.137/+0.661/+0.619 for IED OFF references 00/single-input/all-OFF versus opening-energy gain. Each uses 389 nonconstant cells and 219,807 usable rows. Both gains are higher-is-better. | The original -0.075/+0.651/+0.620 population/variable pairing was not reproduced exactly. New values are model-to-model agreement, not measured performance. Original floor percentages lack sufficient identified provenance and are removed from visible §8.3, retained in source comments. No evidence selects 0.05 as default. |
| 4. Compiler decisions | §8.4 links Algorithm 1/Figure 4.6, specifies implemented count/time limits, interleaving and ON-first evaluation, and lists stored provenance. | Adaptive allocation after preliminary per-pair evaluations is proposed, not implemented or proven optimal. Sample failure cannot establish universal pair failure. |
| 5. Lock/A trade-off and A-anchored | §8.1/8.5/8.6 now prioritize lock stability over extra A complementarity when competing, conditional on B release/ON. Audit reproduces median A-site energy rho -0.7007 with x* engagement, -0.4695 with main-arm engagement (420 cells), and +0.0234 with ON opening cost (388 cells). A-label exclusion was already removed in the previous integration correction. | Correlated energies do not prove an independent causal lever. Historical 0/4,330 is scoped to its reported computational test, not every A-anchored construct. No new categorical prune was introduced. |
| 6. Saturated occupancy | Last §8.5 row now explicitly concerns only the 306 preferred-stem subset, approximately 0.998–1.000 occupancy. Low resolution there does not invalidate occupancy across the 3,113-design lever grid. | Path estimates remain supplementary experimental hypotheses, not global replacement rankers or protection thresholds. |
| 7. Two deliverables | §8.6 leads with the computational records/export and its current yield limitation, followed by the separate equilibrium-baseline/barrier-challenge experimental plan. Existing Figure 8.1 is linked and retained. | No experimental panel has been tested. Challenge rejects remain outside current computational feasibility. |
| 8. Low/high path example | Reproduced astC x ggt key `naive:astC:ggt:1175:789:4:4:d0_gc3_GCC:trigger_derived:trigger_derived`: occupancy 0.9987400314, ON cost 4.8163757324, path 4.5. Contrasted fadB x ggt key `naive:fadB:ggt:1981:1440:9:1:d0_gc3_GCC:WWW_AUA:wobble_GU`: 0.9998087344, 4.8188018799, path 25.2. | Same ON cost to two decimals does not control transcripts, overlap length or lever settings. No within-pair contrast met gap >=8 kcal/mol, ON tolerance <=0.5, and both occupancies >0.99 among the 3,113 joined lever-grid records. Smaller contrasts remain possible. High heuristic upper bounds do not prove slow leakage. |
| 9. Presentation | All 27 scientific tables are section-numbered, including expandable panels. §8.5 has a scoped wrapping fix. Discussion links existing analyses/figures rather than duplicating them. | Local browser/print checks pass; this does not publish the revised page. |

Effective toehold length means the available nucleation sequence/span in a specified
state; A-site duplex energy and partner-specific occupancy are separate quantities.
Current footprints are geometry-defined. Closure writes are not a direct binary
“complementary/noncomplementary to A” control. Establishing that requires the actual
aligned sequence, not a closure label.

The smallest useful **next computational experiment** is a matched factorial on
fixed gene/windows/overlap/geometry: first identify feasible secondary stems offering
different A-site energies at similar lock/B energies, then cross the two upper3
and two lower3 settings with sequence-verified bulge alternatives. Record attempted
assemblies, no-op edits, all four states and all checks; retain ON-screen failures
as missing later measurements. Testing toehold extension independently needs an
explicit architecture change, not relabeling an energy or occupancy measurement.
No such new architecture or compensation sweep was implemented here.

## B. Implementation changes

- `src/engine/gates/toehold.py`: additive diagnostics (`and-equilibrium-diagnostics-v2`):
  each check, raw ON/OFF alternatives and comparability status. Reuses `gate_violations`;
  no new folding, score weights, feasibility thresholds or selection policy.
- `src/engine/pipeline.py`: captures the actual resolved shared profile; expands the
  existing CSV writer and adds sequence-free `and-candidates.json` through the shared
  `write_artifact`. The existing inter-stage record and release controls are preserved.
- `tests/engine/test_prokaryotic_and_pipeline.py`: output consistency, A/B roles,
  retained missing-check failures, and absence of full switch sequence in audit export.
- `README.md`, `docs/and-gate.md`: correct stale mandatory-full-CDS wording and document
  the actual audit schema, score definitions and limitations. Eukaryotic module untouched.
- `tools/and_revision_audit.py` and its compact JSON result: existing shared correlation,
  feasibility and barrier-join methods; six large local historical input hashes recorded.
- `docs/evidence/prokaryotic-and/`: one new compressed real-run audit archive plus its
  checksum entry/readme. All earlier archive bytes remain unchanged.
- Wiki `wiki/pages/and-gate-model.html`: §4.9 exact default selection/grid;
  §§8.1/8.3–8.6 scientific/engineering revisions; page-wide table numbering.
  All original `EDITOR V2` comments retained; removed visible §8.3 claims preserved in
  a source comment; generic §8.4 GC prose shortened with its Results evidence retained.
- Wiki `static/and-gate-model.css`: only §8.5 prose-table wrapping/column sizing.

No shared scoring profile, gene-selection module, circuit designer, deployment
configuration, eukaryotic gate, or teammate overview page was modified.

## C. CERNAL deliverable and reproduction

The production interface is `CandidateResult`: full switch sequence/design,
ordered input features, metrics, rank/status and diagnostic evidence. CSV/JSON
are exports, not the interface between compiler stages.

The local real example is `var/and-revision/compiler-final/and-candidates.json`, with
`candidates.csv`, `and-search.json` and the standard run manifest/report. It contains
**20 rejected records, zero ranked survivors**, from 23 assembly attempts; elapsed
55.565 seconds on this computer with another test process running. It verifies the
export path, not successful design yield. Synthetic contract tests separately cover
positive ranking; the real selected historical regression passes all 22 checks.

Portable preserved evidence is
`docs/evidence/prokaryotic-and/revision-export-gfp-20.json.gz`, containing
`execution`, `candidate_audit` and precise producer-file hashes. Its producer is
`d32703e` plus the recorded local changes. Decode with `gzip`/`json`; the checksum
index verifies both compressed and uncompressed bytes.

JSON schema `and-candidate-audit-v1` exposes `ref`, `rank`, `overall_score`,
`rejected`, `rejection_reason`, ordered `inputs` with A/B roles and intervals,
`parameters`, sequence hash, model/family versions, `metrics`, and `equilibrium`.
The last block includes `states`, 22 `checks`, `observables`, `feasibility`,
`ranking_measures` and `ranking_profile`. Full sequences stay in the existing
internal record; audit exports do not bypass public sequence-release controls.

Optional manual reproduction from the engine root (no user action required):

```console
uv run --locked --extra dev python tools/pair_budget_on_pfas.py --pipeline --pipeline-output gfp --seed 7 --max-designs 20 --max-pairs 8 --run-dir var/and-revision/reproduction --out var/and-revision/reproduction.json
uv run --locked --extra dev python tools/and_revision_audit.py --out var/and-revision/reproduced-audit.json
```

The second command requires the six ignored local `axes_c8_0..5.csv` shards.
Their original producing environment/input provenance remains incompletely pinned;
this audit verifies stored results, not a full regeneration of the study. The
post-hoc 4,762 structural passes among 301,440 historical rows are not a nonempty
shortlist delivered by the current upstream-region search. No claim is made that
the whole study or this local revision is reproducible from `main`.

## D. Results that must not be claimed

- Functional two-input AND behavior, low protein leakage, calibrated cross-family
  protein predictions, PFOA specificity, or kinetic protection.
- Proven compensation for stronger/longer A binding by combining main-hairpin edits.
- A validated ratio floor, pathway threshold, optimized top-K/stem count, or adaptive
  per-pair allocation.
- A successful current-search shortlist, completed wet-lab panel, or arbitrary
  physical multi-gate compiler.
- Greater accuracy from mandatory full-output folding. The declared model remains
  the complete switch through its linker, excluding all output CDS.

## E. Earlier checkpoint validation and Git state

- Focused AND integration plus house/boundary rules: **913 passed**, 79.55 s.
- Final AND integration, production/helper/inventory, scoring and pipeline set:
  **242 passed**, 249.41 s. The two sets overlap; do not add them as unique tests.
- Modified Python files: Ruff check/format clean. Both repository diffs pass
  whitespace checks. Existing `motifs.py` escape-sequence SyntaxWarnings were not
  changed. No full fresh backend/frontend CI run was claimed for this local revision.
- All 35 Wiki templates compile; AND page renders HTTP 200; canonical Flask freeze
  succeeds. Browser: 27 numbered tables, no duplicate IDs/broken internal anchors,
  all image-role SVGs named. Desktop §8.5 table width/scroll width both 825 px;
  mobile body remains 390 px with scrolling confined to the 366-px wrapper;
  print exposes content from all 29 details panels. Local screenshots/PDF are in
  `var/and-revision/` and ignored.
- Eleven evidence archives verify against compressed and uncompressed SHA-256;
  the new scientific audit records source data/code hashes.
- Engine branch `offer/a0-to-cernal`, HEAD/remote `d32703e`; remote main `66a6d26`,
  **0 behind / 11 ahead**, with local changes above. Main has not advanced.
- Wiki branch `offer/prokaryotic-and-integration`, HEAD/remote `78afc34`;
  current main `812cff8`, **2 behind / 2 ahead**. New main commits `537d5dc` and
  merge `812cff8` update Zeev's `and-gate-model-overview.html`, not our page/CSS.
  No merge was performed. Existing draft PR #84 and MR !3 do not contain these
  uncommitted local changes.
- Only read-only Git inspection and local workspace writes were performed.
  No commit, push, merge or deployment.

## F. Earlier checkpoint recommendations

**Ready for supervisor review:** local Wiki preview, explicit algorithm defaults,
ranking explanation, matched historical analysis, numerical provenance and scoped
presentation fixes; additive engine audit/export changes.

**Computational next:** demonstrate nonempty accepted yield from upstream nominated
regions with an explicitly expanded budget; compare broader pair/stem coverage
without changing thresholds; resolve shared-filter and cross-family scoring policy
with the scoring/circuit owner; design the matched compensation experiment above.
The current two-stem fixed-bin ordering is a candidate for comparison, not silently
changed here. Reconcile the unrelated newer Wiki main commits during the approved
integration step. Large historical inputs need a versioned archive/producer record;
ignored `var/` logs/previews stay local and compact evidence remains reviewable.

**Wet lab in parallel:** four-state reporter/time/concentration measurements for
an equilibrium baseline and labeled barrier-challenge panel, with matched sequence
contexts where possible. Evaluate whether path estimates add predictive value.

The author subsequently approved Wiki publication and engine PR preparation;
the current integration checkpoint is recorded at the top of this report.
