"""``ToeholdGate`` — single-input toehold switch generation and evaluation.

Real ``FoldEngine``/ViennaRNA throughout, matching ``test_antisense.py``: every switch
here tops out under 90 nt, so a real fold costs low milliseconds.
"""

import pytest

from engine import sequences as sq
from engine.domain import Compatibility, Constraints, Host, TriggerCandidate, TriggerSet
from engine.gates.registry import available_families
from engine.gates.toehold import (
    EukaryoticToeholdAndGate,
    EukaryoticToeholdGate,
    ProkaryoticToeholdAndGate,
    ProkaryoticToeholdGate,
    ToeholdAndGate,
    ToeholdGate,
    _arm_conflicts,
    _build_arms,
    _invasion_runs_ok,
    _pareto_front,
    _secondary_domains,
)
from engine.gates.tools.codons import CodonOptimizer
from engine.gates.tools.folding import FoldEngine
from engine.gates.tools.translation import TranslationScorer

# A non-repetitive, deterministic 36 nt trigger — long enough for every swept toehold
# length (12/15/18 + the 9+3+6 nt stem) with room to spare.
TRIGGER_SEQUENCE = "GCUAAAGACAAUUACAUAACAUACACGUCAGCACGA"[:36]


def make_trigger(**overrides) -> TriggerCandidate:
    """A tiny, deterministic activator trigger. Any field can be overridden."""
    sequence = overrides.pop("sequence", TRIGGER_SEQUENCE)
    defaults = {
        "trigger_id": "trig-000042",
        "gene_id": "b0002",
        "symbol": "thrA",
        "sequence": sequence,
        "start_index": 10,
        "openness": 0.70,
        "accessibility": 0.62,
        "mfe": -4.0,
        "off_target_penalty": 0.0,
        "segment_specificity": 0.9,
        "gc_content": sq.gc_content(sequence),
        "score": 0.8,
    }
    defaults.update(overrides)
    return TriggerCandidate(**defaults)


@pytest.fixture
def gate() -> ToeholdGate:
    return ToeholdGate(
        Host.ECOLI,
        FoldEngine(temperature=37.0),
        TranslationScorer(Host.ECOLI),
        CodonOptimizer(Host.ECOLI),
    )


@pytest.fixture
def activator_set() -> TriggerSet:
    return TriggerSet(activators=(make_trigger(),))


@pytest.fixture
def constraints() -> Constraints:
    return Constraints()


# --- required_tools -----------------------------------------------------------------


def test_required_tools_declares_viennarna(gate):
    tools = gate.required_tools()
    assert [t.name for t in tools] == ["ViennaRNA"]


# --- is_compatible: cheap checks, no folding -----------------------------------------


def test_compatible_with_a_single_activator(gate, activator_set, constraints):
    assert gate.is_compatible(activator_set, constraints) == Compatibility.yes()


def test_incompatible_with_a_repressor():
    """This gate turns ON when its trigger is present, so its one input must be an
    activator, not a repressor."""
    gate = ToeholdGate(
        Host.ECOLI, FoldEngine(), TranslationScorer(Host.ECOLI), CodonOptimizer(Host.ECOLI)
    )
    trigger_set = TriggerSet(activators=(), repressors=(make_trigger(),))
    result = gate.is_compatible(trigger_set, Constraints())
    assert not result.ok


def test_incompatible_with_two_activators(gate, constraints):
    trigger_set = TriggerSet(
        activators=(make_trigger(trigger_id="trig-a"), make_trigger(trigger_id="trig-b"))
    )
    result = gate.is_compatible(trigger_set, constraints)
    assert not result.ok
    assert "exactly 1" in result.reason


