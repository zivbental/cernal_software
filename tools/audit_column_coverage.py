"""Quantities the notebook measures that the ENGINE does not — the recurring defect, as a check.

Run it:

    uv run python tools/audit_column_coverage.py

**The failure this exists for.** Five times in one working session a quantity we had already
analysed turned out to be absent from the engine's path, each time discovered by accident:

* ``free_xstar_01`` sat in a runner's column list naming an observable the engine has never
  returned — 0 values out of 346,528, and nothing said so.
* 66 of the 90 numbers ``measure_design`` computes were folded and discarded on every row,
  because the runner kept its own list of 24.
* nine lever fields (``wobble_applied`` and friends) were computed by ``_apply_lower3`` and
  dropped before any output — the one field that makes a lever's effect estimable among them.
* ``ied_gain``, ``dG_rbs_linker``, ``f2`` and ``f5`` are analysed in the notebook panels and are
  **not measured anywhere in the engine**.
* ``min_window_gap`` and ``overlap_range`` were declared on ``Constraints`` and read by nobody.

The first three are now machine-checked: ``MEASURED_KEYS`` and ``GENERATION_KEYS`` are declared on
``ToeholdAndGate`` and ``tests/engine/gates/test_toehold_and_inventory.py`` asserts equality in
both directions, so computed-and-dropped is a test failure. **The fourth is a different gap and
nothing catches it**: those columns are not dropped, they do not exist on the engine path at all,
and the only thing that would have noticed is somebody remembering. This replaces the
remembering.

It reads the notebook modules' own field tuples — the lists they really write — and sets them
against what the engine declares. Nothing is folded and nothing is run: it is a name comparison,
so it costs milliseconds and can run in CI.

**What a row in the output means.** A name in "notebook only" is a quantity we have analysed and
the pipeline cannot produce. That is not automatically a bug: some are objective aggregates that
belong to whoever is ranking rather than to a measurement (``f2``, ``f5``, ``score``), and
CLAUDE.md §3 is explicit that a family must not emit those. But every one of them needs a
*decision*, and the point is that the list is visible instead of being rediscovered.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# ruff: noqa: E402 - the engine imports must follow the sys.path.insert above.
from engine.gates.toehold import ProkaryoticToeholdAndGate

NOTEBOOK = ROOT / "src" / "engine" / "gates" / "notebooks" / "toehold_and"

#: Where each notebook module keeps the column list it actually writes. Read from the module
#: rather than copied here, so this audit cannot itself go stale -- which is the defect it is for.
SOURCES: tuple[tuple[str, str], ...] = (
    ("objective_energy", "_FIELDS"),
    ("objective_panel", "COMPLETION_COLUMNS"),
    ("complete_panel", "FIELDS"),
    ("stem_opens_mfe", "FIELDS"),
    ("drift_fold", "FIELDS"),
    ("aug_rescue", "FIELDS"),
)

#: Names that are bookkeeping or identity rather than measurements, so their absence from the
#: engine's measurement set is correct and not a finding. Kept short and justified: anything
#: added here is a claim that the engine should not measure it.
NOT_A_MEASUREMENT = frozenset(
    {
        # identity and coordinates, carried on `architecture` or the records themselves
        "switch",
        "pair",
        "geom",
        "arm",
        "closure",
        "upper3",
        "lower3",
        "scheme",
        "len_x",
        "stem_index",
        "gene_a",
        "gene_b",
        "x_start",
        "xstar_start",
        "trigger_a",
        "trigger_b",
        "design_id",
        "key",
        "row",
        "index",
        "a_start",
        "a_end",
        "b_start",
        "b_end",
        # driver bookkeeping: `score` and `skipped` are decisions, not measurements, and
        # CLAUDE.md §3 forbids a family emitting a total at all
        "score",
        "skipped",
        "reason",
        "rank",
        "n_contacts",
        "n_on_arm",
        # `aug_rescue` is a before/after experiment on one repair, not a measurement pass: its
        # columns are two readings of metrics the engine already has, under `_before`/`_after`.
        # The metric is what has to be covered; the experiment's bookkeeping is not.
        "edit",
        "switch_before",
    }
)

#: The SAME quantity under a different name. Without this the audit reports a rename as a missing
#: measurement, and a check that cries wolf gets ignored -- which would make it worse than no
#: check. Each entry is a claim that two names mean one thing, so each is as reviewable as code.
ALIASES: dict[str, str] = {
    # The notebook measures hairpin fidelity in the OFF state only and leaves the state implicit.
    # The engine measures all four states and says which.
    "hairpin_worst": "hairpin_worst_00",
    "hairpin_main_pre": "hairpin_main_pre_00",
    "hairpin_k1": "hairpin_k1_00",
    "hairpin_lock": "hairpin_lock_00",
    "hairpin_sec": "hairpin_sec_00",
    # The engine prefixes an accessibility mean with `A_`.
    "r2_star_00": "A_r2_star_00",
}

#: A column whose suffix names a READING of a metric rather than a metric: `open_11_before` is
#: `open_11` taken at one point in an experiment. Stripped before the comparison.
EXPERIMENT_SUFFIXES = ("_before", "_after")


def canonical(name: str) -> str:
    """The engine name a notebook column refers to, after renames and experiment suffixes."""
    for suffix in EXPERIMENT_SUFFIXES:
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    return ALIASES.get(name, name)


def load(name: str):
    path = NOTEBOOK / f"{name}.py"
    if not path.exists():
        return None
    # The notebook modules import each other by bare name, so the notebook directory has to be
    # importable or `objective_panel` -- which holds the longest column list -- silently skips.
    if str(NOTEBOOK) not in sys.path:
        sys.path.insert(0, str(NOTEBOOK))
    spec = importlib.util.spec_from_file_location(f"_audit_{name}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as error:  # a notebook module that cannot import is itself reportable
        print(f"  ! {name}: cannot import ({type(error).__name__}: {error})")
        return None
    return module


def main() -> int:
    engine_measured = set(ProkaryoticToeholdAndGate.MEASURED_KEYS)
    engine_generated = set(ProkaryoticToeholdAndGate.GENERATION_KEYS)
    engine_all = engine_measured | engine_generated
    print(
        f"\n  engine declares {len(engine_measured)} measurement keys and "
        f"{len(engine_generated)} generation keys\n"
    )

    notebook: dict[str, set[str]] = {}
    for name, attribute in SOURCES:
        module = load(name)
        if module is None:
            continue
        fields = getattr(module, attribute, None)
        if fields is None:
            print(f"  ! {name}.{attribute} no longer exists -- this audit's own list is stale")
            continue
        notebook[f"{name}.{attribute}"] = {
            f for f in fields if isinstance(f, str)
        } - NOT_A_MEASUREMENT

    missing: dict[str, list[str]] = {}
    renamed: dict[str, str] = {}
    print(f"  {'source':44s}{'exact':>7}{'renamed':>9}{'absent':>8}{'of':>5}")
    for source, fields in sorted(notebook.items()):
        exact = {f for f in fields if f in engine_all}
        rest = fields - exact
        under_alias = {f for f in rest if canonical(f) in engine_all}
        for f in under_alias:
            renamed[f] = canonical(f)
        gap = sorted(rest - under_alias)
        print(f"  {source:44s}{len(exact):>7}{len(under_alias):>9}{len(gap):>8}{len(fields):>5}")
        if gap:
            missing[source] = gap

    if renamed:
        print(f"\n  {len(renamed)} matched under another name -- the same quantity, so not a gap:")
        for a, b in sorted(renamed.items()):
            print(f"    {a:24s} -> {b}")

    if not missing:
        print("\n  Every notebook column has an engine counterpart.")
        return 0

    union = sorted({name for gap in missing.values() for name in gap})
    print(f"\n  {len(union)} quantities the notebook writes and the engine does not produce:\n")
    for source, gap in missing.items():
        print(f"    {source}")
        for name in gap:
            print(f"      {name}")
    print(
        "\n  Each needs a DECISION, not a fix by default: an objective aggregate belongs to\n"
        "  whoever is ranking (CLAUDE.md section 3 forbids a family emitting a total), while a\n"
        "  real measurement belongs in `measure_design` and `MEASURED_KEYS`. What is not\n"
        "  acceptable is the status quo, where the only thing noticing is somebody's memory."
    )
    # Reported, not failed: the gap is a decision list. A test that fails on it would be a test
    # that forces every notebook column into the engine, which is the wrong default.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
