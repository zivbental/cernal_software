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


# --- generate_designs: the "trailing" Kozak layout --------------------------------------
#
# A second, biologically distinct eukaryotic layout: Kozak and the start codon sit after
# the closed hairpin (scanning-ribosome blockage) rather than inside its loop (steric
# occlusion, borrowed from the prokaryotic mechanism). See KOZAK_LAYOUTS's docstring.


def test_prokaryotic_host_only_ever_builds_the_loop_layout(gate, activator_set, constraints):
    """Shine-Dalgarno initiation has no scanning phase for a hairpin to block, so a
    prokaryotic host must ignore "trailing" even though it is in the default sweep."""
    assert gate.kozak_layouts == ("loop", "trailing")  # the class default, unrestricted
    designs = list(gate.generate_designs(activator_set, constraints))
    assert designs  # not vacuously true
    assert {d.architecture["kozak_layout"] for d in designs} == {"loop"}


def test_eukaryotic_host_sweeps_both_kozak_layouts_by_default(activator_set, constraints):
    gate = ToeholdGate(
        Host.HUMAN, FoldEngine(), TranslationScorer(Host.HUMAN), CodonOptimizer(Host.HUMAN)
    )
    designs = list(gate.generate_designs(activator_set, constraints))
    assert {d.architecture["kozak_layout"] for d in designs} == {"loop", "trailing"}


def test_kozak_layouts_can_be_restricted_to_one(activator_set, constraints):
    """The parameter this class exposes for "choose between the architectures",
    mirroring how ``host`` is a parameter rather than a subclass (docs/engine.md §2.4)."""
    gate = ToeholdGate(
        Host.HUMAN,
        FoldEngine(),
        TranslationScorer(Host.HUMAN),
        CodonOptimizer(Host.HUMAN),
        kozak_layouts=("trailing",),
    )
    designs = list(gate.generate_designs(activator_set, constraints))
    assert designs
    assert {d.architecture["kozak_layout"] for d in designs} == {"trailing"}


def test_trailing_layout_sweeps_loop_length_and_kozak_linker_length(activator_set, constraints):
    gate = ToeholdGate(
        Host.HUMAN,
        FoldEngine(),
        TranslationScorer(Host.HUMAN),
        CodonOptimizer(Host.HUMAN),
        kozak_layouts=("trailing",),
    )
    designs = list(gate.generate_designs(activator_set, constraints))
    combos = {(d.architecture["loop_len"], d.architecture["kozak_linker_len"]) for d in designs}
    expected = {
        (loop_len, linker_len)
        for loop_len in gate.TRAILING_LOOP_LENGTHS
        for linker_len in gate.KOZAK_LINKER_LENGTHS
    }
    # One toehold_length's worth at minimum; every combination must appear at least once.
    assert expected.issubset(combos)


def test_trailing_layout_places_kozak_and_start_codon_after_the_hairpin(activator_set, constraints):
    gate = ToeholdGate(
        Host.HUMAN,
        FoldEngine(),
        TranslationScorer(Host.HUMAN),
        CodonOptimizer(Host.HUMAN),
        kozak_layouts=("trailing",),
    )
    design = next(gate.generate_designs(activator_set, constraints))
    arch = design.architecture
    aug_index = arch["aug_index"]

    # Kozak immediately precedes the start codon, as the Kozak consensus requires.
    kozak_start = aug_index - len(gate.KOZAK_EUKARYOTIC)
    assert design.sequence[kozak_start:aug_index] == gate.KOZAK_EUKARYOTIC
    assert design.sequence[aug_index : aug_index + 3] == sq.START_CODON

    # And that whole Kozak+AUG region sits after the fully closed hairpin — the entire
    # point of this layout — rather than inside the loop the way "loop" builds it.
    hairpin_end = (
        arch["leader_len"]
        + arch["toehold_length"]
        + arch["stem_pre_bulge_len"]
        + 3
        + arch["stem_post_bulge_len"]
        + arch["loop_len"]
        + arch["stem_post_bulge_len"]
        + 3
        + arch["stem_pre_bulge_len"]
    )
    assert kozak_start >= hairpin_end + arch["kozak_linker_len"]


