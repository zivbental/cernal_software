"""The analysis run lifecycle.

**Every status transition in the system happens here** (rule 5). Views parse and
authorize, tasks are thin shells, this module decides.

The invariant that matters most: a run must never be left in RUNNING. Every path out of
``execute_run`` reaches a terminal state, including unexpected exceptions.
"""

import json
import logging
import shutil
import threading
import uuid
from contextlib import contextmanager
from dataclasses import asdict, replace
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import caches
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from apps.analyses.models import AnalysisRun, InputMode, RunStatus
from apps.results.services import ResultImportError, import_job_result
from engine.client import (
    load_engine,
    lookup_reference_gene,
    normalize_trigger_sequence,
    validate_job_configuration,
)
from engine.contract import (
    CANCELLED,
    SCHEMA_VERSION,
    SUCCEEDED,
    ArtifactRef,
    CandidateResult,
    JobRequest,
    JobResult,
    MetricValue,
)

logger = logging.getLogger(__name__)

#: How often the engine's progress callback writes to the database. The mock reports
#: eight times per run; a real pipeline may report far more often.
_PROGRESS_STEP = 1


class RunError(Exception):
    """A run could not be submitted or acted upon."""


class SubmissionConflict(RunError):
    """An idempotency key was reused with different immutable inputs."""


class RunQuotaExceeded(RunError):
    """The account or credential active-run ceiling has been reached."""


class InvalidTransition(RunError):
    """An illegal status change was attempted."""


class _ImportCancelled(RunError):
    """Roll back imported records and files before acknowledging cancellation."""


# --- Submission -------------------------------------------------------------------


