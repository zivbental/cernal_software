"""The two-input inventory: every metric that must survive the trip to a report.

Six times in this work a measured column stopped at a layer boundary and read as absent
downstream while sitting at full coverage two layers up -- a name missing from a CSV field
list, a candidate dict, a per-panel store, a completion-column list. Each was found by eye,
late, after a figure had been drawn from the gap. These tests are cheaper than the seventh.
"""

import math

import pytest

from engine.domain import Constraints, Host, TriggerCandidate, TriggerSet
from engine.gates.toehold import (
    KimSecondaryArmToeholdAndGate,
    ProkaryoticToeholdAndGate,
)
from engine.gates.tools.codons import CodonOptimizer
from engine.gates.tools.folding import FoldEngine
from engine.gates.tools.translation import TranslationScorer
from engine.scoring.profiles import DEFAULT_V1

#: A real mCherry fragment carrying trigger pairs the engine's own finder discovers, so the
#: fixtures below are designs the architecture actually produces rather than hand-built ones.
TRANSCRIPT = (
    "AUGGUGAGCAAGGGCGAGGAGGAUAACAUGGCCAUCAUCAAGGAGUUCAUGCGCUUCAAGGUGCAC"
    "AUGGAGGGCUCCGUGAACGGCCACGAGUUCGAGAUCGAGGGCGAGGGCGAGGGCCGCCCCUACGAG"
    "GGCACCCAGACCGCCAAGCUGAAGGUGACCAAGGGUGGCCCCCUGCCCUUCGCCUGGGACAUCCUG"
    "UCCCCUCAGUUCAUGUACGGCUCCAAGGCCUACGUGAAGCACCCCGCCGACAUCCCCGACUACUUG"
    "AAGCUGUCCUUCCCCGAGGGCUUCAAGUGGGAGCGCGUGAUGAACUUCGAGGACGGCGGCGUGGUG"
)

#: Written at GENERATION time, free of folding -- from the ENGINE's declaration, never a second
#: list. Nine of these were produced by the levers and discarded before any output, including
#: `wobble_applied`, which is the one field that makes a lever's effect estimable at all: comparing
#: an override against the control across all designs mixes the designs it never changed, where the
#: natural sequence already was the override, with the ones it did. The assertion below is two-way,
#: for the same reason it is on the measurement side.
ARCHITECTURE_KEYS = ProkaryoticToeholdAndGate.GENERATION_KEYS

#: Written by the one MEASUREMENT pass -- taken from the ENGINE's own declaration, never a second
#: list. A parallel list is how a measurement gets computed and then dropped: `measure_design`
#: returns 90 numbers, this test used to name 41 of them and `tools/characterise_axes.py` named 24,
#: and nothing related the three, so 66 folded values were discarded on every row of a
#: 346,528-design run. The assertion below is therefore two-way.
MEASURED_KEYS = ProkaryoticToeholdAndGate.MEASURED_KEYS

#: The seven terms x* can be in, which partition it exactly. Asserted as a sum rather than
#: as presence: a double-counted term, a span read against the wrong partner, or a trigger
#: offset taken from the wrong tube all break the sum and none breaks a presence check.
XSTAR_TERMS = (
    "A_S",  # free -- paired to nothing
    "xstar_locked",  # its own arm, sw_x
    "xstar_engA",
    "xstar_engB",
    "xstar_linker",
    "xstar_sec_z",
    "xstar_other",  # the residual, so nothing is dropped
)

FAMILIES = (ProkaryoticToeholdAndGate, KimSecondaryArmToeholdAndGate)


