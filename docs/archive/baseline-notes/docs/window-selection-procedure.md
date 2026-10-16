# Trigger and nucleation window-selection procedure

**Scope:** reusable offline/research analysis implemented by
[`tools/trigger_nucleation_ranking.py`](../tools/trigger_nucleation_ranking.py).

This document specifies how CERNAL turns one target-RNA sequence and one per-base
RNAplfold marginal-accessibility profile into a complete, deterministic ranking of
fixed-length trigger windows and their best nested nucleation windows. It describes the
35 nt trigger / 6 nt nucleation analysis and the 39 nt trigger / 9 nt nucleation analysis,
but the procedure accepts any valid pair of lengths.

This is not the production gate-aware `engine.stages.triggers.TriggerScorer` procedure.
The production scorer uses different evidence and gate-design constraints. The utility
described here is a narrower research analysis of arithmetic aggregates of one-base
**marginal** P(unpaired) values.

## 1. Inputs and orientation

The analysis has two aligned inputs:

1. `sequence`: the complete supplied target/sense RNA sequence; and
2. `profile`: one marginal P(unpaired) value for each base in `sequence`.

The input contract is deliberately strict:

- `sequence` must be non-empty uppercase RNA containing only `A`, `C`, `G`, and `U`.
- The sequence is preserved exactly. The utility does not trim whitespace, change case,
  convert `T` to `U`, resolve ambiguity symbols, or otherwise normalize it.
- The exact ASCII sequence bytes are hashed for provenance.
- The supplied sequence is interpreted in its provided **5′→3′ target/sense
  orientation**. It is never silently reversed or reverse-complemented.
- Every reported trigger or nucleation sequence is therefore a segment of the supplied
  target RNA, written 5′→3′. It is not the complementary trigger oligonucleotide that a
  downstream design step might synthesize.
- `profile[i]` is the one-base marginal P(unpaired) for `sequence[i]`. It must be finite
  and in the closed interval `[0, 1]`.

If a complementary molecule is needed later, derive and label it in that downstream
step. Do not change the orientation of this analysis or relabel target segments as
oligonucleotides.

## 2. Full-context marginal-accessibility profiling

Create the profile once for the complete supplied sequence:

```python
profile = profiler.profile(sequence)
```

Use the repository's injected
[`FoldProfiler`](../src/engine/stages/folding.py); do not instantiate a second RNAplfold
adapter inside the ranking utility and do not profile each trigger independently.
Profiling the full sequence once has two consequences:

1. all trigger windows are evaluated against the same structural ensemble and parameter
   set; and
2. a base's marginal accessibility includes interactions with the rest of the supplied
   sequence, not only bases inside its candidate window.

`FoldProfiler.profile(...)` returns one-base marginal P(unpaired) values. A value `p_i`
means the modeled marginal probability that target position `i` is unpaired. The window
scores below are arithmetic summaries of these one-base marginals.

They are **not**:

- the probability that every base in a window is simultaneously unpaired;
- a product of per-base probabilities;
- a call to `FoldProfiler.joint_probability(...)`; or
- a calibrated binding or biological-efficacy probability.

### RNAplfold parameters

Unless the caller supplies another prespecified `FoldProfiler` configuration, the
repository wrapper uses:

| Parameter | Repository default | Effective value for a sequence of length `n` |
|---|---:|---:|
| local window, `W` | 200 nt | `min(n, 200)` |
| maximum base-pair span, `L` | 150 nt | `min(n, 150, W)` |
| maximum reported unpaired interval, `u` | 20 nt | `min(n, 20)` |
| temperature, `T` | 37 °C | 37 °C |

The wrapper fails closed if ViennaRNA's process-global temperature is not 37 °C. Record
the effective, possibly clamped values from `profiler.provenance(sequence)`, not only the
nominal defaults.

RNAplfold's `u` and this analysis's nucleation length are different parameters. The
ranking utility uses only length-1 marginal values from the profile and can average any
valid nested nucleation length. It does not request a joint `u`-length opening
probability.

## 3. Coordinate conventions

Two coordinate systems are used, and conversions must be explicit.

### Internal coordinates

Python operations use **zero-based, half-open** intervals:

```text
sequence[start0:end0]
```

The first included base is `start0`; `end0` is excluded; the interval length is
`end0 - start0`.

### User-facing coordinates

Candidate tables and documentation use **one-based, inclusive** coordinates:

```text
start_1based = start0 + 1
end_1based   = end0
length       = end_1based - start_1based + 1
```

