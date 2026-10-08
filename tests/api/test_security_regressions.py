"""Desired authorization behavior for the 2026-10-08 audit findings."""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib import admin
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, RequestFactory
from django.utils import timezone

from apps.accounts.admin import ApiKeyAdmin
from apps.accounts.models import ApiKey, User
from apps.accounts.services import (
    RegistrationError,
    authenticate_api_key,
    issue_api_key,
    regenerate_api_key,
    register_user,
)
from apps.analyses.models import AnalysisRun
from apps.datasets.models import Dataset
from apps.results.models import Artifact, CandidateMetric


@pytest.mark.parametrize(
    "attributes",
    [
        {"is_staff": True},
        {"is_superuser": True},
        {"is_active": False},
        {},
    ],
)
def test_reviewer_collision_cannot_establish_anonymous_session(client, db, settings, attributes):
    settings.REVIEWER_LOGIN_ENABLED = True
    account = User.objects.create_user("reviewer", password="ordinary-password", **attributes)
    response = client.post("/api/auth/reviewer-login")
    assert response.status_code == 422
    assert client.get("/api/auth/me").status_code == 401
    account.refresh_from_db()
    assert account.check_password("ordinary-password")
    assert account.is_staff == attributes.get("is_staff", False)


def test_reviewer_username_is_reserved(db):
    with pytest.raises(RegistrationError, match="reserved"):
        register_user(username=" ReVieWer ", email="real@example.org", password="strong-123-pw")


@pytest.mark.parametrize(
    "path,payload",
    [
        ("login", {"username": "researcher", "password": "test-password-123"}),
        ("reviewer-login", {}),
        (
            "register",
            {"username": "new-person", "email": "new@example.org", "password": "strong-123-pw"},
        ),
    ],
)
def test_auth_entries_require_csrf(path, payload, user, settings):
    settings.REVIEWER_LOGIN_ENABLED = True
    client = Client(enforce_csrf_checks=True)
    response = client.post(
        f"/api/auth/{path}",
        data=payload,
        content_type="application/json",
        HTTP_ORIGIN="https://foreign.example",
    )
    assert response.status_code == 403
    assert client.get("/api/auth/me").status_code == 401


