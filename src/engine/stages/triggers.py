"""Stage 2 — trigger scoring.

**The pruning point.** Everything downstream scales with how many candidates survive
here, so this filter sets the compute budget more than any hardware choice does.
"""

from collections.abc import Iterator

from engine.domain import Constraints, SelectedGene, TriggerCandidate
from engine.tools.folding import FoldProfiler
from engine.tools.motifs import MotifScreener
from engine.tools.off_target import OffTargetScanner


class TriggerScorer:
    """Slide a window along each selected gene's transcript and rank every sub-segment.

    Ranked by how unpaired it is in local folding context, plus off-target load, GC and
    forbidden motifs — per length class, because each gate family needs a different
    footprint.
    """

    def __init__(
        self,
        profiler: FoldProfiler,
        off_target: OffTargetScanner,
        screener: MotifScreener,
    ) -> None:
        self.profiler = profiler
        self.off_target = off_target
        self.screener = screener

    def score(
        self,
        genes: list[SelectedGene],
        sequences: dict[str, str],
        constraints: Constraints,
    ) -> Iterator[TriggerCandidate]:
        """Yield ranked trigger candidates per gene.

        Step 5: for each gene and each length in `constraints.trigger_lengths`, slide a
        window; compute openness from the fold profile, off-target penalty, GC and motif
        violations; drop anything failing a hard rule; score and yield.

        **Yields** rather than returns: a few hundred genes across several length classes
        is tens of thousands of candidates.

        `sequences` maps gene_id to transcript — see docs/step-5-engine-plan.md §10
        question 1, which is not yet answered.
        """
        raise NotImplementedError("Step 5")
