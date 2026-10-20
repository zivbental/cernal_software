# AND workbenches: start here

This directory contains manual research drivers, retained results and report
helpers. CERNAL's application does not invoke these scripts as pipeline stages.
The gate implementations live in [`../../toehold.py`](../../toehold.py).
For the runtime/research/data boundary and exact recovery commands, read the
[prokaryotic AND reproduction guide](../../../../../docs/prokaryotic-and-reproducibility.md).

## Bacterial two-hairpin AND research

| Files | Role |
|---|---|
| `find_candidates.py`, `trigger_accessibility.py` | Historical A0 transcript-window discovery and accessibility measurements. These do not consume CERNAL's new accessible-region table. |
| `full_sweep.py`, `design_panel.py`, `rank_candidates.py`, `objective_energy.py`, `objective_panel.py` | Historical design sweeps, research objectives and experimental-panel selection. Their grids and population-relative scores are not the application's shared ranking policy. |
| `green_calibration.py`, `*_vs_green.py`, `*_vs_libraries.py`, `proposal_validation.py`, `kim2019_benchmark.py` | External-library comparisons. Single-input library correlations do not validate the bacterial AND gate. |
| `complete_panel.py`, `build_report.py`, `report/`, `*_figures.py`, `state_diagrams.py` | Research measurement completion and report/figure generation. |
| `folding_barriers.py`, `kinetic_pathway.py`, `kinetic_proxy.py` | Earlier exploratory path analyses. See the corrected `tools/barrier_designs.py` analysis and its superseded-data explanation in the reproduction guide. |
| `review/*.py` | Worked construction and within-cell analysis examples. |
| `results/`, `Reports/`, `review/runlogs/` | Historical outputs and records; see the recovery boundaries below. |
| `data/`, `mCherry_original.txt`, `mCherry original.txt` | Retained research inputs. Both transcript filenames are kept because older commands reference them. |
| `run_*.ps1`, `*.ps1`, `run_full_objective.sh` | Historical launch/status wrappers. Read their settings before running; their broad sweeps are not application defaults or a quick demo. |
| `STATUS.md`, `*_FINDINGS.md`, `SELECTION_SPEC.md`, other analysis Markdown | Dated research observations/specifications. They record earlier policies and do not override current source or the accessible-region integration revision. |

Helper modules beside these drivers remain at their original paths because
research imports, notebooks, figures and tests depend on them. Start with the
driver's module docstring for inputs, outputs and interpretation, then follow its
imports rather than treating a helper as a separate pipeline stage.

## Eukaryotic workbench and shared helpers

`eu_and_v3.ipynb`, `eu_and_v3_spec.md`, `eu_and_v3_*.svg`,
`_sampled_and_parallel.py`, `_sampled_stem_parallel.py`, `_joint_state_parallel.py`
and `_switch_construct.py` belong to the eukaryotic/shared research workbench.
They are distinct from the bacterial two-hairpin study. The original
`toehold_and.ipynb` is the gate walkthrough. Shared report helpers may serve both
workflows; folder membership alone does not establish authorship.

## Recovered outputs and missing evidence

Large generated outputs were removed from the source tip and indexed in
[`data/research-archive.json`](../../../../../data/research-archive.json).
Use `tools/and_research_archive.py` from the repository root to list, recover and
verify those exact bytes. Recovery is opt-in and preserves different local files.
New bulk runs and local previews belong in ignored output locations.

Some full axis-sweep shards and console logs were never committed. The retained
summary tables are available, but they cannot replace missing row-level evidence.
The [run-log record](review/runlogs/README.md) identifies that limit explicitly.
Do not regenerate into an existing evidence file merely to make a missing-input
error disappear.
