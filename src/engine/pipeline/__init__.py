"""The real scientific pipeline.

**Not implemented until Step 5.** ``LocalEngine`` calls ``run_pipeline``; until the
stages in ``engine.pipeline.stages`` are filled in, use ``MockEngine`` instead
(``CERNAL_ENGINE=engine.client.MockEngine``, the default).

The orchestration below is written out as comments rather than code so that Step 5 has a
concrete target: it is the ordering the stages were designed around, and the point where
cancellation is checked.
"""

from engine.contract import JobRequest, JobResult

ProgressFn = None  # re-exported from engine.client at call time; see run_pipeline


def run_pipeline(request: JobRequest, on_progress) -> JobResult:
    """Execute the full scientific pipeline for one job.

    Step 5 implementation outline, in stage order (design map 11):

    1.  ``validate_inputs``          → raise InputValidationError on bad science
    2.  ``load_and_preprocess``      → verify input_checksum first
    3.  ``discover_features``
    4.  ``generate_trigger_sets``
    5.  ``evaluate_triggers``        → drop sets failing hard constraints, with reasons
    6.  ``generate_gates``           → per requested family, via engine.gates.registry
    7.  ``evaluate_gates``
    8.  ``construct_circuits``
    9.  ``normalize_metrics``        → engine.scoring.normalize.build_metrics
    10. ``score_candidates``         → engine.scoring.normalize.weighted_score
    11. ``rank_and_filter``          → engine.scoring.normalize.rank_candidates
    12. ``generate_artifacts``       → engine.artifacts.write_artifact
    13. ``publish_result``

    ``on_progress(pct, stage)`` must be called between stages, and a ``False`` return
    must raise ``JobCancelled`` — cancellation is cooperative, never a killed thread
    (docs/software-design.md §6.2).
    """
    raise NotImplementedError(
        "The real pipeline lands in Step 5. Set CERNAL_ENGINE=engine.client.MockEngine."
    )
