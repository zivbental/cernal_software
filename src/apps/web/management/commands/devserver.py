"""Supervise the development web server and its background worker together."""

import fcntl
import os
import signal
import subprocess
import sys
import time

from django.conf import settings
from django.contrib.staticfiles.management.commands.runserver import Command as RunserverCommand
from django.core.management.base import CommandError
from django.db import DatabaseError

from apps.analyses.worker import worker_available


def stop_process(process):
    if process is None or process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        process.wait()
        return
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()


class Command(RunserverCommand):
    help = "Run the development server with an automatically restarted analysis worker."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("devserver is only available with development settings.")
        with (settings.VAR_DIR / "devserver.lock").open("w") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise CommandError("A supervised development server is already running.") from exc
            previous_handler = signal.signal(signal.SIGTERM, self.terminate)
            try:
                self.supervise(options)
            finally:
                signal.signal(signal.SIGTERM, previous_handler)

    @staticmethod
    def terminate(signum, frame):
        raise KeyboardInterrupt

    def supervise(self, options):
        env = dict(
            os.environ,
            CERNAL_SUPERVISED_CHILD="1",
            DJANGO_SETTINGS_MODULE=settings.SETTINGS_MODULE,
        )
        base = [sys.executable, str(settings.BASE_DIR / "manage.py")]
        server_args = [options.get("addrport") or "8000"]
        for key, flag in (("use_reloader", "--noreload"), ("use_threading", "--nothreading")):
            if not options.get(key, True):
                server_args.append(flag)
        if options.get("use_ipv6"):
            server_args.append("--ipv6")
        for key, flag in (("use_static_handler", "--nostatic"), ("insecure_serving", "--insecure")):
            if options.get(key) == (key == "insecure_serving"):
                server_args.append(flag)
        server = subprocess.Popen(
            [*base, "runserver", *server_args], env=env, start_new_session=True
        )
        worker = None
        last_healthy = time.monotonic()
        try:
            while server.poll() is None:
                if worker is not None and worker.poll() is not None:
                    self.stderr.write("Analysis worker exited; restarting it.")
                    worker = None
                try:
                    healthy = worker_available()
                except DatabaseError:
                    # An unavailable status store is not proof the worker died.
                    self.stderr.write("Worker status temporarily unavailable; retrying.")
                    last_healthy = time.monotonic()
                    time.sleep(1)
                    continue
                if healthy:
                    last_healthy = time.monotonic()
                elif worker is not None and time.monotonic() - last_healthy > 15:
                    self.stderr.write("Analysis worker heartbeat lost; restarting it.")
                    stop_process(worker)
                    worker = None
                if worker is None and not healthy:
                    self.stdout.write("Starting the analysis worker alongside the web server.")
                    worker = subprocess.Popen([*base, "qcluster"], env=env, start_new_session=True)
                    last_healthy = time.monotonic()
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            stop_process(server)
            stop_process(worker)
        if server.returncode not in (0, -signal.SIGTERM, -signal.SIGINT):
            raise CommandError(f"Development server exited with code {server.returncode}.")