@pytest.fixture(scope="module")
def built():
    """One gate and one design per family, built once for the whole module.

    Module-scoped because each test otherwise constructs a fresh `FoldEngine`, and a fresh
    `FoldEngine` is a cold cache: the same four tubes were folded six times over, which was
    most of the 26 s this module cost. It also matches the rule the engine runs under --
    one folder per run, since a second instance is a second chance to fold at a different
    temperature and nothing detects that.
    """
    out = {}
    for family in FAMILIES:
        folder = FoldEngine(37.0)
        gate = family(Host.ECOLI, folder, TranslationScorer(Host.ECOLI), CodonOptimizer(Host.ECOLI))
        out[family] = (gate, *_first_design(gate))
    return out


def _candidate(name: str, sequence: str, start: int) -> TriggerCandidate:
    return TriggerCandidate(
        trigger_id=name,
        gene_id="mcherry",
        symbol="mcherry",
        sequence=sequence,
        start_index=start,
        openness=0.5,
        accessibility=0.5,
        mfe=-10.0,
        gc_content=50.0,
    )


def _first_design(gate):
    pairs = sorted(gate.find_trigger_pairs(TRANSCRIPT), key=lambda p: (-p.len_x, -p.gap()))
    for pair in pairs:
        a_lo, a_hi = pair.window_a()
        b_lo, b_hi = pair.window_b()
        trigger_set = TriggerSet(
            activators=(
                _candidate("trig-a", TRANSCRIPT[a_lo:a_hi], a_lo),
                _candidate("trig-b", TRANSCRIPT[b_lo:b_hi], b_lo),
            )
        )
        design = next(iter(gate.generate_designs(trigger_set, Constraints(stems_per_pair=2))), None)
        if design is not None:
            return design, (a_lo, a_hi), (b_lo, b_hi)
    pytest.skip("no trigger pair in this fragment reached a design")


@pytest.mark.parametrize("family", FAMILIES, ids=lambda f: f.__name__)
def test_architecture_carries_every_generation_time_key(family, built):
    """Declaration and result must agree EXACTLY, both ways.

    Declared-but-absent is a column that vanished. Present-but-undeclared is the one that was
    invisible: the lever computes it and every reader works from the declaration, so it is
    produced and dropped. That is what happened to all nine wobble and repair fields.

    `wobble_codon` and its three siblings are deliberately NOT declared: `_apply_lower3` emits
    them only when the lever actually converted something, so requiring them on every design
    would demand a value for a lever that never ran.
    """
    _gate, design, _site_a, _site_b = built[family]
    optional = {
        "wobble_codon",
        "wobble_made_stop",
        "wobble_made_rare",
        "wobble_rescued",
        "aug_utr_unrepairable",
    }
    declared = set(ARCHITECTURE_KEYS)
    present = set(design.architecture) - optional
    assert not declared - present, f"architecture lost: {sorted(declared - present)}"
    assert not present - declared, (
        f"architecture carries undeclared key(s), so no reader can know they exist: "
        f"{sorted(present - declared)}"
    )


@pytest.mark.parametrize("family", FAMILIES, ids=lambda f: f.__name__)
def test_the_measurement_pass_carries_every_metric(family, built):
    """The declaration and the result must agree EXACTLY, in both directions.

    Declared-but-absent is a column that vanished. Returned-but-undeclared is worse and was
    invisible: the number is folded and then discarded, because every reader works from the
    declaration. That is what left 66 of 90 measurements unwritten on every row of a
    346,528-design run, and what let `free_xstar_01` sit in a runner's column list naming an
    observable this class has never returned.
    """
    gate, design, site_a, site_b = built[family]
    measured = gate.measure_design(design, transcript=TRANSCRIPT, site_a=site_a, site_b=site_b)

    # `skipped` is a reason, not a measurement, and appears only when the ceiling stopped the
    # pass -- which it did not here, since no ceiling was given.
    returned = set(measured) - {"skipped"}
    declared = set(MEASURED_KEYS)
    assert not declared - returned, f"declared but not measured: {sorted(declared - returned)}"
    assert not returned - declared, (
        f"measured but not declared, so no reader can carry it: {sorted(returned - declared)}"
    )

    # Present is not the same as measured. Anything that came back None is reported, so a
    # whole column quietly going None is visible here rather than three layers downstream.
    unmeasured = sorted(key for key in MEASURED_KEYS if measured.get(key) is None)
    assert unmeasured == [], f"present but unmeasured: {unmeasured}"


