"""S15 — input quality control.

Runs before anything expensive. The pipeline map calls this "currently a footnote with no
home", and it earns a home because every stage after it is wasted effort if the matrix is
unusable — and because a researcher would much rather be told "your two condition samples
cluster with your controls" in ten seconds than receive confident nonsense in ten minutes.

This stage never *fixes* anything. It reports, and the run either proceeds or stops.
Silently correcting a researcher's data is how a tool loses their trust.
"""

import math

from engine.domain import CountMatrix, QcReport, SampleMetadata


class InputQualityCheck:
    """Validates the uploaded count matrix before the pipeline starts.

    Args:
        min_samples_per_group: Fewest replicates per group to proceed. Below about 2 the
            differential-expression results carry no usable confidence, and CERNAL is
            building a circuit on top of them.
    """

    def __init__(self, min_samples_per_group: int = 2) -> None:
        self.min_samples_per_group = min_samples_per_group

    def check(self, counts: CountMatrix, metadata: SampleMetadata) -> QcReport:
        """Inspect the matrix and report what is wrong with it.

        Args:
            counts: The parsed count matrix, genes by samples.
            metadata: Which columns are control and which are condition.

        Returns:
            ``QcReport(ok, warnings, errors, stats)``.

            * ``errors`` stop the run. Reserve them for things that make the analysis
              meaningless: too few replicates, a group with no samples, an all-zero
              matrix, gene IDs that do not match the DGE table.
            * ``warnings`` are shown and the run continues. Use them for things that are
              suspicious but survivable: one sample with a very different library size,
              apparent batch structure, high zero-inflation.
            * ``stats`` carries the numbers behind both, so the report can show them.

        What to check (Step 5):
            1. **Shape.** Gene IDs in the matrix and the DGE table overlap. A mismatch
               here usually means two different annotation builds, and it is the most
               common real failure.
            2. **Group sizes.** Each group has at least ``min_samples_per_group``.
            3. **Library sizes.** Column sums. An order-of-magnitude outlier suggests a
               failed library rather than biology.
            4. **Zero inflation.** Fraction of zero counts per sample. Very high suggests
               the wrong file, or single-cell data submitted as bulk.
            5. **Sample clustering.** PCA or correlation on log counts. If controls and
               conditions do not separate, the circuit is being designed on noise — this
               is the highest-value check and the one worth stating plainly in the report.
            6. **Batch structure.** If the separation follows something other than the
               condition, say so.

        Note:
            Steps 1 to 4 are cheap and should always run. Step 5 needs numpy and costs a
            second or two — still trivial against a ten-minute pipeline, and worth it.
        """
        errors: list[str] = []
        warnings: list[str] = []
        genes, samples = counts.shape
        stats: dict = {
            "genes": genes,
            "samples": samples,
            "batch_assessment": "unavailable",
            "clustering": "unmeasured",
        }
        if metadata != counts.metadata:
            errors.append("Supplied metadata differs from the matrix metadata.")
        if not genes or not samples:
            errors.append("The count matrix must contain genes and samples.")
        if len(set(counts.gene_ids)) != genes or len(set(counts.samples)) != samples:
            errors.append("Gene and sample identifiers must be unique.")
        named = metadata.control_samples + metadata.condition_samples
        if len(set(named)) != len(named) or set(named) != set(counts.samples):
            errors.append("Each matrix sample must belong to exactly one metadata group.")
        for name, group in (
            ("control", metadata.control_samples),
            ("condition", metadata.condition_samples),
        ):
            if len(group) < self.min_samples_per_group:
                errors.append(f"{name} requires at least {self.min_samples_per_group} samples.")
        if len(counts.counts) != genes or any(len(row) != samples for row in counts.counts):
            errors.append("Count rows do not match matrix gene/sample dimensions.")
        elif any(
            isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0
            for row in counts.counts
            for v in row
        ):
            errors.append("Counts must be finite nonnegative numbers.")
        elif genes and samples:
            libraries = [sum(row[index] for row in counts.counts) for index in range(samples)]
            zeros = [
                sum(row[index] == 0 for row in counts.counts) / genes for index in range(samples)
            ]
            stats["library_sizes"] = dict(zip(counts.samples, libraries, strict=True))
            stats["zero_fractions"] = dict(zip(counts.samples, zeros, strict=True))
            if not any(libraries):
                errors.append("The count matrix is all zero.")
            if any(size == 0 for size in libraries):
                errors.append("One or more samples has a zero library size.")
            positive = [size for size in libraries if size > 0]
            if positive and max(positive) / min(positive) >= 10:
                warnings.append("Library sizes differ by at least an order of magnitude.")
            warnings.append("Clustering, batch effects and DGE overlap were not assessed.")
        return QcReport(ok=not errors, warnings=tuple(warnings), errors=tuple(errors), stats=stats)