@transaction.atomic
def submit_run(
    *,
    user,
    dataset=None,
    input_mode: str = InputMode.DE,
    trigger_sequence: str = "",
    organism: str = "",
    params: dict | None = None,
    gate_families: list[str] | None = None,
    scoring_profile: str = "default",
    seed: int | None = None,
    idempotency_key: str | None = None,
    max_concurrent_runs: int | None = None,
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
        if not dataset.is_usable:
            raise RunError("This dataset did not pass validation and cannot be analysed.")
    elif input_mode == InputMode.DIRECT:
        dataset = None
    elif input_mode == InputMode.GENE:
        dataset = None
        target = (params or {}).get("target_gene") or {}
        if not isinstance(target, dict):
            raise RunError("target_gene must contain a reference gene ID or symbol.")
        identifier = target.get("gene_id", "")
        if not isinstance(identifier, str) or not identifier.strip():
            raise RunError("Choose a reference gene ID or symbol for a gene-input run.")
        try:
            reference = lookup_reference_gene((params or {}).get("organism", organism), identifier)
        except ValueError as exc:
            raise RunError(str(exc)) from exc
        trigger_sequence = reference["sequence"]
        params = {
            **(params or {}),
            "gene_reference": {key: value for key, value in reference.items() if key != "sequence"},
        }
    else:
        raise RunError(f"Unknown input mode '{input_mode}'.")

    configured_host = (params or {}).get("host") or (params or {}).get("organism")
    if configured_host and organism and configured_host != organism:
        raise RunError("The organism and params host/organism must agree.")
    try:
        params = validate_job_configuration(
            params or {},
            gate_families or ["toehold"],
            scoring_profile,
            input_mode,
            trigger_sequence,
            organism,
        )
    except ValueError as exc:
        raise RunError(str(exc)) from exc

    try:
        params = json.loads(json.dumps(params, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise RunError("Configuration must contain finite JSON values.") from exc

    key = idempotency_key or uuid.uuid4().hex
    if not isinstance(key, str) or not key.strip() or len(key) > 64:
        raise RunError("idempotency_key must contain 1 to 64 characters.")
    capabilities = load_engine(settings.CERNAL_ENGINE).capabilities()
    families = gate_families or ["toehold"]
    _validate_against_capabilities(families, scoring_profile, capabilities)

    # Serialize submissions for this account on PostgreSQL and acquire SQLite's write
    # reservation before reading the count. The update intentionally leaves the value intact.
    users = get_user_model().objects
    users.filter(pk=user.pk).update(last_login=F("last_login"))
    users.select_for_update().get(pk=user.pk)
    existing = AnalysisRun.objects.filter(created_by=user, idempotency_key=key).first()
    if existing is not None:
        existing_checksum = existing.dataset.checksum_sha256 if existing.dataset_id else None
        incoming_checksum = dataset.checksum_sha256 if dataset else None
        identity = (
            input_mode,
            trigger_sequence,
            organism,
            dict(params or {}),
            families,
            scoring_profile,
            seed,
            incoming_checksum,
        )
        recorded = (
            existing.input_mode,
            existing.trigger_sequence,
            existing.organism,
            existing.params_snapshot,
            existing.gate_families,
            existing.scoring_profile,
            existing.seed,
            existing_checksum,
        )
        if identity != recorded:
            raise SubmissionConflict("This idempotency key was already used with different inputs.")
        logger.info("Idempotent resubmission of run %s", existing.id)
        return existing, False

    account_limit = getattr(settings, "MAX_ACTIVE_RUNS_PER_ACCOUNT", 2)
    effective_limit = (
        min(account_limit, max_concurrent_runs) if max_concurrent_runs else account_limit
    )
    active = AnalysisRun.objects.filter(
        created_by=user, status__in=[RunStatus.QUEUED, RunStatus.RUNNING]
    ).count()
    if active >= effective_limit:
        raise RunQuotaExceeded(
            f"{active} run(s) already active; this account allows {effective_limit}."
        )

    run = AnalysisRun.objects.create(
        input_mode=input_mode,
        dataset=dataset,
        trigger_sequence=trigger_sequence,
        organism=organism,
        created_by=user,
        idempotency_key=key,
        # The snapshot is what makes a run immutable: later edits to its configuration
        # cannot change what this run computed (rule 7).
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

    logger.info("Run %s submitted by %s", run.id, user)
    return run, True


#: Minimum length the Platform will accept before bothering the engine.
MIN_TRIGGER_NT = 20


def _clean_trigger(sequence: str) -> str:
    """Normalize a pasted mRNA. Rejects anything that is not plainly a sequence."""
    if not sequence.strip():
        raise RunError("Paste the trigger mRNA sequence, or switch to dataset upload.")
    try:
        cleaned = normalize_trigger_sequence(sequence)
    except ValueError as exc:
        raise RunError(str(exc)) from exc
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
    """Publish a durable QUEUED row; reconciliation retries failed publication."""
    from django_q.tasks import async_task

    if not AnalysisRun.objects.filter(pk=run_id, status=RunStatus.QUEUED).exists():
        return
    try:
        async_task(
            "apps.analyses.tasks.run_analysis",
            str(run_id),
            task_name=f"run-{str(run_id)[:8]}",
        )
    except Exception:
        logger.exception("Queue publication failed for run %s; reconciliation will retry", run_id)
        AnalysisRun.objects.filter(pk=run_id, status=RunStatus.QUEUED).update(
            stage="Dispatch pending; retrying",
            enqueued_at=None,
        )
    else:
        AnalysisRun.objects.filter(pk=run_id, status=RunStatus.QUEUED).update(
            enqueued_at=timezone.now(),
            stage="Queued",
        )


# --- Execution --------------------------------------------------------------------


def execute_run(run_id: str) -> None:
    """Run one analysis to a terminal state.

    Called by the worker task. Safe to re-run: a run that is already terminal is a
    no-op, so a redelivered task cannot recompute or duplicate results.
    """
    run = AnalysisRun.objects.filter(pk=run_id).select_related("dataset").first()
    if run is None:
        logger.warning("execute_run called for unknown run %s", run_id)
        return

    if run.status == RunStatus.RUNNING:
        _reconcile_running(run)
        return

    if run.is_terminal:
        logger.info("Run %s is already %s; nothing to do", run.id, run.status)
        return

    if run.cancel_requested:
        _finish(run, RunStatus.CANCELLED, stage="Cancelled")
        return

    try:
        _transition(
            run,
            RunStatus.RUNNING,
            stage="Starting",
            started_at=timezone.now(),
            execution_token=uuid.uuid4(),
        )
    except InvalidTransition:
        logger.warning("Run %s could not start from %s", run.id, run.status)
        return

    try:
        with _run_heartbeat(run):
            _execute(run)
    except BaseException as exc:
        # The last line of defence. A run stuck in RUNNING is the worst failure mode in
        # the system, so even a programming error must land somewhere terminal.
        logger.exception("Run %s failed unexpectedly", run.id)
        try:
            _finish(
                run,
                RunStatus.FAILED,
                stage="Interrupted" if not isinstance(exc, Exception) else "Failed",
                error_summary=(
                    "The analysis failed unexpectedly. You can submit a new run; "
                    "diagnostics were recorded."
                ),
            )
        except InvalidTransition:
            logger.info("Run %s lost its execution lease or already finished", run.id)
        if not isinstance(exc, Exception):
            raise


def _execute(run: AnalysisRun) -> None:
    engine = load_engine(settings.CERNAL_ENGINE)

    # Keep successful science until import is acknowledged. Failed import can be
    # retried into a new run without rewriting a terminal run's history.
    output_dir = _staging_dir(run)
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        request = JobRequest(
            schema_version=SCHEMA_VERSION,
            run_id=str(run.id),
            idempotency_key=run.idempotency_key,
            input_mode=run.input_mode,
            trigger_sequence=run.trigger_sequence,
            input_path=run.dataset.file.path if run.dataset else "",
            input_checksum=run.dataset.checksum_sha256 if run.dataset else "",
            organism=run.organism,
            params=run.params_snapshot,
            gate_families=run.gate_families,
            scoring_profile=run.scoring_profile,
            seed=run.seed,
            output_dir=str(output_dir),
        )

        result = engine.run(request, _progress_callback(run))
        if not _owns_execution(run):
            return
        if AnalysisRun.objects.filter(pk=run.pk, cancel_requested=True).exists():
            _finish(run, RunStatus.CANCELLED, stage="Cancelled")
            return

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

        manifest = output_dir / "result.json"
        temporary = manifest.with_suffix(".tmp")
        temporary.write_text(json.dumps(asdict(result), allow_nan=False), encoding="utf-8")
        temporary.replace(manifest)
        try:
            _import_and_complete(run, result, output_dir)
        except _ImportCancelled:
            _finish(run, RunStatus.CANCELLED, stage="Cancelled", cancel_requested=True)
            return
        except ResultImportError as exc:
            # The science succeeded; only the import failed. Say so plainly, so a retry
            # can re-import rather than recompute (design map 07).
            logger.error("Result import failed for run %s: %s", run.id, exc)
            _finish(
                run,
                RunStatus.FAILED,
                stage="Import failed; result retained",
                engine_version=result.engine_version,
                error_summary=(
                    "The results could not be imported. Computed results are retained for an "
                    "operator to retry import without rerunning the analysis."
                ),
            )
            return

    finally:
        current = AnalysisRun.objects.filter(pk=run.pk).values_list("status", flat=True).first()
        if current in (RunStatus.COMPLETED, RunStatus.CANCELLED):
            shutil.rmtree(output_dir, ignore_errors=True)


def _owns_execution(run):
    return AnalysisRun.objects.filter(
        pk=run.pk,
        status=RunStatus.RUNNING,
        execution_token=run.execution_token,
    ).exists()


def _import_and_complete(run, result, output_dir):
    def prepare():
        # Take the write lock before reading cancellation. The importer's transaction
        # owns both finalization and commit so storage cleanup also covers their errors.
        active = AnalysisRun.objects.filter(
            pk=run.pk, status=RunStatus.RUNNING, execution_token=run.execution_token
        )
        if not active.update(updated_at=timezone.now()):
            raise InvalidTransition("The run no longer owns its execution lease.")
        if active.filter(cancel_requested=True).exists():
            raise _ImportCancelled()

    def finalize():
        if AnalysisRun.objects.filter(pk=run.pk, cancel_requested=True).exists():
            raise _ImportCancelled()
        _finish(
            run,
            RunStatus.COMPLETED,
            stage="Completed",
            progress_pct=100,
            engine_version=result.engine_version,
            warnings=list(result.warnings),
        )

    try:
        import_job_result(run, result, output_dir, prepare=prepare, finalize=finalize)
    except BaseException:
        # Database rollback does not restore this Python object's attributes. Retain
        # the original lease token; later failure/cancellation still uses its CAS.
        run.status = RunStatus.RUNNING
        raise
    logger.info("Run %s completed with %d candidates", run.id, len(result.candidates))


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
            updated = AnalysisRun.objects.filter(
                pk=run.pk,
                status=RunStatus.RUNNING,
                execution_token=run.execution_token,
                cancel_requested=False,
            ).update(progress_pct=percent, stage=stage, updated_at=timezone.now())
            if not updated:
                return False
            run.progress_pct = percent
            run.stage = stage

        return AnalysisRun.objects.filter(
            pk=run.pk,
            status=RunStatus.RUNNING,
            execution_token=run.execution_token,
            cancel_requested=False,
        ).exists()

    return on_progress


# --- Cancellation -----------------------------------------------------------------


def cancel_run(run: AnalysisRun) -> str:
    """Request cancellation. Returns what actually happened.

    Cancellation is cooperative: a RUNNING run is flagged, and the engine notices
    between stages. Nothing is killed (docs/architecture.md §6.2).
    """
    run.refresh_from_db()
    if run.is_terminal:
        return "already_terminal"

    if run.status in (RunStatus.DRAFT, RunStatus.QUEUED):
        try:
            _finish(run, RunStatus.CANCELLED, stage="Cancelled", cancel_requested=True)
        except InvalidTransition:
            return cancel_run(run)
        return "cancelled"

    if not AnalysisRun.objects.filter(pk=run.pk, status=RunStatus.RUNNING).update(
        cancel_requested=True,
        updated_at=timezone.now(),
    ):
        return "already_terminal"
    run.cancel_requested = True
    logger.info("Cancellation requested for running run %s", run.id)
    return "cancellation_requested"


# --- Transitions ------------------------------------------------------------------


def _transition(run: AnalysisRun, status: str, **fields) -> None:
    """The only place ``AnalysisRun.status`` is ever written."""
    if not run.can_transition_to(status):
        raise InvalidTransition(f"Cannot move run {run.id} from {run.status} to {status}.")

    expected_status = run.status
    query = AnalysisRun.objects.filter(pk=run.pk, status=expected_status)
    if expected_status == RunStatus.RUNNING:
        query = query.filter(execution_token=run.execution_token)
    if status == RunStatus.COMPLETED:
        query = query.filter(cancel_requested=False)
    now = timezone.now()
    if not query.update(status=status, updated_at=now, **fields):
        raise InvalidTransition(f"Run {run.id} changed before the transition could be applied.")
    run.status = status
    run.updated_at = now
    for name, value in fields.items():
        setattr(run, name, value)


def _finish(run: AnalysisRun, status: str, **fields) -> None:
    """Transition into a terminal state, stamping ``finished_at``."""
    fields.setdefault("finished_at", timezone.now())
    _transition(run, status, **fields)


def _heartbeat_key(run):
    return f"run-heartbeat:{run.pk}:{run.execution_token}"


@contextmanager
def _run_heartbeat(run):
    """An independent liveness signal while expensive science/import holds the DB."""
    cache = caches["worker_status"]
    key = _heartbeat_key(run)
    stopped = threading.Event()

    def beat():
        cache.set(key, timezone.now().timestamp(), timeout=settings.RUN_HEARTBEAT_TIMEOUT * 2)

    def maintain():
        while not stopped.wait(settings.RUN_HEARTBEAT_SECONDS):
            try:
                beat()
            except Exception:
                logger.exception("Run heartbeat could not be stored for %s", run.id)

    beat()
    thread = threading.Thread(target=maintain, daemon=True, name=f"run-heartbeat-{run.pk}")
    thread.start()
    try:
        yield
    finally:
        stopped.set()
        thread.join(timeout=1)
        cache.delete(key)


def _reconcile_running(run):
    now = timezone.now()
    started = run.started_at or run.updated_at
    last = caches["worker_status"].get(_heartbeat_key(run)) or started.timestamp()
    expired = (now - started).total_seconds() > settings.RUN_EXECUTION_TIMEOUT
    stale = now.timestamp() - last > settings.RUN_HEARTBEAT_TIMEOUT
    if not (expired or stale):
        return False
    try:
        with transaction.atomic():
            active = AnalysisRun.objects.filter(
                pk=run.pk, status=RunStatus.RUNNING, execution_token=run.execution_token
            )
            if not active.update(updated_at=now):
                return False
            # Cancellation may have arrived after the reconciler enumerated this run.
            # Read it only after acquiring the write lock that serializes finalization.
            cancelled = active.values_list("cancel_requested", flat=True).get()
            last = caches["worker_status"].get(_heartbeat_key(run)) or started.timestamp()
            if not expired and now.timestamp() - last <= settings.RUN_HEARTBEAT_TIMEOUT:
                return False
            _finish(
                run,
                RunStatus.CANCELLED if cancelled else RunStatus.FAILED,
                stage="Cancelled" if cancelled else "Worker interrupted",
                error_summary=(
                    "The worker stopped responding or exceeded its runtime limit. "
                    "This run was interrupted; submit a new run to retry."
                ),
            )
    except InvalidTransition:
        return False
    return True


def reconcile_runs():
    """Recover dispatch gaps and terminate expired leases; never recompute silently."""
    cutoff = timezone.now() - timedelta(seconds=settings.RUN_QUEUE_REPUBLISH_SECONDS)
    queued = AnalysisRun.objects.filter(status=RunStatus.QUEUED).filter(
        Q(enqueued_at__isnull=True) | Q(enqueued_at__lt=cutoff)
    )
    published = 0
    for run_id in queued.values_list("pk", flat=True).iterator():
        _enqueue(run_id)
        published += 1
    interrupted = sum(
        _reconcile_running(run)
        for run in AnalysisRun.objects.filter(
            status=RunStatus.RUNNING,
        ).iterator()
    )
    return {"dispatch_attempts": published, "interrupted": interrupted}


def _staging_dir(run):
    return Path(settings.RUN_STAGING_ROOT) / str(run.pk) / str(run.execution_token)


def retry_result_import(source):
    """Create a new, traceable result-import attempt; preserve the failed run unchanged."""
    source.refresh_from_db()
    if source.status != RunStatus.FAILED:
        raise RunError("Only a failed run with retained results can be re-imported.")
    path = _staging_dir(source)
    try:
        raw = json.loads((path / "result.json").read_text(encoding="utf-8"))
        raw["candidates"] = [
            CandidateResult(
                **{
                    **item,
                    "metrics": [MetricValue(**m) for m in item.get("metrics", [])],
                }
            )
            for item in raw.get("candidates", [])
        ]
        raw["artifacts"] = [ArtifactRef(**item) for item in raw.get("artifacts", [])]
        result = JobResult(**raw)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise RunError("No readable retained result is available for this run.") from exc
    if result.status != SUCCEEDED:
        raise RunError("Only a successful computation can be imported again.")
    result = replace(
        result,
        warnings=[
            *result.warnings,
            f"Results re-imported from failed run {source.pk}; science was not recomputed.",
        ],
    )
    new = AnalysisRun.objects.create(
        created_by=source.created_by,
        input_mode=source.input_mode,
        dataset=source.dataset,
        trigger_sequence=source.trigger_sequence,
        organism=source.organism,
        params_snapshot=source.params_snapshot,
        gate_families=source.gate_families,
        scoring_profile=source.scoring_profile,
        seed=source.seed,
        idempotency_key=f"import-{source.pk.hex}-{uuid.uuid4().hex[:16]}",
        status=RunStatus.QUEUED,
        submitted_at=timezone.now(),
    )
    _transition(new, RunStatus.RUNNING, started_at=timezone.now(), execution_token=uuid.uuid4())
    target = _staging_dir(new)
    try:
        with _run_heartbeat(new):
            shutil.copytree(path, target)
            (target / "result.json").write_text(
                json.dumps(asdict(result), allow_nan=False), encoding="utf-8"
            )
            _import_and_complete(new, result, target)
    except BaseException:
        try:
            _finish(
                new,
                RunStatus.FAILED,
                stage="Import retry failed; result retained",
                error_summary="Import retry failed. Review the retained output and operator logs.",
            )
        except InvalidTransition:
            logger.info("Re-import attempt %s is already terminal or lost its lease", new.pk)
        raise
    shutil.rmtree(target, ignore_errors=True)
    return new
