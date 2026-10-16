# Integrating scientific engine contributions

Source baseline: `c1bb92cc085a6bad272298b81bda28c22b1d57f5` (16 October 2026).
See [status](status.md) for release evidence and pending work.

Integrate against the current executable path, not a historical “fill every stub” list.
Many scientific components are implemented; some research classes are intentionally
excluded from production. The [engine guide](engine.md) and [status](status.md) separate
those scopes. Follow [CLAUDE.md](../CLAUDE.md) for repository contribution rules.

## NucSyn research-data boundary

The [NucSyn guide](nucsyn.md) documents the existing ranked-CSV notebook workflow and
upstream attribution. It is not the production gate generator or a runtime adapter.
Do not silently substitute NucSyn scores for CERNAL metrics, assume historical exports
were produced by the newest release, or bundle/expose the external executable without
checking the applicable permission scope.

## Before changing a calculation

1. Find the shared implementation and its callers. Read `pipeline.build_tools`,
   `run_pipeline`, `client._installed_capabilities` and the relevant stage/gate tests.
2. Identify the biological quantity, units, coordinates, context, missing-data policy
   and evidence needed to interpret it. Write down the difference from the old quantity.
3. Reuse injected tools and typed records. Keep platform imports at `engine.client` and
   `engine.contract`; do not create an independent folding or scoring implementation.
4. Distinguish an available research implementation from a supported application route.
   Registry flags, pipeline exclusions, host rules and physical compiler guards all apply.

## Where contributions belong

| Responsibility | Existing home |
|---|---|
| DE parsing and reference lookup | `inputs.py`, `transcriptome.py` |
| Gene filtering and budget allocation | `stages/genes.py` |
| Transcript-context trigger selection | `stages/triggers.py`, `stages/folding.py` |
| Gate construction and raw measurements | `gates/` and injected `gates/tools/` |
| Construct validation and assembly | `stages/switches.py`, `stages/plasmids.py` |
| Normalization, weighting and filters | `scoring/` |
| Wiring, cancellation, budgets, provenance and artifacts | `pipeline.py` |

Research utilities may live separately, such as
[`tools/trigger_nucleation_ranking.py`](../tools/trigger_nucleation_ranking.py), when they
answer a distinct question. Do not silently substitute a marginal-accessibility research
ranking for production joint-opening selection.

## Scientific change checklist

- Return raw measurements under the declared profile vocabulary. Unknown metric names
  can be skipped; a plausible misspelling can bypass both ranking and a hard filter.
- Use `None` for unavailable evidence. Never convert failed calculations into perfect
  zero leakage or a clean off-target result.
- Preserve source sequence hashes, reference IDs, parameter/model versions and seed.
- Add focused regression tests, boundary/house-rule tests and an integration case that
  proves the new computation is actually reachable through the intended route.
- Version scientific changes and update relevant fixtures deliberately; a refactor must
  not silently move stored scores.
- Label computational predictions, empirical measurements and proposed validation
  separately. Document new limitations before advertising broader capability.

## Release gates

A physical multi-input or inhibitory compiler, sample-level discrimination workflow,
transcriptome interaction screen, or newly enabled chemistry needs an explicit reviewed
integration contract. Merely exposing a class or concatenating sequences is insufficient.
[Off-target analysis](off-target-analysis.md) retains the research proposal without claiming
it is deployed. Pending pull requests and dated checks belong in [status](status.md).

Run focused tests first, then `uv run pytest tests/engine -q`, relevant platform integration
tests and `uv run ruff check .`. Use [development](development.md) for environment and
workflow setup. Never use old machine-specific inspection paths or historical test counts
as current evidence.

## Historical evidence

The [preserved design and development record](archive/scientific-design/integration.md)
contains earlier measurements, alternatives and decisions. It is historical evidence,
not current implementation guidance.
