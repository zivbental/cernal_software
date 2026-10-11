"""Session auth and the shared error envelope (docs/architecture.md §7.2)."""

import json

import pytest


def test_login_returns_the_user(client, user):
    response = client.post(
        "/api/auth/login",
        data={"username": "researcher", "password": "test-password-123"},
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["username"] == "researcher"


def test_login_with_a_bad_password_is_401(client, user):
    response = client.post(
        "/api/auth/login",
        data={"username": "researcher", "password": "wrong"},
        content_type="application/json",
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


def test_login_does_not_reveal_whether_a_username_exists(client, user):
    known = client.post(
        "/api/auth/login",
        data={"username": "researcher", "password": "wrong"},
        content_type="application/json",
    ).json()
    unknown = client.post(
        "/api/auth/login",
        data={"username": "nobody-here", "password": "wrong"},
        content_type="application/json",
    ).json()

    assert known == unknown


def test_me_requires_authentication(client, db):
    response = client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


def test_me_returns_the_logged_in_user(auth_client):
    assert auth_client.get("/api/auth/me").json()["username"] == "researcher"


def test_logout_ends_the_session(auth_client):
    assert auth_client.post("/api/auth/logout").status_code == 204
    assert auth_client.get("/api/auth/me").status_code == 401


# --- Reviewer instant login ---------------------------------------------------------


def test_reviewer_login_is_404_when_disabled(client, db, settings):
    settings.REVIEWER_LOGIN_ENABLED = False

    response = client.post("/api/auth/reviewer-login")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_reviewer_login_signs_in_as_an_unprivileged_account(client, db, settings):
    settings.REVIEWER_LOGIN_ENABLED = True

    response = client.post("/api/auth/reviewer-login")
    body = response.json()

    assert response.status_code == 200
    assert body["username"] == "reviewer"
    assert body["is_staff"] is False
    assert client.get("/api/auth/me").json()["username"] == "reviewer"


def test_reviewer_login_reuses_the_same_account(client, db, settings):
    settings.REVIEWER_LOGIN_ENABLED = True

    first = client.post("/api/auth/reviewer-login").json()
    client.post("/api/auth/logout")
    second = client.post("/api/auth/reviewer-login").json()

    assert first["id"] == second["id"]


def test_reviewer_account_has_no_usable_password(client, db, settings):
    """The button is the only door in — a correct-looking guess at the normal login
    form must never work."""
    settings.REVIEWER_LOGIN_ENABLED = True
    client.post("/api/auth/reviewer-login")

    response = client.post(
        "/api/auth/login",
        data={"username": "reviewer", "password": ""},
        content_type="application/json",
    )

    assert response.status_code == 401


# --- Envelope ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "code"),
    [
        ("/api/datasets/00000000-0000-0000-0000-000000000000", "not_found"),
        ("/api/runs/00000000-0000-0000-0000-000000000000", "not_found"),
    ],
)
def test_errors_share_one_shape(auth_client, path, code):
    response = auth_client.get(path)
    body = response.json()

    assert response.status_code == 404
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "detail"}
    assert body["error"]["code"] == code


def test_invalid_body_returns_422_with_details(auth_client):
    response = auth_client.post(
        "/api/runs",
        data=json.dumps({"dataset_id": "not-a-uuid"}),
        content_type="application/json",
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


# --- Meta -------------------------------------------------------------------------


def test_health_needs_no_authentication(client, db):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_version_advertises_engine_capabilities(client, db):
    body = client.get("/api/version").json()

    assert body["engine"] == "LocalEngine"
    assert "default" in body["scoring_profiles"]


def test_version_advertises_the_scoring_vocabulary(client, db):
    """docs/public-api.md §4/§7: this is what a client validates a custom scoring block
    against before submitting — units included, so it never has to guess linear vs. log2."""
    body = client.get("/api/version").json()

    metric_names = {metric["name"] for metric in body["metrics"]}
    assert "predicted_leakage" in metric_names
    assert all(metric["unit"] for metric in body["metrics"])

    by_metric = {hf["metric"] for hf in body["hard_filters"]}
    assert "predicted_leakage" in by_metric

    families = {f["name"]: f for f in body["gate_families"]}
    assert families["toehold"]["available"]
    assert families["toehold"]["label"] == "Toehold Riboswitch"
    # Planned mechanisms are advertised so the UI can grey them out honestly.
    assert not families["crispr"]["available"]


def test_version_advertises_reviewer_login_flag(client, db, settings):
    settings.REVIEWER_LOGIN_ENABLED = True
    assert client.get("/api/version").json()["reviewer_login_enabled"] is True

    settings.REVIEWER_LOGIN_ENABLED = False
    assert client.get("/api/version").json()["reviewer_login_enabled"] is False


def test_version_exposes_no_secrets(client, db, settings):
    body = client.get("/api/version").json()

    assert settings.SECRET_KEY not in str(body)
    assert "var/" not in str(body)


def test_openapi_schema_is_published(client, db):
    """The SPA generates its typed client from this (ADR 0004)."""
    schema = client.get("/api/openapi.json").json()

    assert schema["info"]["title"] == "CERNAL API"
    assert "/api/runs/{run_id}" in schema["paths"]


def test_csrf_endpoint_hands_out_a_cookie(client, db):
    """A single-page app has no server-rendered form to carry the CSRF token."""
    response = client.get("/api/auth/csrf")

    assert response.status_code == 204
    assert "csrftoken" in response.cookies
