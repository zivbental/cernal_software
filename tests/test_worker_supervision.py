"""Missing and failed workers must recover without manual startup."""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from django.utils import timezone
from django_q.conf import Conf

from apps.analyses.worker import worker_available
from apps.web.management.commands import devserver


@pytest.mark.parametrize(
    "age,status,workers,expected",
    [
        (0, Conf.IDLE, [1], True),
        (0, Conf.WORKING, [1], True),
        (30, Conf.IDLE, [1], False),
        (0, Conf.STOPPED, [1], False),
        (0, Conf.IDLE, [], False),
    ],
)
def test_worker_heartbeat_requires_a_live_cluster(monkeypatch, age, status, workers, expected):
    stat = SimpleNamespace(
        timestamp=timezone.now() - timedelta(seconds=age), status=status, workers=workers
    )
    monkeypatch.setattr("apps.analyses.worker.Stat.get_all", lambda: [stat])
    assert worker_available() is expected


def test_devserver_starts_and_restarts_a_missing_worker(monkeypatch):
    server = Mock(returncode=0)
    server.poll.side_effect = [None, None, None, 0]
    dead_worker = Mock()
    dead_worker.poll.return_value = 1
    replacement = Mock()
    replacement.poll.return_value = None
    launch = Mock(side_effect=[server, dead_worker, replacement])
    stop = Mock()
    monkeypatch.setattr(devserver.subprocess, "Popen", launch)
    monkeypatch.setattr(devserver, "worker_available", lambda: False)
    monkeypatch.setattr(devserver, "stop_process", stop)
    monkeypatch.setattr(devserver.time, "sleep", lambda _: None)
    devserver.Command().supervise({})
    assert [call.args[0][2] for call in launch.call_args_list] == [
        "runserver",
        "qcluster",
        "qcluster",
    ]
    stop.assert_any_call(server)
    stop.assert_any_call(replacement)


def test_devserver_reuses_an_existing_live_worker(monkeypatch):
    server = Mock(returncode=0)
    server.poll.side_effect = [None, 0]
    launch = Mock(return_value=server)
    monkeypatch.setattr(devserver.subprocess, "Popen", launch)
    monkeypatch.setattr(devserver, "worker_available", lambda: True)
    monkeypatch.setattr(devserver, "stop_process", Mock())
    monkeypatch.setattr(devserver.time, "sleep", lambda _: None)
    devserver.Command().supervise({})
    assert launch.call_count == 1


def test_devserver_restarts_a_worker_that_loses_its_heartbeat(monkeypatch):
    server = Mock(returncode=0)
    server.poll.side_effect = [None, None, 0]
    unresponsive = Mock()
    unresponsive.poll.return_value = None
    replacement = Mock()
    launch = Mock(side_effect=[server, unresponsive, replacement])
    stop = Mock()
    clock = Mock(side_effect=[0, 1, 17, 18])
    monkeypatch.setattr(devserver.subprocess, "Popen", launch)
    monkeypatch.setattr(devserver, "worker_available", lambda: False)
    monkeypatch.setattr(devserver, "stop_process", stop)
    monkeypatch.setattr(devserver.time, "monotonic", clock)
    monkeypatch.setattr(devserver.time, "sleep", lambda _: None)
    devserver.Command().supervise({})
    assert launch.call_count == 3
    stop.assert_any_call(unresponsive)


@pytest.mark.django_db
@pytest.mark.parametrize("online", [False, True])
def test_queued_status_exposes_worker_health(auth_client, run, monkeypatch, online):
    monkeypatch.setattr("api.routers.runs.worker_available", lambda: online)
    monkeypatch.setattr("api.routers.design.worker_available", lambda: online)
    for endpoint in ("runs", "design"):
        response = auth_client.get(f"/api/{endpoint}/{run.id}")
        assert response.status_code == 200
        assert response.json()["worker_available"] is online


def test_heartbeat_cache_is_independent_of_result_database(settings):
    from django.core.cache import caches

    assert settings.Q_CLUSTER["cache"] == "worker_status"
    assert "filebased" in settings.CACHES["worker_status"]["BACKEND"]
    cache = caches["worker_status"]
    cache.set("qa-heartbeat", "alive", 3)
    try:
        assert cache.get("qa-heartbeat") == "alive"
    finally:
        cache.delete("qa-heartbeat")


def test_supervisor_survives_a_temporary_status_store_error(monkeypatch):
    from django.db import OperationalError

    server = Mock(returncode=0)
    server.poll.side_effect = [None, None, 0]
    launch = Mock(return_value=server)
    health = Mock(side_effect=[OperationalError("database is locked"), True])
    monkeypatch.setattr(devserver.subprocess, "Popen", launch)
    monkeypatch.setattr(devserver, "worker_available", health)
    monkeypatch.setattr(devserver, "stop_process", Mock())
    monkeypatch.setattr(devserver.time, "sleep", lambda _: None)
    devserver.Command().supervise({})
    assert health.call_count == 2
    assert launch.call_count == 1
