# Scientific engine: implemented application path

Source baseline: `66a6d265577810e8943709f3e5bb21bffdab212c` (16 October 2026).
See [status](status.md) for release evidence and pending work.

CERNAL's `LocalEngine` compiles supplied sequences or differential-expression results
into computationally ranked single-input toeholds or one eukaryotic two-input AND
for Human/yeast DE runs. It does not
establish cellular efficacy, disease discrimination or biological safety. Read
[scientific interpretation](scientific-interpretation.md) before interpreting scores.

## Boundary and records

Platform code calls only [`engine.client`](../src/engine/client.py) and
[`engine.contract`](../src/engine/contract.py). Engine code has no Django dependency.
`JobRequest` and `JobResult` carry the request, candidates, artifacts, warnings and
provenance across this boundary. Internal stages use typed domain records, not exported
CSV files as an interchange format. [Architecture](architecture.md) covers deployment;
[API](api.md) covers the application surface.

`LocalEngine.run` converts expected `EngineError` failures and cancellation into terminal
results. Programming errors propagate. Progress callbacks return `False` to request
cooperative cancellation. `MockEngine` is not an application backend in this checkout.

## Execution map

[`pipeline.py`](../src/engine/pipeline.py) is the executable wiring authority. Several
older module comments describe earlier milestones; inspect calls and guards as well as
class declarations.

| Step | Current behavior | Source |
|---|---|---|
| Validate | Normalize one direct sequence; validate mode, host, configuration and budget | `client.validate_job_configuration`, `pipeline.run_pipeline` |
| Resolve input | Direct sequence, bundled reference gene, or parsed DE results | `inputs.py`, `transcriptome.py` |
| Select genes | DE filters and deterministic budgeted shortlist, with missing-evidence warnings | `stages/genes.py` |
| Select triggers | Short direct input stays one trigger; longer input uses gate-aware scanning | `stages/triggers.py` |
| Design/validate | Compatible single-input toeholds or supported eukaryotic AND; motifs, structural and sequence checks | `gates/toehold.py`, `stages/switches.py` |
| Assemble/evaluate | Each retained gate is paired with every requested output; evaluation includes switch–payload context | `stages/plasmids.py`, `pipeline.py` |
| Score/export | Raw metrics, hard filters, deterministic ranks, release-aware artifacts | `scoring/`, `safety.py`, `artifacts.py`, `pipeline.py` |

The default budget retains 20 validated gate designs in deterministic generator order;
this is a compute-limited search, not proof of a globally optimal sequence. Requested
outputs are alternatives, not simultaneous multi-output logic.

## Capabilities and research boundaries

All four hosts (`ecoli`, `yeast`, `human`, `c_acnes`) have bundled references and direct,
`gene` and `de` input routes. Available application families are `toehold`,
`prokaryotic_toehold`, `eukaryotic_toehold` and `eukaryotic_toehold_and`, subject to
host and input-mode compatibility. [AND guide](and-gate.md) specifies the two-input route.
`LocalEngine.capabilities()` combines registry declarations with pipeline restrictions;
a class's `available` flag alone is insufficient.

Generic/prokaryotic research AND and antisense remain excluded through
`_UNBUILDABLE_FAMILIES`; CRISPR's application family is unavailable. The supported
exception is one eukaryotic AND in DE mode: Human/yeast, two selected up-regulated
gene inputs, `max_triggers=2`, `max_circuit_gates=1`, without mixed families. Aliases
resolve canonically while preserving two-window multiplicity. Single-input defaults
remain unchanged. This is not a general physical AND/OR/NOT compiler, observed
confusion-matrix workflow or transcriptome-wide off-target screen.

## Shared scientific tools

`pipeline.build_tools` constructs the run's folding adapter, RNAplfold profiler, motif
screener, codon optimizer, translation tool and plasmid builder. Tools are injected;
shared calculations should not be duplicated in stages or gate families.

- [`gates/tools/folding.py`](../src/engine/gates/tools/folding.py): cached design-side
  folding and ensemble calculations using an explicit immutable folding model.
- [`stages/folding.py`](../src/engine/stages/folding.py): full supplied-sequence local
  marginal and joint opening probabilities, with effective model provenance.
- [`sequences.py`](../src/engine/sequences.py): alphabet, complement, translation,
  windows and sequence statistics.
- [`scoring/profiles.py`](../src/engine/scoring/profiles.py): metric vocabulary, units,
  missing-value policies and thresholds. `DEFAULT_V1` is the Python constant name;
  its current profile version is `v3-computational-proxies`.
- [`collaborations.md`](collaborations.md): pinned AIS-China codon-reference adapter
  and attribution; [`plasmids.md`](plasmids.md): construction and parts provenance.

Use uppercase RNA internally, zero-based half-open coordinates, kcal/mol energies,
percent GC and explicitly distinguished marginal versus joint probabilities. Unknown
measurements remain `None`. A score is neither a calibrated success probability nor an
experimental validation result.

## External research design inputs

[NucSyn](nucsyn.md) supplies the external ranked designs named in the offline eukaryotic
AND notebook. That notebook reuses CERNAL folding tools for downstream analysis, while
the production generator above constructs its own candidates. Producer scores, notebook
energy comparisons and production scores must retain separate provenance.

## Verification

Use `uv run pytest tests/engine -q` for engine regression tests, and the focused tests
listed in the subject guides. Tests establish implemented behavior within their scope;
they do not validate biological efficacy. Runtime versions, reference selection, input
checksums and model configuration must accompany a reported scientific result.

## Historical evidence

The [preserved design and development record](archive/scientific-design/engine.md)
contains earlier measurements, alternatives and decisions. It is historical evidence,
not current implementation guidance.
