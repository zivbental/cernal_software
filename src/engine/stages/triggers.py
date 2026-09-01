"""Stage 2 — trigger scoring.

Takes the shortlisted genes and finds, within each transcript, the specific segments a
switch could actually be built against.

A trigger is not "a gene". It is a **window of 30-ish nucleotides at a particular offset
in a particular transcript**, and most windows are unusable: buried in structure, shared
with other transcripts, GC-extreme, or carrying a forbidden motif. This stage slides a
window along each transcript and ranks every position.

**This is the pruning point of the whole pipeline.** Everything downstream scales with
how many candidates survive here, so this filter sets the compute budget far more than
any hardware choice does (docs/ROADMAP.md §3). Keeping the top few hundred
across all genes keeps a run in minutes; keeping everything makes it hours.
"""

from collections.abc import Iterator

from engine.domain import Constraints, SelectedGene, TriggerCandidate
from engine.stages.folding import FoldProfiler
from engine.stages.motifs import MotifScreener
from engine.stages.off_target import OffTargetScanner


class TriggerScorer:
    """Rank every sub-segment of every selected gene as a possible switch input.

    Args:
        profiler: The run's shared ``FoldProfiler``. Supplies accessibility, which is the
            single most important trigger property — a sequence buried in a stable
            hairpin cannot be reached however well it matches.
        off_target: The run's shared ``OffTargetScanner``. Answers direction (b): is this
            segment sponged by other transcripts?
        screener: The run's shared ``MotifScreener``. Rejects segments carrying
            restriction sites or long homopolymers, which would make the eventual
            construct unbuildable.

    All three are handed in rather than constructed, so their caches and settings are
    shared with the stages downstream (docs/engine.md §2.4).
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
        """Yield ranked trigger candidates across every selected gene.

        Args:
            genes: Stage 1's shortlist.
            sequences: Gene ID to full transcript sequence. **Where this comes from is
                still an open question** — the DGE table carries identifiers, not
                sequences (docs/ROADMAP.md §2, Q1). A reference
                transcriptome per organism is the likely answer, and it must be the same
                build the ``OffTargetScanner`` indexes, or the two disagree.
            constraints: Supplies ``trigger_lengths`` — the length classes to scan.
                Different gate chemistries need different footprints, which is why this
                is a tuple rather than one number.

        Yields:
            ``TriggerCandidate`` per surviving window, ideally best-scoring first per
            gene. **Yields rather than returns**: a few dozen genes across two length
            classes is tens of thousands of windows before pruning, and materialising
            them all is what makes a pipeline need a bigger machine.

        Per window, compute (Step 5):
            * ``openness`` — ``profiler.openness(transcript, start, end)``. **Profile each
              transcript once** and slice; profiling per window is quadratic and is the
              easiest way to make this stage take hours instead of minutes.
            * ``accessibility`` — the same idea, but the minimum rather than the mean, or
              whatever the scientific team decides. A window that is open at both ends
              and paired in the middle averages well and binds badly.
            * ``mfe`` — the segment's own folding energy. A trigger that folds tightly on
              itself competes with binding the switch.
            * ``gc_content`` — ``sequences.gc_content``. Extremes hurt both synthesis and
              duplex behaviour.
            * ``off_target_penalty`` — ``off_target.scan_trigger(window)``.
            * ``aug_indexes`` / ``stop_indexes`` — recorded because a trigger containing a
              start codon can interfere once it is incorporated into the switch's stem.
            * ``segment_specificity`` — how much this window distinguishes its gene from
              its paralogues.

        Filter before scoring where you can:
            Motif violations and GC extremes are cheap; accessibility and off-target are
            expensive. Screening the cheap criteria first avoids folding windows that
            were never going to survive, and on a transcriptome that is most of them.

        Prune before yielding:
            Keep a top-K per gene rather than everything above a threshold. A threshold
            lets one unusually open transcript flood the candidate pool and starve the
            other genes of budget.
        """
        raise NotImplementedError("Step 5")
