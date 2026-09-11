"""Scopes, the per-key rate limit, and the concurrency ceiling (docs/public-api.md §6).

The credential itself is tested in tests/api/test_api_keys.py; this file is what a key
is and is not allowed to *do* once it authenticates.
"""

import json

from django.core.cache import cache

from apps.accounts.services import issue_api_key
from apps.analyses.models import RunStatus


def _submit(client, project, secret=None, **overrides):
    payload = {"dataset_id": str(overrides.pop("dataset_id")), **overrides}
    kwargs = {"HTTP_X_API_KEY": secret} if secret else {}
    return client.post(
        f"/api/projects/{project.id}/runs",
        data=json.dumps(payload),
        content_type="application/json",
        **kwargs,
    )


# --- Scopes ---------------------------------------------------------------------------


def test_a_read_scoped_key_cannot_submit_a_run(client, user, project, dataset):
    _key, secret = issue_api_key(owner=user, label="ci", scopes=("read",))

    response = _submit(client, project, secret=secret, dataset_id=dataset.id)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "insufficient_scope"


def test_a_design_scoped_key_can_submit_a_run(client, user, project, dataset):
    _key, secret = issue_api_key(owner=user, label="ci", scopes=("design",))

    response = _submit(client, project, secret=secret, dataset_id=dataset.id)

    assert response.status_code == 202


def test_a_read_scoped_key_cannot_cancel_a_run(client, user, run):
    _key, secret = issue_api_key(owner=user, label="ci", scopes=("read",))

    response = client.post(f"/api/runs/{run.id}/cancel", HTTP_X_API_KEY=secret)

    assert response.status_code == 403


def test_a_read_scoped_key_can_still_read(client, user, project):
    _key, secret = issue_api_key(owner=user, label="ci", scopes=("read",))

    response = client.get(f"/api/projects/{project.id}", HTTP_X_API_KEY=secret)

    assert response.status_code == 200


def test_session_auth_is_exempt_from_scopes(auth_client, project, dataset):
    """A human in the SPA is not a key and is not scope-limited."""
    response = _submit(auth_client, project, dataset_id=dataset.id)
    assert response.status_code == 202


# --- Concurrency ceiling ----------------------------------------------------------


def test_the_ceiling_blocks_a_second_submission(client, user, project, dataset):
    _key, secret = issue_api_key(owner=user, label="ci", scopes=("design",), max_concurrent_runs=1)

    first = _submit(client, project, secret=secret, dataset_id=dataset.id, idempotency_key="a")
    second = _submit(client, project, secret=secret, dataset_id=dataset.id, idempotency_key="b")

    assert first.status_code == 202
    assert second.status_code == 429
    body = second.json()
    assert body["error"]["code"] == "too_many_active_runs"
    assert second.headers["Retry-After"]


def test_the_ceiling_is_per_owner_not_per_key(client, user, project, dataset):
    """Two keys, same owner: each has its own limit, but the count is the owner's total
    active runs — a script cannot dodge the ceiling by minting a second key."""
    _key_a, secret_a = issue_api_key(
        owner=user, label="key-a", scopes=("design",), max_concurrent_runs=1
    )
    _key_b, secret_b = issue_api_key(
        owner=user, label="key-b", scopes=("design",), max_concurrent_runs=1
    )

    first = _submit(client, project, secret=secret_a, dataset_id=dataset.id, idempotency_key="a")
    second = _submit(client, project, secret=secret_b, dataset_id=dataset.id, idempotency_key="b")

    assert first.status_code == 202
    assert second.status_code == 429


def test_session_auth_is_exempt_from_the_ceiling(auth_client, project, dataset):
    response1 = _submit(auth_client, project, dataset_id=dataset.id, idempotency_key="a")
    response2 = _submit(auth_client, project, dataset_id=dataset.id, idempotency_key="b")

    assert response1.status_code == 202
    assert response2.status_code == 202


def test_the_ceiling_does_not_count_completed_runs(client, user, project, run):
    """run fixture is QUEUED; finish it, then confirm a fresh submission is allowed."""
    run.status = RunStatus.COMPLETED
    run.save(update_fields=["status"])

    _key, secret = issue_api_key(owner=user, label="ci", scopes=("design",), max_concurrent_runs=1)
    response = _submit(client, project, secret=secret, dataset_id=run.dataset_id)

    assert response.status_code == 202


# --- Rate limit ---------------------------------------------------------------------


def test_a_key_over_its_rate_limit_gets_429(client, user):
    cache.clear()
    _key, secret = issue_api_key(owner=user, label="ci", rate_per_minute=1)

    first = client.get("/api/auth/whoami", HTTP_X_API_KEY=secret)
    second = client.get("/api/auth/whoami", HTTP_X_API_KEY=secret)

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "rate_limited"
    assert second.headers["Retry-After"]


def test_two_keys_have_independent_rate_buckets(client, user, other_user):
    """A shared CI key must not throttle a teammate's laptop (docs/public-api.md §6)."""
    cache.clear()
    _key_a, secret_a = issue_api_key(owner=user, label="ci", rate_per_minute=1)
    _key_b, secret_b = issue_api_key(owner=other_user, label="laptop", rate_per_minute=1)

    client.get("/api/auth/whoami", HTTP_X_API_KEY=secret_a)
    response = client.get("/api/auth/whoami", HTTP_X_API_KEY=secret_b)

    assert response.status_code == 200


def test_session_auth_is_not_rate_limited_by_this_mechanism(auth_client):
    cache.clear()
    for _ in range(3):
        assert auth_client.get("/api/auth/me").status_code == 200
