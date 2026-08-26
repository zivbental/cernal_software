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

from collections.abc import Iterable, Iterator

from engine.domain import (
    BooleanExpression,
    CircuitCandidate,
    ConfusionMatrix,
    CountMatrix,
    GateDesign,
    SelectedGene,
)
from engine.tools.off_target import OffTargetScanner


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
            5. ``evaluator.cross_talk_penalty(designs)`` for interference between the
               circuit's own parts.
            6. Build the ``LogicGraph`` the results view renders — genes with their ON/OFF
               state and direction, the gate operators, and the caption.
            7. Score: separation margin against complexity, minus cross-talk. Yield.

        On overfitting:
            With few samples, a large expression can score perfectly by memorising them.
            That is why ``max_terms`` exists and why complexity is a scored axis rather
            than a tiebreak. Say so in the report: a 6-term circuit at 100% on 8 samples
            deserves less trust than a 2-term circuit at 90%.
        """
        raise NotImplementedError("Step 5")

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
        """
        raise NotImplementedError("Step 5")


class ConfusionEvaluator:
    """Scores a circuit by how it behaves on the actual samples.

    The pipeline map's confusion table: circuit ON or OFF, against condition or control.

    This is the most honest signal in the pipeline. Everything before it is prediction —
    predicted folding, predicted binding, predicted off-target load. This is measurement,
    against data the researcher actually collected.

    Args:
        off_target: Shared scanner, used **only** for cross-talk between a circuit's own
            components. Per-trigger and per-switch penalties are already computed and
            stored upstream; re-scanning here would be slow and would disagree with the
            numbers already recorded (docs/engine.md §3.4).
    """

    def __init__(self, off_target: OffTargetScanner) -> None:
        self.off_target = off_target

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

    def cross_talk_penalty(self, designs: list[GateDesign]) -> float:
        """Interference between a circuit's own switches.

        Each switch was validated in isolation against the transcriptome. In a circuit
        they coexist, and trigger A may open switch B. A two-input AND whose switches
        cross-activate is really an OR, and it will look fine in every earlier stage.

        Args:
            designs: Every switch in this circuit.

        Returns:
            A penalty, 0.0 for no interference and rising with it. Subtracted from the
            circuit score, and it should also raise the false-positive expectation.

        Implementation (Step 5):
            For each ordered pair of designs, ask whether one's trigger resembles the
            other's binding site — ``off_target.find_similar`` against the
            reverse complement, as in ``scan_switch``. Skip self-pairs. Weight by
            similarity.

        Note:
            This is the **only** genuinely new off-target search at this stage. Everything
            else was computed upstream and stored.
        """
        raise NotImplementedError("Step 5")