Thus Python slice `[10:45]` is target positions `11–45`, inclusive, and contains 35 nt.
Coordinates always refer to the supplied target RNA in its original 5′→3′ orientation.
"Earlier 5′" means the smaller target coordinate.

Every implementation or run-level QC check should verify:

```python
sequence[start_1based - 1 : end_1based] == reported_target_rna_5to3
```

Apply the same check to the selected nucleation sequence.

## 4. Trigger-window enumeration

Let:

- `n` be the sequence length;
- `t` be the trigger length; and
- `s` be the trigger stride.

The reusable analysis accepts an explicit positive integer stride. The established dense
analysis uses `s = 1`.

Trigger starts are enumerated in increasing target coordinate:

```python
for start0 in range(0, n - t + 1, s):
    end0 = start0 + t
    trigger = sequence[start0:end0]
```

The expected number of trigger candidates is:

```text
floor((n - t) / s) + 1
```

For stride 1, this simplifies to `n - t + 1`. No candidate is removed before ranking.
The candidate identifier is coordinate-derived:

```text
cand-{start_1based:04d}-{end_1based:04d}
```

For example, target positions `11–45` become `cand-0011-0045`.

For each trigger, retain both:

- its exact target-RNA subsequence; and
- the aligned profile values for the same interval.

## 5. Nested nucleation-window enumeration

Let `k` be the nucleation length, with the required relationship:

```text
1 <= k <= t <= n
```

For a trigger spanning internal interval `[start0:end0)`, enumerate every contiguous
`k`-nt interval fully nested inside it:

```python
for nucleation_start0 in range(start0, end0 - k + 1):
    nucleation_end0 = nucleation_start0 + k
```

Each trigger therefore has exactly:

```text
t - k + 1
```

possible nucleation placements. Placements are evaluated in target 5′→3′ order.

For every placement, calculate the arithmetic mean of its marginal P(unpaired) values.
Select the placement with the highest mean. If two or more placements have exactly equal
means, select the placement with the earliest 5′ start, meaning the smallest target
coordinate.

This tie-break is local to nucleation placement. It occurs before candidates are ranked
against one another.

## 6. Score definitions

For a trigger containing marginal values `p_1, ..., p_t`, define:

### Full-trigger mean marginal accessibility

```text
F = (p_1 + ... + p_t) / t
```

Output column: `full_trigger_mean_marginal_pu`.

`F` summarizes average modeled single-base accessibility across the complete trigger.

### Full-trigger minimum marginal accessibility

```text
F_min = min(p_1, ..., p_t)
```

Output column: `full_trigger_min_marginal_pu`.

`F_min` is a diagnostic for the least accessible base in the trigger. It is a
length-dependent extreme statistic and must not be interpreted as a joint opening
probability.

### Selected nucleation mean marginal accessibility

For each nested placement `j`, calculate:

```text
N_j = arithmetic mean of the k marginal values in placement j
```

Then select:

```text
N = max_j(N_j)
```

with the earliest 5′ placement winning an exact tie.

Output column: `nucleation_mean_marginal_pu`.

### Selected nucleation minimum marginal accessibility

For the selected placement only:

```text
N_min = minimum marginal value in that placement
```

Output column: `nucleation_min_marginal_pu`.

`N_min` is exported as a diagnostic. It is not a tie-break in either current ranking
mode.

### Balanced geometric mean

The separate balanced mode uses:

```text
G = sqrt(F * N)
```

Output column: `balanced_geometric_mean`.

All inputs are in `[0, 1]`, so `F`, `F_min`, `N`, `N_min`, and `G` are also in `[0, 1]`.
No normalization, rescaling, or batch-relative transformation is applied.

## 7. Ranking modes and deterministic tie-breaks

The candidate pool is the complete trigger enumeration. Ranking does not change the
selected nucleation placement for a candidate.

### 7.1 `nucleation_first` — primary/default mode

Sort candidates lexicographically by:

1. higher selected nucleation mean `N`;
2. higher full-trigger mean `F`;
3. higher full-trigger minimum `F_min`;
4. earlier trigger start coordinate; and
5. lexicographically earlier target-RNA trigger sequence.

The `ranking_score` field is `N`, but the complete order is defined by all five keys.
Sequential ranks start at 1. This mode is the preserved primary behavior for the
established 35/6 and 39/9 analyses.

### 7.2 `balanced_geometric_mean` — separate sensitivity mode

Sort candidates lexicographically by:

