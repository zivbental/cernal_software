"""The analysis run lifecycle.

**Every status transition in the system happens here** (rule 5). Views parse and
authorize, tasks are thin shells, this module decides.

The invariant that matters most: a run must never be left in RUNNING. Every path out of
``execute_run`` reaches a terminal state, including unexpected exceptions.
"""

import logging
import tempfile
import uuid

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.analyses.models import AnalysisRun, InputMode, RunStatus
from apps.results.services import ResultImportError, import_job_result
from engine.client import load_engine
from engine.contract import CANCELLED, SCHEMA_VERSION, SUCCEEDED, JobRequest

logger = logging.getLogger(__name__)

#: How often the engine's progress callback writes to the database. The mock reports
#: eight times per run; a real pipeline may report far more often.
_PROGRESS_STEP = 1


class RunError(Exception):
    """A run could not be submitted or acted upon."""


class InvalidTransition(RunError):
    """An illegal status change was attempted."""


# --- Submission -------------------------------------------------------------------


def submit_run(
    *,
    project,
    user,
    dataset=None,
    input_mode: str = InputMode.DE,
    trigger_sequence: str = "",
    params: dict | None = None,
    gate_families: list[str] | None = None,
    scoring_profile: str = "default",
    seed: int | None = None,
    idempotency_key: str | None = None,
) -> tuple[AnalysisRun, bool]:
    """Freeze a submission and queue it.

    Returns ``(run, created)``. ``created`` is ``False`` when an existing run was
    returned for a repeated idempotency key — a retried submission must never launch a
    second expensive computation.
    """
    trigger_sequence = _clean_trigger(trigger_sequence) if input_mode == InputMode.DIRECT else ""

    if input_mode == InputMode.DE:
        if dataset is None:
            raise RunError("A dataset is required for a differential-expression run.")
        if dataset.project_id != project.id:
            raise RunError("That dataset belongs to a different project.")
        if not dataset.is_usable:
            raise RunError("This dataset did not pass validation and cannot be analysed.")
    elif input_mode == InputMode.DIRECT:
        dataset = None
    else:
        raise RunError(f"Unknown input mode '{input_mode}'.")

    key = idempotency_key or uuid.uuid4().hex
    existing = AnalysisRun.objects.filter(idempotency_key=key).first()
    if existing is not None:
        logger.info("Idempotent resubmission of run %s (key %s)", existing.id, key)
        return existing, False

    capabilities = load_engine(settings.CERNAL_ENGINE).capabilities()
    families = gate_families or ["toehold"]
    _validate_against_capabilities(families, scoring_profile, capabilities)

    run = AnalysisRun.objects.create(
        project=project,
        input_mode=input_mode,
        dataset=dataset,
        trigger_sequence=trigger_sequence,
        created_by=user,
        idempotency_key=key,
        # The snapshot is what makes a run immutable: later edits to the project or its
        # configuration cannot change what this run computed (rule 7).
        params_snapshot=dict(params or {}),
        gate_families=families,
        scoring_profile=scoring_profile,
        seed=seed,
        status=RunStatus.QUEUED,
        stage="Queued",
        progress_pct=0,
        submitted_at=timezone.now(),
    )

    # Queued after commit so the worker can never pick up a run that is not yet visible.
    transaction.on_commit(lambda: _enqueue(run.id))

    logger.info("Run %s submitted for project %s", run.id, project.id)
    return run, True


#: Minimum length the Platform will accept before bothering the engine.
MIN_TRIGGER_NT = 20


def _clean_trigger(sequence: str) -> str:
    """Normalize a pasted mRNA. Rejects anything that is not plainly a sequence."""
    cleaned = "".join(sequence.split()).upper().replace("T", "U")
    if not cleaned:
        raise RunError("Paste the trigger mRNA sequence, or switch to dataset upload.")
    if set(cleaned) - set("ACGU"):
        raise RunError("The trigger sequence may contain only A, C, G, U (or T).")
    if len(cleaned) < MIN_TRIGGER_NT:
        raise RunError(
            f"The trigger sequence is too short — at least {MIN_TRIGGER_NT} nucleotides."
        )
    return cleaned


def _validate_against_capabilities(families, scoring_profile, capabilities) -> None:
    available = capabilities.available_families
    unknown = sorted(set(families) - set(available))
    if unknown:
        raise RunError(
            f"Unavailable gate family: {', '.join(unknown)}. Available: {', '.join(available)}."
        )
    if scoring_profile not in capabilities.scoring_profiles:
        raise RunError(
            f"Unknown scoring profile '{scoring_profile}'. "
            f"Available: {', '.join(capabilities.scoring_profiles)}."
        )


def _enqueue(run_id) -> None:
    from django_q.tasks import async_task

    async_task(
        "apps.analyses.tasks.run_analysis",
        str(run_id),
        task_name=f"run-{str(run_id)[:8]}",
    )


# --- Execution --------------------------------------------------------------------


