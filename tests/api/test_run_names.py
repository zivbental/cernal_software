"""Editable run labels must not alter computation, ownership or release decisions."""

import json
from uuid import uuid4

import pytest

from apps.accounts.models import ApiKeyScope
from apps.accounts.services import issue_api_key
from apps.analyses.models import AnalysisRun


def rename(client, run_id, name, **headers):
    return client.patch(
        f"/api/runs/{run_id}",
        data=json.dumps({"name": name}),
        content_type="application/json",
        **headers,
    )


@pytest.mark.parametrize("status", ["QUEUED", "RUNNING", "COMPLETED", "FAILED", "CANCELLED"])
def test_name_persists_across_run_views_without_changing_submission(auth_client, run, status):
    run.status = status
    run.save()
    before = AnalysisRun.objects.values().get(pk=run.pk)
    response = rename(auth_client, run.id, "  GFP response — trial 1  ")
    assert response.status_code == 200
    run.refresh_from_db()
    assert run.name == "GFP response — trial 1"
    after = AnalysisRun.objects.values().get(pk=run.pk)
    assert {k: v for k, v in before.items() if k not in {"name", "updated_at"}} == {
        k: v for k, v in after.items() if k not in {"name", "updated_at"}
    }
    for path in [f"/api/runs/{run.id}", f"/api/runs/{run.id}/detail"]:
        assert auth_client.get(path).json()["name"] == run.name
    assert auth_client.get("/api/runs").json()[0]["name"] == run.name
    assert rename(auth_client, run.id, " " * 3).json()["name"] == ""


@pytest.mark.parametrize(
    "name", ["x" * 121, "line\nbreak", "tab\tname", "null\x00", "del\x7f", None, 17]
)
def test_invalid_rename_leaves_name_unchanged(auth_client, run, name):
    assert rename(auth_client, run.id, name).status_code == 422
    run.refresh_from_db()
    assert run.name == ""


def test_name_length_boundary_and_literal_markup(auth_client, run):
    for name in ["x" * 120, '<script>alert("label")</script>']:
        assert rename(auth_client, run.id, name).json()["name"] == name


def test_other_owner_and_missing_run_are_indistinguishable(other_client, run):
    assert rename(other_client, run.id, "stolen").status_code == 404
    assert rename(other_client, uuid4(), "missing").status_code == 404
    run.refresh_from_db()
    assert run.name == ""


def test_rename_requires_authentication_and_design_scope(client, user, run):
    assert rename(client, run.id, "anonymous").status_code == 401
    _, secret = issue_api_key(owner=user, label="name reader", scopes=(ApiKeyScope.READ,))
    assert rename(client, run.id, "reader", HTTP_X_API_KEY=secret).status_code == 403
    _, secret = issue_api_key(owner=user, label="name editor", scopes=(ApiKeyScope.DESIGN,))
    assert rename(client, run.id, "editor", HTTP_X_API_KEY=secret).status_code == 200


def test_named_submission_and_retry_preserve_renames(
    auth_client, dataset, django_capture_on_commit_callbacks
):
    payload = {"dataset_id": str(dataset.id), "name": "  First trial  ", "idempotency_key": "named"}
    with django_capture_on_commit_callbacks():
        response = auth_client.post(
            "/api/runs", data=json.dumps(payload), content_type="application/json"
        )
    assert response.status_code == 202
    first = response.json()
    assert first["name"] == "First trial"
    assert rename(auth_client, first["id"], "Renamed trial").status_code == 200
    with django_capture_on_commit_callbacks():
        retry = auth_client.post(
            "/api/runs", data=json.dumps(payload), content_type="application/json"
        )
    assert retry.status_code == 202
    assert retry.json()["id"] == first["id"]
    assert retry.json()["name"] == "Renamed trial"
    assert AnalysisRun.objects.count() == 1


@pytest.mark.parametrize("name", ["x" * 121, "bad\nname", None])
def test_invalid_submission_name_does_not_create_run(auth_client, dataset, name):
    response = auth_client.post(
        "/api/runs",
        data=json.dumps({"dataset_id": str(dataset.id), "name": name}),
        content_type="application/json",
    )
    assert response.status_code == 422
    assert AnalysisRun.objects.count() == 0