1. higher geometric mean `G = sqrt(F * N)`;
2. higher `min(F, N)`;
3. higher `F`;
4. higher `N`;
5. lower preserved `nucleation_first_rank`;
6. earlier trigger start coordinate; and
7. lexicographically earlier target-RNA trigger sequence.

The `ranking_score` field is `G`. Every balanced result also retains the candidate's
primary `nucleation_first_rank`.

Balanced mode asks which candidates keep both mean components high. It is not a new
primary endpoint, a joint opening probability, or an efficacy model. Run it over the
same complete candidate pool as the primary mode. Reranking only a primary top-N subset
can identify the best balanced candidate in that subset, not the global balanced winner.

## 8. Worked window-count and coordinate examples

These examples illustrate enumeration and coordinates. They do not claim that the
illustrative selected nucleation placement would win without an actual RNAplfold profile.

### 8.1 35 nt trigger with a 6 nt nucleation window

Set `t = 35`, `k = 6`, and `s = 1`.

For a 100 nt target:

- trigger candidates: `100 - 35 + 1 = 66`;
- nested placements per trigger: `35 - 6 + 1 = 30`; and
- nested placement means evaluated over the full scan: `66 × 30 = 1,980`.

Consider trigger `cand-0011-0045`:

```text
target coordinates:       11–45 inclusive
internal Python slice:     [10:45]
trigger length:            45 - 11 + 1 = 35 nt
first 6 nt placement:      11–16  -> [10:16]
last 6 nt placement:       40–45  -> [39:45]
number of placements:      30
```

If positions `19–24` have the highest 6-base mean, the selected nucleation interval is:

```text
nucleation coordinates:    19–24 inclusive
internal Python slice:     [18:24]
```

If positions `19–24` and `20–25` have exactly equal highest means, positions `19–24` win
because they start earlier in the target's 5′→3′ coordinate system.

### 8.2 39 nt trigger with a 9 nt nucleation window

Set `t = 39`, `k = 9`, and `s = 1`.

For a 100 nt target:

- trigger candidates: `100 - 39 + 1 = 62`;
- nested placements per trigger: `39 - 9 + 1 = 31`; and
- nested placement means evaluated over the full scan: `62 × 31 = 1,922`.

Consider trigger `cand-0011-0049`:

```text
target coordinates:       11–49 inclusive
internal Python slice:     [10:49]
trigger length:            49 - 11 + 1 = 39 nt
first 9 nt placement:      11–19  -> [10:19]
last 9 nt placement:       41–49  -> [40:49]
number of placements:      31
```

If positions `21–29` have the highest 9-base mean, the selected nucleation interval is
`21–29` inclusive and the internal slice is `[20:29]`.

### 8.3 Comparing 35/6 and 39/9 results

Treat the two configurations as separate analyses with separate provenance. A rank from
one configuration is not directly interchangeable with a rank from the other because:

- trigger and nucleation means average different numbers of positions;
- minimum statistics become more extreme as windows become longer;
- candidate counts and coordinate endpoints differ; and
- each trigger length has a different set of nested placements.

If the scientific question requires comparison, use the same exact input sequence,
full-context profile, RNAplfold parameters, ranking mode, and prespecified comparison
rule. Do not select whichever configuration looks best after inspecting results.

## 9. Quality-control checks

A run is valid only if all applicable checks pass.

### 9.1 Input and profile QC

- sequence is non-empty uppercase `A/C/G/U` with no whitespace or normalization;
- trigger length and nucleation length are integers;
- `1 <= nucleation_length <= trigger_length <= sequence_length`;
- stride is a positive integer;
- profile length equals sequence length exactly;
- every profile value is finite and lies in `[0, 1]`; and
- the sequence hash and profile hash match the recorded inputs.

### 9.2 Enumeration QC

- actual candidate count equals `floor((n - t) / s) + 1`;
- for dense stride-1 runs, every start from 1 through `n - t + 1` occurs exactly once;
- every trigger has exactly `t` bases;
- every trigger sequence equals its source-sequence slice;
- every selected nucleation interval is nested inside its trigger;
- every selected nucleation sequence has exactly `k` bases and equals its source slice;
- the selected nucleation mean is the maximum over all `t - k + 1` placements; and
- an exact local tie selects the earliest 5′ placement.

### 9.3 Score and rank QC

- recomputed `F`, `F_min`, `N`, and `N_min` match exported values;
- `G` equals `sqrt(F * N)`;
- all candidate IDs are non-empty and unique;
- ranks are unique and complete from 1 through the candidate count;
- the recorded ranking mode and tie-break list match the applied ordering;
- balanced rows retain the correct primary `nucleation_first_rank`; and
- `joint_probability_used` and `normalization_applied` remain `false`.

