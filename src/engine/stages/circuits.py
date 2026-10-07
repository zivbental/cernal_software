"""Stage 4 — circuit design and scoring.

Stages 1 to 3 produced parts. This stage decides how to wire them.

The researcher's real requirement is a **Boolean condition**: fire in the target state,
stay dark in the control. Stage 1 gave a set of genes and which way each moved; that
pattern implies a truth table, and many different expressions reproduce the same table
with different component counts. This stage enumerates them, keeps the ones actually
buildable from switches designed upstream, and ranks them.

Scoring here is unlike the earlier stages. A trigger is scored on its properties; a
**circuit is scored on its behaviour** — run it against every real sample and count how
often it gets the answer right. That is the confusion matrix, and it is a far more
honest measure than any thermodynamic proxy.
"""

import itertools
from collections.abc import Iterable, Iterator

from engine.domain import (
    BooleanExpression,
    CircuitCandidate,
    ConfusionMatrix,
    CountMatrix,
    GateDesign,
    GeneState,
    LogicGene,
    LogicGraph,
    LogicOperator,
    Regulation,
    SelectedGene,
)


class CircuitDesigner:
    """Turn an up/down gene pattern into ranked, buildable circuits.

    Args:
        evaluator: Scores a candidate expression against the samples.
        max_terms: Cap on expression size. Larger circuits fit the training samples
            better and are harder to build and more likely to misbehave — this is the
            complexity side of the trade-off the Pareto filter later exposes.
    """

    def __init__(self, evaluator: "ConfusionEvaluator", max_terms: int = 4) -> None:
        self.evaluator = evaluator
        self.max_terms = max_terms

    def design(
        self,
        genes: list[SelectedGene],
        designs: Iterable[GateDesign],
        counts: CountMatrix,
    ) -> Iterator[CircuitCandidate]:
        """Yield scored circuits, buildable from the switches that exist.

        Args:
            genes: Stage 1's shortlist, with each gene's direction.
            designs: Stage 3's validated switches. **The binding constraint** — an
                expression needing an input with no switch is not a circuit, it is a wish.
            counts: The count matrix, for evaluating behaviour on real samples.

        Yields:
            ``CircuitCandidate`` with its expression, logic graph, component designs,
            confusion matrix and score.

            **Rejected circuits are yielded too**, carrying a ``Rejection``. Unlike
            stage 3, where a failed design is a construction error, a circuit rejected
            for scoring below a threshold is a real alternative the researcher may want
            to see — and rule 8, enforced by a database constraint on import, requires the
            reason to travel with it.

        The method (Step 5):
            1. Index the available designs by the gene they respond to, so checking
               buildability is a lookup rather than a scan.
            2. ``enumerate_expressions(genes)`` for candidate logic.
            3. Drop any expression referencing a gene with no design.
            4. ``evaluator.evaluate(expression, counts, threshold)`` for the confusion
               matrix.
            5. Build the ``LogicGraph`` the results view renders — genes with their ON/OFF
               state and direction, the gate operators, and the caption.
            6. Score: separation margin against complexity. Yield.

        On overfitting:
            With few samples, a large expression can score perfectly by memorising them.
            That is why ``max_terms`` exists and why complexity is a scored axis rather
            than a tiebreak. Say so in the report: a 6-term circuit at 100% on 8 samples
            deserves less trust than a 2-term circuit at 90%.

        On ``designs`` order:
            The **first** design found for a gene is the one used, so a caller that wants
            each circuit built from the best available switch passes them best-first.
            Choosing between a gene's designs needs their scores, and scoring is
            ``engine.scoring``'s job, not this stage's (CLAUDE.md §3) — so the choice is
            the caller's to express through ordering rather than this method's to make.

        On ``counts`` being empty:
            ``confusion`` is only measured when ``counts`` actually carries samples. The
            product collects a differential-expression table and no per-sample count
            matrix (docs/genes.md §3 G-a), so today it does not: a circuit is yielded
            with an all-zero ``ConfusionMatrix`` that nothing downstream reads, exactly
            as ``pipeline._build_plasmid`` already does for the one-gene case. That zero
            must never be read as a measured separation — when the count matrix exists,
            ``ConfusionEvaluator.evaluate`` fills it and ``score`` becomes the separation
            margin the docstring above describes.

        On ``score`` and ``circuit_id``:
            ``score`` stays 0.0 and the id is derived from the genes. Weighting and
            ranking belong to ``engine.scoring``, and the stored id is minted by
            ``CandidateStore`` — the caller replaces both.
        """
        by_gene: dict[str, GateDesign] = {}
        for design in designs:
            triggers = design.trigger_set.activators + design.trigger_set.repressors
            for trigger in triggers:
                # First wins: see "On designs order" above.
                by_gene.setdefault(trigger.gene_id, design)

        for expression in self.enumerate_expressions(genes):
            gene_ids = expression.gene_ids()
            if len(gene_ids) > self.max_terms:
                continue
            members = [by_gene.get(gene_id) for gene_id in gene_ids]
            if any(member is None for member in members):
                # Not buildable: an expression needing a switch nobody designed is a
                # wish, not a circuit. Dropped rather than rejected — the researcher
                # never asked for this combination, the enumerator proposed it.
                continue

            by_id = {gene.gene_id: gene for gene in genes}
            yield CircuitCandidate(
                circuit_id="circuit-" + "-".join(gene_ids),
                expression=expression,
                logic_graph=self._logic_graph(expression, gene_ids, by_id),
                # Dedup by id, not by value: GateDesign carries an ``architecture``
                # dict and so is not hashable. Two genes can legitimately resolve to
                # one design when a single switch responds to both.
                designs=tuple({d.design_id: d for d in members}.values()),
                confusion=(
                    self.evaluator.evaluate(expression, counts, threshold=0.0)
                    if counts.samples
                    else ConfusionMatrix(0, 0, 0, 0)
                ),
                output="",
            )

    @staticmethod
    def _logic_graph(
        expression: BooleanExpression,
        gene_ids: tuple[str, ...],
        by_id: dict[str, SelectedGene],
    ) -> LogicGraph:
        """The circuit in the shape the results view draws.

        ``state`` is what the circuit *requires* of each transcript, which is not the
        same as the direction the gene moved: an UP gene must be present (``ON``), a DOWN
        gene must be absent (``OFF``) — ``Regulation`` describes the data, ``GeneState``
        describes the requirement (domain.py's own note on the distinction).
        """
        logic_genes = []
        for gene_id in gene_ids:
            gene = by_id.get(gene_id)
            regulation = gene.regulation if gene else Regulation.UP
            logic_genes.append(
                LogicGene(
                    name=gene.symbol if gene and gene.symbol else gene_id,
                    role=gene_id,
                    state=GeneState.OFF if regulation is Regulation.DOWN else GeneState.ON,
                    direction=regulation,
                )
            )
        return LogicGraph(
            genes=tuple(logic_genes),
            mid_gate=expression.operator,
            outer_gate=expression.operator,
            invert=expression.operator is LogicOperator.NOT,
            output="",
            caption=f"IF {expression.render()}",
        )

    def enumerate_expressions(self, genes: list[SelectedGene]) -> Iterator[BooleanExpression]:
        """Generate Boolean expressions reproducing the genes' up/down pattern.

        Args:
            genes: The shortlist. UP genes are natural activators; DOWN genes are natural
                repressors, reached through NOT.

        Yields:
            ``BooleanExpression`` trees, **simplest first**, so a caller that stops early
            keeps the cheapest circuits.

        Why several (Step 5):
            ``A AND (B OR C)`` and ``(A AND B) OR (A AND C)`` have identical truth tables
            and different component counts. The first needs three switches, the second
            four. Enumerating equivalents lets the cheaper form win.

            Start narrow and widen only if the results justify it:

            * singles: ``A``
            * pairs: ``A AND B``, ``A AND NOT B``
            * one nesting level: ``A AND (B OR C)``, ``A AND NOT B``

            The full space of Boolean functions over n variables is 2^(2^n) and is not
            worth enumerating. Cap at ``max_terms`` and generate structurally, not by
            filtering every possible function.

        Gotcha:
            Deduplicate by truth table, not by rendered string. ``A AND B`` and ``B AND A``
            are the same circuit and should not both be scored.

        What this builds:
            Conjunctions, smallest first: every gene on its own, then every pair, up to
            ``max_terms`` genes. Each gene enters oriented by its own direction — an UP
            gene as itself, a DOWN gene through ``NOT`` — so the expression fires in the
            target state and stays dark in the control, which is the requirement the
            module docstring states.

            Disjunctions and nested forms (``A AND (B OR C)``) are **not** generated
            yet. The docstring above describes them as the widening step, and widening
            is only worth it once there are enough samples to tell the equivalents
            apart; with no count matrix (see ``design``) nothing here can measure which
            of two equivalent forms behaves better, so generating both would multiply
            the candidate pool without adding information.
        """
        ordered = sorted(genes, key=lambda gene: gene.gene_id)
        terms = {gene.gene_id: self._term(gene) for gene in ordered}
        gene_ids = [gene.gene_id for gene in ordered]

        seen: set[tuple[tuple[str, ...], tuple[bool, ...]]] = set()
        ceiling = max(1, min(self.max_terms, len(gene_ids)))
        for size in range(1, ceiling + 1):
            for combination in itertools.combinations(gene_ids, size):
                if size == 1:
                    expression = terms[combination[0]]
                else:
                    expression = BooleanExpression(
                        LogicOperator.AND, tuple(terms[gene_id] for gene_id in combination)
                    )
                key = self._truth_table(expression)
                if key in seen:
                    continue
                seen.add(key)
                yield expression

    @staticmethod
    def _term(gene: SelectedGene) -> BooleanExpression:
        """One gene as a circuit input, oriented by the direction it actually moved.

        An UP gene is present in the target state, so the circuit fires *on* it. A DOWN
        gene is absent there, so it reaches the circuit through ``NOT`` — which is a real
        extra component, and ``BooleanExpression.complexity()`` counts it as one.
        """
        if gene.regulation is Regulation.DOWN:
            return BooleanExpression(LogicOperator.NOT, (gene.gene_id,))
        return BooleanExpression.gene(gene.gene_id)

    @staticmethod
    def _truth_table(
        expression: BooleanExpression,
    ) -> tuple[tuple[str, ...], tuple[bool, ...]]:
        """``(genes, outputs)`` over every assignment — the identity used to deduplicate.

        Two expressions are the same circuit when they fire on exactly the same inputs,
        however they are written. Keyed on the sorted gene set as well as the outputs so
        that two expressions over *different* genes are never conflated by having the
        same shape.
        """
        gene_ids = tuple(sorted(expression.gene_ids()))
        outputs = tuple(
            expression.evaluate(frozenset(active))
            for size in range(len(gene_ids) + 1)
            for active in itertools.combinations(gene_ids, size)
        )
        return gene_ids, outputs


