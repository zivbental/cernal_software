"""Staging cleanup preserves failed science by default and never removes active work."""

import io
import json
import os
import time
import uuid

from django.core.management import call_command

from apps.analyses.models import RunStatus


def retained(run, settings, tmp_path, status):
    settings.RUN_STAGING_ROOT = tmp_path / "run-staging"
    run.status = status
    run.execution_token = uuid.uuid4()
    run.save(update_fields=["status", "execution_token"])
    lease = settings.RUN_STAGING_ROOT / str(run.pk) / str(run.execution_token)
    lease.mkdir(parents=True)
    result = lease / "result.json"
    result.write_text("retained science")
    old = time.time() - 40 * 86400
    for path in [result, lease]:
        os.utime(path, (old, old))
    return lease


def test_staging_cleanup_defaults_to_dry_run_and_protects_failed_results(run, settings, tmp_path):
    lease = retained(run, settings, tmp_path, RunStatus.FAILED)
    output = io.StringIO()
    call_command("cleanup_staging", stdout=output)
    assert json.loads(output.getvalue())["staging_directories"] == []
    call_command("cleanup_staging", include_failed=True, stdout=io.StringIO())
    assert lease.exists()
    call_command("cleanup_staging", include_failed=True, apply=True, stdout=io.StringIO())
    assert not lease.exists()


def test_staging_cleanup_removes_old_completed_work_only_when_applied(run, settings, tmp_path):
    lease = retained(run, settings, tmp_path, RunStatus.COMPLETED)
    output = io.StringIO()
    call_command("cleanup_staging", stdout=output)
    assert json.loads(output.getvalue())["staging_directories"]
    assert lease.exists()
    call_command("cleanup_staging", apply=True, stdout=io.StringIO())
    assert not lease.exists()


def test_staging_cleanup_never_removes_running_unknown_or_mismatched_leases(
    run, settings, tmp_path
):
    lease = retained(run, settings, tmp_path, RunStatus.RUNNING)
    unknown = settings.RUN_STAGING_ROOT / str(uuid.uuid4()) / str(uuid.uuid4())
    unknown.mkdir(parents=True)
    old = time.time() - 40 * 86400
    os.utime(unknown, (old, old))
    call_command("cleanup_staging", apply=True, include_failed=True, stdout=io.StringIO())
    assert lease.exists()
    assert unknown.exists()
    run.status = RunStatus.COMPLETED
    run.execution_token = uuid.uuid4()
    run.save(update_fields=["status", "execution_token"])
    call_command("cleanup_staging", apply=True, include_failed=True, stdout=io.StringIO())
    assert lease.exists()
