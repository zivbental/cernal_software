# Prokaryotic AND gate: code, research and reproduction

Start here to find the bacterial two-hairpin AND work. The gate implementation,
the research that informed it and the Wiki presentation are separate entry points.
None of the commands below requires starting the web application.

## 1. Which code CERNAL uses

| Responsibility | Source | How it is used |
|---|---|---|
| Bacterial gate construction and four-state measurements | [`ToeholdAndGate` and `ProkaryoticToeholdAndGate`](../src/engine/gates/toehold.py) | Engine classes: `generate_designs`, `measure_design`, `evaluate_design`. The same file also contains other contributors' single-input and eukaryotic families. |
| Shared folding and sequence operations | [`gates/tools/folding.py`](../src/engine/gates/tools/folding.py), [`sequences.py`](../src/engine/sequences.py) | Shared engine services; research drivers call these rather than providing a second implementation. |
| Input regions and switch-stage orchestration | [`stages/triggers.py`](../src/engine/stages/triggers.py), [`stages/switches.py`](../src/engine/stages/switches.py), [`pipeline.py`](../src/engine/pipeline.py) | Shared compiler stages, not private AND research scripts. |
| Comparison with other gate families | [`scoring/profiles.py`](../src/engine/scoring/profiles.py), [`scoring/normalize.py`](../src/engine/scoring/normalize.py) | Own metric normalization, filters and final ranking. A notebook score is not this score. |
| Application support and saved results | [`client.py`](../src/engine/client.py), [`stages/reporting.py`](../src/engine/stages/reporting.py) | The installed application's capability contract and reporting paths. Registry presence alone does not establish application support. |

