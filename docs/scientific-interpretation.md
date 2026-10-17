# Interpreting current application metrics

These definitions describe the LocalEngine application path at audit baseline
`2baa75a7f0dc89f9aafac58dad50da5982f3f56a`. They do not transfer notebook-specific
observables or pending research branches into the application's scoring contract.
The bacterial AND extension below describes `local-0.14.0-prokaryotic-and-equilibrium`.
The metrics are computational proxies. No established transcriptome-wide off-target
or wet-lab validation, or calibrated cellular success probability, is claimed.

## Leakage and dynamic range

### Bacterial two-input AND extension

`prokaryotic_toehold_and` uses a different observable from the single-input family:
the joint probability that the entire 30-nt initiation window is unpaired. Its
coordinates are -17 through +13 relative to start-codon A at +1, with no zero base.
`predicted_leakage` is the largest probability over 00, 10 and 01; ON is 11.
`dynamic_range` is ON/worst-OFF, and `state_separation` is its log2 equivalent
derived from the opening-energy difference with the actual model temperature.
These are equilibrium structural proxies, not protein output or kinetic rates.

Pair-aware discovery and finite search budgets precede a short output-prefix
screen. The shared scoring profile selects a small full-output finalist cohort;
only complete switch-plus-output CDS measurements passing all 22 structural checks,
shared scoring filters and construct checks receive final ranks. Prefix failures
can exclude designs a complete output might rescue. Unchecked screen survivors
remain explicit, unranked `not_evaluated_budget` records. The finite search does
not establish global optimality or a complete set of feasible designs.

The retained 7.2 kcal/mol ON ceiling originally came from a 31-nt single-input
calibration, not this exact 30-nt window. An explicit recheck of the same 77 Green
switches above 20-fold measured ON/OFF gives maximum computed ON cost 7.048805 for
30 nt and 7.204948 for 31 nt. The threshold is retained, not retuned; this does not
validate an AND or full-CDS context. See the
[recorded coordinate audit](evidence/prokaryotic-and/README.md).

### Single-input families (audit baseline)

In [`ToeholdGate.evaluate_design`](../src/engine/gates/toehold.py), a loop-layout
design measures `predicted_leakage` as the mean marginal unpaired probability over
`[aug_index, aug_index + 3)`: **AUG only, three bases**. For each base it subtracts
the sum of its pairing probabilities from one, then averages the three values.
It is not the joint probability that all three bases are open simultaneously, nor
a measurement over the wider bacterial ribosome-binding/initiation footprint.

The bacterial target structure leaves AUG as an **unpaired bulge**. Thus low
ensemble defect relative to that target and low AUG accessibility are different
objectives; a target-like fold does not establish suppression of translation.
Do not interpret this metric as measured basal protein expression or silently
rename it as wider-footprint accessibility. A different biological proxy requires
scientific evidence and a separately reviewed algorithm/version change.

For the trailing eukaryotic layout, the evaluated region is the toehold-plus-stem
span, not AUG. A flagged eukaryotic Kozak reverse-complement interaction forces
OFF accessibility to 1.0 conservatively. These layout-specific proxies are not
interchangeable measurements of an experimentally calibrated leakage rate.

`dynamic_range = on_accessibility / max(off_accessibility, 1e-3)` in this path.
The **0.001 denominator floor** prevents division by zero and limits how much a
very small OFF estimate amplifies the ratio. For example, ON 0.6 and OFF 0.0001
yield 600, not 6000. The default scoring range `[1, 500]` is a normalization range,
not a statement that raw ratios cannot exceed 500. This is an accessibility ratio,
not measured ON/OFF protein fold change.

## Structural checks

[`SwitchValidator.validate`](../src/engine/stages/switches.py) checks sequence and
target-structure integrity, then stores length-normalized ensemble defect as
`structure_deviation`. The folding adapter returns expected incorrectly paired
bases; division by sequence length produces a fraction. Nonfinite values and values
outside `[0, 1]` fail validation. There is **no calibrated functional cutoff**:
passing this check establishes computational validity, not functional switching.
The target dot-bracket drawing is a design target, not necessarily the MFE structure.

## Success heuristic and ranking

The historical field name `predicted_success_rate` remains for API compatibility.
[`binding_energy_factor`](../src/engine/gates/tools/binding.py) computes
`1 / (1 + exp((binding_dg - (-15.0)) / 2.0))`, with its exponent clamped to
`[-50, 50]`. `weakest_binding_confidence` takes the minimum across required inputs.
The value 0.5 at -15 kcal/mol is a chosen reference point, **not a measured 50%
chance of cellular success**. A bounded sigmoid is not a calibration experiment.

The weighted score ranks candidates under the selected profile and constraints.
Neither that score, `predicted_success_rate`, a passed filter nor a completed run
establishes efficacy, specificity, biological safety or readiness for synthesis.
Missing metrics mean not measured or not applicable, not zero.

## Scope of evidence

Single-gate orthogonality is not a transcriptome-wide off-target screen. A sequence
screening or release-policy decision is also distinct from biological specificity.
Research workbenches can use other windows, joint opening probabilities, sampling
or AND-state comparisons; identify their exact revision and definitions separately.
PR 68 research reports and PR 69 screening UI were unmerged at the audit baseline.

Software regression tests can establish that the implementation follows these
definitions. Functional cutoffs and cellular probabilities still require suitable
experimental data and calibration; no such result is fabricated by this correction.
