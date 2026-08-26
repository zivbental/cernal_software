"""The engine's domain types.

These are implemented, not stubbed, so they are tested like any other code.
"""

import dataclasses

import pytest

from engine.domain import (
    AssemblyStandard,
    BooleanExpression,
    ConfusionMatrix,
    GeneState,
    Host,
    LogicOperator,
    Plasmid,
    Regulation,
    SampleMetadata,
    Segment,
    SegmentKind,
    TriggerCandidate,
    TriggerSet,
)


def _trigger(ref: str, gene: str = "lacZ", seq: str = "ACGUACGUAC") -> TriggerCandidate:
    return TriggerCandidate(
        trigger_id=ref,
        gene_id=gene,
        symbol=gene,
        sequence=seq,
        start_index=0,
        openness=0.8,
        accessibility=0.7,
        mfe=-12.0,
        off_target_penalty=0.1,
        segment_specificity=0.9,
        gc_content=50.0,
    )


# --- Host and track ---------------------------------------------------------------


def test_ecoli_is_prokaryotic_and_the_others_are_not():
    """Design rules follow the track, so this mapping is load-bearing."""
    assert Host.ECOLI.track == "prokaryotic"
    assert Host.YEAST.track == "eukaryotic"
    assert Host.HUMAN.track == "eukaryotic"


def test_enums_are_strings_so_they_serialise_unchanged():
    """StrEnum members go into JobResult as plain strings; the contract needs no
    knowledge of them."""
    assert Host.ECOLI == "ecoli"
    assert AssemblyStandard.RFC10 == "RFC10"
    assert SegmentKind.PROMOTER == "promoter"


# --- Boolean expressions ----------------------------------------------------------


def test_a_single_gene_evaluates_to_its_presence():
    expression = BooleanExpression.gene("IL6")
    assert expression.evaluate(frozenset({"IL6"}))
    assert not expression.evaluate(frozenset())


def test_and_not_behaves_as_written():
    """IL6 AND NOT FOXP3 — the shape the design's example circuit uses."""
    expression = BooleanExpression(
        LogicOperator.AND,
        (
            BooleanExpression.gene("IL6"),
            BooleanExpression(LogicOperator.NOT, (BooleanExpression.gene("FOXP3"),)),
        ),
    )

    assert expression.evaluate(frozenset({"IL6"}))
    assert not expression.evaluate(frozenset({"IL6", "FOXP3"}))
    assert not expression.evaluate(frozenset({"FOXP3"}))
    assert not expression.evaluate(frozenset())


def test_or_fires_on_either():
    expression = BooleanExpression(
        LogicOperator.OR, (BooleanExpression.gene("A"), BooleanExpression.gene("B"))
    )
    assert expression.evaluate(frozenset({"B"}))
    assert not expression.evaluate(frozenset({"C"}))


def test_gene_ids_are_collected_in_order_without_duplicates():
    expression = BooleanExpression(
        LogicOperator.AND,
        (BooleanExpression.gene("A"), BooleanExpression.gene("B"), BooleanExpression.gene("A")),
    )
    assert expression.gene_ids() == ("A", "B")


def test_complexity_counts_components_not_just_genes():
    """Complexity is the axis score is traded against, so a nested expression must cost
    more than a flat one."""
    flat = BooleanExpression(
        LogicOperator.AND, (BooleanExpression.gene("A"), BooleanExpression.gene("B"))
    )
    nested = BooleanExpression(
        LogicOperator.AND,
        (
            BooleanExpression.gene("A"),
            BooleanExpression(
                LogicOperator.OR, (BooleanExpression.gene("B"), BooleanExpression.gene("C"))
            ),
        ),
    )
    assert nested.complexity() > flat.complexity()


def test_rendering_reads_the_way_the_caption_should():
    expression = BooleanExpression(
        LogicOperator.AND,
        (
            BooleanExpression.gene("A"),
            BooleanExpression(LogicOperator.NOT, (BooleanExpression.gene("D"),)),
        ),
    )
    assert expression.render() == "(A AND NOT D)"


# --- Trigger sets -----------------------------------------------------------------


def test_two_triggers_from_the_same_gene_are_kept():
    """The pipeline map is explicit: '2 inputs can be of the same gene or trigger'."""
    trigger_set = TriggerSet(activators=(_trigger("t1", "lacZ"), _trigger("t2", "lacZ")))

    assert trigger_set.arity == 2
    assert trigger_set.trigger_ids == ("t1", "t2")


@pytest.mark.parametrize(
    ("activators", "repressors", "expected"),
    [
        (1, 0, "single-input"),
        (2, 0, "AND"),
        (1, 1, "AND-NOT"),
        (0, 1, "NOT"),
    ],
)
def test_logic_type_follows_the_trigger_shape(activators, repressors, expected):
    trigger_set = TriggerSet(
        activators=tuple(_trigger(f"a{i}") for i in range(activators)),
        repressors=tuple(_trigger(f"r{i}") for i in range(repressors)),
    )
    assert trigger_set.logic_type == expected


# --- Confusion matrix -------------------------------------------------------------


def test_a_perfect_circuit_has_a_separation_margin_of_one():
    perfect = ConfusionMatrix(
        true_positive=10, false_positive=0, false_negative=0, true_negative=10
    )
    assert perfect.separation_margin == pytest.approx(1.0)


def test_a_circuit_that_always_fires_separates_nothing():
    """Firing on everything scores no better than chance, which the margin must show."""
    always_on = ConfusionMatrix(
        true_positive=10, false_positive=10, false_negative=0, true_negative=0
    )
    assert always_on.separation_margin == pytest.approx(0.0)


def test_sensitivity_and_specificity_survive_empty_groups():
    empty = ConfusionMatrix(0, 0, 0, 0)
    assert empty.sensitivity == 0.0
    assert empty.specificity == 0.0


# --- Plasmid ----------------------------------------------------------------------


def test_plasmid_length_and_gc_are_computed_from_its_segments():
    plasmid = Plasmid(
        segments=(
            Segment(SegmentKind.PROMOTER, "J23119", "GGGCCC"),
            Segment(SegmentKind.PAYLOAD, "GFP", "AAAATT"),
        )
    )

    assert plasmid.length_bp == 12
    assert plasmid.sequence == "GGGCCCAAAATT"
    assert plasmid.gc_content == pytest.approx(50.0)


# --- Immutability -----------------------------------------------------------------


def test_records_are_frozen():
    """Frozen because the pipeline parallelises by pickling and must be deterministic."""
    trigger = _trigger("t1")
    with pytest.raises(dataclasses.FrozenInstanceError):
        trigger.score = 1.0


def test_a_sample_cannot_be_both_control_and_condition():
    with pytest.raises(ValueError, match="both control and condition"):
        SampleMetadata(control_samples=("s1", "s2"), condition_samples=("s2", "s3"))


def test_gene_state_and_regulation_stay_distinct():
    """A gene being down-regulated is not the same as it needing to be OFF."""
    assert GeneState.OFF != Regulation.DOWN
