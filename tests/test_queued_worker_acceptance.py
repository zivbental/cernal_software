"""Separate-process queue acceptance, with no shared database, cache, media or ports."""

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
from django.core.management import get_commands
from django.core.management.base import CommandError

from apps.common.management.commands import qcluster
from apps.web.management.commands import devserver


def test_native_windows_commands_explain_supported_workflow(monkeypatch):
    assert get_commands()["qcluster"] == "apps.common"
    monkeypatch.setattr(qcluster.sys, "platform", "win32")
    monkeypatch.setattr(devserver, "IS_WINDOWS", True)
    launch = Mock()
    monkeypatch.setattr(devserver.subprocess, "Popen", launch)
    for command in (qcluster.Command(), devserver.Command()):
        with pytest.raises(CommandError, match=r"docs/windows-worker\.md"):
            command.handle()
    launch.assert_not_called()


@pytest.mark.skipif(sys.platform == "win32", reason="Real worker requires Linux/WSL2 fork")
def test_real_queue_worker_completes_local_engine_run(tmp_path):
    root = Path(__file__).resolve().parents[1]
    settings = tmp_path / "queue_acceptance_settings.py"
    settings.write_text(
        "from config.settings.dev import *\n"
        f"VAR_DIR = Path({str(tmp_path)!r})\n"
        "DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', "
        "'NAME': str(VAR_DIR / 'queue.sqlite3'), 'OPTIONS': {'timeout': 30}}}\n"
        "MEDIA_ROOT = VAR_DIR / 'media'\n"
        "RUN_STAGING_ROOT = VAR_DIR / 'staging'\n"
        "CACHES = {'default': {'BACKEND': 'django.core.cache.backends.db.DatabaseCache', "
        "'LOCATION': 'cernal_cache_table'}, 'worker_status': "
        "{'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache', "
        "'LOCATION': str(VAR_DIR / 'worker-status')}}\n"
        "Q_CLUSTER = {**Q_CLUSTER, 'name': 'isolated-acceptance', 'sync': False}\n"
        "REVIEWER_LOGIN_ENABLED = False\n"
    )
    env = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "queue_acceptance_settings",
        "PYTHONPATH": os.pathsep.join([str(tmp_path), str(root / "src")]),
    }
    # This process submits through the application service, then starts a real
    # qcluster, and inspects durable results. No direct execute_run/engine call.
    scenario = r"""
import json
import subprocess
import sys
import time
import django
django.setup()
from django.core.management import call_command
from django.contrib.auth import get_user_model
from django_q.models import OrmQ, Success
from apps.analyses.models import RunStatus
from apps.analyses.services import submit_run
from apps.common.checksums import sha256_file
from apps.web.management.commands.devserver import stop_process

call_command("migrate", interactive=False, verbosity=0)
user = get_user_model().objects.create_user(username="queue-acceptance")
run, created = submit_run(
    user=user, input_mode="direct", organism="ecoli",
    trigger_sequence="AACUUGUUGGCCCAGUGUGAAUCGCUUAAGGGUUAA",
    params={"payload": {"outputs": ["other"], "custom_sequence": "ATGGCTGCTTAA"},
            "budget": {"max_designs": 3}},
    gate_families=["toehold"], seed=42,
)
assert created and run.status == RunStatus.QUEUED
assert OrmQ.objects.count() == 1, "Submission must reach the durable queue"
assert not run.candidates.exists(), "Nothing may execute before the worker starts"
worker = subprocess.Popen(
    [sys.executable, "manage.py", "qcluster"], start_new_session=True
)
try:
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        assert worker.poll() is None, "qcluster exited before acceptance completed"
        run.refresh_from_db()
        if run.status == RunStatus.FAILED:
            raise AssertionError(run.error_summary)
        if run.status == RunStatus.COMPLETED and Success.objects.exists():
            break
        time.sleep(0.25)
    else:
        raise AssertionError(f"Worker timeout: {run.status}: {run.stage}")
    assert run.engine_version.startswith("local-")
    assert run.candidates.exists()
    assert run.artifacts.exists()
    for artifact in run.artifacts.all():
        assert sha256_file(artifact.file.path) == artifact.checksum_sha256
    assert OrmQ.objects.count() == 0
    print(json.dumps({"status": run.status, "engine": run.engine_version,
                      "candidates": run.candidates.count(),
                      "artifacts": run.artifacts.count(), "queue_empty": True}))
finally:
    stop_process(worker)
"""
    result = subprocess.run(
        [sys.executable, "-c", scenario],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=240,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"queue_empty": true' in result.stdout
    print(result.stdout)
