"""``ToeholdGate`` — the single-input translational switch.

Real ``FoldEngine``/ViennaRNA throughout, same rationale as ``test_antisense.py``: every
sequence here is tiny (the switch tops out around 65 nt, the dimer around 100), so a real
fold costs low milliseconds and the file stays under docs/engine.md §8's one-second budget.
"""

import pytest

from engine import sequences as sq
from engine.domain import Compatibility, Constraints, Host, TriggerCandidate, TriggerSet
from engine.gates.toehold import ToeholdAndGate, ToeholdGate
from engine.gates.tools.codons import CodonOptimizer
from engine.gates.tools.folding import FoldEngine
from engine.gates.tools.translation import TranslationScorer

# A made-up but deterministic 35 nt trigger window — plausible values, not pinned to any
# external run (unlike AntisenseNotGate's MCHERRY_TRIGGER, this gate has no source pipeline
# to reuse a validated window from; see the class docstring's provenance note).
TRIGGER_SEQUENCE = "CGUACAACGUCAACAUCAAGUUGGACAUCACCUCC"


def make_trigger(**overrides) -> TriggerCandidate:
    """A tiny, deterministic activator trigger. Any field can be overridden."""
    sequence = overrides.pop("sequence", TRIGGER_SEQUENCE)
    defaults = {
        "trigger_id": "trig-thra-100",
        "gene_id": "b0002",
        "symbol": "thrA",
        "sequence": sequence,
        "start_index": 100,
        "openness": 0.72,
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


def test_incompatible_with_a_repressor(gate, constraints):
    """This gate has no inverting mechanism — every input must be an activator."""
    trigger_set = TriggerSet(activators=(), repressors=(make_trigger(trigger_id="trig-r"),))
    result = gate.is_compatible(trigger_set, constraints)
    assert not result.ok
    assert "activator" in result.reason


def test_incompatible_with_two_inputs(gate, constraints):
    trigger_set = TriggerSet(
        activators=(make_trigger(trigger_id="trig-a"), make_trigger(trigger_id="trig-b")),
    )
    result = gate.is_compatible(trigger_set, constraints)
    assert not result.ok
    assert "1 input" in result.reason


def test_incompatible_when_trigger_too_short(gate, constraints):
    short = make_trigger(sequence="ACGUACGUACGU")  # 12 nt, below any toehold+stem floor
    trigger_set = TriggerSet(activators=(short,))
    result = gate.is_compatible(trigger_set, constraints)
    assert not result.ok
    assert "too short" in result.reason


def test_incompatible_when_switch_would_exceed_length_limit(gate):
    tight = Constraints(max_switch_length=20)  # smaller than the trigger itself
    trigger_set = TriggerSet(activators=(make_trigger(),))
    result = gate.is_compatible(trigger_set, tight)
    assert not result.ok
    assert "exceed" in result.reason


def test_is_compatible_never_folds(gate, activator_set, constraints, monkeypatch):
    """Cheap checks only — the whole point of ``is_compatible`` is to avoid folding."""

    def _boom(*_args, **_kwargs):
        raise AssertionError("is_compatible must not fold")

    monkeypatch.setattr(gate.folder, "mfe", _boom)
    monkeypatch.setattr(gate.folder, "base_pair_probabilities", _boom)
    gate.is_compatible(activator_set, constraints)


def test_and_gate_is_compatible_inherits_and_requires_two_activators(constraints):
    """``ToeholdAndGate`` does not override ``is_compatible`` — it must keep working
    correctly by inheritance, generic over ``max_inputs``, not hardcoded to 1."""
    and_gate = ToeholdAndGate(
        Host.ECOLI, FoldEngine(), TranslationScorer(Host.ECOLI), CodonOptimizer(Host.ECOLI)
    )
    two = TriggerSet(
        activators=(make_trigger(trigger_id="trig-a"), make_trigger(trigger_id="trig-b"))
    )
    one = TriggerSet(activators=(make_trigger(),))
    assert and_gate.is_compatible(two, constraints) == Compatibility.yes()
    assert not and_gate.is_compatible(one, constraints).ok


# --- generate_designs -----------------------------------------------------------------


def test_generate_designs_yields_at_least_one(gate, activator_set, constraints):
    designs = list(gate.generate_designs(activator_set, constraints))
    assert designs


def test_every_design_respects_the_length_constraint(gate, activator_set):
    tight = Constraints(max_switch_length=50)
    for design in gate.generate_designs(activator_set, tight):
        assert design.length <= 50


def test_generated_sequences_are_valid_rna(gate, activator_set, constraints):
    for design in gate.generate_designs(activator_set, constraints):
        assert sq.is_valid_rna(design.sequence)


def test_architecture_records_enough_to_relocate_boundaries(gate, activator_set, constraints):
    design = next(gate.generate_designs(activator_set, constraints))
    architecture = design.architecture
    assert architecture.keys() >= {
        "toehold_length",
        "stem_length",
        "loop_length",
        "loop_element",
        "track",
    }
    toehold_len = architecture["toehold_length"]
    stem_len = architecture["stem_length"]
    loop_len = architecture["loop_length"]
    loop_start = toehold_len + stem_len
    assert design.sequence[loop_start : loop_start + loop_len] == architecture["loop_element"]
    assert design.sequence[-3:] == "AUG"


def test_design_ids_are_unique_and_traceable(gate, activator_set, constraints):
    designs = list(gate.generate_designs(activator_set, constraints))
    ids = [d.design_id for d in designs]
    assert len(ids) == len(set(ids))
    assert all(
        d.trigger_set.activators[0].trigger_id in i for d, i in zip(designs, ids, strict=True)
    )


def test_widening_the_toehold_shrinks_the_switch(gate, activator_set, constraints):
    """The stem appears twice (ascending and descending arms are separate stretches), so
    widening the toehold shrinks it: 2*trigger_length - toehold_length + loop_length
    (see ``is_compatible``'s tightest_switch_length comment)."""
    designs = sorted(
        gate.generate_designs(activator_set, constraints),
        key=lambda d: d.architecture["toehold_length"],
    )
    lengths = [d.length for d in designs]
    assert lengths == sorted(lengths, reverse=True)
    assert len(set(lengths)) == len(lengths)


# --- evaluate_design: raw values, no scoring -------------------------------------------


def test_evaluate_design_returns_the_declared_metric_names(gate, activator_set, constraints):
    design = next(gate.generate_designs(activator_set, constraints))
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


def test_predicted_leakage_and_success_rate_are_fractions(gate, activator_set, constraints):
    design = next(gate.generate_designs(activator_set, constraints))
    metrics = gate.evaluate_design(design)
    assert 0.0 <= metrics["predicted_leakage"] <= 1.0
    assert 0.0 <= metrics["predicted_success_rate"] <= 1.0
    assert metrics["dynamic_range"] > 0.0


def test_trigger_accessibility_is_carried_not_recomputed(gate, activator_set, constraints):
    """Stage 2 already measured this; evaluate_design must read it, not refold it."""
    design = next(gate.generate_designs(activator_set, constraints))
    metrics = gate.evaluate_design(design)
    assert metrics["trigger_accessibility"] == activator_set.activators[0].accessibility


# --- emit_sequence / describe -----------------------------------------------------------


def test_emit_sequence_is_the_design_sequence(gate, activator_set, constraints):
    design = next(gate.generate_designs(activator_set, constraints))
    assert gate.emit_sequence(design) == design.sequence


def test_describe_names_the_gene(gate, activator_set, constraints):
    design = next(gate.generate_designs(activator_set, constraints))
    assert "thrA" in gate.describe(design)


# --- Golden: fixed input, committed output (docs/engine.md §8) -------------------------


def test_golden_first_design_for_the_trigger(gate, activator_set, constraints):
    """Pins the exact switch and metrics this gate produces for a known trigger.

    A refactor that changes these numbers must be a deliberate, reviewed change — update
    the expected values here and bump ``ToeholdGate.version`` alongside it.
    """
    design = next(gate.generate_designs(activator_set, constraints))

    assert design.design_id == "toehold-trig-thra-100-0001"
    assert design.architecture == {
        "toehold_length": 12,
        "stem_length": 23,
        "loop_length": 7,
        "loop_element": "AGGAGGA",
        "track": "prokaryotic",
    }
    assert design.sequence == "GGAGGUGAUGUCCAACUUGAUGUUGACGUUGUACGAGGAGGACGUACAACGUCAACAUCAAGAUG"

    metrics = gate.evaluate_design(design)
    assert metrics == pytest.approx(
        {
            "gate_folding_energy": -34.900001525878906,
            "predicted_leakage": 0.3318126020077467,
            "dynamic_range": 1.8385989841609207,
            "trigger_accessibility": 0.65,
            "predicted_success_rate": 0.9999130420727482,
            "gc_content": 47.69230769230769,
            "initiation_open_run_nt": 9.0,
        }
    )


def test_generate_designs_count_for_the_default_sweep_and_trigger(gate, activator_set, constraints):
    """A second golden pin, on the search space itself rather than one design."""
    assert len(list(gate.generate_designs(activator_set, constraints))) == 3
