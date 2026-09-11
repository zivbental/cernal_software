"""Stage 3 — ``SwitchDesigner`` (dispatch) and ``SwitchValidator`` (the hard rules).

``SwitchValidator``'s two deferred rules — the structural check and RBS placement — are
not tested here because they are not implemented; docs/smoke-run.md §3 S4 says why, and
the class's own docstring repeats it. ``ToeholdGate`` is real and already tested
(tests/engine/gates/test_toehold.py), so the dispatch tests below drive it directly
rather than faking a gate family — the same "use the real thing when it already exists"
choice tests/engine/test_tools.py makes.
"""

import pytest

from engine.domain import (
    Constraints,
    GateDesign,
    GateKind,
    Host,
    TriggerCandidate,
)
from engine.gates.toehold import ToeholdGate
from engine.gates.tools.codons import CodonOptimizer
from engine.gates.tools.folding import FoldEngine
from engine.gates.tools.translation import TranslationScorer
from engine.stages.motifs import MotifScreener
from engine.stages.off_target import OffTargetScanner
from engine.stages.switches import SwitchDesigner, SwitchValidator, _windows_overlap

# A sequence whose reverse-complement-built switch does not echo extra AUGs —
# tests/engine/test_switches.py's own smoke run hit exactly this with a hand-repeated
# sequence, which is why this one is a fixed, checked-in constant instead.
CLEAN_TRIGGER_SEQUENCE = "AACUUGUUGGCCCAGUGUGAAUCGCUUAAGGGUUAA"


def _trigger(**overrides) -> TriggerCandidate:
    defaults = {
        "trigger_id": "trig-000001",
        "gene_id": "g1",
        "symbol": "g1",
        "sequence": CLEAN_TRIGGER_SEQUENCE,
        "start_index": 0,
        "openness": 0.6,
        "accessibility": 0.5,
        "mfe": -5.0,
        "off_target_penalty": 0.0,
        "segment_specificity": 1.0,
        "gc_content": 45.0,
    }
    defaults.update(overrides)
    return TriggerCandidate(**defaults)


@pytest.fixture
def folder():
    return FoldEngine()


@pytest.fixture
def toehold_gate(folder):
    host = Host.ECOLI
    return ToeholdGate(host, folder, TranslationScorer(host), CodonOptimizer(host))


@pytest.fixture
def validator(folder):
    return SwitchValidator(
        folder, OffTargetScanner({}), MotifScreener(), TranslationScorer(Host.ECOLI), Constraints()
    )


# --- SwitchDesigner.build_trigger_sets ----------------------------------------------


def test_singletons_come_first():
    designer = SwitchDesigner([], validator=None, host=Host.ECOLI)
    triggers = [_trigger(trigger_id="a"), _trigger(trigger_id="b")]

    sets = list(designer.build_trigger_sets(triggers, Constraints(max_triggers=2)))

    assert sets[0].activators == (triggers[0],)
    assert sets[1].activators == (triggers[1],)


def test_pairs_may_share_a_gene():
    """The pipeline map is explicit: two inputs may come from the same gene."""
    designer = SwitchDesigner([], validator=None, host=Host.ECOLI)
    a = _trigger(trigger_id="a", gene_id="g1", start_index=0)
    b = _trigger(trigger_id="b", gene_id="g1", start_index=100)  # same gene, far apart

    sets = designer.build_trigger_sets([a, b], Constraints(max_triggers=2))
    pairs = [s for s in sets if s.arity == 2]

    assert len(pairs) == 1
    assert {t.trigger_id for t in pairs[0].activators} == {"a", "b"}


def test_overlapping_windows_on_the_same_gene_are_not_paired():
    designer = SwitchDesigner([], validator=None, host=Host.ECOLI)
    a = _trigger(trigger_id="a", gene_id="g1", start_index=0, sequence="A" * 30)
    b = _trigger(trigger_id="b", gene_id="g1", start_index=10, sequence="A" * 30)  # overlaps a

    sets = designer.build_trigger_sets([a, b], Constraints(max_triggers=2))
    pairs = [s for s in sets if s.arity == 2]

    assert pairs == []


def test_non_overlapping_windows_on_different_genes_are_paired_even_if_positions_collide():
    designer = SwitchDesigner([], validator=None, host=Host.ECOLI)
    a = _trigger(trigger_id="a", gene_id="g1", start_index=0, sequence="A" * 30)
    b = _trigger(trigger_id="b", gene_id="g2", start_index=0, sequence="A" * 30)  # different gene

    sets = designer.build_trigger_sets([a, b], Constraints(max_triggers=2))
    pairs = [s for s in sets if s.arity == 2]

    assert len(pairs) == 1


def test_no_pairs_when_max_triggers_is_one():
    designer = SwitchDesigner([], validator=None, host=Host.ECOLI)
    triggers = [_trigger(trigger_id="a"), _trigger(trigger_id="b")]

    sets = list(designer.build_trigger_sets(triggers, Constraints(max_triggers=1)))

    assert all(s.arity == 1 for s in sets)


def test_no_triples_even_when_max_triggers_allows_them():
    """Q3 (docs/ROADMAP.md §2) has not set a ceiling above 2 — this stage never
    generates one on its own."""
    designer = SwitchDesigner([], validator=None, host=Host.ECOLI)
    triggers = [_trigger(trigger_id=str(i), gene_id=str(i)) for i in range(4)]

    sets = list(designer.build_trigger_sets(triggers, Constraints(max_triggers=5)))

    assert all(s.arity <= 2 for s in sets)


