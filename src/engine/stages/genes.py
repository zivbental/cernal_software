"""Stage 1 — gene selection.

Narrows a whole transcriptome to the handful of genes worth building a circuit around.

The criteria are all about **separation**: a useful gene is one whose expression tells
the two cell states apart cleanly. That is not the same as "most differentially
expressed" — a gene with a huge fold change between two barely-detectable values is
statistically impressive and biologically useless, because a switch cannot respond to
transcripts that are not there.

CERNAL does **not** run differential expression. The researcher supplies DESeq2-style
results; this stage filters and ranks them.
"""

from engine.domain import (
    Constraints,
    CountMatrix,
    DgeTable,
    SelectedGene,
)


class GeneSelector:
    """Keep the genes that actually separate the two cell states.

    Args:
        constraints: Thresholds the researcher configured — ``min_separation`` (log2
            fold change) and ``max_p_adj``.
        atlas: Optional reference expression, e.g. Human Cell Atlas (map input 7). Used
            for **condition specificity**: a gene strongly expressed in the target state
            but also everywhere else in the body is a poor trigger for a therapeutic
            circuit, however clean the in-vitro separation looks.
    """

    def __init__(self, constraints: Constraints, atlas: dict[str, float] | None = None) -> None:
        self.constraints = constraints
        self.atlas = atlas

    def select(self, counts: CountMatrix, dge: DgeTable) -> list[SelectedGene]:
        """Filter, score and rank genes; return a shortlist with an up/down call.

        Args:
            counts: The count matrix. Needed for absolute abundance and percentiles —
                the DGE table gives ``base_mean`` but not per-group distributions.
            dge: The researcher's differential-expression results.

        Returns:
            ``SelectedGene`` list, best first. Typically tens of genes, not thousands:
            everything downstream scales with this, and a hundred genes makes pair
            enumeration a five-figure problem before any folding happens.

        What to compute (Step 5):
            1. **Filter on significance.** ``p_adj <= constraints.max_p_adj``. Drop rows
               with a null ``p_adj`` — DESeq2 emits those for genes it filtered out, and
               they are not "not significant", they are "not tested".
            2. **Filter on effect size.** ``abs(log2_fold_change) >= min_separation``.
            3. **Filter on absolute abundance, in both states.** This is the criterion
               the pipeline map calls out and the one most easily forgotten. Too low in
               the ON state and the switch never sees enough trigger — a false negative.
               Too high in the OFF state and the switch leaks — a false positive. Express
               it as a usable window, not a floor.
            4. **Percentiles.** Where each gene's expression sits within its own group's
               distribution. A gene in the 95th percentile of the condition and the 20th
               of the control separates cleanly; two genes with identical fold changes
               can differ sharply here.
            5. **Condition specificity.** How much of this gene's expression is in the
               target state versus everywhere. Use ``atlas`` when available.
            6. **Score and sort.** Combine the above. Keep it explicit and documented —
               this weighting decides what the whole run explores, and it should be a
               recorded scientific choice rather than an accident of implementation.

        Note on direction:
            ``regulation`` (UP or DOWN) is not the same as the gate's ``GeneState``. An
            UP gene is a natural activator input; a DOWN gene is a natural repressor
            input, reached through a NOT gate. Stage 4 makes that mapping — this stage
            only records which way the gene moved.
        """
        raise NotImplementedError("Step 5")