class ConfusionEvaluator:
    """Scores a circuit by how it behaves on the actual samples.

    The pipeline map's confusion table: circuit ON or OFF, against condition or control.

    This is the most honest signal in the pipeline. Everything before it is prediction —
    predicted folding, predicted binding. This is measurement, against data the
    researcher actually collected.
    """

    def evaluate(
        self, expression: BooleanExpression, counts: CountMatrix, threshold: float
    ) -> ConfusionMatrix:
        """Run an expression over every sample and tally the four outcomes.

        Args:
            expression: The circuit's logic.
            counts: The count matrix, with metadata naming control and condition columns.
            threshold: Expression level above which a gene counts as present. See the
                warning below.

        Returns:
            ``ConfusionMatrix``. ``separation_margin`` (Youden's J) is the headline: 1.0
            is perfect, 0.0 is no better than chance, and a circuit that fires on
            everything scores 0.0 despite catching every true positive — which is exactly
            why the margin is used rather than accuracy.

        The method (Step 5):
            For each sample: build the set of genes present at ``threshold``, call
            ``expression.evaluate(present)``, and compare against whether the sample is
            condition or control. Increment the matching cell.

        On the threshold:
            A single global cut-off is the crude version and fine to start with. It is
            also the weakest assumption in this stage — genes have wildly different
            dynamic ranges, and one number cannot suit all of them. A per-gene threshold
            derived from its own control distribution (say, the control 90th percentile)
            is more defensible and not much more work. **Whatever is chosen, record it**:
            the confusion matrix means nothing without knowing what "present" meant.
        """
        raise NotImplementedError("Step 5")
