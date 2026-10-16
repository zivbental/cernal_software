# RNA off-target analysis: current scope and research proposal

Source baseline: `66a6d265577810e8943709f3e5bb21bffdab212c` (16 October 2026).
See [status](status.md) for release evidence and pending work.

No transcriptome-wide RNA interaction scan is integrated into the production application
at this baseline. The old `src/engine/stages/off_target.py` interface is absent; neither
`TriggerScorer` nor `SwitchValidator` receives or calls that scanner. Run evidence reports
`off_target_screen: unmeasured`. An unavailable analysis must not be interpreted as zero
risk, and a sequence-release check is not a biological specificity assessment.

## Separate questions and orientation

Two physically distinct analyses need separately labeled evidence:

- **Cross-activation candidates:** non-cognate RNAs that could bind a gate's recognition
  region. If target trigger T binds region B = reverse-complement(T), another RNA
  resembling T could bind B.
- **Trigger sequestration candidates:** RNAs that could bind the intended trigger T,
  generally resembling B rather than T.

Supply actual molecules in their physical 5′→3′ orientation. A matching substring does
not by itself establish antiparallel interaction, gate activation or material depletion
of free trigger. Those interpretations also depend on gate architecture, concentration,
localization, kinetics and experimental context.

## Preserved proposal, not deployed capability

The [complete research proposal](archive/scientific-design/off-target-analysis.md)
retains the interaction contract, feasibility spike, backend considerations, coordinate
rules, intended-target handling, caching/batching strategy, test plan and primary
bibliography. It proposes IntaRNA 3.4.1 as a feasibility-gated candidate backend. This is
not a statement that it is installed, integrated, benchmarked successfully or chosen for
production. The proposal's description of the then-existing scanner is historical.

Any future result must include query context and allowed interaction region, reference
identity and digest, source interval, coordinate/strand semantics, tool/model version,
energy components, accessibility assumptions, search/resource limits and whether the
search was heuristic or exact. Preserve candidate-level evidence and distinguish an
unperformed search from a performed search with no retained hits.

A backend should accept explicit reference collections rather than silently equating a
host enum with a full cellular transcriptome. Non-Human bundled references are CDS-only;
Human representative mature transcripts do not exhaust all expressed isoforms. Reference
coverage and intended-source exclusion therefore need explicit scientific review.

## Integration acceptance

A future interaction engine must have a tested orientation/coordinate contract, honest
incomplete-search outcomes, feasible batching and a reviewed interpretation layer per
chemistry. CRISPR genomic off-target analysis is a separate problem. No universal leakage,
translation or calibrated gate-success probability should be attached to interaction
energy alone. Follow [integration](integration.md) and [status](status.md) for reviewed
application changes and pending work.

## Historical evidence

The [preserved design and development record](archive/scientific-design/off-target-analysis.md)
contains earlier measurements, alternatives and decisions. It is historical evidence,
not current implementation guidance.
