"""Session auth and the shared error envelope (docs/software-design.md §7.2)."""

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


# --- Envelope ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "code"),
    [
        ("/api/projects/00000000-0000-0000-0000-000000000000", "not_found"),
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
        "/api/projects", data={"organism": "E. coli"}, content_type="application/json"
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


# --- Meta -------------------------------------------------------------------------


def test_health_needs_no_authentication(client, db):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_version_advertises_engine_capabilities(client, db):
    body = client.get("/api/version").json()

    assert body["engine"] == "MockEngine"
    assert "default" in body["scoring_profiles"]

    families = {f["name"]: f for f in body["gate_families"]}
    assert families["toehold"]["available"]
    assert families["toehold"]["label"] == "Toehold Riboswitch"
    # Planned mechanisms are advertised so the UI can grey them out honestly.
    assert not families["crispr"]["available"]


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
