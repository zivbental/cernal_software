# Endogenous CRISPR workbench

Run from the repository root:

```bash
uv sync --extra dev
uv run python tools/run_crispr.py examples/crispr/demo.json --output var/crispr-demo
uv run pytest tests/engine/gates/test_crispr.py -q
```

`demo.json` is a synthetic software exercise with a toy scaffold and invented
external scores, the selected inner/outer weights and the selected CRISPR thresholds. Its result is not experimental validation. `your_model.template.json`
contains the user's 80-nt scaffold, matching reference structure and null placeholders for missing scientific inputs;
the runner refuses incomplete inputs. See the Hebrew docs/crispr-workbench.he.md for the complete mapping from equations to code and input definitions.

The model evaluates free g in OFF and connected gT in ON. Both accessibility values
are joint partition-function ratios for all 20 spacer bases being unpaired. ON is
conditioned on complex formation: binding does not force spacer opening, and the
model does not predict what fraction of guides bind in a tube. No concentrations
are required; old guide_molar/trigger_molar inputs must be removed. Output identifies
model off-g-on-connected-gT-v1, with no bound_fraction field. Standard binding free
energy remains G(gT)-G(g)-G(T), computed by the shared FoldEngine.
The model assumes equilibrium naked RNA and exhaustively searches
all 2**m binary spacer/trigger-complement combinations per geometry (m <= 20). It does not implement homodimers, a genome-wide specificity
predictor, experimental calibration, unrestricted four-base optimization, or platform UI integration.
The confirmed geometry uses B=20 nt, complementary E/E-prime=10 nt each, and
BT lengths 10/15/20 nt. All three are searched for each loop length from 14 to 32
in steps of 2: 30 architecture templates. The intended trigger footprint is
BT-B-Eprime-loop, so trigger length is BT+20+10+L (25 distinct lengths, 54–82 nt).
The loop is the reverse complement of the first L bases of the trigger window;
templates specify lengths only and explicit loop sequences are rejected.
The demo uses an 82-nt synthetic transcript and stride 100 to produce one window
per length; the default research stride is 1. Complementarity is a design rule,
not evidence of opening kinetics or biological activity.

`result.json` preserves up to `guide_audit_limit` audit records (default 1000),
all pair winners and aggregate rejection counts. This cap never limits search.
The thermodynamic constraint cache is bounded to 4096 entries. `ranked.csv`
contains top surviving pairs. Research conclusions require valid references and calibration.

API sources used for the thermodynamic adapter:

- https://viennarna.readthedocs.io/en/latest/partfunc/global.html
- https://viennarna.readthedocs.io/en/latest/grammar/constraints/hard.html
- https://docs.nupack.org/analysis/ (complex versus tube distinction; no NUPACK dependency)

The standalone workbench constructs tools through engine.pipeline and reuses
engine.sequences and engine.artifacts. J/Phi are deliberately separate from DEFAULT_V1.

Thermodynamic measurements stop at the first failed gate: A_OFF, d_OFF, A_ON, d_ON.
The demo uses a repetitive synthetic trigger solely to keep full enumeration small.

Selected thresholds are defined once in `src/engine/domain.py`, in
`CrisprObjective` under `# Selected thresholds`: tau_off=0.05, tau_on=0.50,
epsilon=0.10. Both example inputs inherit these values. Explicit `objective`
fields override defaults per run. `result.json` records the effective values
in `objective_parameters`.

The selected inner weights are w_on=0.4, w_off=0.6 and
w_energy=w_accessibility=0.5 in both example configurations. Lambda is not an
input: the workbench computes mean |JE| / mean |JA| from every inner-feasible
guide across all pairs admitted by the preliminary external checks. Measurements
are spooled to temporary disk storage; after the global scale is known, J winners
and Phi rankings are selected without refolding. Audit truncation never changes
this batch. Output includes lambda_calculation with scope, count and value.
An empty batch returns no candidates and lambda=null. A zero denominator raises
an explicit error; a zero numerator with positive denominator gives lambda=0.
Legacy scale_lambda input is rejected. Scores depend on the batch being ranked.

The revised outer objective uses only Q_S=v_on*eta_on+v_off*(1-eta_off),
with Phi=(W_S*Q_S+W_T*Q_T)*max(0,J_best). The original J_best is retained;
j_positive and selectable explain the clamp and recommendation decision.
Feasible pairs with J_best<=0 retain Phi=0 and bottom ranks in pairs, but are
excluded from top_candidates and ranked.csv. If none has positive J_best,
status is no_positive_switch_candidates. Hard-gate failures remain rejected.
Remove legacy spacer_score_mode input; no alternative formula is supported.

Selected outer parameters: v_on=0.4, v_off=0.6, W_S=0.6, W_T=0.4,
o_max=0.2. Both examples store these in objective. Off-target risk exactly 0.2
passes; greater values reject the pair before folding. eta_on, eta_off and Q_T
are upstream inputs, already normalized to [0,1]; this workbench validates and
uses them without computing or renormalizing them. A direct connection to the
upstream pipeline is separate from this explicit-input workbench.

Measurement failures are distinct from hard-gate rejections: audit entries use
feasible=null, evaluation_status=measurement_failed and a separate error field.
Partial observables are retained. Global and per-pair error counts survive audit
truncation. Any such failure returns measurement_incomplete; no batch lambda,
final scores or recommended winners are computed from incomplete measurements.
The CLI still writes diagnostics and an empty ranked.csv. measurement_complete
covers attempted measurements. Missing or invalid upstream inputs raise ValueError before folding; valid off-target precheck rejections remain in pairs.
PAM scanning remains SpCas9 NGG on both strands, with a 20-nt protospacer inside
the supplied activation window. The PAM itself must be in the supplied DNA but
need not be inside the protospacer window. Cas type and targeting window are not inferred.

Input preflight (0.12.1) validates JSON shapes, sequence alphabets, coordinates, scaffold/reference consistency, complete template geometry, finite numerical parameters and score coverage. Every supplied eta_on/eta_off/q_trigger must be a numeric value in [0,1]; booleans, strings, null, NaN and infinity are rejected. Every scanned spacer and trigger window that enters a pair must have scores under its coordinate-based identifier. Missing scores raise a contextual error before any candidate folding. No upstream score is replaced or inferred.