def execute_run(run_id: str) -> None:
    """Run one analysis to a terminal state.

    Called by the worker task. Safe to re-run: a run that is already terminal is a
    no-op, so a redelivered task cannot recompute or duplicate results.
    """
    run = AnalysisRun.objects.filter(pk=run_id).select_related("project", "dataset").first()
    if run is None:
        logger.warning("execute_run called for unknown run %s", run_id)
        return

    if run.is_terminal:
        logger.info("Run %s is already %s; nothing to do", run.id, run.status)
        return

    if run.cancel_requested:
        _finish(run, RunStatus.CANCELLED, stage="Cancelled")
        return

    try:
        _transition(run, RunStatus.RUNNING, stage="Starting", started_at=timezone.now())
    except InvalidTransition:
        logger.warning("Run %s could not start from %s", run.id, run.status)
        return

    try:
        _execute(run)
    except Exception:
        # The last line of defence. A run stuck in RUNNING is the worst failure mode in
        # the system, so even a programming error must land somewhere terminal.
        logger.exception("Run %s failed unexpectedly", run.id)
        _finish(
            run,
            RunStatus.FAILED,
            stage="Failed",
            error_summary="The analysis failed unexpectedly. The team has been notified.",
        )


def _execute(run: AnalysisRun) -> None:
    engine = load_engine(settings.CERNAL_ENGINE)

    with tempfile.TemporaryDirectory(prefix=f"cernal-run-{str(run.id)[:8]}-") as output_dir:
        request = JobRequest(
            schema_version=SCHEMA_VERSION,
            run_id=str(run.id),
            idempotency_key=run.idempotency_key,
            input_mode=run.input_mode,
            trigger_sequence=run.trigger_sequence,
            input_path=run.dataset.file.path if run.dataset else "",
            input_checksum=run.dataset.checksum_sha256 if run.dataset else "",
            organism=run.project.organism,
            params=run.params_snapshot,
            gate_families=run.gate_families,
            scoring_profile=run.scoring_profile,
            seed=run.seed,
            output_dir=output_dir,
        )

        result = engine.run(request, _progress_callback(run))

        if result.status == CANCELLED:
            _finish(
                run, RunStatus.CANCELLED, stage="Cancelled", engine_version=result.engine_version
            )
            return

        if result.status != SUCCEEDED:
            _finish(
                run,
                RunStatus.FAILED,
                stage="Failed",
                engine_version=result.engine_version,
                error_summary=result.error or "The analysis failed.",
                warnings=list(result.warnings),
            )
            return

        try:
            import_job_result(run, result, output_dir)
        except ResultImportError as exc:
            # The science succeeded; only the import failed. Say so plainly, so a retry
            # can re-import rather than recompute (design map 07).
            logger.error("Result import failed for run %s: %s", run.id, exc)
            _finish(
                run,
                RunStatus.FAILED,
                stage="Failed",
                engine_version=result.engine_version,
                error_summary=f"The results could not be imported: {exc}",
            )
            return

    _finish(
        run,
        RunStatus.COMPLETED,
        stage="Completed",
        progress_pct=100,
        engine_version=result.engine_version,
        warnings=list(result.warnings),
    )
    logger.info("Run %s completed with %d candidates", run.id, run.candidates.count())


def _progress_callback(run: AnalysisRun):
    """Stream engine progress into the run row, and carry cancellation back out.

    ``cancel_requested`` is re-read from the database on every call: the flag is set by
    the web process, not this one.
    """
    state = {"last": -_PROGRESS_STEP}

    def on_progress(percent: int, stage: str) -> bool:
        percent = max(0, min(100, int(percent)))
        if percent - state["last"] >= _PROGRESS_STEP or stage != run.stage:
            state["last"] = percent
            AnalysisRun.objects.filter(pk=run.pk).update(progress_pct=percent, stage=stage)
            run.progress_pct = percent
            run.stage = stage

        cancelled = (
            AnalysisRun.objects.filter(pk=run.pk).values_list("cancel_requested", flat=True).first()
        )
        return not cancelled

    return on_progress


# --- Cancellation -----------------------------------------------------------------


def cancel_run(run: AnalysisRun) -> str:
    """Request cancellation. Returns what actually happened.

    Cancellation is cooperative: a RUNNING run is flagged, and the engine notices
    between stages. Nothing is killed (docs/architecture.md §6.2).
    """
    if run.is_terminal:
        return "already_terminal"

    if run.status in (RunStatus.DRAFT, RunStatus.QUEUED):
        _finish(run, RunStatus.CANCELLED, stage="Cancelled", cancel_requested=True)
        return "cancelled"

    AnalysisRun.objects.filter(pk=run.pk).update(cancel_requested=True)
    run.cancel_requested = True
    logger.info("Cancellation requested for running run %s", run.id)
    return "cancellation_requested"


# --- Transitions ------------------------------------------------------------------


def _transition(run: AnalysisRun, status: str, **fields) -> None:
    """The only place ``AnalysisRun.status`` is ever written."""
    if not run.can_transition_to(status):
        raise InvalidTransition(f"Cannot move run {run.id} from {run.status} to {status}.")

    run.status = status
    for name, value in fields.items():
        setattr(run, name, value)

    run.save(update_fields=["status", "updated_at", *fields.keys()])


def _finish(run: AnalysisRun, status: str, **fields) -> None:
    """Transition into a terminal state, stamping ``finished_at``."""
    fields.setdefault("finished_at", timezone.now())
    _transition(run, status, **fields)