**Revision matters.** On the assessed main revision
`a7cf4abeaefa30e0e0eba3f34e5a6bbfbe630aed`, the bacterial gate's legacy engine
implementation exists, but the accessible-region application integration is still
separate in [PR 84](https://github.com/zivbental/cernal_software/pull/84).
Its recorded head is
[`2dc229477dd28ee71b71f2fe0baaf938f07cbdfe`](https://github.com/zivbental/cernal_software/tree/2dc229477dd28ee71b71f2fe0baaf938f07cbdfe).
Use that exact revision for the Wiki's selected-candidate reproduction. Do not
interpret this guide as a merge or an application capability change.

## 2. Which files are research and presentation

These files are invoked explicitly by a researcher; the application does not run
them as compiler stages.

| Files | Purpose |
|---|---|
| [`notebooks/toehold_and/`](../src/engine/gates/notebooks/toehold_and/README.md) | Historical bacterial A0 experiments, helpers, panel reports and an inventory separating the eukaryotic workbench. |
| [`tools/characterise_axes.py`](../tools/characterise_axes.py), [`analyse_axes.py`](../tools/analyse_axes.py), [`probe_axes.py`](../tools/probe_axes.py), [`analyse_levers.py`](../tools/analyse_levers.py), [`analyse_closure.py`](../tools/analyse_closure.py) | Broad research sweeps and their conditional analyses. Their sweep grids do not define the bounded integration settings. |
| [`tools/pair_budget_on_pfas.py`](../tools/pair_budget_on_pfas.py), [`stem_census_on_pfas.py`](../tools/stem_census_on_pfas.py), [`audit_feasibility.py`](../tools/audit_feasibility.py), [`audit_column_coverage.py`](../tools/audit_column_coverage.py), [`audit_grid_coverage.py`](../tools/audit_grid_coverage.py) | Research budgets, historical policy comparisons, measurement coverage and grid audits. The stem census retains its earlier two-stem and scheme-filter comparison; it is not the current selection specification. |
| [`tools/barrier_designs.py`](../tools/barrier_designs.py), [`barrier_compare.py`](../tools/barrier_compare.py), [`barrier_report.py`](../tools/barrier_report.py), [`experiment_contrasts.py`](../tools/experiment_contrasts.py) | Corrected heuristic refolding-path analyses and experiment contrasts. They do not supply equilibrium gate ranking or measured kinetic rates. |
| [Pinned corrected path outputs](https://github.com/zivbental/cernal_software/tree/2dc229477dd28ee71b71f2fe0baaf938f07cbdfe/docs/assets/barrier), [`docs/assets/barrier_superseded/README.md`](assets/barrier_superseded/README.md) | Corrected outputs from the integration revision and the explanation of the superseded endpoint-energy analysis. Keep the superseded record for comparison, not as kinetic evidence. |
| [`tools/figure_methods.py`](../tools/figure_methods.py), [`figure_and_gate_states.py`](../tools/figure_and_gate_states.py), [`figure_flow.py`](../tools/figure_flow.py), [`figure_results.py`](../tools/figure_results.py), [`figure_kinetic.py`](../tools/figure_kinetic.py) | Research/Wiki SVG generators. They produce presentation assets, not compiler candidates. |
| [`tools/wiki_embed_figure.py`](../tools/wiki_embed_figure.py), [`wiki_clear_marks.py`](../tools/wiki_clear_marks.py) | Historical publication utilities. Both require an explicit `--page`; embedding changes that file. Neither is needed to reproduce scientific measurements. |
| [`docs/wiki/`](wiki/README.md), [`findings-register.md`](findings-register.md) | Historical analysis records, snapshots and the finding-to-command index. The live Wiki source is in a separate repository. |

Git authorship is evidence of contribution, not file-wide ownership. The assessed
research scripts were traced to `offersimha-bit <offersimha@mail.tau.ac.il>`.
Shared engine files contain several contributors' code. AI assistance disclosures
and third-party attribution remain in [attribution](attribution.md).

## 3. Data: what is available and what must be recovered

| Material | Where to find it | Reproduction boundary |
|---|---|---|
| Runtime reference sequences | [`data/manifest.json`](../data/manifest.json) and [`tools/install_data.py`](../tools/install_data.py) | Pinned sizes, hashes and download sources. Follow [data installation](data-installation.md). This is separate from research output recovery. |
| Historical generated AND outputs | [`data/research-archive.json`](../data/research-archive.json) | 153 files pinned to commit `ca4e3b0d90d43f494ef3647b0098795f804fc2ba`, each with byte count and SHA-256. They are not installed with the application. |
| Corrected path-energy research outputs | [`data/prokaryotic-and-path-archive.json`](../data/prokaryotic-and-path-archive.json) | 18 files pinned to integration revision `2dc229477dd28ee71b71f2fe0baaf938f07cbdfe`. Recover them with `--dataset corrected-paths`; their recovery does not merge the integration code. |
| Small retained summaries and examples | [`docs/assets/axes_c8/`](assets/axes_c8/), the workbench's [`results/`](../src/engine/gates/notebooks/toehold_and/results/) | Retained evidence, not a substitute for every raw sweep row. |
| Full local axis-sweep shards and console logs | Research run outputs; see the scripts' `--out`/`--shard` options | Some were never tracked or archived. A Git clone cannot recover a file that was never committed. Retained summaries alone cannot independently re-derive every statistic. |
| mCherry input and E. coli codon table | [`mCherry_original.txt`](../src/engine/gates/notebooks/toehold_and/mCherry_original.txt), [`data/ecoli_codon_usage_table.csv`](../src/engine/gates/notebooks/toehold_and/data/ecoli_codon_usage_table.csv) | Tracked research inputs. The spaced `mCherry original.txt` path also remains for compatibility. |
| Green 2014 and VISTA supplementary tables | Original publication inputs supplied by the researcher | External inputs are not silently downloaded or replaced. Use `--table`, `--csv` or `--data` where offered. Default directories are `var/and-inputs/green2014` and `var/and-inputs/vista2026`; environment overrides are `CERNAL_AND_GREEN_2014` and `CERNAL_AND_VISTA_2026`. |

Recover exact historical bytes without checking out another branch:

```bash
# From the CERNAL repository root; the first command changes nothing.
uv run python tools/and_research_archive.py --list

# Recover and verify all archived outputs in an isolated, ignored directory.
uv run python tools/and_research_archive.py --restore
uv run python tools/and_research_archive.py --check

# Separately recover the corrected path-energy research record.
uv run python tools/and_research_archive.py --dataset corrected-paths --restore
uv run python tools/and_research_archive.py --dataset corrected-paths --check

# To use legacy drivers that read their original results/ paths, recover there explicitly.
# Existing files with different bytes are refused, never replaced.
uv run python tools/and_research_archive.py --restore --output-dir .
```

Use repeated `--path` arguments to recover only the required manifest entries.
The recovery utility uses local Git objects, verifies both size and SHA-256, and
does not fetch a substitute dataset. A shallow/source-only checkout must obtain
the pinned historical commit first. Data recovery does not rerun the experiment.

## 4. A short, reproducible entry point

Record the exact revision and use the locked Python environment:

```bash
git rev-parse HEAD
uv sync --locked --extra dev

# Inspect the historical single-transcript pair-selection interface.
uv run python src/engine/gates/notebooks/toehold_and/find_candidates.py --help

# A geometry/control-feasibility example, not the compiler's two-gene workflow.
uv run python src/engine/gates/notebooks/toehold_and/find_candidates.py --fasta src/engine/gates/notebooks/toehold_and/mCherry_original.txt --top 3

# Read the declared measurement-column coverage; does not fold candidates.
uv run python tools/audit_column_coverage.py
```

Long sweeps are opt-in. Read the selected driver's module docstring and `--help`,
record input hashes, settings, seed, gate version and output prefix, and preserve
all rejection reasons. Historical measured runtimes apply to their stated machine,
inputs and versions; they are not a runtime promise for a new experiment.

For the published eight-fold candidate illustration, use the separate
[Wiki reproduction guide](https://gitlab.igem.org/2026/tau-israel/-/blob/main/docs/AND_GATE_REPRODUCIBILITY.md).
It pins the engine commit, selected candidate and numerical evidence. A selected
example is neither an unbiased search benchmark nor wet-lab validation.
