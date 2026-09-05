"""The real scientific pipeline.

**Composition only.** This module constructs the tools once, hands them to the stages,
and runs them in order. It contains no science — if it grows past ~150 lines, logic has
leaked into it from a stage.

Not implemented until Step 5. ``LocalEngine`` calls ``run_pipeline``; until the stages
are filled in, use ``MockEngine`` (``CERNAL_ENGINE=engine.client.MockEngine``, the
default).
"""

from collections.abc import Callable

from engine.contract import JobRequest, JobResult
from engine.domain import Host

ProgressFn = Callable[[int, str], bool]

#: How much of the run each stage is expected to cost. Progress is weighted by this
#: rather than by stage index, or the bar sits at 60% for ten minutes.
STAGE_WEIGHTS: dict[str, int] = {
    "Validating inputs": 2,
    "Selecting genes": 5,
    "Scoring triggers": 25,
    "Designing switches": 45,
    "Designing circuits": 15,
    "Constructing plasmids": 5,
    "Writing report": 3,
}


def build_tools(request: JobRequest, host: Host) -> dict[str, object]:
    """Construct every tool **once** per run, and hand them back for wiring.

    Args:
        request: The immutable submission. Supplies the parameters each tool is
            configured from, so that configuration is recorded rather than hardcoded.
        host: The organism. Selects the codon table and the translation mechanism.

    Returns:
        The constructed tools, keyed by name, ready to pass into stages and gate
        families.

    Why this is a function and not a per-class concern:
        ``FoldEngine``'s cache lives on the instance. Four instances means four cold
        caches — and, worse, four chances for someone to construct one at a different
        temperature. Two designs folded at different temperatures produce numbers that
        ``engine.scoring`` will normalise onto the same axis as though they were
        comparable, and the resulting ranking is wrong in a way nothing detects.

        Constructing them here also means the whole configuration of a run is visible in
        one place, which is what makes it recordable.

    Note:
        The transcriptome that ``OffTargetScanner`` indexes **must be the same build**
        the trigger sequences came from. Loading them separately is how two references
        drift apart, and the symptom is off-target penalties that look plausible and mean
        nothing.
    """
    raise NotImplementedError("Step 5 — see the sketch in run_pipeline")


def run_pipeline(request: JobRequest, on_progress: ProgressFn) -> JobResult:
    """Execute the full pipeline for one job.

    The shape Step 5 fills in::

        host        = Host(request.params["organism"])
        constraints = Constraints(**request.params.get("constraints", {}))
        profile     = get_profile(request.scoring_profile)

        # Tools — constructed once, shared by everything below.
        folder      = FoldEngine()
        profiler    = FoldProfiler()
        off_target  = OffTargetScanner(transcriptome, max_mismatch=2)
        screener    = MotifScreener(constraints.standard)
        codons      = CodonOptimizer(host)
        translation = TranslationScorer(host)

        # Stages — each receives what it needs, holds no accumulated state.
        InputQualityCheck().check(counts, metadata)
        genes    = GeneSelector(constraints).select(counts, dge)
        triggers = TriggerScorer(profiler, off_target, screener, folder).score(
                       genes, sequences, constraints)
        switches = SwitchDesigner(families, validator, host).design(triggers, constraints)
        circuits = CircuitDesigner(ConfusionEvaluator(off_target)).design(
                       genes, switches, counts)
        plasmids = [PlasmidBuilder(screener, codons).build(c, outcome) for c in ranked]
        artifacts = ReportBuilder(StructureRenderer()).build(ranked, plasmids, output_dir)

    Generators run between the stages so memory stays flat until ranking, which is the
    one step that legitimately needs everything at once.

    ``on_progress(pct, stage)`` must be called between stages **and between batches**
    within the expensive ones — it is both the progress bar and the cancellation check.
    A ``False`` return must raise ``JobCancelled``.
    """
    raise NotImplementedError(
        "The real pipeline lands in Step 5. Set CERNAL_ENGINE=engine.client.MockEngine."
    )