def test_same_origin_spa_login_with_csrf_succeeds(user):
    client = Client(enforce_csrf_checks=True)
    client.get("/api/auth/csrf")
    response = client.post(
        "/api/auth/login",
        data={"username": "researcher", "password": "test-password-123"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
        HTTP_ORIGIN="http://testserver",
    )
    assert response.status_code == 200


def test_auth_abuse_limit_precedes_password_verification(client, user, settings):
    cache.clear()
    settings.AUTH_ATTEMPTS_PER_MINUTE = 1
    first = client.post(
        "/api/auth/login",
        data={"username": "unknown", "password": "wrong"},
        content_type="application/json",
    )
    second = client.post(
        "/api/auth/login",
        data={"username": "unknown", "password": "wrong"},
        content_type="application/json",
    )
    assert first.status_code == 401
    assert second.status_code == 429
    assert second.headers["Retry-After"]
    cache.clear()


def test_debug_media_has_no_anonymous_byte_route(client, dataset, settings):
    settings.DEBUG = True
    response = client.get(f"/media/{dataset.file.name}")
    assert response.status_code == 404
    assert response.content != dataset.file.read()


def test_read_only_key_cannot_upload_or_materialize(client, user):
    _, secret = issue_api_key(owner=user, label="read-only", scopes=("read",))
    response = client.post(
        "/api/datasets",
        {"file": SimpleUploadedFile("data.csv", b"gene_id,log2fc\nb0005,2\n")},
        HTTP_X_API_KEY=secret,
    )
    assert response.status_code == 403
    for path, body in [
        ("/api/datasets/example", {"key": "ecoli-oxidative-stress"}),
        ("/api/public-datasets/materialize", {"comparison_key": "anything"}),
    ]:
        response = client.post(
            path, data=body, content_type="application/json", HTTP_X_API_KEY=secret
        )
        assert response.status_code == 403
    assert not Dataset.objects.exists()


def test_legacy_empty_scope_key_cannot_read_protected_endpoints(client, user, run):
    key, secret = issue_api_key(owner=user, label="legacy")
    key.scopes = []
    key.save(update_fields=["scopes"])
    for path in [
        "/api/auth/me",
        "/api/auth/whoami",
        "/api/datasets",
        "/api/runs",
        f"/api/runs/{run.id}",
    ]:
        assert client.get(path, HTTP_X_API_KEY=secret).status_code == 403
    assert client.get("/api/version").status_code == 200


@pytest.mark.parametrize(
    "overrides",
    [
        {"scopes": ()},
        {"expires_in_days": 0},
        {"expires_in_days": -1},
        {"expires_in_days": 1000000},
        {"max_concurrent_runs": 0},
        {"rate_per_minute": -1},
    ],
)
def test_invalid_key_configuration_is_rejected(user, overrides):
    with pytest.raises(RegistrationError):
        issue_api_key(owner=user, label="invalid", **overrides)


def test_expired_regeneration_refuses_and_preserves_old_identity(user):
    key, secret = issue_api_key(owner=user, label="expired")
    key.expires_at = timezone.now() - timedelta(days=1)
    key.save(update_fields=["expires_at"])
    original_hash = key.key_hash
    with pytest.raises(RegistrationError, match="expired"):
        regenerate_api_key(key)
    key.refresh_from_db()
    assert key.key_hash == original_hash
    assert authenticate_api_key(secret) is None
    assert ApiKeyAdmin(ApiKey, admin.site).status(key) == "expired"


def test_prefix_collision_is_retried_without_replacing_existing_key(user):
    with patch("apps.accounts.services.secrets.token_urlsafe", return_value="samePrefixExisting"):
        original, old_secret = issue_api_key(owner=user, label="original")
    with patch(
        "apps.accounts.services.secrets.token_urlsafe",
        side_effect=["samePrefixNew", "uniquePrefixNew"],
    ):
        new, secret = issue_api_key(owner=user, label="new")
    assert original.prefix != new.prefix
    assert authenticate_api_key(old_secret).id == original.id
    assert authenticate_api_key(secret).id == new.id


@pytest.mark.parametrize("model", [AnalysisRun, Dataset, Artifact, CandidateMetric])
def test_scientific_admin_forms_cannot_write_frozen_records(model, staff_user):
    request = RequestFactory().get("/admin/")
    request.user = staff_user
    model_admin = admin.site._registry[model]
    form = model_admin.get_form(request)
    assert not form.base_fields
    assert not model_admin.has_add_permission(request)


def test_identical_retry_is_allowed_at_account_quota(auth_client, dataset, settings):
    settings.MAX_ACTIVE_RUNS_PER_ACCOUNT = 1
    body = {"dataset_id": str(dataset.id), "idempotency_key": "retry"}
    first = auth_client.post("/api/runs", data=body, content_type="application/json")
    second = auth_client.post("/api/runs", data=body, content_type="application/json")
    assert first.status_code == second.status_code == 202
    assert first.json()["id"] == second.json()["id"]
    body["idempotency_key"] = "other"
    assert (
        auth_client.post("/api/runs", data=body, content_type="application/json").status_code == 429
    )


def test_idempotency_key_is_owner_scoped(auth_client, other_client, user, other_user, dataset):
    body = {"input_mode": "direct", "trigger_sequence": "AUGC" * 10, "idempotency_key": "shared"}
    first = auth_client.post("/api/runs", data=body, content_type="application/json")
    second = other_client.post("/api/runs", data=body, content_type="application/json")
    assert first.status_code == second.status_code == 202
    assert first.json()["id"] != second.json()["id"]
    assert AnalysisRun.objects.get(pk=first.json()["id"]).created_by == user
    assert AnalysisRun.objects.get(pk=second.json()["id"]).created_by == other_user


def test_changed_input_cannot_reuse_idempotency_key(auth_client):
    body = {"input_mode": "direct", "trigger_sequence": "AUGC" * 10, "idempotency_key": "immutable"}
    first = auth_client.post("/api/runs", data=body, content_type="application/json")
    assert first.status_code == 202
    body["trigger_sequence"] = "AUGG" * 10
    second = auth_client.post("/api/runs", data=body, content_type="application/json")
    assert second.status_code == 409
    assert AnalysisRun.objects.count() == 1