def test_trailing_layout_dot_bracket_marks_kozak_and_aug_unpaired(activator_set, constraints):
    gate = ToeholdGate(
        Host.HUMAN,
        FoldEngine(),
        TranslationScorer(Host.HUMAN),
        CodonOptimizer(Host.HUMAN),
        kozak_layouts=("trailing",),
    )
    design = next(gate.generate_designs(activator_set, constraints))
    aug_index = design.architecture["aug_index"]
    tail = design.dot_bracket[aug_index - len(gate.KOZAK_EUKARYOTIC) :]
    assert set(tail) == {"."}
    assert len(design.dot_bracket) == len(design.sequence)
    assert design.dot_bracket.count("(") == design.dot_bracket.count(")")


def test_trailing_layout_ends_at_the_start_codon_no_linker(activator_set, constraints):
    """Unlike "loop", "trailing" carries no LINKER_SEQUENCE after the AUG — the
    scanning ribosome initiates the moment it meets Kozak+AUG, so nothing after the
    start codon plays a role in this layout's own mechanism, and the payload attaches
    directly at plasmid assembly (PlasmidBuilder fuses from aug_index onward)."""
    gate = ToeholdGate(
        Host.HUMAN,
        FoldEngine(),
        TranslationScorer(Host.HUMAN),
        CodonOptimizer(Host.HUMAN),
        kozak_layouts=("trailing",),
    )
    design = next(gate.generate_designs(activator_set, constraints))
    aug_index = design.architecture["aug_index"]
    assert design.architecture["linker_len"] == 0
    assert design.sequence[aug_index:] == sq.START_CODON
    assert len(design.sequence) == aug_index + 3


def test_design_ids_stay_unique_across_both_layouts(activator_set, constraints):
    gate = ToeholdGate(
        Host.HUMAN, FoldEngine(), TranslationScorer(Host.HUMAN), CodonOptimizer(Host.HUMAN)
    )
    ids = [d.design_id for d in gate.generate_designs(activator_set, constraints)]
    assert len(ids) == len(set(ids))


# --- payload: folding the real effector gene's head instead of a placeholder -----------
#
# Without a payload, evaluate_design folds the switch alone (or with LINKER_SEQUENCE for
# "loop") — a different molecule from what a real ribosome sees once a specific gene is
# fused on. PAYLOAD_HEAD_LENGTH folds the real gene's own first nucleotides in instead,
# same idea as AntisenseNotGate.payload (Kudla et al. 2009).

PAYLOAD_CDS = "AUG" + "GCUGGUCAUGCUAGCUAGCGGAUCGAUCGAUCGGCUAGCGAUCGAUCGAUCGGCUAGC" + "UAA"


def test_payload_must_start_with_a_start_codon():
    with pytest.raises(ValueError, match="start codon"):
        ToeholdGate(
            Host.HUMAN,
            FoldEngine(),
            TranslationScorer(Host.HUMAN),
            CodonOptimizer(Host.HUMAN),
            payload="GCUGCUGCU",
        )


def test_payload_must_be_valid_rna_or_dna():
    with pytest.raises(ValueError, match="RNA or DNA"):
        ToeholdGate(
            Host.HUMAN,
            FoldEngine(),
            TranslationScorer(Host.HUMAN),
            CodonOptimizer(Host.HUMAN),
            payload="AUGXYZ",
        )


def test_without_a_payload_nothing_changes(activator_set, constraints):
    """Regression guard: the payload feature is purely additive."""
    with_none = ToeholdGate(
        Host.HUMAN, FoldEngine(), TranslationScorer(Host.HUMAN), CodonOptimizer(Host.HUMAN)
    )
    assert with_none.payload is None
    assert with_none.payload_head is None
    design = next(with_none.generate_designs(activator_set, constraints))
    assert design.architecture["payload_head_length"] == 0


def test_payload_head_is_folded_into_the_loop_layout(activator_set, constraints):
    gate = ToeholdGate(
        Host.HUMAN,
        FoldEngine(),
        TranslationScorer(Host.HUMAN),
        CodonOptimizer(Host.HUMAN),
        kozak_layouts=("loop",),
        payload=PAYLOAD_CDS,
    )
    expected_head = sq.to_rna(PAYLOAD_CDS)[3 : 3 + gate.PAYLOAD_HEAD_LENGTH]
    assert gate.payload_head == expected_head

    design = next(gate.generate_designs(activator_set, constraints))
    assert design.sequence.endswith(expected_head)
    assert design.architecture["payload_head_length"] == len(expected_head)
    # LINKER_SEQUENCE must be gone, replaced by the real head, not appended alongside it.
    assert gate.LINKER_SEQUENCE not in design.sequence


