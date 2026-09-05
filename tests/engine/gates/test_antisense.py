"""``AntisenseNotGate`` — the NOT gate's inverting element.

Real ``FoldEngine``/ViennaRNA throughout: unlike ``test_tools.py``, there is no fake to
fall back to here, and the whole point of the golden test is to pin the actual
partition-function numbers this gate produces. Every sequence involved is tiny (the
switch tops out around 55 nt, the dimer around 85), so a real fold costs low
milliseconds and the whole file stays comfortably under docs/engine.md §8's
one-second budget.
"""

import pytest

from engine import sequences as sq
from engine.domain import Compatibility, Constraints, Host, TriggerCandidate, TriggerSet
from engine.gates.antisense import AntisenseNotGate
from engine.gates.tools.codons import CodonOptimizer
from engine.gates.tools.folding import FoldEngine

# The exact trigger window validated outside this repo (choose_trigger.py's pick against
# mCherry as a stand-in payload: the most AU-rich window with no anti-SD motif). Reused
# here rather than a made-up sequence so the golden test pins real science, not noise.
MCHERRY_TRIGGER = "UGAUGAACUUCGAGGACGGCGGCGUGGUGA"

# The gate is generic over the payload gene (it's a required constructor argument, not a
# hardcoded sequence) — this is a real payload to prove that genericity against something
# other than the trigger's own gene. Standard EGFP CDS.
GFP_PAYLOAD = (
    "AUGGUGAGCAAGGGCGAGGAGCUGUUCACCGGGGUGGUGCCCAUCCUGGUCGAGCUGGACGGCGACGUAAACGGCCAC"
    "AAGUUCAGCGUGUCCGGCGAGGGCGAGGGCGAUGCCACCUACGGCAAGCUGACCCUGAAGUUCAUCUGCACCACCGGC"
    "AAGCUGCCCGUGCCCUGGCCCACCCUCGUGACCACCCUGACCUACGGCGUGCAGUGCUUCAGCCGCUACCCCGACCAC"
    "AUGAAGCAGCACGACUUCUUCAAGUCCGCCAUGCCCGAAGGCUACGUCCAGGAGCGCACCAUCUUCUUCAAGGACGAC"
    "GGCAACUACAAGACCCGCGCCGAGGUGAAGUUCGAGGGCGACACCCUGGUGAACCGCAUCGAGCUGAAGGGCAUCGAC"
    "UUCAAGGAGGACGGCAACAUCCUGGGGCACAAGCUGGAGUACAACUACAACAGCCACAACGUCUAUAUCAUGGCCGAC"
    "AAGCAGAAGAACGGCAUCAAGGUGAACUUCAAGAUCCGCCACAACAUCGAGGACGGCAGCGUGCAGCUCGCCGACCAC"
    "UACCAGCAGAACACCCCCAUCGGCGACGGCCCCGUGCUGCUGCCCGACAACCACUACCUGAGCACCCAGUCCGCCCUG"
    "AGCAAAGACCCCAACGAGAAGCGCGAUCACAUGGUCCUGCUGGAGUUCGUGACCGCCGCCGGGAUCACUCUCGGCAUG"
    "GACGAGCUGUACAAGUAA"
)


def make_trigger(**overrides) -> TriggerCandidate:
    """A tiny, deterministic repressor trigger. Any field can be overridden."""
    sequence = overrides.pop("sequence", MCHERRY_TRIGGER)
    defaults = {
        "trigger_id": "trig-mcherry-589",
        "gene_id": "mCherry",
        "symbol": "mCherry",
        "sequence": sequence,
        "start_index": 588,
        "openness": 0.70,
        "accessibility": 0.65,
        "mfe": -4.0,
        "off_target_penalty": 0.0,
        "segment_specificity": 0.9,
        "gc_content": sq.gc_content(sequence),
        "score": 0.8,
    }
    defaults.update(overrides)
    return TriggerCandidate(**defaults)


@pytest.fixture
def gate() -> AntisenseNotGate:
    return AntisenseNotGate(
        Host.ECOLI, FoldEngine(temperature=37.0), CodonOptimizer(Host.ECOLI), GFP_PAYLOAD
    )


@pytest.fixture
def repressor_set() -> TriggerSet:
    return TriggerSet(activators=(), repressors=(make_trigger(),))


@pytest.fixture
def constraints() -> Constraints:
    return Constraints()


# --- payload: generic over the gene, not hardcoded ------------------------------------


def test_construction_requires_a_payload():
    with pytest.raises(TypeError):
        AntisenseNotGate(Host.ECOLI, FoldEngine(), CodonOptimizer(Host.ECOLI))  # type: ignore[call-arg]


def test_payload_must_be_valid_rna_or_dna():
    with pytest.raises(ValueError, match="RNA or DNA"):
        AntisenseNotGate(Host.ECOLI, FoldEngine(), CodonOptimizer(Host.ECOLI), "not a sequence")


