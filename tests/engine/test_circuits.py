"""Stage 4 — ``CircuitDesigner``: enumerating circuit logic and building circuits.

The two implemented halves. ``ConfusionEvaluator.evaluate`` is deliberately still a
stub (the product collects a differential-expression table and no per-sample count
matrix, docs/genes.md §3 G-a), so these tests exercise the ``counts``-free path that
``design`` documents.
"""

import dataclasses

import pytest

from engine.domain import (
    Constraints,
    CountMatrix,
    GateDesign,
    GateKind,
    GeneState,
    Host,
    LogicOperator,
    Regulation,
    SampleMetadata,
    SelectedGene,
    TriggerCandidate,
    TriggerSet,
)
from engine.stages.circuits import CircuitDesigner, ConfusionEvaluator

EMPTY_COUNTS = CountMatrix(
    gene_ids=(),
    samples=(),
    counts=(),
    metadata=SampleMetadata(control_samples=(), condition_samples=()),
)


def make_gene(gene_id: str, symbol: str, regulation: Regulation) -> SelectedGene:
    return SelectedGene(
        gene_id=gene_id,
        symbol=symbol,
        regulation=regulation,
        log2_fold_change=2.5 if regulation is Regulation.UP else -2.5,
        score=0.5,
    )


def make_design(gene_id: str, symbol: str) -> GateDesign:
    trigger = TriggerCandidate(
        trigger_id=f"trig-{gene_id}",
        gene_id=gene_id,
        symbol=symbol,
        sequence="AUGGCUAGCAAGGGCGAGGAGCUGUUCACCGGG",
        start_index=0,
        openness=0.7,
        accessibility=0.6,
        mfe=-4.0,
        gc_content=55.0,
        log2_fold_change=2.5,
        score=0.8,
    )
    return GateDesign(
        design_id=f"sw-{gene_id}",
        gate_kind=GateKind.TOEHOLD,
        host=Host.ECOLI,
        trigger_set=TriggerSet(activators=(trigger,)),
        sequence="GGGAAACCCUUUGGGAAACCCAUGGCUAGC",
        architecture={"toehold_length": 12},
    )


@pytest.fixture
def genes() -> list[SelectedGene]:
    """Two up, one down — so the DOWN gene has to reach the circuit through NOT."""
    return [
        make_gene("b0001", "aceB", Regulation.UP),
        make_gene("b0002", "rpoS", Regulation.DOWN),
        make_gene("b0003", "katG", Regulation.UP),
    ]


@pytest.fixture
def designer() -> CircuitDesigner:
    return CircuitDesigner(ConfusionEvaluator(), max_terms=2)


# --- enumerate_expressions ----------------------------------------------------------


def test_every_gene_gets_a_single_gene_circuit(designer, genes):
    rendered = [e.render() for e in designer.enumerate_expressions(genes)]
    assert "b0001" in rendered
    assert "b0003" in rendered


def test_a_down_gene_enters_through_not(designer, genes):
    """Regulation describes the data; the circuit has to invert a gene that went down
    or it would fire in the control state instead of the target one."""
    rendered = [e.render() for e in designer.enumerate_expressions(genes)]
    assert "NOT b0002" in rendered
    assert "b0002" not in rendered


def test_expressions_come_simplest_first(designer, genes):
    """A caller that stops early must get the cheapest circuits, not an arbitrary
    slice — so gate count must never decrease as enumeration proceeds."""
    sizes = [len(e.gene_ids()) for e in designer.enumerate_expressions(genes)]

    assert sizes == sorted(sizes)
    assert sizes[0] == 1


def test_max_terms_caps_the_number_of_gates(genes):
    for cap in (1, 2, 3):
        designer = CircuitDesigner(ConfusionEvaluator(), max_terms=cap)
        sizes = {len(e.gene_ids()) for e in designer.enumerate_expressions(genes)}
        assert max(sizes) == cap


def test_pairs_are_not_duplicated_in_both_orders(designer, genes):
    """``A AND B`` and ``B AND A`` are one circuit. Deduplication is by truth table,
    so the gene *sets* must be unique."""
    sets = [frozenset(e.gene_ids()) for e in designer.enumerate_expressions(genes)]
    assert len(sets) == len(set(sets))


def test_no_genes_yields_no_expressions(designer):
    assert list(designer.enumerate_expressions([])) == []


# --- design -------------------------------------------------------------------------


def test_a_two_gene_circuit_carries_both_designs(designer, genes):
    designs = [make_design(g.gene_id, g.symbol) for g in genes]
    circuits = list(designer.design(genes, designs, EMPTY_COUNTS))

    pairs = [c for c in circuits if len(c.expression.gene_ids()) == 2]
    assert pairs
    for circuit in pairs:
        assert len(circuit.designs) == 2
        assert {d.design_id for d in circuit.designs} == {
            f"sw-{gene_id}" for gene_id in circuit.expression.gene_ids()
        }