@pytest.mark.parametrize("family", FAMILIES, ids=lambda f: f.__name__)
def test_overlap_range_narrows_the_search_and_each_geometry_clamps_its_own_ceiling(family, built):
    """`Constraints.overlap_range` must change the result, and never move trigger B's site.

    For its whole life this field was declared and unread: `_overlap_lengths` walked
    `range(invasion, MIN_OVERLAP - 1, -1)` and ignored it, so setting it raised no error and
    changed nothing. That is why this exercises it rather than asserting it exists.

    The ceiling is the geometry's own `SECONDARY_INVASION_LEN`, not a shared 18: Kim's secondary
    arm is 20 nt but trigger B invades only 17 of it, so a declared 18 cannot be reached there.
    A declared range may only narrow what the architecture can build.
    """
    gate, design, _site_a, _site_b = built[family]
    role_a, role_b = design.trigger_set.activators
    trigger_a, trigger_b = role_a.sequence, role_b.sequence

    wide = gate._overlap_lengths(trigger_a, trigger_b, Constraints())
    assert wide, "the fixture's pair has no overlap at all, so nothing below can be read"
    (found,) = wide

    # A floor above the pair's overlap leaves nothing.
    assert (
        gate._overlap_lengths(trigger_a, trigger_b, Constraints(overlap_range=(found + 1, 18)))
        == ()
    )
    # A ceiling at the overlap keeps it.
    assert gate._overlap_lengths(
        trigger_a, trigger_b, Constraints(overlap_range=(gate.MIN_OVERLAP, found))
    ) == (found,)
    # The declared ceiling can never exceed what this geometry's arm supports.
    for length in gate._overlap_lengths(trigger_a, trigger_b, Constraints(overlap_range=(4, 18))):
        assert length <= gate.SECONDARY_INVASION_LEN


def test_min_window_gap_is_gone_from_constraints():
    """It was read by nobody, so it is removed rather than withheld.

    The gap that exists is `find_trigger_pairs(transcript, min_window_gap=...)`, defaulting to
    the class constant, and it never consulted `Constraints`. The cross-gene path cannot use one
    at all: two windows on separate transcripts cannot overlap. A field wired to nothing is worse
    than no field, because setting it raises no error and changes no behaviour.
    """
    import dataclasses

    names = {field.name for field in dataclasses.fields(Constraints)}
    assert "min_window_gap" not in names
    # The real knob is still there, on the class that owns the scan.
    assert isinstance(ProkaryoticToeholdAndGate.MIN_WINDOW_GAP, int)


@pytest.mark.parametrize("family", FAMILIES, ids=lambda f: f.__name__)
def test_the_xstar_breakdown_accounts_for_all_of_it(family, built):
    """The seven x* terms must sum to 1.0 in every state, or they are not a breakdown.

    x* is either unpaired or paired to exactly one thing, so the partition is exhaustive by
    construction -- `other` is the residual rather than a named list, which is what stops a
    partner nobody thought of from silently vanishing. What the sum actually tests is that all
    seven are read off the SAME matrix with one term per pair: the matrix is symmetric with a
    zero diagonal, so summing both triangles pushes a probability above 1, and that has been a
    real bug in this repo.

    It also pins the per-state trigger offsets. The tubes are ``switch&B`` for 01 and
    ``switch&A&B`` for 11, so trigger B starts after the switch in one and after trigger A in
    the other. Reusing one offset would read A's positions as B's in state 11 and the sum would
    exceed 1.
    """
    gate, design, site_a, site_b = built[family]
    measured = gate.measure_design(design, transcript=TRANSCRIPT, site_a=site_a, site_b=site_b)
    for state in ("00", "01", "10", "11"):
        terms = {name: measured[f"{name}_{state}"] for name in XSTAR_TERMS}
        if any(value is None for value in terms.values()):
            # A tube that could not be folded reports None throughout, which is a legal
            # outcome; what is not legal is a partial breakdown.
            assert all(value is None for value in terms.values()), (
                f"state {state} has some x* terms measured and some not: {terms}"
            )
            continue
        total = sum(terms.values())
        assert math.isclose(total, 1.0, abs_tol=1e-6), (
            f"state {state}: the x* terms sum to {total!r}, not 1.0 -- {terms}"
        )
        assert terms["xstar_other"] >= -1e-6, (
            f"state {state}: the residual is negative ({terms['xstar_other']!r}), so a named "
            f"term is counted twice -- {terms}"
        )


