# Gate notebooks

A folder per gate family, for driving a single gate by hand — instantiate it, feed it a
trigger set, call each method, look at what comes back — **without** starting Django, the
task worker or the pipeline.

| Folder | Primary notebook | Class | Status |
|---|---|---|---|
| [`toehold/`](toehold/) | [`toehold.ipynb`](toehold/toehold.ipynb) | `ToeholdGate` — single input | `available`, bodies land in Step 5 |
| [`toehold_and/`](toehold_and/) | [`toehold_and.ipynb`](toehold_and/toehold_and.ipynb) | `ToeholdAndGate` — two-input AND | `available`, bodies land in Step 5 |
| [`antisense/`](antisense/) | [`antisense.ipynb`](antisense/antisense.ipynb) | `AntisenseNotGate` — NOT | planned (`available = False`) |
| [`crispr/`](crispr/) | [`crispr.ipynb`](crispr/crispr.ipynb) | `CrisprGate` — sgRNA / iSBH | planned, eukaryotic only |

Each folder holds the gate's walkthrough now and gets more notebooks as the science
lands — parameter sweeps, leakage scans, structure comparisons. The walkthrough keeps
the gate's own name; name the siblings for what they do (`toehold/stem-length-scan.ipynb`).

[`_fixtures.py`](_fixtures.py) is the shared setup every notebook imports as `fx`: the
`sys.path` bootstrap, sample `TriggerCandidate` / `TriggerSet` / `Constraints` builders,
a fake `StubFoldEngine` (so the sequence-construction code runs with no ViennaRNA), and
one-line gate builders (`fx.toehold(...)`, `fx.crispr(...)`, …). It stays in this root
folder; the notebooks reach up to it.

## Running them

**VS Code** — open a notebook and pick the `.venv` interpreter. `ipykernel` is already
installed, so nothing else is needed.

**Browser** — install a front end once, then launch from this folder:

```bash
uv pip install jupyterlab          # or:  uv add --dev jupyterlab
cd src/engine/gates/notebooks
../../../../.venv/bin/jupyter lab
```

Wherever a notebook is launched from, its first cell walks up from its own folder until
it finds `_fixtures.py`, adds that folder to `sys.path`, and then `fx.bootstrap()` puts
`<repo>/src` on the path so `import engine...` resolves.

## What to expect

Every scientific method on a gate currently raises `NotImplementedError("Step 5")`.
`fx.attempt(...)` catches that and prints `pending Step 5` instead of a traceback, so a
notebook still reads top to bottom today. What already produces real output:

- `required_tools()` — the declared external dependencies
- `is_compatible()` for the **planned** families (`antisense`, `crispr`) — they return
  `Compatibility.no(...)` rather than raising
- `emit_sequence()` and `describe()` — via a hand-built `fx.sample_design(...)`

When the Step 5 bodies land, the same notebooks become a live manual test harness with
no edits — the `pending Step 5` lines start printing results.

## Real folding

The default `fx.StubFoldEngine` is deterministic and fake. For genuine structure
predictions (needs `import RNA` — ViennaRNA — to work):

```python
gate = fx.toehold(host=fx.Host.ECOLI, real_fold=True)
folder = fx.fold_engine(real=True)
folder.mfe("GGGAAACCCUUUGGGAAACCC")
```

## Not part of the package

This tree is a manual workbench, not importable engine code — no `__init__.py`, and
nothing under `engine/` imports from here. Keep one-off experiments in a new notebook in
the relevant gate folder rather than editing the walkthroughs; those are meant to stay
runnable as-is.