### 9.4 Artifact QC

- CSV row count equals candidate count;
- provenance candidate count equals both expected count and CSV row count;
- output files are newly created or an explicit overwrite was authorized;
- implementation, input, and output hashes are recorded and rechecked; and
- the repository branch, commit, worktree status, tool versions, and effective RNAplfold
  parameters are captured with the run.

## 10. Reproducibility and provenance

The core analysis records deterministic provenance without adding a wall-clock timestamp.
For identical validated inputs and implementation, the core provenance is reproducible.
It includes:

- exact-sequence SHA-256 over ASCII bytes;
- profile SHA-256 over the validated values encoded as big-endian float64 values;
- implementation-file SHA-256;
- schema version and implementation identifier;
- sequence, trigger, and nucleation lengths;
- stride, expected candidate count, and actual candidate count;
- ranking mode and exact tie-break order;
- orientation and coordinate conventions;
- marginal aggregate and nucleation-placement semantics;
- explicit `joint_probability_used = false`;
- explicit `normalization_applied = false`; and
- caller-supplied source provenance.

The run harness should add at least:

- repository remote, branch, commit, and pre-run worktree status;
- ViennaRNA version;
- nominal and effective `FoldProfiler` parameters;
- exact input artifact names and hashes;
- prespecified analysis identifier, including `35/6` or `39/9`;
- test and QC commands with exit status; and
- run-level start/completion timestamps, if operational timestamps are required.

Use the writers in `tools.trigger_nucleation_ranking.py` for ranked CSV and provenance
JSON. They refuse accidental overwrite unless `overwrite=True` is explicit. Keep large or
dated generated analyses in the report/experiment tree rather than committing them to the
source repository. Commit the reusable procedure, code, and tests.

A minimal call is:

```python
from tools.trigger_nucleation_ranking import (
    RankingMode,
    analyze_profile,
    write_analysis_csv,
    write_provenance_json,
)

profile = profiler.profile(sequence)
analysis = analyze_profile(
    sequence,
    profile,
    trigger_length=35,
    nucleation_length=6,
    stride=1,
    mode=RankingMode.NUCLEATION_FIRST,
    source_provenance={
        "repository_branch": repository_branch,
        "repository_commit": repository_commit,
        "repository_status": repository_status,
        "rnaplfold": profiler.provenance(sequence),
        "parameter_set": "trigger35_nucleation6_stride1",
    },
)
write_analysis_csv(analysis, output_dir / "ranked_candidates.csv")
write_provenance_json(analysis, output_dir / "provenance.json")
```

Run 39/9 by changing only the prespecified length pair and its parameter-set identifier.
Run balanced mode as a second explicit analysis; do not overwrite or relabel the primary
nucleation-first result.

## 11. Interpretation limits

The procedure produces a deterministic structural-accessibility ranking under one model,
one sequence context, and one recorded parameter set. It does not establish that a
candidate will bind, activate a gate, or work in a cell.

Specifically, it does not model:

- simultaneous joint opening of all bases in a trigger or nucleation window;
- trigger-target hybridization free energy or competing intermolecular structures;
- partner concentration, association kinetics, or displacement kinetics;
- transcript abundance, RNA turnover, proteins, ribosomes, or cellular crowding;
- off-target binding, paralogues, transcriptome specificity, or toxicity;
- translation, gate folding, constructibility, or gate activation; or
- experimental efficacy or a calibrated probability of success.

An arithmetic mean can hide one or more poorly accessible bases; inspect the exported
minimum diagnostics and the per-position profile rather than treating the mean as a joint
event. Conversely, the minimum is an extreme statistic and should not replace the
prespecified rank after outcome inspection.

Finally, "full context" means the full **supplied** sequence, not necessarily the complete
biological transcript or plasmid context. Candidates near either sequence boundary may
change materially when omitted 5′ or 3′ flanking sequence is restored. Record that
limitation and rerun with the biologically appropriate context when it is available.

## 12. Related documentation

- [`trigger-nucleation-ranking.md`](trigger-nucleation-ranking.md) describes the reusable
  utility and its ranking modes.
- [`triggers.md`](triggers.md) describes the separate production trigger-selection stage
  and gate-aware evidence.
- [`../tools/trigger_nucleation_ranking.py`](../tools/trigger_nucleation_ranking.py) is the
  executable source of truth if this document and the implementation ever disagree.
