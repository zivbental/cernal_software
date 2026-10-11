"""``EukaryoticAntisenseNotGate`` — Kozak NOT gate, not the prokaryotic RBS layout.

Geometry tests do not fold. The one evaluation test uses a real ``FoldEngine``
on a single ~84 nt switch, the same budget as ``test_antisense.py``.
"""

import pytest

from engine import sequences as sq
from engine.domain import Compatibility, Constraints, Host, TriggerCandidate, TriggerSet
from engine.gates.antisense import AntisenseNotGate
from engine.gates.euk_antisense import EukaryoticAntisenseNotGate
from engine.gates.tools.codons import CodonOptimizer
from engine.gates.tools.folding import FoldEngine

# 30 nt, no AAAAA, and neither arm reverse-complements to an AUG or an in-frame stop.
CLEAN_TRIGGER = "CG" * 15

PAYLOAD = "AUG" + "GCU" * 40


def make_trigger(**overrides) -> TriggerCandidate:
    sequence = overrides.pop("sequence", CLEAN_TRIGGER)
    defaults = {
        "trigger_id": "trig-euk-1",
        "gene_id": "AREG",
        "symbol": "AREG",
        "sequence": sequence,
        "start_index": 0,
        "openness": 0.70,
        "accessibility": 0.65,
        "mfe": -4.0,
        "gc_content": sq.gc_content(sequence),
        "score": 0.8,
    }
    defaults.update(overrides)
    return TriggerCandidate(**defaults)


def make_gate(host: Host = Host.HUMAN) -> EukaryoticAntisenseNotGate:
    return EukaryoticAntisenseNotGate(
        host, FoldEngine(temperature=37.0), CodonOptimizer(host), PAYLOAD
    )


@pytest.fixture
def gate() -> EukaryoticAntisenseNotGate:
    return make_gate()


@pytest.fixture
def repressor_set() -> TriggerSet:
    return TriggerSet(activators=(), repressors=(make_trigger(),))


@pytest.fixture
def constraints() -> Constraints:
    return Constraints()


def test_construction_requires_a_payload():
    with pytest.raises(TypeError):
        EukaryoticAntisenseNotGate(Host.HUMAN, FoldEngine(), CodonOptimizer(Host.HUMAN))  # type: ignore[call-arg]


def test_payload_must_start_with_a_start_codon():
    with pytest.raises(ValueError, match="start codon"):
        EukaryoticAntisenseNotGate(
            Host.HUMAN, FoldEngine(), CodonOptimizer(Host.HUMAN), "GCUGCUGCU"
        )


def test_ecoli_is_not_this_family(gate, repressor_set, constraints):
    """E. coli keeps AntisenseNotGate. This family must not silently emit an RBS design."""
    ecoli = make_gate(Host.ECOLI)
    result = ecoli.is_compatible(repressor_set, constraints)
    assert not result.ok
    assert "prokaryotic" in result.reason


def test_human_and_yeast_accept_one_repressor(repressor_set, constraints):
    assert make_gate(Host.HUMAN).is_compatible(repressor_set, constraints) == Compatibility.yes()
    assert make_gate(Host.YEAST).is_compatible(repressor_set, constraints) == Compatibility.yes()


def test_incompatible_when_the_trigger_is_shorter_than_30(gate, constraints):
    short = TriggerSet(activators=(), repressors=(make_trigger(sequence="CG" * 10),))
    result = gate.is_compatible(short, constraints)
    assert not result.ok
    assert "too short" in result.reason


def test_is_compatible_never_folds(gate, repressor_set, constraints, monkeypatch):
    def _boom(*_args, **_kwargs):
        raise AssertionError("is_compatible must not fold")

    monkeypatch.setattr(gate.folder, "mfe", _boom)
    monkeypatch.setattr(gate.folder, "base_pair_probabilities", _boom)
    gate.is_compatible(repressor_set, constraints)


