# Gate research notebooks

These are **offline research/manual workbenches**, not the production capability list.
The application baseline is main `66a6d265577810e8943709f3e5bb21bffdab212c`.
See [current status](../../../../docs/status.md), [engine methods](../../../../docs/engine.md)
and [scientific interpretation](../../../../docs/scientific-interpretation.md).

| Directory | Scope |
|---|---|
| [toehold](toehold/) | Single-input walkthroughs and eukaryotic examples |
| [toehold_and](toehold_and/) | AND experiments and reports; the separate eukaryotic AND application is selectable on main |
| [antisense](antisense/) | Antisense research; its class exists but production capability validation excludes it |
| [crispr](crispr/) | CRISPR notebook; see the separate [workbench guide](../../../../docs/crispr-workbench.he.md) |

The earlier claim that every gate method raises `NotImplementedError("Step 5")` is obsolete.
Inspect the notebook's own inputs, execution cells and saved outputs before relying on it.
Saved outputs can predate current code; rerunning is a separate computation, not proof of
biological efficacy. Merged scope and remaining research work are recorded in [status](../../../../docs/status.md).

## NucSyn design exports

The eukaryotic AND notebook includes a research workflow consuming ranked NucSyn CSVs.
Read [upstream credit, schema and reproducibility limits](../../../../docs/nucsyn.md)
before using it. Its local paths and historical outputs are not a portable v0.1.2
reproduction, and its upstream scores are distinct from CERNAL’s production score.

## Setup and execution

From the repository root, install the locked development environment:

```bash
uv sync --locked --extra dev
```

Open a notebook in VS Code and choose the repository `.venv` interpreter. `ipykernel`
is a development dependency. JupyterLab is an optional front end, not part of the lockfile;
if needed install it into a separate tooling environment or deliberately manage its addition.
Do not imply an optional Jupyter installation changes the project's scientific lock.

[_fixtures.py](_fixtures.py) provides shared bootstrap, example records and gate builders.
Some walkthrough helpers use deterministic `StubFoldEngine` outputs by default. Those
are software fixtures, not real ViennaRNA predictions. Where supported, select real folding:

```python
gate = fx.toehold(host=fx.Host.ECOLI, real_fold=True)
folder = fx.fold_engine(real=True)
folder.mfe("GGGAAACCCUUUGGGAAACCC")
```

Record the exact computation commit, parameters, reference versions, seed, folding backend
and input/output checksums. Distinguish sampled/exact estimands, joint/marginal probabilities
and computational/experimental observations. Retain raw data even when interpretations change.
The [evidence guide](../../../../docs/evidence/README.md) explains reproducibility requirements.

This tree is outside the production import path. Application integration needs capability,
validation, persistence, export and release-policy tests; it does not follow from a notebook
or a gate class's `available` attribute.
