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
| Synthetic 9-nt demo scaffold, regional defect | `0.3159495454032488` |
| Same 9-nt scaffold, native normalized ensemble defect | `0.3159495168921741` |
| User-supplied 80-nt scaffold, regional defect | `0.2695359514470913` |
| Same 80-nt scaffold, native normalized ensemble defect | `0.2695371710538431` |

The full-workbench regression substitutes the review's `GC` / `()` scaffold in the demo and evaluates all 480 guides with real folding. It returns `no_feasible_candidates`, zero inner-feasible guides, zero measurement failures, and no recommendations. Every computed OFF scaffold defect is 1.0. A measured rejection remains distinct from a failed computation.

Tests also cover malformed parentheses, the absence of a hairpin-span restriction across the strand break, default GU pairing, and modified active-model minimum span, maximum span, and `noGU` settings.

Focused run: **70 passed, 110 subtests passed** (26.41 s).
Full backend suite: **2147 passed, 110 subtests passed** (289.15 s); no failures or errors.
Ruff lint/format, Django checks, and the migration check pass. The API surface index was regenerated.

## Export correction authorized on 2026-10-11

The author chose to apply the existing release boundary to research artifacts. `tools/run_crispr.py` now calls `fail_closed_release` for every unique complete guide that appears in retained diagnostics or recommendations, using the configured host. Each occurrence carries the returned audit manifest. Only explicit `release_allowed=True` permits the guide in JSON or CSV. Held guides become JSON null / an empty CSV field; numerical rankings and rejection/measurement diagnostics remain available. Raw input, spacer/trigger sequences, PAMs and architecture sequence fragments are omitted regardless of guide approval, preventing nested fields from bypassing the boundary. Original input identification is preserved through its SHA-256. The in-memory scientific result is unchanged.

The current unprovisioned project screening stack returns `HOLD_SYSTEM`: this is a release hold, not a failed fold or a zero biological score. No private-research exemption or bypass flag was added. Screening failure aborts before writing artifacts. Use a fresh output directory per run: files from a prior run remain if a new run fails before writing.

The original-scaffold regression now explicitly loads the 80-nt user template and asserts its length; the earlier test and table entry had used the 9-nt demo. Both scaffolds agree with their native calculation within the tested tolerance.

Export verification: **13 release/export tests passed**. Full backend run: **2152 passed, 110 subtests passed** (287.59 s). After correcting the original-scaffold fixture, the five export tests and that real 80-nt regression were rerun: **6 passed**. Ruff lint/format and the API-index check passed. The real CLI demo evaluated 480 guides, screened 460 unique retained sequences, and held all 460; no guide or architecture sequence fragments remained in the written results.

Tests cover real HOLD decisions, selective approval, deduplicated screening, input/result immutability, omission of raw/unknown inputs and sequence fragments, overwrite of earlier output files on a successful held run, empty results, and failure before artifact writing.

## Decisions still awaiting maintainer/user input

- **PR scope:** the workbench spans domain, scoring, stages, and pipeline as well as the gate. The review notes a conflict between the older gate-only scope guide and the operative layered implementation guidance. Acceptance of the broader scope or a split into dependency PRs remains a maintainer decision. No repository rules were edited to manufacture an exception.
- **Hosted CI:** these corrections are local pending the author's review. A GitHub CI run against the eventual uploaded commit is still required. The earlier PR's checks describe the earlier head only.

## Documented limits retained

ON is conditional on an already connected complex, not a concentration-weighted tube. Sequence quality inputs, experimental calibration and biological validation remain external. The million-candidate check verifies enumeration, not a million folding evaluations. Inner-loop cancellation/resume is not implemented; progress is between pairs. These were documented limitations in the review, not part of its two reproduced correctness defects.

## API reference

The implementation follows the active model fields and constraint semantics in the [official ViennaRNA Python API](https://viennarna.readthedocs.io/en/latest/api_python.html) and connected-partition definitions in [Global partition functions](https://viennarna.readthedocs.io/en/latest/partfunc/global.html). Regression results above come from the pinned local runtime, not from documentation examples.