def test_payload_must_start_with_a_start_codon():
    with pytest.raises(ValueError, match="start codon"):
        AntisenseNotGate(Host.ECOLI, FoldEngine(), CodonOptimizer(Host.ECOLI), "GCUGCUGCU")


def test_payload_accepts_dna_too():
    """Researchers paste DNA as often as RNA (docs/engine.md's sequences.to_rna rule)."""
    dna_payload = GFP_PAYLOAD.replace("U", "T")
    gate = AntisenseNotGate(Host.ECOLI, FoldEngine(), CodonOptimizer(Host.ECOLI), dna_payload)
    assert gate.payload == GFP_PAYLOAD


def test_different_payloads_produce_different_switches(repressor_set, constraints):
    """The whole point: the same trigger, folded against two different genes, must not
    collapse to the same design — that would mean the payload was never really used."""
    gfp_gate = AntisenseNotGate(Host.ECOLI, FoldEngine(), CodonOptimizer(Host.ECOLI), GFP_PAYLOAD)
    other_payload = "AUG" + "GCU" * 10 + "UAA"
    other_gate = AntisenseNotGate(
        Host.ECOLI, FoldEngine(), CodonOptimizer(Host.ECOLI), other_payload
    )

    gfp_design = next(gfp_gate.generate_designs(repressor_set, constraints))
    other_design = next(other_gate.generate_designs(repressor_set, constraints))

    assert gfp_design.sequence != other_design.sequence
    # Only the part after AUG should differ — the trigger-derived UTR/loop/spacer/AUG
    # are identical, since neither gate's __init__ arguments touched them.
    aug_end = (
        gfp_design.architecture["utr_length"]
        + gfp_design.architecture["loop_length"]
        + gfp_design.architecture["spacer_length"]
        + 3
    )
    assert gfp_design.sequence[:aug_end] == other_design.sequence[:aug_end]
    assert gfp_design.sequence[aug_end:] != other_design.sequence[aug_end:]


# --- required_tools -----------------------------------------------------------------


def test_required_tools_declares_viennarna(gate):
    tools = gate.required_tools()
    assert [t.name for t in tools] == ["ViennaRNA"]


# --- is_compatible: cheap checks, no folding -----------------------------------------


def test_compatible_with_a_single_repressor(gate, repressor_set, constraints):
    assert gate.is_compatible(repressor_set, constraints) == Compatibility.yes()


def test_incompatible_with_an_activator():
    """This gate silences on presence, so its one input must be a repressor."""
    gate = AntisenseNotGate(Host.ECOLI, FoldEngine(), CodonOptimizer(Host.ECOLI), GFP_PAYLOAD)
    trigger_set = TriggerSet(activators=(make_trigger(trigger_id="trig-activator"),))
    result = gate.is_compatible(trigger_set, Constraints())
    assert not result.ok
    assert "repressor" in result.reason


def test_incompatible_with_two_inputs(gate, constraints):
    trigger_set = TriggerSet(
        activators=(),
        repressors=(make_trigger(trigger_id="trig-a"), make_trigger(trigger_id="trig-b")),
    )
    result = gate.is_compatible(trigger_set, constraints)
    assert not result.ok
    assert "one input" in result.reason


def test_incompatible_when_trigger_too_short(gate, constraints):
    short = make_trigger(sequence="ACGUACGUACGU")  # 12 nt, below any UTR+loop+spacer floor
    trigger_set = TriggerSet(activators=(), repressors=(short,))
    result = gate.is_compatible(trigger_set, constraints)
    assert not result.ok
    assert "too short" in result.reason


def test_incompatible_when_trigger_too_structured(gate, constraints):
    buried = make_trigger(accessibility=0.05)
    trigger_set = TriggerSet(activators=(), repressors=(buried,))
    result = gate.is_compatible(trigger_set, constraints)
    assert not result.ok
    assert "structured" in result.reason


def test_is_compatible_never_folds(gate, repressor_set, constraints, monkeypatch):
    """Cheap checks only — the whole point of ``is_compatible`` is to avoid folding."""

    def _boom(*_args, **_kwargs):
        raise AssertionError("is_compatible must not fold")

    monkeypatch.setattr(gate.folder, "mfe", _boom)
    monkeypatch.setattr(gate.folder, "base_pair_probabilities", _boom)
    gate.is_compatible(repressor_set, constraints)


# --- generate_designs -----------------------------------------------------------------


def test_generate_designs_yields_at_least_one(gate, repressor_set, constraints):
    designs = list(gate.generate_designs(repressor_set, constraints))
    assert designs


def test_every_design_respects_the_length_constraint(gate, repressor_set):
    tight = Constraints(max_switch_length=50)
    for design in gate.generate_designs(repressor_set, tight):
        assert design.length <= 50


