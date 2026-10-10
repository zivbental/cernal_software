# PR #65 review corrections

Reviewed starting commit: `984bdd3a2e7edf25c6ed939d401700c659f9d5e0`.
Base rechecked on 2026-10-10: `origin/main` remains `e8e560d`.
CRISPR correction version: `0.12.2-research`.

## Correctness fixes

1. **Impossible reference pairs.** `FoldEngine.constrained_free_energy` checks balanced constraints and validates each requested pair against the compound's model: allowed pair type, `noGU`, intramolecular minimum loop size, and maximum pair span. A well-formed but impossible constraint has an empty ensemble (`+inf` internal free energy, hence probability zero). Malformed syntax raises `ValueError`. Regional defect retains its expected-incorrect-base definition; it does not discard or reward impossible reference pairs.
2. **Valid interstrand pairs.** Connected calculations validate `FcAB` and `FAB`. They no longer reject a valid connected state because isolated `FA`/`FB` cannot satisfy an explicitly intermolecular constraint. Minimum hairpin span is applied only within the same strand.
3. **Inherited CI blocker.** The eukaryotic antisense fixture no longer passes the removed `off_target_penalty` and `segment_specificity` fields. Once those tests could run, they exposed another existing error: `euk_antisense` referenced removed private constants on `AntisenseNotGate`. It now calls the existing shared `binding_energy_factor` in `gates/tools/binding.py`, eliminating the duplicate sigmoid. Its version is `0.1.1`. No assertions were removed or weakened to obtain a pass.

No objective formula, selected weight, threshold, candidate alphabet, or ON/OFF definition was changed. `CrisprGate.available` remains false. The normal application pipeline has not been enabled for CRISPR.

## Regressions and measured results

Real ViennaRNA 2.7.2 results:

| Case | Corrected result |
| --- | --- |
| `region_defect('GC', '()')` | `1.0` |
| `region_defect('GCAAAA', '()....')` | `1/3` |
| `constraint_probability('AAAAA', '(...)')` | `0.0` |
| `constraint_probability('GGGG&CCCC', '(......)')` | `0.8547770532704606` |
| Original 80-nt scaffold, regional defect | `0.3159495454032488` |
| Same scaffold, native normalized ensemble defect | `0.3159495168921741` |

The full-workbench regression substitutes the review's `GC` / `()` scaffold in the demo and evaluates all 480 guides with real folding. It returns `no_feasible_candidates`, zero inner-feasible guides, zero measurement failures, and no recommendations. Every computed OFF scaffold defect is 1.0. A measured rejection remains distinct from a failed computation.

Tests also cover malformed parentheses, the absence of a hairpin-span restriction across the strand break, default GU pairing, and modified active-model minimum span, maximum span, and `noGU` settings.

Focused run: **70 passed, 110 subtests passed** (26.41 s).
Full backend suite: **2147 passed, 110 subtests passed** (289.15 s); no failures or errors.
Ruff lint/format, Django checks, and the migration check pass. The API surface index was regenerated.

## Decisions still awaiting maintainer/user input

- **Research export policy:** no exemption from the existing application sequence-release policy has been inferred. The reviewer requests an explicit maintainer choice between applying that boundary to the standalone research CLI and authorizing a documented private-research exemption. Until decided and implemented, the existing CLI's sequence export remains an unresolved review item; this correction does not claim to resolve it.
- **PR scope:** the workbench spans domain, scoring, stages, and pipeline as well as the gate. The review notes a conflict between the older gate-only scope guide and the operative layered implementation guidance. Acceptance of the broader scope or a split into dependency PRs remains a maintainer decision. No repository rules were edited to manufacture an exception.
- **Hosted CI:** these corrections are local pending the author's review. A GitHub CI run against the eventual uploaded commit is still required. The earlier PR's checks describe the earlier head only.

## Documented limits retained

ON is conditional on an already connected complex, not a concentration-weighted tube. Sequence quality inputs, experimental calibration and biological validation remain external. The million-candidate check verifies enumeration, not a million folding evaluations. Inner-loop cancellation/resume is not implemented; progress is between pairs. These were documented limitations in the review, not part of its two reproduced correctness defects.

## API reference

The implementation follows the active model fields and constraint semantics in the [official ViennaRNA Python API](https://viennarna.readthedocs.io/en/latest/api_python.html) and connected-partition definitions in [Global partition functions](https://viennarna.readthedocs.io/en/latest/partfunc/global.html). Regression results above come from the pinned local runtime, not from documentation examples.