@pytest.mark.parametrize("family", FAMILIES, ids=lambda f: f.__name__)
def test_the_measurement_pass_emits_no_total_and_nothing_normalised(family, built):
    """Raw measurements only. A `score` here would be a ranking baked into a measurement."""
    gate, design, site_a, site_b = built[family]
    measured = gate.measure_design(design, transcript=TRANSCRIPT, site_a=site_a, site_b=site_b)
    for banned in ("score", "final_score", "rank", "normalized", "weighted"):
        assert banned not in measured, f"measure_design must not emit {banned!r}"


@pytest.mark.parametrize("family", FAMILIES, ids=lambda f: f.__name__)
def test_evaluate_design_emits_exactly_the_declared_names(family, built):
    gate, design, _site_a, _site_b = built[family]
    metrics = gate.evaluate_design(design)

    declared = {spec.name for spec in DEFAULT_V1.metrics}
    assert set(metrics) <= declared, f"undeclared: {sorted(set(metrics) - declared)}"

    # No sentinels. 0.0 on predicted_leakage normalises to a PERFECT 1.0 and clears its own
    # 0.85 hard filter, so an unmeasurable metric has to arrive as None.
    for name, value in metrics.items():
        if value is not None:
            assert not math.isnan(value), f"{name} is nan"
            assert value not in (-1.0, 999.0), f"{name} looks like a sentinel: {value}"


@pytest.mark.parametrize("family", FAMILIES, ids=lambda f: f.__name__)
def test_the_two_opening_windows_are_different_measurements(family, built):
    """`open_11` and `dG_open_11` must not be each other.

    One is taken over the main stem's two descending arms, the other over the 30-nt
    ribosome footprint around the AUG. The names are close enough to be swapped by
    accident, and the ON ceiling that rejects 88% of designs rides on the first while
    `separation` rides on the second.
    """
    gate, design, site_a, site_b = built[family]
    arms = tuple(tuple(span) for span in design.architecture["main_stem_arms"])
    assert arms != (tuple(design.architecture["w_rank"]),)

    measured = gate.measure_design(design, transcript=TRANSCRIPT, site_a=site_a, site_b=site_b)
    assert measured["open_11"] != measured["dG_open_11"]


@pytest.mark.parametrize("family", FAMILIES, ids=lambda f: f.__name__)
def test_the_on_ceiling_stops_before_the_barrier_and_says_so(family, built):
    """The ordering that makes the sweep affordable, asserted rather than assumed.

    The barrier alone is 52% of the cost of a fully measured design, and the ON tube's
    ceiling rejects 88% of designs. A ceiling that still paid for the barrier would give
    the cheapest-first ordering back for nothing.
    """
    gate, design, _site_a, _site_b = built[family]
    measured = gate.measure_design(design, on_ceiling=-1e9)

    assert measured["skipped"] == "on_ceiling"
    assert "barrier" not in measured
    assert "open_00" not in measured
    # "Not attempted" and "measurement failed" are different, and the reason distinguishes
    # them -- a bare None beside no reason cannot.
    assert measured["open_11"] is not None
