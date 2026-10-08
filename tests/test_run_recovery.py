"""Fault injection proves dispatch/recovery/cancellation preserve durable states."""

import json
import uuid
from datetime import timedelta
from unittest.mock import Mock

import pytest
from django.core.cache import caches
from django.utils import timezone

from apps.analyses import services
from apps.analyses.models import AnalysisRun, RunStatus
from apps.results.services import ResultImportError
from engine.contract import SCHEMA_VERSION, SUCCEEDED, JobResult

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def isolated_staging(settings, tmp_path, media_root):
    settings.RUN_STAGING_ROOT = tmp_path / "retained-results"


def running(run, *, age=0):
    services._transition(
        run,
        RunStatus.RUNNING,
        execution_token=uuid.uuid4(),
        started_at=timezone.now() - timedelta(seconds=age),
    )
    return run


def result_for(run):
    return JobResult(
        schema_version=SCHEMA_VERSION,
        engine_version="test-runtime",
        status=SUCCEEDED,
        input_checksum=run.dataset.checksum_sha256,
        params=run.params_snapshot,
    )


def test_dispatch_failure_is_republished_from_durable_run(run, monkeypatch):
    publish = Mock(side_effect=RuntimeError("broker temporarily unavailable"))
    monkeypatch.setattr("django_q.tasks.async_task", publish)
    services._enqueue(run.pk)
    run.refresh_from_db()
    assert run.status == RunStatus.QUEUED
    assert run.enqueued_at is None
    assert "Dispatch pending" in run.stage
    publish.side_effect = None
    services.reconcile_runs()
    run.refresh_from_db()
    assert run.enqueued_at is not None
    assert publish.call_count == 2
    services.reconcile_runs()
    assert publish.call_count == 2


def test_stale_worker_cannot_undo_terminal_cancel(run):
    stale = AnalysisRun.objects.get(pk=run.pk)
    services.cancel_run(run)
    with pytest.raises(services.InvalidTransition):
        services._transition(stale, RunStatus.RUNNING)
    run.refresh_from_db()
    assert run.status == RunStatus.CANCELLED
    assert run.finished_at is not None


def test_stale_running_redelivery_fails_without_recomputing(run, monkeypatch):
    running(run, age=300)
    compute = Mock()
    monkeypatch.setattr(services, "_execute", compute)
    services.execute_run(str(run.pk))
    run.refresh_from_db()
    assert run.status == RunStatus.FAILED
    assert run.finished_at is not None
    compute.assert_not_called()


def test_live_running_redelivery_does_not_duplicate_work(run, monkeypatch):
    running(run, age=300)
    cache = caches["worker_status"]
    cache.set(services._heartbeat_key(run), timezone.now().timestamp(), 60)
    compute = Mock()
    monkeypatch.setattr(services, "_execute", compute)
    try:
        services.execute_run(str(run.pk))
        run.refresh_from_db()
        assert run.status == RunStatus.RUNNING
        compute.assert_not_called()
    finally:
        cache.delete(services._heartbeat_key(run))


def test_execution_deadline_expires_even_with_fresh_heartbeat(run, settings):
    settings.RUN_EXECUTION_TIMEOUT = 200
    running(run, age=300)
    cache = caches["worker_status"]
    cache.set(services._heartbeat_key(run), timezone.now().timestamp(), 60)
    try:
        assert services.reconcile_runs()["interrupted"] == 1
        run.refresh_from_db()
        assert run.status == RunStatus.FAILED
    finally:
        cache.delete(services._heartbeat_key(run))


def test_fatal_exit_records_terminal_failure_then_propagates(run, monkeypatch):
    monkeypatch.setattr(services, "_execute", Mock(side_effect=SystemExit(12)))
    with pytest.raises(SystemExit):
        services.execute_run(str(run.pk))
    run.refresh_from_db()
    assert run.status == RunStatus.FAILED
    assert run.finished_at is not None


def test_lost_lease_progress_cannot_overwrite_terminal_state(run):
    running(run)
    callback = services._progress_callback(run)
    assert callback(25, "Calculating")
    AnalysisRun.objects.filter(pk=run.pk).update(
        status=RunStatus.FAILED,
        stage="Worker interrupted",
        progress_pct=25,
    )
    assert not callback(99, "Late progress")
    run.refresh_from_db()
    assert run.stage == "Worker interrupted"
    assert run.progress_pct == 25


def test_cancel_after_engine_return_prevents_import(run, monkeypatch):
    def calculate(request, progress):
        AnalysisRun.objects.filter(pk=run.pk).update(cancel_requested=True)
        return result_for(run)

    monkeypatch.setattr(services, "load_engine", lambda _: Mock(run=calculate))
    services.execute_run(str(run.pk))
    run.refresh_from_db()
    assert run.status == RunStatus.CANCELLED
    assert not run.artifacts.exists()


def test_import_failure_retains_result_and_reimport_creates_new_run(run, monkeypatch):
    original_import = services.import_job_result
    computation = Mock(return_value=result_for(run))
    monkeypatch.setattr(services, "load_engine", lambda _: Mock(run=computation))
    monkeypatch.setattr(services, "import_job_result", Mock(side_effect=ResultImportError("disk")))
    services.execute_run(str(run.pk))
    run.refresh_from_db()
    original_finished = run.finished_at
    assert run.status == RunStatus.FAILED
    saved = services._staging_dir(run) / "result.json"
    assert saved.is_file()
    assert json.loads(saved.read_text())["status"] == SUCCEEDED
    monkeypatch.setattr(services, "import_job_result", original_import)
    recovered = services.retry_result_import(run)
    assert recovered.pk != run.pk
    assert recovered.status == RunStatus.COMPLETED
    assert recovered.created_by_id == run.created_by_id
    assert recovered.params_snapshot == run.params_snapshot
    assert any(str(run.pk) in warning for warning in recovered.warnings)
    assert computation.call_count == 1
    run.refresh_from_db()
    assert run.status == RunStatus.FAILED
    assert run.finished_at == original_finished


def test_completed_run_cannot_be_reimported(run):
    running(run)
    services._finish(run, RunStatus.COMPLETED)
    with pytest.raises(services.RunError, match="failed run"):
        services.retry_result_import(run)