def test_and_gate_needs_exactly_two_activators():
    """`is_compatible` is inherited from `ToeholdGate` unchanged, and generalises via
    `self.max_inputs` rather than a hardcoded arity."""
    gate = ToeholdAndGate(
        Host.ECOLI, FoldEngine(), TranslationScorer(Host.ECOLI), CodonOptimizer(Host.ECOLI)
    )
    two = TriggerSet(
        activators=(make_trigger(trigger_id="trig-a"), make_trigger(trigger_id="trig-b"))
    )
    one = TriggerSet(activators=(make_trigger(trigger_id="trig-a"),))
    assert gate.is_compatible(two, Constraints()) == Compatibility.yes()
    assert not gate.is_compatible(one, Constraints()).ok


def test_toehold_variants_are_registered_by_track_and_arity():
    assert {
        "prokaryotic_toehold",
        "prokaryotic_toehold_and",
        "eukaryotic_toehold",
        "eukaryotic_toehold_and",
    }.issubset(available_families())
    assert ProkaryoticToeholdGate.max_inputs == 1
    assert ProkaryoticToeholdAndGate.max_inputs == 2
    assert EukaryoticToeholdGate.max_inputs == 1
    assert EukaryoticToeholdAndGate.max_inputs == 2


@pytest.mark.parametrize(
    ("family", "host", "expected"),
    [
        (ProkaryoticToeholdGate, Host.ECOLI, True),
        (ProkaryoticToeholdGate, Host.HUMAN, False),
        (EukaryoticToeholdGate, Host.HUMAN, True),
        (EukaryoticToeholdGate, Host.ECOLI, False),
        (ProkaryoticToeholdAndGate, Host.ECOLI, True),
        (EukaryoticToeholdAndGate, Host.YEAST, True),
    ],
)
def test_toehold_variants_limit_supported_hosts(family, host, expected):
    instance = family(host, FoldEngine(), TranslationScorer(host), CodonOptimizer(host))
    assert instance.supports(host) is expected


def test_incompatible_when_trigger_too_short(gate, constraints):
    short = make_trigger(sequence="ACGUACGUACGU")  # 12 nt, below any sweep's footprint
    trigger_set = TriggerSet(activators=(short,))
    result = gate.is_compatible(trigger_set, constraints)
    assert not result.ok
    assert "too short" in result.reason.lower() or "shorter than" in result.reason


def test_is_compatible_never_folds(gate, activator_set, constraints, monkeypatch):
    """Cheap checks only — the whole point of `is_compatible` is to avoid folding."""

    def _boom(*_args, **_kwargs):
        raise AssertionError("is_compatible must not fold")

    monkeypatch.setattr(gate.folder, "mfe", _boom)
    monkeypatch.setattr(gate.folder, "base_pair_probabilities", _boom)
    gate.is_compatible(activator_set, constraints)


# --- generate_designs -----------------------------------------------------------------


def test_generate_designs_yields_one_per_toehold_length(gate, activator_set, constraints):
    designs = list(gate.generate_designs(activator_set, constraints))
    assert len(designs) == len(gate.toehold_lengths)
    assert [d.architecture["toehold_length"] for d in designs] == list(gate.toehold_lengths)


def test_generated_sequences_are_valid_rna(gate, activator_set, constraints):
    for design in gate.generate_designs(activator_set, constraints):
        assert sq.is_valid_rna(design.sequence)


def test_dot_bracket_is_balanced_and_the_same_length_as_the_sequence(
    gate, activator_set, constraints
):
    for design in gate.generate_designs(activator_set, constraints):
        assert len(design.dot_bracket) == len(design.sequence)
        assert design.dot_bracket.count("(") == design.dot_bracket.count(")")


def test_every_design_respects_the_length_constraint(gate, activator_set):
    tight = Constraints(max_switch_length=85)
    designs = list(gate.generate_designs(activator_set, tight))
    assert designs  # the shortest (toehold_length=12) sweep is 83 nt, still fits
    assert len(designs) < len(gate.toehold_lengths)  # but not every sweep does
    for design in designs:
        assert design.length <= 85


