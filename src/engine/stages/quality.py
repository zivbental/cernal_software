"""S15 — input quality control.

The pipeline map calls this "currently a footnote with no home". It belongs in front of
GeneSelector, because everything downstream is wasted effort if the matrix is unusable.
"""

from engine.domain import CountMatrix, QcReport, SampleMetadata


class InputQualityCheck:
    """Validates the uploaded matrix before anything expensive runs."""

    def __init__(self, min_samples_per_group: int = 2) -> None:
        self.min_samples_per_group = min_samples_per_group

    def check(self, counts: CountMatrix, metadata: SampleMetadata) -> QcReport:
        """Distributions, library sizes, outliers, batch structure.

        Step 5: library-size spread, zero-inflation, a PCA of samples to expose batch
        effects, and whether each group has enough replicates to say anything.
        Returns errors that stop the run and warnings that only inform.
        """
        raise NotImplementedError("Step 5")
