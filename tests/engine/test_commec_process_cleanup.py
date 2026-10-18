"""Real process cleanup checks using sleeping mock children, never screening data."""

import os
import signal
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path

import pytest

from engine.safety import AdapterStatus
from tests.engine.test_common_mechanism import (
    adapter as adapter,
)
from tests.engine.test_common_mechanism import (
    repin_mock_program,
)
from tests.engine.test_common_mechanism import (
    submission as submission,
)


def _running(pid):
    """An orphan may briefly be a zombie until the host's init reaps it."""
    try:
        status = Path(f"/proc/{pid}/status").read_text()
    except FileNotFoundError:
        return False
    return not any(line.startswith("State:") and "Z" in line for line in status.splitlines())


@pytest.mark.skipif(sys.platform != "linux", reason="Linux process-group/proc regression")
@pytest.mark.parametrize("outcome", ["nonzero", "timeout", "interrupt"])
def test_process_group_descendants_do_not_survive(
    adapter, submission, tmp_path, monkeypatch, outcome
):
    pidfile = tmp_path / "sleeping-child.pid"
    ending = "raise SystemExit(3)" if outcome == "nonzero" else "time.sleep(60)"
    program = f"""#!{sys.executable}
import pathlib, subprocess, sys, time
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
pathlib.Path({str(pidfile)!r}).write_text(str(child.pid))
{ending}
"""
    adapter = replace(repin_mock_program(adapter, program), timeout_seconds=1)
    real_wait = subprocess.Popen.wait
    interrupted = False

    def interrupt_once(process, *args, **kwargs):
        nonlocal interrupted
        if not interrupted:
            interrupted = True
            deadline = time.monotonic() + 3
            while not pidfile.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            assert pidfile.exists(), "mock child did not start"
            raise KeyboardInterrupt("synthetic worker interruption")
        return real_wait(process, *args, **kwargs)

    if outcome == "interrupt":
        monkeypatch.setattr(subprocess.Popen, "wait", interrupt_once)
    try:
        if outcome == "interrupt":
            with pytest.raises(KeyboardInterrupt, match="synthetic worker"):
                adapter.screen(submission)
        else:
            expected = AdapterStatus.FAILED if outcome == "nonzero" else AdapterStatus.TIMEOUT
            assert adapter.screen(submission).adapter_status == expected
        pid = int(pidfile.read_text())
        deadline = time.monotonic() + 3
        while _running(pid) and time.monotonic() < deadline:
            time.sleep(0.01)
        assert not _running(pid), "screening subprocess descendant survived cleanup"
    finally:
        # A regression must not leave the harmless sleep process behind either.
        if pidfile.exists():
            pid = int(pidfile.read_text())
            if _running(pid):
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