def test_generated_sequences_are_valid_rna(gate, repressor_set, constraints):
    for design in gate.generate_designs(repressor_set, constraints):
        assert sq.is_valid_rna(design.sequence)


def test_architecture_records_enough_to_relocate_boundaries(gate, repressor_set, constraints):
    design = next(gate.generate_designs(repressor_set, constraints))
    architecture = design.architecture
    assert architecture.keys() >= {
        "utr_length",
        "loop_length",
        "spacer_length",
        "payload_head_length",
        "window_start",
        "loop_element",
        "track",
    }
    utr_len = architecture["utr_length"]
    loop_len = architecture["loop_length"]
    spacer_len = architecture["spacer_length"]
    assert design.sequence[utr_len : utr_len + loop_len] == architecture["loop_element"]
    aug_start = utr_len + loop_len + spacer_len
    assert design.sequence[aug_start : aug_start + 3] == "AUG"


def test_design_ids_are_unique_and_traceable(gate, repressor_set, constraints):
    designs = list(gate.generate_designs(repressor_set, constraints))
    ids = [d.design_id for d in designs]
    assert len(ids) == len(set(ids))
    assert all(
        d.trigger_set.repressors[0].trigger_id in i for d, i in zip(designs, ids, strict=True)
    )


# --- evaluate_design: raw values, no scoring -------------------------------------------


def test_evaluate_design_returns_the_declared_metric_names(gate, repressor_set, constraints):
    design = next(gate.generate_designs(repressor_set, constraints))
    metrics = gate.evaluate_design(design)

    assert metrics.keys() == {
        "gate_folding_energy",
        "predicted_leakage",
        "dynamic_range",
        "trigger_accessibility",
        "predicted_success_rate",
        "gc_content",
        "initiation_open_run_nt",
    }
    assert all(isinstance(v, float) for v in metrics.values())


def test_predicted_leakage_and_success_rate_are_fractions(gate, repressor_set, constraints):
    design = next(gate.generate_designs(repressor_set, constraints))
    metrics = gate.evaluate_design(design)
    assert 0.0 <= metrics["predicted_leakage"] <= 1.0
    assert 0.0 <= metrics["predicted_success_rate"] <= 1.0
    assert metrics["dynamic_range"] > 0.0


def test_trigger_accessibility_is_carried_not_recomputed(gate, repressor_set, constraints):
    """Stage 2 already measured this; evaluate_design must read it, not refold it."""
    design = next(gate.generate_designs(repressor_set, constraints))
    metrics = gate.evaluate_design(design)
    assert metrics["trigger_accessibility"] == repressor_set.repressors[0].accessibility


# --- emit_sequence / describe -----------------------------------------------------------


def test_emit_sequence_is_the_design_sequence(gate, repressor_set, constraints):
    design = next(gate.generate_designs(repressor_set, constraints))
    assert gate.emit_sequence(design) == design.sequence


def test_describe_names_the_inverted_logic(gate, repressor_set, constraints):
    design = next(gate.generate_designs(repressor_set, constraints))
    assert "NOT" in gate.describe(design)


# --- Golden: fixed input, committed output (docs/engine.md §8) -------------------------


def test_golden_first_design_for_the_mcherry_trigger(gate, repressor_set, constraints):
    """Pins the exact switch and metrics this gate produces for a known-good trigger.

    A refactor that changes these numbers must be a deliberate, reviewed change — update
    the expected values here and bump ``AntisenseNotGate.version`` alongside it.
    """
    design = next(gate.generate_designs(repressor_set, constraints))

    assert design.design_id == "antisense-trig-mcherry-589-0001"
    assert design.architecture == {
        "utr_length": 8,
        "loop_length": 7,
        "spacer_length": 5,
        "payload_head_length": 30,
        "window_start": 0,
        "loop_element": "AGGAGGA",
        "track": "prokaryotic",
    }
    assert design.sequence == "GUUCAUCAAGGAGGAGCCGUAUGGUGAGCAAGGGCGAGGAGCUGUUCACCGGG"

    metrics = gate.evaluate_design(design)
    assert metrics == pytest.approx(
        {
            "gate_folding_energy": -15.100000381469727,
            "predicted_leakage": 0.533380593550929,
            "dynamic_range": 1.0444077964760763,
            "trigger_accessibility": 0.65,
            "predicted_success_rate": 0.05215354657818643,
            "gc_content": 60.37735849056604,
            "initiation_open_run_nt": 4.0,
        }
    )


def test_generate_designs_count_for_the_default_sweep_and_trigger(gate, repressor_set, constraints):
    """A second golden pin, on the search space itself rather than one design.

    ``UTR_LENGTHS x SPACER_LENGTHS x window offsets`` for a 30 nt trigger — a change to any
    of the swept constants or the windowing stride should move this number, which is the
    point: it is what makes such a change visible instead of silent.
    """
    assert len(list(gate.generate_designs(repressor_set, constraints))) == 28