def test_payload_head_is_folded_into_the_trailing_layout(activator_set, constraints):
    gate = ToeholdGate(
        Host.HUMAN,
        FoldEngine(),
        TranslationScorer(Host.HUMAN),
        CodonOptimizer(Host.HUMAN),
        kozak_layouts=("trailing",),
        payload=PAYLOAD_CDS,
    )
    expected_head = sq.to_rna(PAYLOAD_CDS)[3 : 3 + gate.PAYLOAD_HEAD_LENGTH]
    design = next(gate.generate_designs(activator_set, constraints))
    aug_index = design.architecture["aug_index"]
    assert design.sequence[aug_index:] == sq.START_CODON + expected_head
    assert design.architecture["payload_head_length"] == len(expected_head)


def test_payload_changes_evaluate_design_metrics(activator_set, constraints):
    """The whole point: folding in the real downstream sequence changes the OFF/ON
    ensemble the switch is measured against, so a design can score differently with a
    payload than the placeholder-based estimate — this is what could change which
    design ranks best, not just plumbing that returns the same numbers either way."""
    no_payload = ToeholdGate(
        Host.HUMAN,
        FoldEngine(),
        TranslationScorer(Host.HUMAN),
        CodonOptimizer(Host.HUMAN),
        kozak_layouts=("trailing",),
    )
    with_payload = ToeholdGate(
        Host.HUMAN,
        FoldEngine(),
        TranslationScorer(Host.HUMAN),
        CodonOptimizer(Host.HUMAN),
        kozak_layouts=("trailing",),
        payload=PAYLOAD_CDS,
    )
    design_a = next(no_payload.generate_designs(activator_set, constraints))
    design_b = next(with_payload.generate_designs(activator_set, constraints))
    assert design_a.sequence != design_b.sequence

    metrics_a = no_payload.evaluate_design(design_a)
    metrics_b = with_payload.evaluate_design(design_b)
    assert metrics_a["gate_folding_energy"] != pytest.approx(metrics_b["gate_folding_energy"])


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


def test_trailing_layout_reads_leakage_at_the_hairpin_not_the_aug(activator_set, constraints):
    """For "trailing", the AUG sits outside the hairpin and stays accessible regardless
    of the trigger — see evaluate_design's docstring on why AUG-region accessibility
    would not discriminate ON from OFF here. predicted_leakage must instead track the
    toehold+stem region, not the (always-open) AUG."""
    gate = ToeholdGate(
        Host.HUMAN,
        FoldEngine(),
        TranslationScorer(Host.HUMAN),
        CodonOptimizer(Host.HUMAN),
        kozak_layouts=("trailing",),
    )
    design = next(gate.generate_designs(activator_set, constraints))
    metrics = gate.evaluate_design(design)

    arch = design.architecture
    region_start = arch["leader_len"]
    region_end = region_start + (
        arch["toehold_length"] + arch["stem_pre_bulge_len"] + 3 + arch["stem_post_bulge_len"]
    )
    off_matrix = gate.folder.base_pair_probabilities(design.sequence)
    expected_leakage = sum(
        max(0.0, 1.0 - sum(off_matrix[i])) for i in range(region_start, region_end)
    ) / (region_end - region_start)
    assert metrics["predicted_leakage"] == pytest.approx(expected_leakage, abs=1e-6)

    # And it must differ from what the AUG-region formula alone would have given — the
    # whole point of not reusing the "loop" layout's proxy unmodified.
    aug_index = arch["aug_index"]
    aug_accessibility = (
        sum(max(0.0, 1.0 - sum(off_matrix[i])) for i in range(aug_index, aug_index + 3)) / 3
    )
    assert metrics["predicted_leakage"] != pytest.approx(aug_accessibility, abs=1e-6)


def test_trailing_layout_evaluate_design_emits_only_declared_metric_names(
    activator_set, constraints
):
    gate = ToeholdGate(
        Host.HUMAN,
        FoldEngine(),
        TranslationScorer(Host.HUMAN),
        CodonOptimizer(Host.HUMAN),
        kozak_layouts=("trailing",),
    )
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

    assert design.design_id == "toehold-trig-000042-12-loop"
    assert design.architecture == {
        "toehold_length": 12,
        "stem_pre_bulge_len": 9,
        "stem_post_bulge_len": 6,
        "loop_len": 11,
        "leader_len": 3,
        "linker_len": 21,
        "payload_head_length": 0,
        "aug_index": 50,
        "track": "prokaryotic",
        "kozak_layout": "loop",
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
