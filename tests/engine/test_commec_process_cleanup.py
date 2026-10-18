"""Real process cleanup checks using sleeping mock children, never screening data."""

import errno
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
    except (FileNotFoundError, ProcessLookupError):
        # /proc can vanish before open (ENOENT) or during the read (ESRCH).
        return False
    return not any(line.startswith("State:") and "Z" in line for line in status.splitlines())


@pytest.mark.parametrize("error_number", [errno.ENOENT, errno.ESRCH])
def test_running_returns_false_when_process_vanishes(monkeypatch, error_number):
    def vanished(path):
        assert path == Path("/proc/12345/status")
        raise OSError(error_number, "process vanished during status read")

    monkeypatch.setattr(Path, "read_text", vanished)
    assert not _running(12345)


@pytest.mark.parametrize("error_number", [errno.EACCES, errno.EIO])
def test_running_preserves_unexpected_status_read_errors(monkeypatch, error_number):
    error = OSError(error_number, "unexpected status read failure")

    def unreadable(path):
        raise error

    monkeypatch.setattr(Path, "read_text", unreadable)
    with pytest.raises(OSError) as caught:
        _running(12345)
    assert caught.value is error


@pytest.mark.parametrize("state,expected", [("S (sleeping)", True), ("Z (zombie)", False)])
def test_running_distinguishes_live_and_zombie_processes(monkeypatch, state, expected):
    monkeypatch.setattr(Path, "read_text", lambda path: f"Name:\ttest-child\nState:\t{state}\n")
    assert _running(12345) is expected


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
