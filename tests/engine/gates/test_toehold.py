"""``ToeholdGate`` — single-input toehold switch generation and evaluation.

Real ``FoldEngine``/ViennaRNA throughout, matching ``test_antisense.py``: every switch
here tops out under 90 nt, so a real fold costs low milliseconds.
"""

import itertools

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
    _mean_unpaired,
    _pareto_front,
    _secondary_domains,
)
from engine.gates.tools.binding import (
    alignment_pairs,
    can_pair,
    longest_complementary_run,
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


def test_forbidden_motifs_are_caught_in_the_trigger_window():
    """These are regular expressions, which is exactly why they cannot go through
    `MotifScreener` — it `re.escape`s its extra motifs and can only match literals."""
    gate = _and_gate()
    clean_pre = "GCAUCGAUC"

    assert gate.screen_trigger_window("ACGUACGUACGU", clean_pre) == ()
    assert "RNase_E" in gate.screen_trigger_window("ACGAAUGAACGU", clean_pre)
    assert "poly_U" in gate.screen_trigger_window("ACGUUUUUACGU", clean_pre)
    assert "internal_SD" in gate.screen_trigger_window("ACGAGGAGGACG", clean_pre)


def test_a_stop_codon_in_main_pre_is_read_in_its_own_frame():
    """`main_pre` lands at +4..+12 in the finished switch, so its frame is set by the
    switch's own start codon, not by the frame it occupied in the source transcript. Read
    in the wrong frame this check both misses real stops and invents absent ones."""
    gate = _and_gate()

    assert "in_frame_stop" in gate.screen_trigger_window("ACGUACGUACGU", "GCAUAAGCU")
    #      ^ UAA at offset 3, in frame.  Below, the same UAA sits at offset 4 - out of
    #        frame, harmless, and must not be reported.
    assert "in_frame_stop" not in gate.screen_trigger_window("ACGUACGUACGU", "GCAGUAAGC")


def test_a_trigger_of_pure_methionine_and_tryptophan_cannot_be_knocked_out():
    """AUG and UGG have no synonym at all, so no synonymous substitution can touch them.
    A pair resting on such a stretch has no negative control and is unusable however good
    the gate would be - which is why this runs inside the scan, not after it."""
    gate = _and_gate()
    immovable = "AUGUGGAUGUGGAUGUGG"

    assert not gate.knockout_possible(immovable, 0, 6, sq.reverse_complement(immovable[:6]))


def test_a_trigger_with_synonymous_freedom_can_be_knocked_out():
    """The other side of the check: leucine and serine each have six codons, so these
    positions can be broken and the control is buildable. Without a passing case the
    immovable one above would also pass a function that always answered `False`."""
    gate = _and_gate()
    region = "CUGCUGCUGAGCAGCAGC"

    assert gate.knockout_possible(region, 0, len(region), sq.reverse_complement(region))


# --- Assembly ------------------------------------------------------------------------


def _assembled(conflict_at=_CONFLICT_AT):
    gate = _and_gate()
    trigger_a, trigger_b, _ = _contested_pair(conflict_at=conflict_at)
    stem = gate.secondary_stems(trigger_a, trigger_b, len(_OVERLAP))[0]
    return gate, gate.assemble(trigger_a, trigger_b, len(_OVERLAP), stem)


def test_the_folded_region_is_161_nucleotides_whatever_the_overlap_length():
    """`len_k2 = 18 - len_x` cancels `len_x`, so the cap-through-LINKER region the four
    tubes fold is a fixed size. This is the one number that catches a dropped or
    duplicated domain, because every other check would still pass."""
    gate = _and_gate()

    for len_x in (4, 5, 6, 7):
        trigger_a, trigger_b, _ = _contested_pair()
        stem = gate.secondary_stems(trigger_a, trigger_b, len_x)[0]
        assert len(gate.assemble(trigger_a, trigger_b, len_x, stem).sequence) == 161


def test_every_domain_lands_on_the_coordinate_the_specification_quotes():
    """The layout, in the framework's own numbering. An off-by-one here still folds and
    still scores, so it has to be asserted rather than inspected."""
    _, switch = _assembled()

    expected = {
        "main_pre_star": (-42, -34),
        "bulge_star": (-33, -31),
        "k1_star": (-30, -25),
        "rbs_loop": (-24, -7),
        "main_z": (-6, -1),
        "aug": (1, 3),
        "main_pre": (4, 12),
    }
    for name, (first, last) in expected.items():
        start, end = switch.domains[name]
        assert (switch.position(start), switch.position(end - 1)) == (first, last), name


def test_the_start_codon_is_where_the_windows_are_measured_from():
    _, switch = _assembled()
    start, end = switch.domains["aug"]

    assert switch.sequence[start:end] == "AUG"
    assert switch.position(start) == 1
    assert switch.position(start - 1) == -1, "the numbering has no zero"
    # -17 is 17 bases before the A; +13 is the 13th base of the CDS, and the numbering
    # skips zero, so the half-open end lands at start + 13 rather than end + 13.
    assert switch.span(-17, 13) == (start - 17, start + 13)
    assert switch.span(-17, 13)[1] - switch.span(-17, 13)[0] == 30  # W_rank
    assert switch.span(-24, 13)[1] - switch.span(-24, 13)[0] == 37  # W_flank


def test_the_two_hairpins_are_directly_adjacent():
    """`a = 0` is the defining parameter: with no exposed spacer, trigger A has nowhere to
    land until trigger B has opened the inhibitory hairpin."""
    _, switch = _assembled()

    assert switch.domains["sw_xs"][1] == switch.domains["main_pre_star"][0]


def test_the_ribosome_binding_site_sits_flush_at_the_3_end_of_its_loop():
    """What makes `k1*` the Shine-Dalgarno-to-start spacing (R2, R8). If the RBS floated
    within the loop that spacing would silently change."""
    gate, switch = _assembled()
    start, end = switch.domains["rbs_loop"]

    assert switch.sequence[start:end].endswith(gate.RBS_PROKARYOTIC)
    assert end - start == 18


def test_the_main_stem_uses_trigger_as_own_k1_so_it_pairs_perfectly():
    """`mainZ` is trigger A's 5' six nucleotides, which makes the main stem's ddG_pref
    exactly zero — accepted, because trigger A's advantage comes from the toehold and from
    pairing straight through the 3x3 internal loop the hairpin cannot."""
    gate, switch = _assembled()
    trigger_a, _, _ = _contested_pair()
    k1_start, k1_end = switch.domains["k1_star"]
    z_start, z_end = switch.domains["main_z"]

    assert switch.sequence[z_start:z_end] == trigger_a[: gate.STEM_POST_BULGE_LEN]
    assert switch.sequence[k1_start:k1_end] == sq.reverse_complement(switch.sequence[z_start:z_end])


def test_the_off_structure_is_a_legal_balanced_target():
    """`ensemble_defect` takes this as its reference, and rejects anything unbalanced or
    of the wrong length."""
    _, switch = _assembled()

    assert len(switch.dot_bracket) == len(switch.sequence)
    assert switch.dot_bracket.count("(") == switch.dot_bracket.count(")")
    depth = 0
    for character in switch.dot_bracket:
        depth += (character == "(") - (character == ")")
        assert depth >= 0
    assert depth == 0


def test_the_start_codon_is_left_open_in_the_off_state():
    """It sits in the 3x3 internal loop opposite the bulge and is already unpaired with no
    trigger present. The gate works by burying the ribosome binding site and the stem
    around the AUG, not the AUG itself."""
    _, switch = _assembled()
    start, end = switch.domains["aug"]

    assert switch.dot_bracket[start:end] == "..."


def test_the_off_structure_pairs_only_what_the_bases_can_actually_pair():
    """Scheme C leaves mismatches in the upper stem by design, so a reference structure
    drawn from the diagram rather than the sequence would score every design against
    something impossible."""
    _, switch = _assembled()

    opens: list[int] = []
    for index, character in enumerate(switch.dot_bracket):
        if character == "(":
            opens.append(index)
        elif character == ")":
            partner = opens.pop()
            assert can_pair(switch.sequence[partner], switch.sequence[index])


def test_an_aug_inside_main_z_is_repaired_through_a_wobble():
    """A trigger beginning with AUG would put a second start codon in the 5' UTR, out of
    frame with the real one. Rather than discard the candidate, the A moves to a G: it
    still pairs with its partner in `k1*`, as a G:U wobble rather than Watson-Crick, so
    the stem stays closed and only that one pair weakens. On mCherry this recovers 54 of
    the 93 candidates the check would otherwise reject."""
    gate = _and_gate()
    trigger_a, trigger_b, _ = _contested_pair()
    with_aug = "AUGAAA" + trigger_a[6:]
    stem = gate.secondary_stems(with_aug, trigger_b, len(_OVERLAP))[0]

    switch = gate.assemble(with_aug, trigger_b, len(_OVERLAP), stem)
    start, end = switch.domains["main_z"]
    main_z = switch.sequence[start:end]

    assert gate.assembly_violations(switch) == ()
    assert main_z != with_aug[:6], "mainZ should have been repaired"
    assert sum(a != b for a, b in zip(main_z, with_aug[:6], strict=True)) == 1
    # every position still pairs with k1*, which is what makes the repair cheap
    k1_start, k1_end = switch.domains["k1_star"]
    assert all(alignment_pairs(main_z, switch.sequence[k1_start:k1_end]))


def test_an_aug_straddling_the_rbs_loop_boundary_cannot_be_repaired():
    """The RBS loop ends in A, so a `mainZ` beginning `UG` makes an AUG across the join —
    and U and G are exactly the two bases with no alternative, since only U pairs with A
    and only G pairs with C. The fault is reported rather than papered over with a design
    that quietly stopped pairing."""
    gate = _and_gate()
    trigger_a, trigger_b, _ = _contested_pair()
    straddling = "UGAAAA" + trigger_a[6:]
    stem = gate.secondary_stems(straddling, trigger_b, len(_OVERLAP))[0]

    switch = gate.assemble(straddling, trigger_b, len(_OVERLAP), stem)

    assert gate.RBS_PROKARYOTIC.endswith("A")
    assert "upstream_aug" in gate.assembly_violations(switch)


def test_a_clean_switch_reports_no_assembly_violations():
    gate, switch = _assembled()

    assert gate.assembly_violations(switch) == ()


# --- Stage 4: the four tubes ---------------------------------------------------------


@pytest.fixture(scope="module")
def four_tubes():
    """One assembled switch and its observables. Module-scoped: four partition functions
    over a 161-nt switch plus two triggers costs a few seconds."""
    gate = _and_gate()
    trigger_a, trigger_b, _ = _contested_pair()
    stem = gate.secondary_stems(trigger_a, trigger_b, len(_OVERLAP))[0]
    switch = gate.assemble(trigger_a, trigger_b, len(_OVERLAP), stem)
    return (
        gate,
        switch,
        trigger_a,
        trigger_b,
        gate.four_tube_observables(switch, trigger_a, trigger_b),
    )


def test_all_four_logic_states_are_folded(four_tubes):
    _, _, _, _, o = four_tubes

    for state in ("00", "01", "10", "11"):
        assert o[f"dG_open_{state}"] is not None


def test_separation_is_the_worst_off_state_against_the_on_state(four_tubes):
    """A minimum, not a mean. An AND gate is only as good as its leakiest OFF state, and
    taking the minimum is what makes a state-10 leak collapse the score instead of being
    averaged away by two healthy states."""
    _, _, _, _, o = four_tubes

    worst = min(o[f"dG_open_{s}"] for s in ("00", "01", "10"))
    assert o["separation"] == pytest.approx(worst - o["dG_open_11"])


def test_trigger_a_is_scored_conditioned_on_trigger_b(four_tubes):
    """`dG_bind_A_given_B` is G(S.A.B) - G(S.B) - G(A), never G(S.A) - G(S) - G(A).
    Measured against the bare switch, the term would reward trigger A for opening the main
    hairpin alone — which is exactly the state-10 leak the gates exist to prevent, so the
    score and the gate would pull in opposite directions."""
    gate, switch, trigger_a, _, o = four_tubes
    folder = gate.folder

    conditioned = o["dG_bind_A_given_B"]
    against_bare_switch = (
        folder.partition(f"{switch.sequence}&{trigger_a}")
        - folder.partition(switch.sequence)
        - folder.partition(trigger_a)
    )
    assert conditioned != pytest.approx(against_bare_switch)


def test_the_two_binding_energies_are_not_summed(four_tubes):
    """Summing them telescopes to G(S.A.B) - G(S) - G(A) - G(B), the total ternary energy,
    which is path-independent and carries no information about the cascade at all. The
    sequential structure conditioning was introduced to capture would be destroyed."""
    gate, switch, trigger_a, trigger_b, o = four_tubes
    folder = gate.folder

    telescoped = (
        folder.partition(f"{switch.sequence}&{trigger_a}&{trigger_b}")
        - folder.partition(switch.sequence)
        - folder.partition(trigger_a)
        - folder.partition(trigger_b)
    )
    assert o["dG_bind_B"] + o["dG_bind_A_given_B"] == pytest.approx(telescoped)


def test_a_construct_that_opens_on_trigger_a_alone_fails_separation(four_tubes):
    """The deliberately-broken case, and the one worth having: when trigger A alone opens
    the main hairpin, `dG_open(10)` falls to `dG_open(11)`, the minimum selects state 10,
    and `separation` collapses to zero or below. Getting the wrong sign here is the test
    passing."""
    _, _, _, _, o = four_tubes

    assert o["dG_open_10"] == pytest.approx(o["dG_open_11"], abs=0.01)
    assert o["separation"] <= 0.01
    assert o["A_M_10"] > 0.2, "state-10 leak should also fail the A_M(10) gate"


def test_the_flank_is_measured_but_never_ranked(four_tubes):
    """`W_flank` adds the seven designed nucleotides 5' of the RBS and is a pass/fail check
    on those alone. It never enters `separation`, because in state 11 the region upstream
    of -24 is duplexed to trigger A and ranking there penalises a working gate."""
    _, switch, _, _, o = four_tubes

    assert switch.span(-24, 13)[1] - switch.span(-24, 13)[0] == 37
    assert switch.span(-17, 13)[1] - switch.span(-17, 13)[0] == 30
    assert o["flank_penalty"] == pytest.approx(o["dG_open_flank_00"] - o["dG_open_00"])
    assert o["flank_penalty"] >= -0.01, "a wider window cannot be cheaper to open"


def test_stem_and_toehold_accessibility_are_probabilities(four_tubes):
    """Bounded in [0, 1], so the 0.2 and 0.5 thresholds mean something. Not the joint
    probability that a whole arm opens at once — over eighteen nucleotides that is ~1e-22
    even with nothing to pair against, and every design would fail every gate."""
    _, _, _, _, o = four_tubes

    for state in ("00", "01", "10", "11"):
        for name in ("A_S", "A_M", "A_S_full"):
            assert 0.0 <= o[f"{name}_{state}"] <= 1.0
    assert 0.0 <= o["A_r2_star_00"] <= 1.0
    assert 0.0 <= o["d_off"] <= 1.0


# --- The cheap pre-filter, and the gates ---------------------------------------------


def test_the_pair_screen_agrees_with_a_full_evaluation_on_every_stem():
    """The premise the funnel rests on. Scheme C designs only the secondary hairpin, so
    the main hairpin, the free toehold and everything derived from them are the same
    molecule whichever build it picks. If this ever stops holding, screening a pair before
    enumerating its stems starts discarding designs that would have worked."""
    gate = _and_gate()
    trigger_a, trigger_b, _ = _contested_pair()
    stems = gate.secondary_stems(trigger_a, trigger_b, len(_OVERLAP))
    weakest = max(stems, key=lambda s: s.ddg_pref)
    strongest = min(stems, key=lambda s: s.lock_energy)
    assert weakest is not strongest

    screened = gate.screen_pair(trigger_a, trigger_b, len(_OVERLAP))
    full = [
        gate.four_tube_observables(
            gate.assemble(trigger_a, trigger_b, len(_OVERLAP), stem), trigger_a, trigger_b
        )
        for stem in (weakest, strongest)
    ]

    # Not exactly equal, and should not be: the two hairpins sit on one molecule, so the
    # ensembles couple slightly. The measured spread is under 0.01 kcal/mol, two orders of
    # magnitude below the folding model's own ~1.5 kcal/mol error, so it cannot move a gate
    # or a ranking.
    assert set(screened) == gate.STEM_INDEPENDENT
    for name in gate.STEM_INDEPENDENT:
        assert full[0][name] == pytest.approx(full[1][name], abs=0.02), name
        assert screened[name] == pytest.approx(full[0][name], abs=0.02), name


def test_everything_trigger_b_touches_is_excluded_from_the_pair_screen():
    """The other half, and the one that would silently break the funnel. Trigger B binds
    the secondary stem, so every observable involving it moves with the build — measured
    here at ~20 kcal/mol for `dG_bind_B` alone. Screening a pair on these would reject
    candidates a different stem would have saved."""
    gate = _and_gate()
    trigger_a, trigger_b, _ = _contested_pair()
    stems = gate.secondary_stems(trigger_a, trigger_b, len(_OVERLAP))
    pair = (max(stems, key=lambda s: s.ddg_pref), min(stems, key=lambda s: s.lock_energy))

    full = [
        gate.four_tube_observables(
            gate.assemble(trigger_a, trigger_b, len(_OVERLAP), stem), trigger_a, trigger_b
        )
        for stem in pair
    ]

    for name in ("dG_bind_B", "dG_bind_A_given_B", "dG_open_01", "ddG_AND"):
        assert name not in gate.STEM_INDEPENDENT, name
        assert abs(full[0][name] - full[1][name]) > 0.5, name
    assert abs(full[0]["dG_bind_B"] - full[1]["dG_bind_B"]) > 10.0


def test_the_pair_screen_only_gates_what_no_stem_could_rescue():
    """A rejection at the pair screen is final, so it may only use thresholds whose
    observable the build cannot move."""
    gate = _and_gate()

    screened = dict.fromkeys(gate.STEM_INDEPENDENT)  # every value None -> "<name>=None"
    names = {v.removesuffix("=None") for v in gate.pair_gate_violations(screened)}

    assert names <= gate.STEM_INDEPENDENT
    assert "A_M_10" in names, "the state-10 leak is the whole point of screening early"
    assert not any(n.startswith("A_S") or n == "separation" for n in names)


def test_the_probe_switch_serves_both_triggers_everywhere():
    """Built at the corner that needs no energies, so screening a pair costs one fold and
    no stem enumeration at all."""
    gate = _and_gate()
    trigger_a, trigger_b, wanted = _contested_pair()

    probe = gate.probe_switch(trigger_a, trigger_b, len(_OVERLAP))
    start, end = probe.domains["k2_star"]

    assert probe.sequence[start:end] == wanted


def test_the_gates_report_every_failure_not_the_first():
    """A design failing one threshold and a design failing six are different objects, and
    when nothing passes, *which* gate is binding is the entire result."""
    gate = _and_gate()
    hopeless = dict.fromkeys(
        (name for name, _, _ in gate.THRESHOLDS), 0.35
    )  # fails every < 0.2 and every > 0.5 at once
    hopeless["separation"] = 0.0
    hopeless["ddG_AND"] = 0.0

    violations = gate.gate_violations(hopeless)

    assert len(violations) == len(gate.THRESHOLDS)


def test_an_unmeasured_observable_fails_its_gate_rather_than_passing_it():
    """`None` means the ensemble could not be computed. Admitting the design would let it
    outrank measured ones on a number nobody has."""
    gate = _and_gate()
    observables = {name: None for name, _, _ in gate.THRESHOLDS}

    assert all(v.endswith("=None") for v in gate.gate_violations(observables))


def test_a_design_meeting_every_threshold_passes():
    gate = _and_gate()
    good = {}
    for name, comparison, threshold in gate.THRESHOLDS:
        good[name] = threshold - 0.05 if comparison == "<" else threshold + 0.05

    assert gate.gate_violations(good) == ()


# --- Stage 6: the bench constructs ---------------------------------------------------


def test_a_knockout_leaves_no_run_long_enough_to_nucleate():
    """The criterion comes from the architecture, not from taste: a trigger needs four
    contiguous complementary nucleotides to nucleate at all, so a control is any
    synonymous variant leaving none. Wobbles count, which is what makes it demanding."""
    gate = _and_gate()
    # Nine nucleotides of leucine, which is the scale a real overlap is: mCherry's clean
    # candidates top out at len_x = 7. A longer perfect duplex needs more breaks than the
    # four-substitution budget allows, and correctly returns None.
    region = "CUGCUGCUG"
    partner = sq.reverse_complement(region)

    result = gate.knockout(region, 0, len(region), partner)

    assert result is not None
    assert result.residual_run < gate.MIN_OVERLAP
    disabled = result.sequence[0 : len(region)]
    assert longest_complementary_run(disabled, partner) < gate.MIN_OVERLAP


def test_a_knockout_never_changes_the_protein():
    """The whole point of the four constructs is that they differ in one variable. A
    control that translates differently is testing two things at once."""
    gate = _and_gate()
    region = "CUGCUGCUG"

    result = gate.knockout(region, 0, len(region), sq.reverse_complement(region))

    assert result is not None
    assert sq.translate(result.sequence, stop_at_stop=False) == sq.translate(
        region, stop_at_stop=False
    )


def test_a_knockout_spends_the_fewest_substitutions_that_work():
    """Minimal substitutions, by supervisor instruction and matching the .docx. The
    original sequence is the one with bench data behind it, and every edit perturbs local
    folding and expression, so a control spends only what the no-run-of-four criterion
    demands. Ties break toward the variant retaining least pairing."""
    gate = _and_gate()
    region = "CUGCUGCUG"
    partner = sq.reverse_complement(region)

    result = gate.knockout(region, 0, len(region), partner)

    assert result is not None
    assert result.edits
    for position, was, now in result.edits:
        assert region[position] == was
        assert result.sequence[position] == now
        assert was != now
    assert result.pairable_positions < sum(alignment_pairs(region, partner))
    # Brute-force every synonymous spelling of this 3-codon region: none that satisfies the
    # criterion may use fewer substitutions than the variant chosen.
    spent = len(result.edits)
    for a in [region[0:3], *gate._synonymous(region[0:3])]:
        for b in [region[3:6], *gate._synonymous(region[3:6])]:
            for c in [region[6:9], *gate._synonymous(region[6:9])]:
                variant = a + b + c
                if variant == region:
                    continue
                if longest_complementary_run(variant, partner) >= gate.MIN_OVERLAP:
                    continue
                if sq.translate(variant, stop_at_stop=False) != sq.translate(
                    region, stop_at_stop=False
                ):
                    continue
                changed = sum(1 for p, q in zip(variant, region, strict=True) if p != q)
                assert changed >= spent, f"{variant} disables it in {changed} < {spent}"


def test_a_long_region_is_disabled_rather_than_refused():
    """There is no cap on substitutions. The ported script carried `max_edits=4` as an
    undeclared default, which silently refused any region needing more -- a 15-nt perfect
    duplex among them. Every edit is confined to one trigger domain, so the total
    perturbation stays around 1% of the transcript either way."""
    gate = _and_gate()
    long_perfect = "CUGCUGCUGAGCAGC"

    result = gate.knockout(long_perfect, 0, len(long_perfect), sq.reverse_complement(long_perfect))

    assert result is not None
    assert len(result.edits) > 4, "this is exactly what the old cap refused"
    assert result.residual_run < gate.MIN_OVERLAP


def test_an_unbreakable_region_yields_no_knockout_rather_than_a_bad_one():
    """AUG and UGG have no synonym at all. Returning `None` is the honest answer, and it
    is why feasibility is checked during the scan rather than after a pair is chosen."""
    gate = _and_gate()
    immovable = "AUGUGGAUGUGGAUGUGG"

    assert gate.knockout(immovable, 0, 6, sq.reverse_complement(immovable[:6])) is None


def test_state_00_disables_both_triggers_on_the_same_background():
    """By instruction, state 00 is a variant with *both* triggers deleted rather than the
    transcript withheld. Withholding it also removes its transcriptional and translational
    load, so 00-versus-11 would confound the triggers with the burden of expressing the
    molecule at all. Every construct here is the same length, abundance and protein."""
    gate = _and_gate()
    transcript, _ = _transcript_with_a_planted_overlap()
    pair = next(gate.find_trigger_pairs(transcript, min_window_gap=0))

    constructs = gate.bench_constructs(transcript, pair)

    assert set(constructs) == {"00", "01", "10", "11"}
    assert constructs["11"] == sq.to_rna(transcript)
    if constructs["00"] is not None:
        assert len(constructs["00"]) == len(constructs["11"])
        assert sq.translate(constructs["00"], stop_at_stop=False) == sq.translate(
            constructs["11"], stop_at_stop=False
        )
        # 00 is the two single knockouts applied together, so it carries both edit sets.
        changed = {
            i
            for i, (a, b) in enumerate(zip(constructs["11"], constructs["00"], strict=True))
            if a != b
        }
        for single in ("01", "10"):
            if constructs[single] is None:
                continue
            assert {
                i
                for i, (a, b) in enumerate(zip(constructs["11"], constructs[single], strict=True))
                if a != b
            } <= changed


def test_disabling_trigger_a_gives_state_01_not_state_10():
    """The left digit is trigger A, so the construct with trigger A disabled is state 01.
    Swapping these mislabels every control in the panel, and the experiment cannot tell."""
    gate = _and_gate()
    transcript, _ = _transcript_with_a_planted_overlap()
    pair = next(gate.find_trigger_pairs(transcript, min_window_gap=0))

    constructs = gate.bench_constructs(transcript, pair)

    for state, site in (("01", pair.x_start), ("10", pair.xstar_start)):
        if constructs[state] is None:
            continue
        changed = [
            i
            for i, (a, b) in enumerate(zip(sq.to_rna(transcript), constructs[state], strict=True))
            if a != b
        ]
        assert changed, state
        # every edit sits in, or in the invasion arm 5' of, the disabled trigger's own site
        assert min(changed) >= site - gate.ARM_LEN
        assert max(changed) < site + pair.len_x + 3


def test_stems_are_labelled_by_the_scheme_that_could_build_them():
    """A panel is stratified by family, so each build has to say which one it belongs to.
    "mixed" is the only label that is evidence scheme C earns its 3^n cost: it resolves
    some positions the A way and others the B way, which neither global scheme can
    express."""
    gate = _and_gate()
    trigger_a, trigger_b, _ = _contested_pair()

    stems = gate.secondary_stems(trigger_a, trigger_b, len(_OVERLAP))
    labels = {stem.scheme for stem in stems}

    assert labels <= {"A-anchored", "B-anchored", "mixed", "unlocked"}
    for stem in stems:
        states = set(stem.states)
        if {"lockA", "lockB"} <= states:
            assert stem.scheme == "mixed"
        elif "lockA" in states:
            assert stem.scheme == "A-anchored"
        elif "lockB" in states:
            assert stem.scheme == "B-anchored"
        else:
            assert stem.scheme == "unlocked"
    assert "mixed" in labels, "scheme C should reach builds neither global scheme can"


# --- main_stem_energies: the three numbers behind the state-10 leak -------------------


def test_the_design_as_it_stands_lets_trigger_a_beat_its_own_stem():
    """The state-10 leak, as an energy rather than as a fold. With `mainZ = k1` — what
    `assemble` chooses — trigger A is complementary to all 18 nt of the ascending arm, so
    `grip_alone` beats `stem` outright and nothing about trigger B is needed to open the
    hairpin. This is the measurement the whole problem rests on, so it is pinned."""
    gate = _and_gate()
    trigger_a, _, _ = _contested_pair()
    k1 = trigger_a[: gate.STEM_POST_BULGE_LEN]

    stem, grip_alone, grip_with_x = gate.main_stem_energies(trigger_a, len(_OVERLAP), k1)

    assert grip_alone < stem, "as designed, trigger A wins on the 18-nt arm alone"
    assert grip_with_x < grip_alone, "the overlap can only add base pairs, never remove any"


def test_some_spacer_puts_the_stem_back_in_front_of_trigger_a():
    """The one lever, and the claim the whole experiment rests on: that the window
    `grip_with_x < stem < grip_alone` is reachable by choosing `mainZ` alone. `k1*` is
    `revcomp(mainZ)`, so a spacer unrelated to trigger A's `k1` costs trigger A six of its
    eighteen pairs while the stem keeps all eighteen. Searched rather than asserted on one
    hand-picked spacer, because which spacers land inside depends on the trigger's own GC
    content — the search is what `strength_window.py` does, at one pair."""
    gate = _and_gate()
    trigger_a, _, _ = _contested_pair()

    inside = []
    for letters in itertools.product("ACGU", repeat=gate.STEM_POST_BULGE_LEN):
        spacer = "".join(letters)
        stem, alone, with_x = gate.main_stem_energies(trigger_a, len(_OVERLAP), spacer)
        if alone > stem > with_x:
            inside.append((min(alone - stem, stem - with_x), spacer))

    assert inside, "no spacer reaches the window; the experiment would have nothing to test"
    best_margin, best = max(inside)
    assert best != trigger_a[: gate.STEM_POST_BULGE_LEN]
    assert best_margin > 0.0


def test_the_window_is_a_screen_and_never_a_score():
    """`main_stem_energies` prices three fixed alignments and knows nothing about the rest
    of the molecule, so it can only ever narrow the set that gets folded. Asserting the
    contract — no folding, so no `None` from a sentinel, and identical inputs give
    identical answers — keeps a later caller from ranking on it."""
    gate = _and_gate()
    trigger_a, _, _ = _contested_pair()

    first = gate.main_stem_energies(trigger_a, len(_OVERLAP), "GCCGAC")
    again = gate.main_stem_energies(trigger_a, len(_OVERLAP), "GCCGAC")

    assert first == again
    assert all(value is not None and abs(value) < 1e4 for value in first)


def test_an_unmeasurable_span_is_none_rather_than_a_fully_sequestered_region():
    """`_mean_unpaired` feeds accessibility metrics, where higher is better, so 0.0 is the
    worst possible score and not a missing one. A span that runs off the matrix means the
    domain map and the folded sequence are out of step -- reporting 0.0 would hide that
    bug behind a design that merely looks bad. CLAUDE.md section 3."""
    matrix = [[0.0, 0.4], [0.4, 0.0]]

    assert _mean_unpaired(matrix, 0, 2) == pytest.approx(0.6)
    assert _mean_unpaired(matrix, 1, 1) is None, "empty span"
    assert _mean_unpaired(matrix, 1, 9) is None, "runs off the end"
    assert _mean_unpaired(matrix, -1, 2) is None, "starts before the matrix"