@pytest.mark.parametrize(
    ("a_start", "a_len", "b_start", "b_len", "expected"),
    [
        (0, 30, 30, 30, False),  # adjacent, not overlapping
        (0, 30, 29, 30, True),  # off by one — overlapping
        (0, 30, 15, 5, True),  # b fully inside a
        (100, 30, 0, 30, False),  # far apart
    ],
)
def test_windows_overlap(a_start, a_len, b_start, b_len, expected):
    a = _trigger(start_index=a_start, sequence="A" * a_len)
    b = _trigger(start_index=b_start, sequence="A" * b_len)
    assert _windows_overlap(a, b) is expected


# --- SwitchDesigner.design (dispatch, real ToeholdGate) ------------------------------


def test_design_yields_only_validated_designs(toehold_gate, validator):
    designer = SwitchDesigner([toehold_gate], validator, Host.ECOLI)
    trigger = _trigger()

    designs = list(designer.design([trigger], Constraints()))

    assert designs
    for design in designs:
        assert validator.validate(design).ok


def test_design_skips_a_family_that_does_not_support_the_host(toehold_gate, validator):
    """ToeholdGate supports every host; a host it does not support must yield nothing,
    not raise, from a family that is simply not asked to run."""
    from engine.gates.crispr import CrisprGate  # read-only import, not modified

    # CrisprGate is host-restricted and unavailable; supports() is False either way,
    # so the family is skipped before is_compatible is ever called.
    SwitchDesigner([toehold_gate], validator, Host.ECOLI)
    assert toehold_gate.supports(Host.ECOLI)
    assert not CrisprGate.available or Host.ECOLI not in CrisprGate.supported_hosts


def test_design_produces_nothing_for_an_empty_trigger_list(toehold_gate, validator):
    designer = SwitchDesigner([toehold_gate], validator, Host.ECOLI)
    assert list(designer.design([], Constraints())) == []


# --- SwitchValidator.validate ---------------------------------------------------------


def _design(**overrides) -> GateDesign:
    from engine.domain import TriggerSet

    defaults = {
        "design_id": "d1",
        "gate_kind": GateKind.TOEHOLD,
        "host": Host.ECOLI,
        "trigger_set": TriggerSet(activators=(_trigger(),)),
        "sequence": "AUGGCUAGCAAGGGCGAGGAGCUG",
        "dot_bracket": "",
        "architecture": {"aug_index": 0},
    }
    defaults.update(overrides)
    return GateDesign(**defaults)


def test_a_clean_design_passes(validator):
    # AUG at 0, no other AUGs, no in-frame stop, short, no motifs.
    design = _design(sequence="AUGGCUAGCAAGGGCGAGGAGCUG")
    result = validator.validate(design)
    assert result.ok, result.violations


def test_length_over_the_constraint_is_rejected(folder):
    validator = SwitchValidator(
        folder,
        OffTargetScanner({}),
        MotifScreener(),
        TranslationScorer(Host.ECOLI),
        Constraints(max_switch_length=10),
    )
    design = _design(sequence="AUGGCUAGCAAGGGCGAGGAGCUG")  # 24 nt > 10

    result = validator.validate(design)

    assert not result.ok
    assert any("nt" in v for v in result.violations)


def test_extra_aug_is_rejected(validator):
    # Two AUGs: one at 0 (declared), one later.
    design = _design(sequence="AUGGCUAUGGCGAGGAGCUG", architecture={"aug_index": 0})

    result = validator.validate(design)

    assert not result.ok
    assert any("AUG" in v for v in result.violations)


def test_in_frame_stop_after_the_aug_is_rejected(validator):
    # AUG at 0, then UAA in-frame at position 3.
    design = _design(sequence="AUGUAAGCGAGGAGCUG", architecture={"aug_index": 0})

    result = validator.validate(design)

    assert not result.ok
    assert any("stop" in v.lower() for v in result.violations)


def test_out_of_frame_stop_is_not_flagged(validator):
    # UAA appears but not in the aug_index=0 frame.
    sequence = "AUGGCUAGCGAGGAGCUG"
    assert "UAA" not in [sequence[i : i + 3] for i in range(0, len(sequence) - 2, 3)]
    design = _design(sequence=sequence, architecture={"aug_index": 0})

    result = validator.validate(design)

    assert result.ok, result.violations


def test_prohibited_motif_is_rejected(validator):
    # EcoRI site (GAATTC, as RNA GAAUUC) with no AUG at all — architecture carries no
    # aug_index, so only the motif rule applies.
    design = _design(sequence="CCCGAAUUCCCC", architecture={})

    result = validator.validate(design)

    assert not result.ok
    assert any("restriction site" in v for v in result.violations)


def test_a_design_with_no_aug_index_skips_the_aug_and_stop_rules(validator):
    """A chemistry with no embedded start codon (e.g. antisense — its architecture has
    no 'aug_index' key at all) must not be judged by a rule that does not apply to it."""
    # This sequence would fail "exactly one AUG" if the rule ran (zero AUGs) — it must
    # pass instead, because architecture declares no aug_index.
    design = _design(sequence="GGCGAGGAGCUGUUCACCGGG", architecture={"track": "prokaryotic"})

    result = validator.validate(design)

    assert result.ok, result.violations


def test_every_violation_is_collected_not_just_the_first(folder):
    """A generator being tuned is far easier to fix when it reports all its problems
    at once (the class's own docstring)."""
    validator = SwitchValidator(
        folder,
        OffTargetScanner({}),
        MotifScreener(),
        TranslationScorer(Host.ECOLI),
        Constraints(max_switch_length=5),
    )
    # Too long AND carries a motif AND has zero AUGs where one was declared.
    design = _design(sequence="GAAUUCGAAUUCGAAUUC", architecture={"aug_index": 0})

    result = validator.validate(design)

    assert not result.ok
    assert len(result.violations) >= 2