def test_a_trigger_too_short_for_a_longer_sweep_still_yields_the_shorter_ones(gate, constraints):
    """36 nt fits every swept toehold length; 33 nt only fits the two shortest."""
    trigger = make_trigger(sequence=TRIGGER_SEQUENCE[:33])
    designs = list(gate.generate_designs(TriggerSet(activators=(trigger,)), constraints))
    assert [d.architecture["toehold_length"] for d in designs] == [12, 15]


def test_architecture_records_enough_to_relocate_the_start_codon(gate, activator_set, constraints):
    design = next(gate.generate_designs(activator_set, constraints))
    aug_index = design.architecture["aug_index"]
    assert design.sequence[aug_index : aug_index + 3] == sq.START_CODON


def test_the_toehold_is_the_trigger_reverse_complement(gate, activator_set, constraints):
    """The mechanism this whole family exists for: the toehold must be complementary to
    the trigger, or the trigger cannot nucleate strand invasion against it."""
    design = next(gate.generate_designs(activator_set, constraints))
    toehold_length = design.architecture["toehold_length"]
    leader_len = design.architecture["leader_len"]
    toehold = design.sequence[leader_len : leader_len + toehold_length]
    expected = sq.reverse_complement(TRIGGER_SEQUENCE)[:toehold_length]
    assert toehold == expected


def test_design_ids_are_unique_and_traceable(gate, activator_set, constraints):
    designs = list(gate.generate_designs(activator_set, constraints))
    ids = [d.design_id for d in designs]
    assert len(ids) == len(set(ids))
    assert all(activator_set.activators[0].trigger_id in i for i in ids)


def test_eukaryotic_host_uses_kozak_instead_of_rbs(activator_set, constraints):
    gate = ToeholdGate(
        Host.HUMAN, FoldEngine(), TranslationScorer(Host.HUMAN), CodonOptimizer(Host.HUMAN)
    )
    design = next(gate.generate_designs(activator_set, constraints))
    assert gate.KOZAK_EUKARYOTIC in design.sequence
    assert gate.RBS_PROKARYOTIC not in design.sequence


# --- evaluate_design: raw values, no scoring -------------------------------------------


def test_evaluate_design_returns_only_declared_metric_names(gate, activator_set, constraints):
    design = next(gate.generate_designs(activator_set, constraints))
    metrics = gate.evaluate_design(design)

    assert metrics.keys() == {
        "gate_folding_energy",
        "predicted_leakage",
        "dynamic_range",
        "trigger_accessibility",
        "gc_content",
    }
    assert all(isinstance(v, float) for v in metrics.values())


def test_predicted_leakage_is_a_fraction(gate, activator_set, constraints):
    design = next(gate.generate_designs(activator_set, constraints))
    metrics = gate.evaluate_design(design)
    assert 0.0 <= metrics["predicted_leakage"] <= 1.0
    assert metrics["dynamic_range"] > 0.0


def test_trigger_accessibility_is_carried_not_recomputed(gate, activator_set, constraints):
    """Stage 2 already measured this; evaluate_design must read it, not refold it."""
    design = next(gate.generate_designs(activator_set, constraints))
    metrics = gate.evaluate_design(design)
    assert metrics["trigger_accessibility"] == activator_set.activators[0].accessibility


def test_a_tighter_stem_at_the_start_codon_leaks_less(gate, constraints):
    """Sanity check on the mechanism, not just the plumbing: an OFF-state switch whose
    start codon is well and truly paired should show lower predicted_leakage than one
    that leaves it exposed. Regression coverage for an inverted accessible/paired sign."""
    design = next(gate.generate_designs(TriggerSet(activators=(make_trigger(),)), constraints))
    metrics = gate.evaluate_design(design)
    off_matrix = gate.folder.base_pair_probabilities(design.sequence)
    aug_index = design.architecture["aug_index"]
    mean_aug_unpaired = (
        sum(max(0.0, 1.0 - sum(off_matrix[i])) for i in range(aug_index, aug_index + 3)) / 3
    )
    # predicted_leakage is the *unpaired* fraction, so it must fall as pairing rises.
    assert metrics["predicted_leakage"] == pytest.approx(mean_aug_unpaired, abs=1e-6)


