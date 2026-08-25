"""The run lifecycle in apps/analyses/services.py.

Rule 5 says every status transition happens here, so this is where the state machine is
actually exercised. The invariant under most scrutiny: **a run must never be left in
RUNNING**, whatever goes wrong.
"""

import pytest

from apps.analyses import services
from apps.analyses.models import AnalysisRun, RunStatus
from apps.analyses.services import InvalidTransition, cancel_run, execute_run, submit_run
from apps.analyses.tasks import run_analysis

# --- Happy path -------------------------------------------------------------------


def test_executing_a_queued_run_completes_it(run, media_root):
    execute_run(str(run.id))
    run.refresh_from_db()

    assert run.status == RunStatus.COMPLETED
    assert run.progress_pct == 100
    assert run.stage == "Completed"
    assert run.started_at is not None
    assert run.finished_at is not None
    assert run.engine_version.startswith("mock")


def test_a_completed_run_has_its_results_imported(run, media_root):
    execute_run(str(run.id))

    assert run.candidates.exists()
    assert run.artifacts.exists()
    assert run.candidates.filter(is_rejected=False, rank=1).exists()


def test_progress_is_written_to_the_database_as_it_goes(run, media_root):
    """This is what the polling endpoint reads while a run is in flight."""
    seen: list[tuple[int, str]] = []
    original = services._progress_callback

    def spy(run_obj):
        callback = original(run_obj)

        def wrapper(percent, stage):
            keep_going = callback(percent, stage)
            seen.append(
                AnalysisRun.objects.filter(pk=run_obj.pk)
                .values_list("progress_pct", "stage")
                .first()
            )
            return keep_going

        return wrapper

    services._progress_callback = spy
    try:
        execute_run(str(run.id))
    finally:
        services._progress_callback = original

    percentages = [percent for percent, _ in seen]
    assert percentages == sorted(percentages)
    assert percentages[-1] >= 90
    assert all(stage for _, stage in seen)


def test_the_task_is_a_thin_shell_over_the_service(run, media_root):
    run_analysis(str(run.id))
    run.refresh_from_db()

    assert run.status == RunStatus.COMPLETED


# --- Failure ----------------------------------------------------------------------


def test_an_engine_failure_lands_in_failed_with_a_readable_reason(run, media_root):
    run.params_snapshot = {"mock": {"fail": True, "fail_message": "Unsupported organism."}}
    run.save()

    execute_run(str(run.id))
    run.refresh_from_db()

    assert run.status == RunStatus.FAILED
    assert run.error_summary == "Unsupported organism."
    assert run.finished_at is not None
    assert not run.candidates.exists()


def test_a_failure_message_never_leaks_internals(run, media_root, settings):
    run.params_snapshot = {"mock": {"fail": True}}
    run.save()

    execute_run(str(run.id))
    run.refresh_from_db()

    assert "Traceback" not in run.error_summary
    assert str(settings.VAR_DIR) not in run.error_summary
    assert settings.SECRET_KEY not in run.error_summary


def test_an_unexpected_exception_still_reaches_a_terminal_state(run, media_root, monkeypatch):
    """A run stuck in RUNNING is the worst failure mode in the system."""

    def explode(*args, **kwargs):
        raise RuntimeError("something nobody anticipated")

    monkeypatch.setattr(services, "_execute", explode)

    execute_run(str(run.id))
    run.refresh_from_db()

    assert run.status == RunStatus.FAILED
    assert run.is_terminal
    assert "unexpectedly" in run.error_summary
    assert "something nobody anticipated" not in run.error_summary


def test_an_import_failure_is_reported_as_such(run, media_root, monkeypatch):
    """The science succeeded; only the import failed. Say so, so a retry re-imports
    rather than recomputing (design map 07)."""
    from apps.results.services import ResultImportError

    def broken_import(*args, **kwargs):
        raise ResultImportError("artifact checksum mismatch")

    monkeypatch.setattr(services, "import_job_result", broken_import)

    execute_run(str(run.id))
    run.refresh_from_db()

    assert run.status == RunStatus.FAILED
    assert "could not be imported" in run.error_summary


# --- Cancellation -----------------------------------------------------------------


def test_a_run_cancelled_before_it_starts_never_runs(run, media_root):
    cancel_run(run)
    run.refresh_from_db()
    assert run.status == RunStatus.CANCELLED

    execute_run(str(run.id))
    run.refresh_from_db()

    assert run.status == RunStatus.CANCELLED
    assert not run.candidates.exists()


def test_cancellation_requested_mid_run_stops_the_engine(run, media_root):
    """Cooperative: the flag is set by the web process and read between stages."""
    original = services._progress_callback

    def cancel_on_third_stage(run_obj):
        callback = original(run_obj)
        calls = {"n": 0}

        def wrapper(percent, stage):
            calls["n"] += 1
            if calls["n"] == 3:
                AnalysisRun.objects.filter(pk=run_obj.pk).update(cancel_requested=True)
            return callback(percent, stage)

        return wrapper

    services._progress_callback = cancel_on_third_stage
    try:
        execute_run(str(run.id))
    finally:
        services._progress_callback = original

    run.refresh_from_db()
    assert run.status == RunStatus.CANCELLED
    assert not run.candidates.exists()


def test_cancelling_a_terminal_run_changes_nothing(run, media_root):
    execute_run(str(run.id))
    run.refresh_from_db()

    assert cancel_run(run) == "already_terminal"
    run.refresh_from_db()
    assert run.status == RunStatus.COMPLETED


# --- Re-delivery ------------------------------------------------------------------


def test_re_running_a_completed_run_is_a_no_op(run, media_root):
    """A redelivered task must not recompute or duplicate results."""
    execute_run(str(run.id))
    run.refresh_from_db()
    before = list(run.candidates.values_list("engine_ref", flat=True))
    finished_at = run.finished_at

    execute_run(str(run.id))
    run.refresh_from_db()

    assert list(run.candidates.values_list("engine_ref", flat=True)) == before
    assert run.finished_at == finished_at


def test_executing_an_unknown_run_is_harmless(db, media_root):
    execute_run("00000000-0000-0000-0000-000000000000")


# --- Transitions ------------------------------------------------------------------


def test_an_illegal_transition_is_refused(run):
    run.status = RunStatus.COMPLETED
    with pytest.raises(InvalidTransition):
        services._transition(run, RunStatus.RUNNING)


def test_submit_run_refuses_a_dataset_from_another_project(project, dataset, user):
    from apps.analyses.services import RunError
    from apps.projects.models import Project

    other = Project.objects.create(owner=user, name="Elsewhere", organism="E. coli")
    with pytest.raises(RunError, match="different project"):
        submit_run(project=other, dataset=dataset, user=user)
