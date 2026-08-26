"""Stage 1 — gene selection."""

from engine.domain import (
    Constraints,
    CountMatrix,
    DgeTable,
    SelectedGene,
)


class GeneSelector:
    """Keep the genes that actually separate the two cell states.

    Big enough fold change, statistically significant, and expressed in a usable
    absolute range in both states: too low gives false negatives, too high gives false
    positives.
    """

    def __init__(self, constraints: Constraints, atlas: dict[str, float] | None = None) -> None:
        self.constraints = constraints
        #: Optional Human Cell Atlas reference, for condition specificity.
        self.atlas = atlas

    def select(self, counts: CountMatrix, dge: DgeTable) -> list[SelectedGene]:
        """Rank and shortlist, with an up/down call per gene.

        Step 5: apply the log2 fold change, adjusted p and absolute abundance thresholds
        from `constraints`; compute control and condition expression percentiles and
        condition specificity; score and sort.

        CERNAL does not run differential expression — the researcher supplies it.
        """
        raise NotImplementedError("Step 5")