# --- emit_sequence -----------------------------------------------------------------


def test_emit_sequence_is_the_design_sequence(gate, activator_set, constraints):
    design = next(gate.generate_designs(activator_set, constraints))
    assert gate.emit_sequence(design) == design.sequence


# --- Golden: fixed input, committed output (docs/engine.md §8) -------------------------


def test_golden_first_design_for_a_known_trigger(gate, activator_set, constraints):
    """Pins the exact switch and metrics this gate produces for a known trigger.

    A refactor that changes these numbers must be a deliberate, reviewed change — update
    the expected values here and bump ``ToeholdGate.version`` alongside it.
    """
    design = next(gate.generate_designs(activator_set, constraints))

    assert design.design_id == "toehold-trig-000042-12"
    assert design.architecture == {
        "toehold_length": 12,
        "stem_pre_bulge_len": 9,
        "stem_post_bulge_len": 6,
        "loop_len": 11,
        "leader_len": 3,
        "linker_len": 21,
        "aug_index": 50,
        "track": "prokaryotic",
    }
    assert design.sequence == (
        "GGGUCGUGCUGACGUGUAUGUUAUGUAAUUGUCAACAGAGGAGAGACAAUAUGAUAACAUACAACCUGGCGGCAGCGCAAAAG"
    )

    metrics = gate.evaluate_design(design)
    assert metrics == pytest.approx(
        {
            "gate_folding_energy": -25.899999618530273,
            "predicted_leakage": 0.8595640592508901,
            "dynamic_range": 0.4236469499952924,
            "trigger_accessibility": 0.62,
            "gc_content": 45.78313253012048,
        }
    )


# --- The AND gate's secondary (inhibitory) stem, scheme C ----------------------------
#
# A deterministic pair built so the conflict positions are known by construction: trigger
# A's extension is `_EXT`, and what trigger B needs is the same string with the bases at
# `_CONFLICT_AT` transposed, so those positions and only those are contested.

_OVERLAP = "GCAUCG"
_EXT = "AGGCUAUGCCAU"
_CONFLICT_AT = frozenset({2, 3, 6, 7, 10})
_TRANSPOSE = {"A": "C", "C": "A", "G": "U", "U": "G"}


def _contested_pair(conflict_at=_CONFLICT_AT, ext=_EXT):
    """Trigger A and trigger B sharing `_OVERLAP`, disagreeing exactly at `conflict_at`."""
    wanted = "".join(_TRANSPOSE[b] if p in conflict_at else b for p, b in enumerate(ext))
    k2 = sq.reverse_complement(wanted)
    trigger_a = "AAAAAA" + "CCC" + "GGGGGGGGG" + _OVERLAP + ext
    trigger_b = k2 + sq.reverse_complement(_OVERLAP) + "A" * 32
    return trigger_a, trigger_b, wanted


def _and_gate() -> ProkaryoticToeholdAndGate:
    return ProkaryoticToeholdAndGate(
        Host.ECOLI, FoldEngine(37.0), TranslationScorer(Host.ECOLI), CodonOptimizer(Host.ECOLI)
    )


def test_the_trigger_domains_are_recovered_from_the_two_trigger_sequences():
    """Trigger A reads k1/bulge/main_pre/x/ext and trigger B reads k2/x*/r2, so the stem
    builder needs no separate input — an off-by-one here silently designs a stem against
    the wrong bases."""
    trigger_a, trigger_b, _ = _contested_pair()

    ext, k2 = _secondary_domains(trigger_a, trigger_b, len(_OVERLAP), 18)

    assert ext == _EXT
    assert k2 == trigger_b[: 18 - len(_OVERLAP)]
    assert set(_arm_conflicts(ext, k2)) == _CONFLICT_AT


