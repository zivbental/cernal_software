"""Actual process death against a private SQLite DB; no live user worker is touched."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path


def test_killed_execution_is_reconciled_without_duplicate_computation(tmp_path):
    root = Path(__file__).resolve().parents[1]
    config = tmp_path / "process_settings.py"
    database = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": str(tmp_path / "test.db"),
        }
    }
    cache_settings = {
        "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
        "worker_status": {
            "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
            "LOCATION": str(tmp_path / "cache"),
        },
    }
    config.write_text(
        "from config.settings.dev import *\n"
        f"DATABASES = {database!r}\n"
        f"CACHES = {cache_settings!r}\n"
        "RUN_HEARTBEAT_SECONDS = 1\nRUN_HEARTBEAT_TIMEOUT = 30\n"
    )
    env = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "process_settings",
        "PYTHONPATH": os.pathsep.join((str(tmp_path), str(root / "src"))),
    }
    ready = tmp_path / "ready.json"
    program = f"""
import django, time, json
from pathlib import Path
django.setup()
from django.core.management import call_command
from django.contrib.auth import get_user_model
from apps.analyses import services
from apps.analyses.models import AnalysisRun, RunStatus
call_command('migrate', verbosity=0)
user = get_user_model().objects.create_user(username='process-test')
run = AnalysisRun.objects.create(created_by=user, input_mode='direct',
    trigger_sequence='ACGU' * 8, idempotency_key='isolated-process-test',
    status=RunStatus.QUEUED)
def work(current):
    Path({str(ready)!r}).write_text(json.dumps({{'id': str(current.pk)}}))
    while True:
        time.sleep(0.1)
services._execute = work
services.execute_run(str(run.pk))
"""
    process = subprocess.Popen(
        [sys.executable, "-c", program],
        env=env,
        cwd=root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 30
        while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        assert ready.exists(), (
            process.stderr.read().decode()
            if process.poll() is not None
            else "No worker ready signal"
        )
        run_id = json.loads(ready.read_text())["id"]
        common = (
            "import django; django.setup(); from apps.analyses import services; "
            "from apps.analyses.models import AnalysisRun; "
        )
        duplicate = subprocess.run(
            [
                sys.executable,
                "-c",
                common
                + f"services.execute_run('{run_id}'); "
                + f"print(AnalysisRun.objects.get(pk='{run_id}').status)",
            ],
            env=env,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        )
        assert duplicate.stdout.strip() == "RUNNING"
        process.kill()
        process.wait(timeout=10)
        recovered = subprocess.run(
            [
                sys.executable,
                "-c",
                common
                + "from django.conf import settings; settings.RUN_HEARTBEAT_TIMEOUT = 0; "
                + "services.reconcile_runs(); "
                + f"run = AnalysisRun.objects.get(pk='{run_id}'); "
                + "print(run.status, run.finished_at is not None)",
            ],
            env=env,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        )
        assert recovered.stdout.strip() == "FAILED True"
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)
        process.stderr.close()
