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
The shared scoring layer owns those aggregates. But every one of them needs a
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
        # the shared scoring layer owns aggregate scores
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
    # `engaged_arm_11` and `mainpre_engA_11` are one quantity: the mean probability that
    # `main_pre_star` is paired to trigger A in the ON tube. The engine's name says which partner.
    "engaged_arm_11": "mainpre_engA_11",
    # The state left implicit again.
    "rbs11_mean": "rbs11_mean_11",
    "aug11_mean": "aug_11",
    # `free_xstar_{state}` is the mean UNPAIRED probability over x*, which the engine calls
    # `A_S_{state}`. Recorded here because `free_xstar_01` is the exact name that sat in a
    # runner's column list and produced 0 values out of 346,528 -- this alias is what it meant.
    "free_xstar_00": "A_S_00",
    "free_xstar_01": "A_S_01",
    "free_xstar_10": "A_S_10",
    "free_xstar_11": "A_S_11",
}

#: Quantities that are properties of the trigger PAIR, so measuring them per design would store
#: one value many times and invite ranking designs on something constant within a cell -- which is
#: how `access` came to sit inside a score it could not reorder. The run carries
#: `l_local_a/b/min` for this job.
PAIR_LEVEL = frozenset(
    {
        "l_green_a",
        "l_green_b",
        "l_green_worst",
        "eff_toehold_a",
        "eff_run_a_g0",
        "eff_run_a_g1",
        "eff_run_a_g2",
        "eff_run_lo",
        "eff_run_hi",
        "land_site_nt",
        "land_run_g0",
        "land_run_g1",
        "land_run_g2",
    }
)

#: Each needs one more CONSTRAINED fold per tube, so these are a budget decision rather than an
#: oversight. Roughly +40% on a fully measured design for the four-state ones. Priced here so the
#: next person chooses instead of rediscovering them.
NEEDS_A_FOLD = frozenset(
    {
        "dG_arm_00",
        "dG_arm_11",
        "rbs_aug_open_00",
        "rbs_aug_open_11",
        "aug_z_open_00",
        "aug_z_open_01",
        "aug_z_open_10",
        "aug_z_open_11",
        "aug_z_sep",
        "rbs11_open",
        "rbs11_p",
        "aug11_open",
    }
)

#: Off this path by decision. `offtarget*` needs the transcriptome scanner main removed.
#: `drift_repaired` and the `_before`/`_after` columns belong to repair EXPERIMENTS, not to a
#: measurement pass, and `f2_*` are readings of an objective aggregate, whose ownership stays
#: in the scoring layer rather than the gate family.
OFF_THIS_PATH = frozenset(
    {
        "offtarget",
        "offtarget_fires",
        "offtarget_blocks",
        "drift_repaired",
        "oof_augs_before",
        "oof_augs_after",
        "f2_before",
        "f2_after",
        # `engages_stem_mfe` asks whether trigger A contacts the main stem in the MFE STRUCTURE.
        # The engine measures the same question as an ensemble mean -- `mainpre_engA_11` -- and
        # that is deliberate: `four_tube_observables` chooses no representative structure,
        # because where the minimum free energy structure carries little of the ensemble,
        # substituting it answers a different and worse question. One quantity, better statistic.
        "engages_stem_mfe",
    }
)

#: Every classified name, so the audit can report what is left over -- the genuinely unexplained.
CLASSIFIED = PAIR_LEVEL | NEEDS_A_FOLD | OFF_THIS_PATH

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
    buckets = (
        ("pair-level -- l_local_a/b/min already does this job", PAIR_LEVEL),
        ("needs a constrained fold per tube -- a budget decision", NEEDS_A_FOLD),
        ("off this path by decision", OFF_THIS_PATH),
    )
    print(f"\n  {len(union)} notebook names the engine does not produce, classified:\n")
    for label, bucket in buckets:
        here = sorted(n for n in union if n in bucket)
        if here:
            print(f"    {label}  ({len(here)})")
            print(f"      {', '.join(here)}")
    leftover = sorted(n for n in union if n not in CLASSIFIED)
    if leftover:
        print(f"\n    UNEXPLAINED ({len(leftover)}) -- these have no decision recorded:")
        for name in leftover:
            print(f"      {name}")
    else:
        print("\n    Nothing unexplained: every gap has a recorded reason.")
    print(
        "\n  Each needs a DECISION, not a fix by default: an objective aggregate belongs to\n"
        "  the shared scoring layer rather than the gate family, while a\n"
        "  real measurement belongs in `measure_design` and `MEASURED_KEYS`. What is not\n"
        "  acceptable is the status quo, where the only thing noticing is somebody's memory."
    )
    # Reported, not failed: the gap is a decision list. A test that fails on it would be a test
    # that forces every notebook column into the engine, which is the wrong default.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