def test_a_30_nt_window_is_split_around_gccaccaug(gate, repressor_set, constraints):
    """15 nt UTR, 9 nt cassette, 6 nt linker. The cassette is not a reverse complement."""
    designs = list(gate.generate_designs(repressor_set, constraints))
    assert len(designs) == 1
    design = designs[0]
    window = CLEAN_TRIGGER
    utr_length = design.architecture["utr_length"]
    linker_length = design.architecture["linker_length"]

    assert design.architecture["window_length"] == 30
    assert design.architecture["window_start"] == 0
    assert utr_length == 15
    assert linker_length == 6
    assert utr_length > linker_length
    assert linker_length % 3 == 0
    assert design.architecture["extra_aa"] == 2
    assert design.architecture["kozak"] == AntisenseNotGate.KOZAK_EUKARYOTIC

    cassette = AntisenseNotGate.KOZAK_EUKARYOTIC + "AUG"
    assert design.sequence[utr_length : utr_length + len(cassette)] == cassette
    assert design.sequence[:utr_length] == sq.reverse_complement(window[-utr_length:])
    linker_end = utr_length + len(cassette) + linker_length
    linker = design.sequence[utr_length + len(cassette) : linker_end]
    assert linker[0] == "G"
    assert linker[1:] == sq.reverse_complement(window[:linker_length])[1:]
    assert "AUG" not in design.sequence[:utr_length]
    assert sq.START_CODON not in linker


def test_poly_a_windows_are_dropped(gate, constraints):
    trigger = TriggerSet(activators=(), repressors=(make_trigger(sequence="A" * 30),))
    assert list(gate.generate_designs(trigger, constraints)) == []


def test_an_aug_in_the_utr_arm_is_dropped(gate, constraints):
    """The 3' end of the window is what the UTR arm reverse-complements."""
    window = "C" * 15 + "CAU" + "C" * 12
    assert len(window) == 30
    trigger = TriggerSet(activators=(), repressors=(make_trigger(sequence=window),))
    assert list(gate.generate_designs(trigger, constraints)) == []


def test_an_in_frame_stop_in_the_linker_is_dropped(gate, constraints):
    """First linker codon is forced to G, so the stop has to sit in the second codon."""
    window = "UUA" + "CG" * 13 + "C"
    assert len(window) == 30
    linker = "G" + sq.reverse_complement(window[:6])[1:]
    assert sq.find_stops(linker)
    trigger = TriggerSet(activators=(), repressors=(make_trigger(sequence=window),))
    assert list(gate.generate_designs(trigger, constraints)) == []


def test_payload_changes_only_the_coding_tail(repressor_set, constraints):
    other = EukaryoticAntisenseNotGate(
        Host.HUMAN, FoldEngine(), CodonOptimizer(Host.HUMAN), "AUG" + "AAA" * 40
    )
    first = next(make_gate().generate_designs(repressor_set, constraints))
    second = next(other.generate_designs(repressor_set, constraints))
    coding_start = (
        first.architecture["utr_length"]
        + first.architecture["loop_length"]
        + first.architecture["linker_length"]
    )
    assert first.sequence[:coding_start] == second.sequence[:coding_start]
    assert first.sequence[coding_start:] != second.sequence[coding_start:]


def test_evaluate_design_reports_shared_metrics_and_flank_binding(gate, repressor_set, constraints):
    design = next(gate.generate_designs(repressor_set, constraints))
    raw = gate.evaluate_design(design)

    assert set(raw) == {
        "gate_folding_energy",
        "predicted_leakage",
        "dynamic_range",
        "trigger_accessibility",
        "predicted_success_rate",
        "gc_content",
        "initiation_open_run_nt",
        "flank_binding_probability",
    }
    assert raw["gc_content"] == sq.gc_content(design.sequence)
    assert raw["trigger_accessibility"] == 0.65
    assert 0.0 <= raw["predicted_leakage"] <= 1.0
    assert 0.0 <= raw["flank_binding_probability"] <= 1.0
    assert raw["predicted_success_rate"] is not None
    assert raw["gate_folding_energy"] < 0.0
