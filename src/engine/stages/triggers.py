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

**Provenance.** The sliding-window scan and the use of a window's own folding energy as a
scoring input are a port of a validated approach built outside this repo
(``find_triggers.py``): scan every transcript with ``sequences.windows`` (S6) and
disqualify with the shared ``MotifScreener`` (S7) and ``OffTargetScanner`` (S5) before
anything expensive runs. Not ported: the source script's positional bonus, which added a
Gaussian term straight onto the raw MFE value before ranking. Its own inline comment
("bonus near the edges of the sequence") does not match what the formula it sits next to
actually computes (a Gaussian centred on the *midpoint*, not the ends — see the port's
open questions), and mutating a physical quantity with an undeclared positional prior is
exactly the kind of hidden per-family filter ``CLAUDE.md`` §3 rules out; ``mfe`` here is
therefore the plain folding energy, unadjusted.
"""

from collections.abc import Iterator

from engine import sequences as sq
from engine.domain import Constraints, SelectedGene, TriggerCandidate
from engine.gates.tools.folding import FoldEngine
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
        folder: The run's shared ``FoldEngine``. Needed for ``TriggerCandidate.mfe`` — a
            window's own folding energy — which is not one of ``profiler``'s outputs
            (``FoldProfiler`` wraps windowed ``RNAplfold`` and reports only per-position
            unpaired probability, never an energy). Not part of this class's signature
            before this port; see the port's open questions.

    All four are handed in rather than constructed, so their caches and settings are
    shared with the stages downstream (docs/engine.md §2.4).
    """

    #: Trigger candidates kept per gene after scoring, across every swept trigger length.
    #: ``Constraints`` carries no equivalent field today (see the port's open questions),
    #: so this stays a class constant — a search-budget knob, not an undeclared filter on
    #: any single candidate's numbers.
    TOP_K_PER_GENE = 50

    def __init__(
        self,
        profiler: FoldProfiler,
        off_target: OffTargetScanner,
        screener: MotifScreener,
        folder: FoldEngine,
    ) -> None:
        self.profiler = profiler
        self.off_target = off_target
        self.screener = screener
        self.folder = folder

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

        Deviations from this port (see the module docstring's Provenance note and the
        PR's open questions for the full list): windows are scanned densely
        (``sequences.windows``'s own default stride of 1), since neither the source
        script's ``stride`` parameter nor a GC-content cutoff has a home in
        ``Constraints`` today; ``segment_specificity`` is approximated from the
        off-target report rather than a real paralogue search, for the same reason.
        ``score`` is a simple, explicitly-labelled placeholder combination — per
        ``SelectedGene.score``'s own docstring, a stage's ranking weights are a
        recorded scientific choice, and this one has not been reviewed by the
        scientific team yet.
        """
        for gene in genes:
            transcript = sequences[gene.gene_id]
            # Profile the whole transcript once and slice per window below; profiling
            # per window is quadratic (this method's own docstring, and
            # FoldProfiler.profile's — neither caches per instance).
            profile = self.profiler.profile(transcript)

            candidates: list[TriggerCandidate] = []
            for length in constraints.trigger_lengths:
                for start, window in sq.windows(transcript, length):
                    end = start + length
                    # Cheapest filter first: a string scan, before anything folds or
                    # searches the transcriptome.
                    if self.screener.violations(window):
                        continue

                    local_profile = profile[start:end]
                    openness = sum(local_profile) / length
                    # "the minimum rather than the mean" per this method's own
                    # docstring — open at both ends and paired in the middle binds
                    # badly however good the mean looks. The docstring leaves the
                    # final call to the scientific team; flagged in the PR.
                    accessibility = min(local_profile)

                    off_target_report = self.off_target.scan_trigger(window)
                    # No dedicated paralogue search exists in this engine; the
                    # off-target report is the closest available signal for how much
                    # this window is shared with other transcripts. See the PR's open
                    # questions — this is a proxy, not a distinct measurement.
                    segment_specificity = max(0.0, 1.0 - off_target_report.penalty)

                    candidates.append(
                        TriggerCandidate(
                            trigger_id=f"trig-{gene.gene_id}-{start}-{length}",
                            gene_id=gene.gene_id,
                            symbol=gene.symbol,
                            sequence=window,
                            start_index=start,
                            openness=openness,
                            accessibility=accessibility,
                            mfe=self.folder.mfe(window).energy,
                            off_target_penalty=off_target_report.penalty,
                            segment_specificity=segment_specificity,
                            gc_content=sq.gc_content(window),
                            aug_indexes=sq.find_augs(window),
                            stop_indexes=sq.find_stops(window),
                            score=accessibility * segment_specificity,
                        )
                    )

            candidates.sort(key=lambda c: c.score, reverse=True)
            yield from candidates[: self.TOP_K_PER_GENE]
