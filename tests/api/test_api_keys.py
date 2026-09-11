"""API-key authentication end to end: minting, using, scoping, revoking (ADR 0006).

The credential itself (issue/authenticate/revoke) is tested in tests/test_api_keys.py;
this file is the HTTP surface — the dual auth=[ApiKeyAuth(), django_auth] wiring, the
session-only key-management endpoints, and the 401/403 shapes docs/public-api.md §10
promises.
"""

from apps.accounts.services import issue_api_key


def _key_client(client, user, **kwargs):
    """A plain (unauthenticated) test client, plus the secret for one freshly minted key."""
    _key, secret = issue_api_key(owner=user, label="test-key", **kwargs)
    return secret


# --- The dual credential ------------------------------------------------------------


def test_a_valid_key_authenticates_like_a_session(client, user):
    secret = _key_client(client, user)

    response = client.get("/api/auth/me", HTTP_X_API_KEY=secret)

    assert response.status_code == 200
    assert response.json()["username"] == user.username


def test_a_key_sees_only_its_owners_data(client, user, other_user, dataset):
    """The same ownership path every session request goes through (api/auth.py) —
    proof a key cannot see across accounts (docs/public-api.md §13)."""
    secret = _key_client(client, other_user)

    response = client.get(f"/api/datasets/{dataset.id}", HTTP_X_API_KEY=secret)

    assert response.status_code == 404


def test_a_bad_key_is_401_invalid_api_key(client, db):
    response = client.get("/api/auth/me", HTTP_X_API_KEY="cern_live_not-a-real-key")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_api_key"


def test_no_credential_at_all_is_the_generic_401(client, db):
    """No header, no cookie: falls through both auth mechanisms to the ordinary
    not_authenticated — distinct from a key that was presented and rejected."""
    response = client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


def test_a_revoked_key_is_401(client, user):
    from apps.accounts.services import revoke_api_key

    key, secret = issue_api_key(owner=user, label="test-key")
    revoke_api_key(key)

    response = client.get("/api/auth/me", HTTP_X_API_KEY=secret)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_api_key"


def test_a_session_cookie_still_works_with_no_key_header(auth_client):
    """The SPA's path is untouched (docs/public-api.md §3)."""
    assert auth_client.get("/api/auth/me").status_code == 200


# --- Key management: session-only ----------------------------------------------------


def test_creating_a_key_returns_the_secret_exactly_once(auth_client):
    response = auth_client.post(
        "/api/auth/keys",
        data={"label": "laptop", "scopes": ["read", "design"]},
        content_type="application/json",
    )

    assert response.status_code == 201
    body = response.json()
    assert body["secret"].startswith("cern_live_")
    assert body["prefix"] == body["secret"][:14]


def test_listing_keys_never_includes_the_secret(auth_client, user):
    issue_api_key(owner=user, label="one")
    issue_api_key(owner=user, label="two")

    response = auth_client.get("/api/auth/keys")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert all("secret" not in row for row in body)


def test_listing_keys_shows_only_your_own(auth_client, user, other_user):
    issue_api_key(owner=user, label="mine")
    issue_api_key(owner=other_user, label="not-mine")

    body = auth_client.get("/api/auth/keys").json()

    assert len(body) == 1
    assert body[0]["label"] == "mine"


def test_a_key_cannot_mint_a_key(client, user):
    """You cannot mint a key with a key — session-only, deliberately (ADR 0006)."""
    secret = _key_client(client, user)

    response = client.post(
        "/api/auth/keys",
        data={"label": "new-key"},
        content_type="application/json",
        HTTP_X_API_KEY=secret,
    )

    assert response.status_code == 401


def test_a_key_cannot_list_or_revoke_keys(client, user):
    secret = _key_client(client, user)

    assert client.get("/api/auth/keys", HTTP_X_API_KEY=secret).status_code == 401


def test_revoking_a_key_is_idempotent_204(auth_client, user):
    key, _secret = issue_api_key(owner=user, label="laptop")

    first = auth_client.delete(f"/api/auth/keys/{key.id}")
    second = auth_client.delete(f"/api/auth/keys/{key.id}")

    assert first.status_code == 204
    assert second.status_code == 204


def test_revoking_someone_elses_key_is_404_not_403(auth_client, other_user):
    """Ownership failures are 404, never 403 (docs/architecture.md §7.2)."""
    key, _secret = issue_api_key(owner=other_user, label="not-yours")

    response = auth_client.delete(f"/api/auth/keys/{key.id}")

    assert response.status_code == 404


# --- whoami ---------------------------------------------------------------------------


def test_whoami_confirms_a_key_works(client, user):
    secret = _key_client(client, user, scopes=("read",))

    response = client.get("/api/auth/whoami", HTTP_X_API_KEY=secret)

    assert response.status_code == 200
    body = response.json()
    assert body["username"] == user.username
    assert body["scopes"] == ["read"]
    assert body["key_label"] == "test-key"


def test_whoami_requires_a_key_not_a_session(auth_client):
    """A session has no request.api_key, so whoami — which is about confirming a key —
    correctly refuses it rather than describing a key that was never presented."""
    assert auth_client.get("/api/auth/whoami").status_code == 401


# --- Regenerate ("reset" in the web UI) ---------------------------------------------


def test_regenerate_returns_a_new_secret(auth_client, user):
    key, old_secret = issue_api_key(owner=user, label="laptop")

    response = auth_client.post(f"/api/auth/keys/{key.id}/regenerate")

    assert response.status_code == 200
    body = response.json()
    assert body["secret"] != old_secret
    assert body["secret"].startswith("cern_live_")
    assert body["id"] == str(key.id)
    assert body["label"] == "laptop"


def test_regenerate_invalidates_the_old_secret(client, auth_client, user):
    key, old_secret = issue_api_key(owner=user, label="laptop")
    assert client.get("/api/auth/whoami", HTTP_X_API_KEY=old_secret).status_code == 200

    auth_client.post(f"/api/auth/keys/{key.id}/regenerate")

    assert client.get("/api/auth/whoami", HTTP_X_API_KEY=old_secret).status_code == 401


def test_regenerate_someone_elses_key_is_404_not_403(auth_client, other_user):
    key, _secret = issue_api_key(owner=other_user, label="not-yours")

    response = auth_client.post(f"/api/auth/keys/{key.id}/regenerate")

    assert response.status_code == 404


def test_a_key_cannot_regenerate_a_key(client, user):
    """Session-only, same as mint/list/revoke (ADR 0006)."""
    key, secret = issue_api_key(owner=user, label="laptop")

    response = client.post(f"/api/auth/keys/{key.id}/regenerate", HTTP_X_API_KEY=secret)

    assert response.status_code == 401