def test_an_expression_with_no_switch_for_a_gene_is_dropped(designer, genes):
    """ "An expression needing an input with no switch is not a circuit, it is a wish."
    Only b0001 has a design, so nothing referencing the other two may be yielded."""
    circuits = list(designer.design(genes, [make_design("b0001", "aceB")], EMPTY_COUNTS))

    assert [c.expression.gene_ids() for c in circuits] == [("b0001",)]


def test_the_first_design_per_gene_wins(designer, genes):
    """The caller expresses "best" through ordering (design's own docstring), so the
    first design offered for a gene is the one built with."""
    first = make_design("b0001", "aceB")
    second = dataclasses.replace(first, design_id="sw-b0001-worse")

    circuits = list(designer.design(genes[:1], [first, second], EMPTY_COUNTS))

    assert [d.design_id for c in circuits for d in c.designs] == ["sw-b0001"]


def test_complexity_rises_with_each_gate_and_each_not(designer, genes):
    """The penalty a longer circuit pays. An extra gene costs a gate; a DOWN gene
    costs its NOT on top."""
    designs = [make_design(g.gene_id, g.symbol) for g in genes]
    by_logic = {
        c.expression.render(): c.complexity for c in designer.design(genes, designs, EMPTY_COUNTS)
    }

    assert by_logic["b0001"] == 1
    assert by_logic["NOT b0002"] == 2
    assert by_logic["(b0001 AND b0003)"] == 3
    assert by_logic["(b0001 AND NOT b0002)"] == 4


def test_the_logic_graph_states_what_the_circuit_requires(designer, genes):
    """``GeneState`` is the requirement, ``Regulation`` is the observation — an UP gene
    must be present, a DOWN gene must be absent."""
    designs = [make_design(g.gene_id, g.symbol) for g in genes]
    circuits = {c.expression.render(): c for c in designer.design(genes, designs, EMPTY_COUNTS)}

    up = circuits["b0001"].logic_graph
    assert up.genes[0].state is GeneState.ON
    assert up.genes[0].direction is Regulation.UP
    assert up.genes[0].name == "aceB"

    down = circuits["NOT b0002"].logic_graph
    assert down.genes[0].state is GeneState.OFF
    assert down.genes[0].direction is Regulation.DOWN


def test_a_pair_circuit_reports_its_operator_on_the_graph(designer, genes):
    designs = [make_design(g.gene_id, g.symbol) for g in genes]
    pair = next(c for c in designer.design(genes, designs, EMPTY_COUNTS) if len(c.designs) == 2)

    assert pair.logic_graph.mid_gate is LogicOperator.AND
    assert len(pair.logic_graph.genes) == 2


def test_confusion_is_unmeasured_rather_than_invented_without_counts(designer, genes):
    """No count matrix exists in this product, so there is nothing to measure behaviour
    against. The all-zero matrix is a placeholder nothing downstream reads — it must
    never be mistaken for a circuit that got every sample wrong."""
    designs = [make_design(g.gene_id, g.symbol) for g in genes]
    circuit = next(iter(designer.design(genes, designs, EMPTY_COUNTS)))

    assert circuit.confusion.true_positive == 0
    assert circuit.confusion.false_positive == 0
    assert circuit.confusion.false_negative == 0
    assert circuit.confusion.true_negative == 0


def test_scoring_and_ids_are_left_to_the_caller(designer, genes):
    """Weighting and ranking are engine.scoring's exclusive job (CLAUDE.md §3), and
    the stored id is minted by CandidateStore."""
    designs = [make_design(g.gene_id, g.symbol) for g in genes]
    circuit = next(iter(designer.design(genes, designs, EMPTY_COUNTS)))

    assert circuit.score == 0.0
    assert circuit.rejection is None
    assert circuit.output == ""


def test_design_yields_rather_than_returns_a_list(designer, genes):
    """Every ``-> Iterator[...]`` must actually yield (CLAUDE.md §7)."""
    import inspect

    assert inspect.isgeneratorfunction(CircuitDesigner.design)
    assert inspect.isgeneratorfunction(CircuitDesigner.enumerate_expressions)


# --- the knob ------------------------------------------------------------------------


def test_the_constraint_default_allows_more_than_one_gate():
    """``max_circuit_gates`` is what the API and the wizard set; 1 restores the
    one-circuit-per-gene behaviour this engine had before stage 4 existed."""
    assert Constraints().max_circuit_gates == 2
    assert Constraints(max_circuit_gates=1).max_circuit_gates == 1
