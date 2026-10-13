"""The axis analysis must not restate, or quietly replace, a measurement the engine makes.

The defect this file exists for. ``tools/analyse_axes.derive`` used to assign ``row["ied_gain"]``
a contrast built from ``dG_open_*`` -- an opening free energy over ``W_rank``, in kcal/mol. But
``ied_gain`` is a column ``measure_design`` already returns: the ensemble defect over the RBS-to-
linker span, dimensionless. ``read_rows`` loads it from the CSV and ``derive`` then overwrote it,
so every number the report labelled ``ied_gain`` was a different quantity in different units --
while ``analyse_levers`` and ``analyse_closure``, which read the same column straight from the
CSV, reported the real one. One name, two quantities, four tools, one results directory.

Nothing raised and nothing logged, which is why this is a test and not a comment.
"""

from __future__ import annotations

import math

from tools.analyse_axes import CONTRASTS, ORIENTATION, derive, value_of, worst_off

from engine.gates.toehold import ProkaryoticToeholdAndGate as Gate


def _row() -> dict:
    """One fully measured design: every column `derive` reads, and every one it could clobber."""
    row = {
        "open_00": 12.0,
        "open_01": 10.0,
        "open_10": 8.6,
        "open_11": 3.0,
        "dG_open_00": -9.0,
        "dG_open_01": -7.0,
        "dG_open_10": -6.0,
        "dG_open_11": -2.0,
        "A_M_00": 0.10,
        "A_M_01": 0.15,
        "A_M_10": 0.20,
        "A_M_11": 0.80,
        "ied_rbs_linker_00": 0.70,
        "ied_rbs_linker_01": 0.65,
        "ied_rbs_linker_10": 0.60,
        "ied_rbs_linker_11": 0.28,
    }
    # The engine's own derived columns, as `measure_design` computes them.
    row["A_M_ratio"] = row["A_M_11"] / max(row["A_M_00"], row["A_M_01"], row["A_M_10"])
    row["A_M_off"] = max(row["A_M_00"], row["A_M_01"], row["A_M_10"])
    row["ied_off_worst"] = min(row["ied_rbs_linker_01"], row["ied_rbs_linker_10"])
    row["ied_gain"] = row["ied_rbs_linker_00"] - row["ied_rbs_linker_11"]
    row["ied_gain_worst"] = row["ied_off_worst"] - row["ied_rbs_linker_11"]
    return row


def test_derive_never_overwrites_a_measured_column() -> None:
    """The whole point: a column the engine measured comes out of `derive` unchanged."""
    row = _row()
    before = {key: value for key, value in row.items() if key in set(Gate.MEASURED_KEYS)}
    assert before, "the fixture must carry at least one MEASURED_KEYS column to be a test at all"
    derive([row])
    changed = {k: (v, row[k]) for k, v in before.items() if row[k] != v}
    assert not changed, f"derive() overwrote measured columns: {changed}"


def test_every_objective_is_measured_or_derived() -> None:
    """No objective names a column nothing produces, which would read as an empty row forever."""
    produced = set(Gate.MEASURED_KEYS)
    for contrast, _on, off_key, _pick, _label in CONTRASTS:
        produced.add(contrast)
        produced.add(off_key)
    unknown = sorted(set(ORIENTATION) - produced)
    assert not unknown, f"objectives naming nothing the engine or derive() produces: {unknown}"


def test_contrast_on_terms_are_engine_columns() -> None:
    """Each contrast's ON term is a real measurement, so a rename cannot leave it silently None."""
    measured = set(Gate.MEASURED_KEYS)
    missing = [on for _c, on, *_rest in CONTRASTS if on not in measured]
    assert not missing, f"contrast ON terms absent from MEASURED_KEYS: {missing}"


def test_worst_off_reports_which_state_and_respects_the_pick_rule() -> None:
    """`min` for a cost, `max` for an accessibility -- and the state it came from, named."""
    row = _row()
    # An opening COST: the leakiest OFF state is the one that opens cheapest.
    value, state = worst_off(row, "open", "min")
    assert (value, state) == (8.6, "10")
    # An ACCESSIBILITY: the worst OFF state is the most open one.
    value, state = worst_off(row, "A_M", "max")
    assert (value, state) == (0.20, "10")


def test_an_unmeasured_contrast_is_none_and_never_zero() -> None:
    """A design the ON ceiling stopped has no OFF tubes, and zero would read as perfect."""
    partial = {"open_11": 3.0}  # the ON tube only, which is all a rejected design carries
    derive([partial])
    for contrast, _on, off_key, _pick, _label in CONTRASTS:
        assert partial[contrast] is None, f"{contrast} must be None, got {partial[contrast]!r}"
        assert partial[off_key] is None
        assert partial[f"binding_off_{contrast}"] is None
    assert value_of(partial, "sep_open") is None


def test_the_state_10_leak_survives_the_ceiling_so_it_can_be_read_pre_filter() -> None:
    """`xstar_engA_10` is measured before the ceiling decides, so it is an objective on every row.

    This is what makes a pre-filter answer possible at all: every contrast needs the three OFF
    tubes and so exists only on survivors, while these two do not.
    """
    for name in ("xstar_engA_10", "mainpre_engA_10"):
        assert name in ORIENTATION
        assert name in set(Gate.MEASURED_KEYS)


def test_orientation_faces_an_off_term_opposite_its_on_term() -> None:
    """An OFF state should stay shut, so its sign is the inverse of the ON term it is taken from."""
    for _contrast, on_key, off_key, _pick, _label in CONTRASTS:
        on_sign, off_sign = ORIENTATION[on_key], ORIENTATION[off_key]
        assert math.copysign(1.0, on_sign) != math.copysign(1.0, off_sign), (
            f"{on_key} and {off_key} face the same way; one of them is oriented wrongly"
        )
