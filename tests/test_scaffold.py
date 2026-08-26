"""Step 0 smoke tests: the skeleton is wired correctly.

These are deliberately shallow. They exist to catch the scaffold breaking, not to
test behaviour that does not exist yet.
"""

from django.conf import settings

from apps.common.db import configure_sqlite


def test_custom_user_model_is_active():
    """AUTH_USER_MODEL must be ours from the first migration (docs/architecture.md §5)."""
    from django.contrib.auth import get_user_model

    assert settings.AUTH_USER_MODEL == "accounts.User"
    assert get_user_model().__module__ == "apps.accounts.models"


def test_local_apps_are_installed():
    for app in (
        "apps.accounts",
        "apps.common",
        "apps.projects",
        "apps.datasets",
        "apps.analyses",
        "apps.results",
    ):
        assert app in settings.INSTALLED_APPS


def test_runtime_paths_live_under_var():
    """Rule 9: `rm -rf var/` then migrate must yield a clean system."""
    assert str(settings.MEDIA_ROOT).startswith(str(settings.VAR_DIR))
    assert str(settings.STATIC_ROOT).startswith(str(settings.VAR_DIR))


def test_engine_setting_points_at_a_client():
    assert settings.CERNAL_ENGINE.startswith("engine.client.")


def test_task_queue_needs_no_broker_service():
    """django-q2 on the ORM broker: the queue is a table, not a Redis instance (§9)."""
    assert settings.Q_CLUSTER["orm"] == "default"
    assert settings.Q_CLUSTER["max_attempts"] == 1, "never silently re-run an expensive job"
    assert settings.Q_CLUSTER["retry"] > settings.Q_CLUSTER["timeout"], (
        "retry <= timeout makes django-q2 re-queue tasks that are still running"
    )


class _FakeCursor:
    def __init__(self, log: list[str]) -> None:
        self.log = log

    def execute(self, sql: str) -> None:
        self.log.append(sql)

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


def test_configure_sqlite_sets_wal_and_busy_timeout():
    """WAL is what lets the web process and the worker write concurrently (§12).

    Asserted against the handler directly rather than a live connection: pytest-django
    runs on an in-memory database, which cannot use WAL. The file-backed database used
    by `./do dev` and by the VPS does.
    """
    executed: list[str] = []

    class FakeConnection:
        vendor = "sqlite"

        def cursor(self) -> _FakeCursor:
            return _FakeCursor(executed)

    configure_sqlite(sender=None, connection=FakeConnection())

    statements = " ".join(executed).lower()
    assert "journal_mode=wal" in statements
    assert "busy_timeout" in statements
    assert "foreign_keys=on" in statements


def test_configure_sqlite_ignores_other_backends():
    """Must be a no-op once DATABASE_URL points at Postgres (§16)."""

    class FakeConnection:
        vendor = "postgresql"

        def cursor(self) -> object:
            raise AssertionError("must not touch a non-SQLite connection")

    configure_sqlite(sender=None, connection=FakeConnection())


def test_health_endpoint(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_user_fixture_works(user):
    assert user.pk is not None
    assert user.username == "researcher"
