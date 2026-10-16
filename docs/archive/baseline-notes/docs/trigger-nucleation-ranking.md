# Trigger/nucleation marginal-accessibility ranking

**Status:** reusable offline/research analysis, built and tested.

`tools/trigger_nucleation_ranking.py` is the repository home for the ranking logic that
was previously embedded in dated report-run scripts. It consumes an exact target RNA and
an already-computed one-base marginal P(unpaired) profile, enumerates trigger windows,
selects the best nested nucleation window, and returns deterministic ranks plus
provenance.

This utility is deliberately separate from the production
`engine.stages.triggers.TriggerScorer`. The production scorer ranks exact gate footprints
with gate-aware joint P8 evidence, terminal-20 opening diagnostics, motif screening,
off-target evidence and construct design constraints. This analysis answers a narrower
research question about arithmetic aggregates of **marginal** RNAplfold accessibility. It
must not be substituted for the production stage or described as a biological-success
model.

## Input and coordinate contract

- `sequence` is non-empty uppercase RNA containing only `A`, `C`, `G` and `U`.
- The sequence is the supplied target/sense strand in its provided 5′→3′ orientation.
  The utility never reverse-complements or normalizes it.
- `profile` contains one finite value in `[0, 1]` for every sequence position. Use
  `FoldProfiler.profile(full_sequence)` so every candidate is scored in the same full
  sequence context.
- Internal slices are zero-based and half-open. Candidate outputs are one-based and
  inclusive.
- The default stride is one, so a sequence of length `n` and trigger length `w` produces
  `n - w + 1` candidates.

For each trigger window, the utility evaluates every contiguous nested nucleation window.
It retains the window with the highest arithmetic mean marginal P(unpaired); an exact tie
selects the earliest 5′ placement. Trigger-wide and nucleation values remain separate.
Neither is a joint opening probability.

## Ranking modes

### `nucleation_first` — default and preserved primary behavior

Candidates are ordered lexicographically by:

1. higher selected nucleation-window mean marginal P(unpaired);
2. higher full-trigger mean marginal P(unpaired);
3. higher full-trigger minimum marginal P(unpaired);
4. earlier trigger start;
5. lexicographically earlier target RNA sequence.

This is the migrated nucleation-first rule. It remains the default. `ranking_score` stores
the primary nucleation component, but the complete order is the lexicographic rule above.

### `balanced_geometric_mean` — explicit sensitivity mode

The balanced score is:

`G = sqrt(F * N)`

where `F` is full-trigger mean marginal P(unpaired) and `N` is selected nucleation mean
marginal P(unpaired). Candidates are ordered by:

1. higher `G`;
2. higher `min(F, N)`;
3. higher `F`;
4. higher `N`;
5. lower preserved `nucleation_first_rank`;
6. earlier trigger start;
7. lexicographically earlier target RNA sequence.

Every result retains `nucleation_first_rank`, so a balanced analysis is auditable against
the primary behavior rather than silently rewriting it.

## What the balanced question means

The balanced mode asks: **which candidate keeps both trigger-wide and nucleation marginal
accessibility high, instead of prioritizing nucleation accessibility first?** The geometric
mean penalizes a low component more strongly than an arithmetic mean.

It is a separate sensitivity analysis, not a calibrated efficacy score and not a new
production default. Its candidate pool matters: reranking a nucleation-first top-200 table
finds the best balanced candidate **within that retained subset**. It cannot establish the
global balanced winner. For a global answer, run both modes over the same complete dense
candidate set before any top-N presentation filter.

## Use with the existing FoldProfiler API

The caller owns and injects the profiler; the ranking utility does not create a second
folding adapter or import ViennaRNA.

```python
from tools.trigger_nucleation_ranking import (
    RankingMode,
    analyze_profile,
    write_analysis_csv,
    write_provenance_json,
)


def run_analysis(sequence, profiler, repository_commit, output_dir):
    profile = profiler.profile(sequence)
    analysis = analyze_profile(
        sequence,
        profile,
        trigger_length=35,
        nucleation_length=6,
        mode=RankingMode.NUCLEATION_FIRST,
        source_provenance={
            "repository_commit": repository_commit,
            "rnaplfold": profiler.provenance(sequence),
        },
    )
    write_analysis_csv(analysis, output_dir / "ranked_candidates.csv")
    write_provenance_json(analysis, output_dir / "provenance.json")
    return analysis
```

Run the balanced question with a second explicit call using
`RankingMode.BALANCED_GEOMETRIC_MEAN`; do not mutate or relabel the nucleation-first result.

## Provenance and artifacts

The core provenance is deterministic and records:

- exact sequence SHA-256;
- a SHA-256 over the validated profile encoded as big-endian float64 values;
- implementation-file SHA-256 and schema version;
- lengths, stride, candidate count and selected mode;
- coordinate, orientation, aggregate, nucleation-placement and tie-break semantics;
- explicit `joint_probability_used = false` and `normalization_applied = false`;
- caller-supplied source provenance.

The caller should add the repository branch/commit/status, `FoldProfiler.provenance(...)`,
input artifact hashes and any prespecified parameter-set identifier to `source_provenance`.
Do not put secrets in that mapping. The core intentionally does not add a wall-clock time,
so identical inputs and code produce identical provenance; a run harness may record its own
start/completion times separately.

The CSV and JSON writers refuse to overwrite existing files unless `overwrite=True` is
passed explicitly. Generated CSVs, plots and immutable run directories belong under the
report/experiment tree, not in Git. This repository commits the reusable code, tests and
semantics only. The implementation uses the standard library and adds no dependency or
environment requirement.

## Interpretation limits

Marginal RNAplfold accessibility is equilibrium structural-model evidence for an isolated
sequence under recorded parameters. It does not model hybridization energy, partner
concentration, kinetics, cellular context, off-targets, translation, gate activation or
efficacy. Boundary candidates are especially sensitive to missing transcript or plasmid
flanking context.
