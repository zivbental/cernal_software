# Production trigger selection

Source baseline: `c1bb92cc085a6bad272298b81bda28c22b1d57f5` (16 October 2026).
See [status](status.md) for release evidence and pending work.

A trigger is a specific 5′→3′ target-RNA interval, not a whole gene or a synonym for its
reverse complement. Source sequence, interval and folding context are essential evidence.

## Input routing

[`pipeline._direct_trigger`](../src/engine/pipeline.py) preserves the entire normalized
paste as one trigger when its length is at most `max(constraints.trigger_lengths)`.
The minimum direct length is 20 nt and the maximum supplied transcript length is 10,000
nt. A short trigger has only its supplied context; its accessibility is not a measurement
in an unseen full transcript. Exact triggers still undergo configured motif screening.

Longer direct inputs and resolved gene transcripts are scanned. DE-selected genes use
the same [`TriggerScorer`](../src/engine/stages/triggers.py). Current gate-aware scanning
accepts exact 30, 33 and 36 nt footprints, mapping to 12, 15 and 18 nt toeholds. Other
scanned lengths fail validation rather than silently changing the mechanism.

## Evidence and shortlist

The scorer profiles each full supplied transcript once. It enumerates configured windows,
checks motifs, records GC, AUG/stop locations, window MFE and source gene log2 fold change.
For each window:

- `openness` is mean one-base marginal P(unpaired).
- `accessibility` is minimum one-base marginal P(unpaired), not a joint probability.
- Gate-aware evidence includes selected contiguous 8 nt joint-opening probability (P8),
  seed trials, terminal-20 joint opening and opening-energy diagnostics, and effective
  RNAplfold model provenance.

Candidates are ranked within footprint buckets by higher selected P8, lower terminal-20
opening free energy per nucleotide, then higher terminal-20 mean marginal openness.
Stable coordinate/sequence tie-breaking preserves determinism. The per-gene budget
(`TOP_K_PER_GENE = 50`) is allocated round-robin across footprints. This avoids allowing
one footprint to exhaust the shortlist simply because it has more seed placements.

Adapters without a joint-probability API retain a documented marginal-only compatibility
path. An error from an adapter that does support joint probabilities is not replaced by
a fabricated value. Production uses the injected `FoldProfiler`.

The terminal-20 opening diagnostic uses `-RT ln(max(P20, 1e-12)) / 20` with the effective
model temperature. Joint opening is a mechanistic model hypothesis, not a probability of
successful binding or cellular expression. Scores from different model configurations or
selection methods must not be pooled without identifying those differences.

## What selection does not establish

No transcriptome-wide off-target scan runs in this stage. No missing scan should be
reported as zero risk. Window screening cannot prove the assembled switch is valid:
`SwitchDesigner` and `SwitchValidator` perform later compatibility and construct checks.
The pipeline distinguishes incompatible trigger sets from invalid generated designs in
its warnings because these counts have different units.

The final search is also limited by a retained validated-design budget (20 by default),
in deterministic generation order. A trigger's shortlist position and its final
payload-context candidate rank are different quantities.

## Coordinates and research analyses

Internal intervals are zero-based and half-open; assert that the source transcript slice
matches the reported trigger. A complementary recognition strand is a separately labeled
molecule. RNAplfold's underlying table is indexed by one-based interval end and interval
length; the wrapper performs the conversion.

The offline [trigger/nucleation ranking utility](trigger-nucleation-ranking.md) and its
[detailed procedure](window-selection-procedure.md) average marginal probabilities and
use different ranking rules. They are not the production gate-aware joint-P8 shortlist.

## Regression checks

Relevant tests: `tests/engine/test_triggers.py`, `test_gate_aware_triggers.py`,
`test_folding_configuration.py`, and `tests/test_trigger_nucleation_ranking.py`.
These pin computational definitions and provenance, not biological efficacy.

## Historical evidence

The [preserved design and development record](archive/scientific-design/triggers.md)
contains earlier measurements, alternatives and decisions. It is historical evidence,
not current implementation guidance.