def test_the_three_per_position_states_build_the_arms_they_promise():
    """`both` serves both triggers and opens the lock, `lockA` serves trigger A and the
    lock, `lockB` serves trigger B and the lock. Getting the descending arm's direction
    wrong swaps the last two without changing any length."""
    _, trigger_b, wanted = _contested_pair()
    ext, k2 = _EXT, trigger_b[:12]

    both = _build_arms(ext, k2, {})
    lock_a = _build_arms(ext, k2, dict.fromkeys(_CONFLICT_AT, "lockA"))
    lock_b = _build_arms(ext, k2, dict.fromkeys(_CONFLICT_AT, "lockB"))

    assert both == (wanted, sq.reverse_complement(ext))
    assert lock_a[0] == ext
    assert lock_b[1] == sq.reverse_complement(wanted)


def test_the_invasion_cap_counts_positions_trigger_b_cannot_pair_at_not_the_flips():
    """The cap exists to stop trigger B meeting a stretch it must break pairs across and
    form nothing in. Capping the *flips* instead would scatter the lock's mismatches,
    which costs far more lock stability than clustering them."""
    for conflicts, expected in [({2, 3, 4}, False), ({2, 3}, True), ({2, 4, 6}, True)]:
        _, trigger_b, _ = _contested_pair(conflict_at=conflicts)
        k2 = trigger_b[:12]
        stalled_everywhere = _build_arms(_EXT, k2, dict.fromkeys(conflicts, "lockA"))[0]

        assert _invasion_runs_ok(_EXT, k2, stalled_everywhere, 2) is expected
        assert _invasion_runs_ok(_EXT, k2, _build_arms(_EXT, k2, {})[0], 2) is True


def test_every_surviving_stem_lets_trigger_b_displace_the_switchs_own_copy():
    """R6, and the subtraction order it depends on: ddG_pref is the switch's own copy
    minus the incoming trigger. Free energies are negative, so `>= 0` means the switch's
    copy is the *weaker* binder. Reversed, the gate keeps exactly the designs it should
    reject."""
    trigger_a, trigger_b, _ = _contested_pair()

    stems = _and_gate().secondary_stems(trigger_a, trigger_b, len(_OVERLAP))

    assert stems
    assert all(stem.ddg_pref >= 0.0 for stem in stems)
    assert all(
        stem.ddg_pref == pytest.approx(stem.lock_energy - stem.b_site_energy) for stem in stems
    )


def test_serving_both_triggers_everywhere_is_the_most_displaceable_stem():
    """The all-`both` corner gives trigger B a perfect site and leaves the lock open at
    every contested position, so nothing can beat it on ddG_pref. If some locked build
    scores higher, the lock and the trigger site have been swapped somewhere."""
    trigger_a, trigger_b, wanted = _contested_pair()

    stems = _and_gate().secondary_stems(trigger_a, trigger_b, len(_OVERLAP))
    most_displaceable = max(stems, key=lambda stem: stem.ddg_pref)

    assert set(most_displaceable.states) == {"both"}
    assert most_displaceable.k2_star == wanted
    assert most_displaceable.secondary_z == sq.reverse_complement(_EXT)


def test_the_frontier_keeps_builds_neither_global_strategy_can_express():
    """Scheme C's whole justification. Anchoring every position to trigger A or every
    position to trigger B reaches 2^n builds each; letting positions choose independently
    reaches 3^n and contains both as strict subsets. If the mixed builds never survived,
    the enumeration would be costing 3^n for nothing."""
    trigger_a, trigger_b, _ = _contested_pair()

    stems = _and_gate().secondary_stems(trigger_a, trigger_b, len(_OVERLAP))
    mixed = [s for s in stems if {"lockA", "lockB"} <= set(s.states)]

    assert len(stems) == 22
    assert len(mixed) == 10


def test_the_frontier_is_the_non_dominated_set_and_keeps_exact_ties():
    """Dropping a build requires another that is at least as good on all three claims and
    better on one. Identical triples dominate nothing, and two builds scoring alike here
    are still different sequences that will fold differently."""
    points = [(0.0, 0.0, 0.0), (1.0, 1.0, 1.0), (0.0, 5.0, 5.0), (0.0, 0.0, 0.0)]

    assert _pareto_front(points) == [0, 3]
    assert _pareto_front([(2.0, 1.0, 3.0), (1.0, 2.0, 3.0)]) == [0, 1]


