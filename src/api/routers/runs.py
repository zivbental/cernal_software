"""Submitting, polling and cancelling analysis runs."""

from uuid import UUID

from ninja import Router, Status

from api.auth import get_owned, owned_queryset
from api.errors import ValidationFailed
from api.schemas import CancelOut, RunCounts, RunIn, RunOut, RunStatusOut
from api.security import enforce_concurrency_ceiling, require_scope
from apps.accounts.models import ApiKeyScope
from apps.analyses.models import AnalysisRun, InputMode
from apps.analyses.services import RunError, cancel_run, submit_run
from apps.datasets.models import Dataset
from apps.projects.models import Project

router = Router()


@router.get("/runs", response=list[RunOut])
def list_all_runs(request, limit: int = 20):
    """Recent runs across every project — what "My Circuits" shows first."""
    return (
        owned_queryset(AnalysisRun, request.user)
        .select_related("project")
        .order_by("-created_at")[: max(1, min(limit, 100))]
    )


@router.get("/projects/{project_id}/runs", response=list[RunOut])
def list_runs(request, project_id: UUID):
    get_owned(Project, project_id, request.user)
    return owned_queryset(AnalysisRun, request.user).filter(project_id=project_id)


@router.post("/projects/{project_id}/runs", response={202: RunOut})
def create_run(request, project_id: UUID, payload: RunIn):
    """Freeze a submission and queue it.

    Returns 202: the work has been accepted, not completed. Poll ``GET /api/runs/{id}``.
    A repeated ``idempotency_key`` returns the existing run rather than launching a
    second computation.

    A ``design``-scoped key is required (ADR 0006, docs/public-api.md §6) — this and
    ``POST /api/design`` are the two submission paths, so a ``read``-scoped key must not
    reach either. The per-key concurrency ceiling applies here too, for the same reason.
    """
    require_scope(request, ApiKeyScope.DESIGN)
    enforce_concurrency_ceiling(request)
    project = get_owned(Project, project_id, request.user)

    dataset = None
    if payload.input_mode == InputMode.DE:
        if payload.dataset_id is None:
            raise ValidationFailed("A dataset is required for a differential-expression run.")
        dataset = get_owned(Dataset, payload.dataset_id, request.user)

    try:
        run, _created = submit_run(
            project=project,
            user=request.user,
            dataset=dataset,
            input_mode=payload.input_mode,
            trigger_sequence=payload.trigger_sequence,
            params=payload.params,
            gate_families=payload.gate_families,
            scoring_profile=payload.scoring_profile,
            seed=payload.seed,
            idempotency_key=payload.idempotency_key,
        )
    except RunError as exc:
        raise ValidationFailed(str(exc)) from None

    return Status(202, run)


@router.get("/runs/{run_id}", response=RunStatusOut)
def get_run_status(request, run_id: UUID):
    """The polling endpoint (§7.1). Kept cheap — no joins across candidates."""
    run = get_owned(AnalysisRun, run_id, request.user)

    return RunStatusOut(
        id=run.id,
        status=run.status,
        stage=run.stage,
        progress_pct=run.progress_pct,
        error_summary=run.error_summary or None,
        warnings=run.warnings or [],
        submitted_at=run.submitted_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        counts=RunCounts(
            candidates=run.candidates.count(),
            artifacts=run.artifacts.count(),
        ),
    )


@router.get("/runs/{run_id}/detail", response=RunOut)
def get_run(request, run_id: UUID):
    """The full run record, including its immutable configuration snapshot."""
    return get_owned(AnalysisRun, run_id, request.user)


@router.post("/runs/{run_id}/cancel", response=CancelOut)
def cancel(request, run_id: UUID):
    """Request cancellation.

    Cooperative: a running analysis is flagged and stops between stages. The response
    distinguishes what actually happened, as design map 08 requires.
    """
    require_scope(request, ApiKeyScope.DESIGN)
    run = get_owned(AnalysisRun, run_id, request.user)
    outcome = cancel_run(run)
    run.refresh_from_db()

    return CancelOut(id=run.id, status=run.status, outcome=outcome)
