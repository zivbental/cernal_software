"""Submitting, polling and cancelling runs."""

import json

from apps.analyses.models import AnalysisRun, RunStatus
from apps.datasets.models import ValidationStatus


def _submit(client, project, **overrides):
    payload = {"dataset_id": str(overrides.pop("dataset_id")), **overrides}
    return client.post(
        f"/api/projects/{project.id}/runs",
        data=json.dumps(payload),
        content_type="application/json",
    )


def test_submitting_accepts_the_work_without_completing_it(
    auth_client, project, dataset, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks():
        response = _submit(auth_client, project, dataset_id=dataset.id)
    body = response.json()

    assert response.status_code == 202, "202 = accepted, not completed"
    assert body["status"] == RunStatus.QUEUED
    assert body["submitted_at"] is not None


def test_the_configuration_snapshot_is_frozen_at_submission(
    auth_client, project, dataset, django_capture_on_commit_callbacks
):
    """Rule 7: editing the project afterwards must not change what this run computed."""
    with django_capture_on_commit_callbacks():
        run_id = _submit(
            auth_client, project, dataset_id=dataset.id, params={"max_triggers": 3}
        ).json()["id"]

    project.organism = "S. cerevisiae"
    project.save()

    run = AnalysisRun.objects.get(pk=run_id)
    assert run.params_snapshot == {"max_triggers": 3}


def test_repeating_an_idempotency_key_returns_the_same_run(
    auth_client, project, dataset, django_capture_on_commit_callbacks
):
    """A retried submission must never launch a second expensive computation."""
    with django_capture_on_commit_callbacks():
        first = _submit(
            auth_client, project, dataset_id=dataset.id, idempotency_key="abc-123"
        ).json()
    with django_capture_on_commit_callbacks():
        second = _submit(
            auth_client, project, dataset_id=dataset.id, idempotency_key="abc-123"
        ).json()

    assert first["id"] == second["id"]
    assert AnalysisRun.objects.count() == 1


def test_an_unvalidated_dataset_cannot_be_submitted(auth_client, project, dataset):
    dataset.validation_status = ValidationStatus.INVALID
    dataset.save()

    response = _submit(auth_client, project, dataset_id=dataset.id)

    assert response.status_code == 422
    assert "did not pass validation" in response.json()["error"]["message"]


def test_an_unknown_gate_family_is_rejected_with_the_available_ones(auth_client, project, dataset):
    """Validated against the engine's advertised capabilities, not an imported registry."""
    response = _submit(auth_client, project, dataset_id=dataset.id, gate_families=["warp-drive"])

    assert response.status_code == 422
    message = response.json()["error"]["message"]
    assert "warp-drive" in message
    assert "toehold" in message


def test_an_unknown_scoring_profile_is_rejected(auth_client, project, dataset):
    response = _submit(auth_client, project, dataset_id=dataset.id, scoring_profile="nope")

    assert response.status_code == 422
    assert "nope" in response.json()["error"]["message"]


def test_a_dataset_from_another_project_is_refused(auth_client, project, dataset, user):
    from apps.projects.models import Project

    other = Project.objects.create(owner=user, name="Other", organism="E. coli")
    response = _submit(auth_client, other, dataset_id=dataset.id)

    assert response.status_code == 422
    assert "different project" in response.json()["error"]["message"]


def test_cannot_submit_into_another_users_project(other_client, project, dataset):
    assert _submit(other_client, project, dataset_id=dataset.id).status_code == 404


# --- Polling ----------------------------------------------------------------------


def test_the_polling_endpoint_returns_the_documented_shape(auth_client, run):
    body = auth_client.get(f"/api/runs/{run.id}").json()

    assert set(body) == {
        "id",
        "status",
        "stage",
        "progress_pct",
        "error_summary",
        "warnings",
        "submitted_at",
        "started_at",
        "finished_at",
        "counts",
    }
    assert set(body["counts"]) == {"candidates", "artifacts"}


def test_polling_reports_counts_once_results_exist(auth_client, completed_run):
    body = auth_client.get(f"/api/runs/{completed_run.id}").json()

    assert body["status"] == RunStatus.COMPLETED
    assert body["progress_pct"] == 100
    assert body["counts"]["candidates"] > 0
    assert body["counts"]["artifacts"] > 0


def test_polling_another_users_run_is_404(other_client, run):
    assert other_client.get(f"/api/runs/{run.id}").status_code == 404


def test_run_detail_exposes_the_immutable_snapshot(auth_client, run):
    body = auth_client.get(f"/api/runs/{run.id}/detail").json()

    assert body["params_snapshot"] == {"max_triggers": 2}
    assert body["gate_families"] == ["toehold"]


def test_listing_runs_is_scoped_to_the_project(auth_client, project, run):
    body = auth_client.get(f"/api/projects/{project.id}/runs").json()
    assert [r["id"] for r in body] == [str(run.id)]


# --- Cancellation -----------------------------------------------------------------


def test_cancelling_a_queued_run_cancels_it_immediately(auth_client, run):
    body = auth_client.post(f"/api/runs/{run.id}/cancel").json()

    assert body["outcome"] == "cancelled"
    assert body["status"] == RunStatus.CANCELLED


def test_cancelling_a_running_run_only_requests_it(auth_client, run):
    """Cooperative cancellation: nothing is killed (§6.2)."""
    run.status = RunStatus.RUNNING
    run.save()

    body = auth_client.post(f"/api/runs/{run.id}/cancel").json()
    run.refresh_from_db()

    assert body["outcome"] == "cancellation_requested"
    assert body["status"] == RunStatus.RUNNING
    assert run.cancel_requested


def test_cancelling_a_finished_run_says_so(auth_client, completed_run):
    body = auth_client.post(f"/api/runs/{completed_run.id}/cancel").json()

    assert body["outcome"] == "already_terminal"
    assert body["status"] == RunStatus.COMPLETED