# --- Stage 1: finding trigger pairs in one transcript --------------------------------


def _transcript_with_a_planted_overlap() -> tuple[str, str]:
    """A transcript carrying one deliberate 7-nt reverse-complementary pair, far apart
    enough for both 36 nt and 50 nt windows to fit on either side."""
    overlap = "GCAUCGA"
    filler = "ACAGUACAGUACAGUACAGU"
    left = "ACGUACGUAC" * 6 + overlap + "CAGUCAGUCA" * 6
    right = "AUCAGUCAGU" * 6 + sq.reverse_complement(overlap) + "GUACGUACGU" * 6
    return left + filler + right, overlap


def test_trigger_windows_are_a_constant_36_and_50_nucleotides():
    """`len_k2 = 18 - len_x` cancels `len_x`, so neither window's width depends on the
    overlap. A width that moves with `len_x` means the geometry has drifted."""
    transcript, _ = _transcript_with_a_planted_overlap()

    pairs = list(_and_gate().find_trigger_pairs(transcript, min_window_gap=0))

    assert pairs
    for pair in pairs:
        assert pair.window_a()[1] - pair.window_a()[0] == 36
        assert pair.window_b()[1] - pair.window_b()[0] == 50


def test_the_reported_overlap_really_is_at_the_reported_coordinates():
    """The only check that catches an off-by-one, because a shifted window still folds and
    still scores. `x` at `x_start` must be the reverse complement of `x*` at
    `xstar_start`."""
    transcript, _ = _transcript_with_a_planted_overlap()

    for pair in _and_gate().find_trigger_pairs(transcript, min_window_gap=0):
        x = transcript[pair.x_start : pair.x_start + pair.len_x]
        x_star = transcript[pair.xstar_start : pair.xstar_start + pair.len_x]
        assert sq.reverse_complement(x) == x_star


def test_reported_overlaps_are_maximal_runs():
    """Each pair is reported at its maximal perfect run, never truncated into
    sub-overlaps: a shorter `x` only moves positions out of the conflict-free core and
    into the contested region, with no compensating gain. So no reported overlap may be
    extendable — it must reach the arm length, run off the transcript, or meet a base
    that does not pair.

    The planted overlap is found *inside* a reported one rather than as one, because its
    own flanks extend it. That is the behaviour under test, not an accident.
    """
    transcript, overlap = _transcript_with_a_planted_overlap()
    gate = _and_gate()
    n = len(transcript)

    pairs = list(gate.find_trigger_pairs(transcript, min_window_gap=0))

    assert any(overlap in transcript[p.x_start : p.x_start + p.len_x] for p in pairs)
    for pair in pairs:
        if pair.len_x >= gate.ARM_LEN:
            continue
        extends_3 = (
            pair.x_start + pair.len_x < n
            and pair.xstar_start > 0
            and transcript[pair.xstar_start - 1]
            == sq.reverse_complement(transcript[pair.x_start + pair.len_x])
        )
        extends_5 = (
            pair.x_start > 0
            and pair.xstar_start + pair.len_x < n
            and transcript[pair.xstar_start + pair.len_x]
            == sq.reverse_complement(transcript[pair.x_start - 1])
        )
        assert not extends_3 and not extends_5


def test_trigger_pairs_never_collide_and_respect_the_requested_gap():
    """One nucleotide cannot serve both triggers, and both windows sit on one molecule
    that can fold back and sequester them against each other before either reaches the
    switch — worst in state 11, the one state that has to work."""
    transcript, _ = _transcript_with_a_planted_overlap()

    for pair in _and_gate().find_trigger_pairs(transcript, min_window_gap=40):
        assert pair.disjoint()
        assert pair.gap() >= 40
        assert pair.fits(len(transcript))
