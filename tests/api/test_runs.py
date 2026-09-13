"""Submitting, polling and cancelling runs."""

import json

from apps.analyses.models import AnalysisRun, RunStatus
from apps.datasets.models import ValidationStatus


def _submit(client, **overrides):
    payload = {"dataset_id": str(overrides.pop("dataset_id")), **overrides}
    return client.post("/api/runs", data=json.dumps(payload), content_type="application/json")


def test_submitting_accepts_the_work_without_completing_it(
    auth_client, dataset, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks():
        response = _submit(auth_client, dataset_id=dataset.id)
    body = response.json()

    assert response.status_code == 202, "202 = accepted, not completed"
    assert body["status"] == RunStatus.QUEUED
    assert body["submitted_at"] is not None


def test_the_configuration_snapshot_is_frozen_at_submission(
    auth_client, dataset, django_capture_on_commit_callbacks
):
    """Rule 7: a submitted run's configuration never changes after the fact."""
    with django_capture_on_commit_callbacks():
        run_id = _submit(auth_client, dataset_id=dataset.id, params={"max_triggers": 3}).json()[
            "id"
        ]

    run = AnalysisRun.objects.get(pk=run_id)
    assert run.params_snapshot == {"max_triggers": 3}


def test_repeating_an_idempotency_key_returns_the_same_run(
    auth_client, dataset, django_capture_on_commit_callbacks
):
    """A retried submission must never launch a second expensive computation."""
    with django_capture_on_commit_callbacks():
        first = _submit(auth_client, dataset_id=dataset.id, idempotency_key="abc-123").json()
    with django_capture_on_commit_callbacks():
        second = _submit(auth_client, dataset_id=dataset.id, idempotency_key="abc-123").json()

    assert first["id"] == second["id"]
    assert AnalysisRun.objects.count() == 1


def test_an_unvalidated_dataset_cannot_be_submitted(auth_client, dataset):
    dataset.validation_status = ValidationStatus.INVALID
    dataset.save()

    response = _submit(auth_client, dataset_id=dataset.id)

    assert response.status_code == 422
    assert "did not pass validation" in response.json()["error"]["message"]


def test_an_unknown_gate_family_is_rejected_with_the_available_ones(auth_client, dataset):
    """Validated against the engine's advertised capabilities, not an imported registry."""
    response = _submit(auth_client, dataset_id=dataset.id, gate_families=["warp-drive"])

    assert response.status_code == 422
    message = response.json()["error"]["message"]
    assert "warp-drive" in message
    assert "toehold" in message


def test_an_unknown_scoring_profile_is_rejected(auth_client, dataset):
    response = _submit(auth_client, dataset_id=dataset.id, scoring_profile="nope")

    assert response.status_code == 422
    assert "nope" in response.json()["error"]["message"]


def test_an_unknown_constraint_field_is_rejected_at_submission(auth_client, dataset):
    """The wizard's own bug, reproduced: params.constraints is a typed projection of
    engine.domain.Constraints, unlike every other params key, so a typo here must
    surface as an immediate 422 rather than an async FAILED run once
    engine.pipeline._build_constraints rejects it in the worker."""
    response = _submit(
        auth_client,
        dataset_id=dataset.id,
        params={"constraints": {"max_leakage": 0.08}},
    )

    assert response.status_code == 422
    body = response.json()["error"]
    assert body["code"] == "unknown_parameter"
    assert "max_leakage" in body["message"]
    assert "max_switch_length" in body["detail"]["allowed"]


def test_a_known_constraint_field_is_accepted(
    auth_client, dataset, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks():
        response = _submit(
            auth_client, dataset_id=dataset.id, params={"constraints": {"max_triggers": 3}}
        )

    assert response.status_code == 202


def test_an_unknown_scoring_metric_name_is_rejected_at_submission(auth_client, dataset):
    response = _submit(
        auth_client,
        dataset_id=dataset.id,
        params={"scoring": {"hard_filters": [{"metric": "leakage", "maximum": 0.08}]}},
    )

    assert response.status_code == 422
    body = response.json()["error"]
    assert "leakage" in body["message"]
    assert "predicted_leakage" in body["detail"]["allowed"]


def test_an_unknown_scoring_key_is_rejected_at_submission(auth_client, dataset):
    response = _submit(auth_client, dataset_id=dataset.id, params={"scoring": {"typo": 1}})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "unknown_parameter"


def test_a_hard_filter_with_no_reason_is_rejected_at_submission(auth_client, dataset):
    """engine.scoring.profiles.derive_profile defaults a missing 'reason' to '', and
    Candidate has a DB constraint that a rejected row must carry a non-empty
    rejection_reason — so this must be caught here, not surface as an IntegrityError
    the first time the filter actually rejects a real candidate in the worker."""
    response = _submit(
        auth_client,
        dataset_id=dataset.id,
        params={"scoring": {"hard_filters": [{"metric": "predicted_leakage", "maximum": 0.5}]}},
    )

    assert response.status_code == 422
    message = response.json()["error"]["message"]
    assert "predicted_leakage" in message
    assert "reason" in message


def test_a_valid_scoring_override_is_accepted_and_stored(
    auth_client, dataset, django_capture_on_commit_callbacks
):
    """The mechanism the wizard's Advanced panel now uses (docs/plasmids.md-adjacent
    fix): a per-run hard-filter override, the same X7 path POST /api/design already
    validates."""
    scoring = {
        "hard_filters": [
            {"metric": "predicted_leakage", "maximum": 0.5, "reason": "Researcher-set limit."}
        ]
    }
    with django_capture_on_commit_callbacks():
        response = _submit(auth_client, dataset_id=dataset.id, params={"scoring": scoring})

    assert response.status_code == 202
    run = AnalysisRun.objects.get(pk=response.json()["id"])
    assert run.params_snapshot["scoring"] == scoring


def test_cannot_submit_using_another_users_dataset(other_client, dataset):
    """404, not 403 — 403 would confirm the dataset exists (§7.2)."""
    assert _submit(other_client, dataset_id=dataset.id).status_code == 404


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


def test_listing_runs_is_scoped_to_the_owner(auth_client, other_client, run):
    assert [r["id"] for r in auth_client.get("/api/runs").json()] == [str(run.id)]
    assert other_client.get("/api/runs").json() == []


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
