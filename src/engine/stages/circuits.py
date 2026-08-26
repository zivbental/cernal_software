"""Stage 4 — circuit design and scoring."""

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
    """Turn the genes' up/down pattern into a Boolean function.

    Generates the expressions reproducing it, keeps only those buildable from switches
    actually designed upstream, and ranks by how cleanly they separate condition from
    control against how complex they are.
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
        """Yield scored circuits.

        Step 5: enumerate candidate expressions over the selected genes up to
        `max_terms`; discard any needing a switch that was not designed; evaluate each
        against the samples; yield with its confusion matrix and score.
        """
        raise NotImplementedError("Step 5")

    def enumerate_expressions(self, genes: list[SelectedGene]) -> Iterator[BooleanExpression]:
        """Equivalent Boolean forms of the up/down pattern.

        Several expressions reproduce the same truth table with different component
        counts, and the cheaper one is usually the better circuit.
        """
        raise NotImplementedError("Step 5")


class ConfusionEvaluator:
    """Score a circuit by how it behaves on the actual samples.

    The pipeline map's confusion table: circuit ON/OFF against condition/control.
    """

    def __init__(self, off_target: OffTargetScanner) -> None:
        #: Only for cross-talk between a circuit's own parts. Per-trigger and
        #: per-switch penalties are already computed upstream and must not be re-scanned.
        self.off_target = off_target

    def evaluate(
        self, expression: BooleanExpression, counts: CountMatrix, threshold: float
    ) -> ConfusionMatrix:
        """Run the expression over every sample and tally the four outcomes.

        Step 5: call each gene present or absent per sample at `threshold`, evaluate the
        expression, and compare against whether the sample is condition or control.
        """
        raise NotImplementedError("Step 5")

    def cross_talk_penalty(self, designs: list[GateDesign]) -> float:
        """Interference between a circuit's own switches — one trigger opening another's
        switch. The only genuinely new off-target search at this stage."""
        raise NotImplementedError("Step 5")
