"""Example datasets, and downstream outputs as equivalent choices."""

import json

from apps.datasets.models import Dataset, ValidationStatus


def test_example_datasets_are_advertised(client, db):
    body = client.get("/api/example-datasets").json()

    assert body
    keys = {item["key"] for item in body}
    assert "ecoli-oxidative-stress" in keys
    for item in body:
        assert item["label"] and item["description"]


def test_an_example_can_be_loaded(auth_client, user, media_root):
    """It must be a real, validated dataset — not a special case downstream."""
    response = auth_client.post(
        "/api/datasets/example",
        data=json.dumps({"key": "ecoli-oxidative-stress"}),
        content_type="application/json",
    )
    body = response.json()

    assert response.status_code == 201
    assert body["validation_status"] == ValidationStatus.VALID
    assert body["validation_report"]["rows"] == 50
    assert len(body["checksum_sha256"]) == 64

    dataset = Dataset.objects.get(pk=body["id"])
    assert dataset.uploaded_by_id == user.id
    assert dataset.file.storage.exists(dataset.file.name)


def test_an_example_run_completes_like_any_other(
    auth_client, media_root, django_capture_on_commit_callbacks
):
    from apps.analyses.tasks import run_analysis

    dataset = auth_client.post(
        "/api/datasets/example",
        data=json.dumps({"key": "ecoli-oxidative-stress"}),
        content_type="application/json",
    ).json()

    with django_capture_on_commit_callbacks():
        run = auth_client.post(
            "/api/runs",
            data=json.dumps(
                {
                    "input_mode": "de",
                    "dataset_id": dataset["id"],
                    "organism": "ecoli",
                    "params": {
                        "payload": {"outputs": ["other"], "custom_sequence": "ATGGCTGCTTAA"},
                        "budget": {"max_designs": 3},
                    },
                }
            ),
            content_type="application/json",
        ).json()

    run_analysis(run["id"])
    status = auth_client.get(f"/api/runs/{run['id']}").json()
    assert status["status"] == "COMPLETED"
    assert status["counts"]["candidates"] > 0


def test_an_unknown_example_key_names_the_available_ones(auth_client):
    response = auth_client.post(
        "/api/datasets/example",
        data=json.dumps({"key": "does-not-exist"}),
        content_type="application/json",
    )

    assert response.status_code == 422
    assert "ecoli-oxidative-stress" in response.json()["error"]["message"]


# --- Outputs ----------------------------------------------------------------------


def _run_with_outputs(client, dataset, outputs):
    from apps.analyses.tasks import run_analysis

    run = client.post(
        "/api/runs",
        data=json.dumps(
            {
                "input_mode": "de",
                "dataset_id": str(dataset.id),
                "organism": "ecoli",
                "params": {
                    "payload": {"outputs": outputs, "custom_sequence": None},
                    "budget": {"max_designs": 1},
                },
            }
        ),
        content_type="application/json",
    ).json()
    run_analysis(run["id"])
    return run["id"]


def test_the_candidate_list_says_what_each_one_expresses(
    auth_client, dataset, media_root, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks():
        run_id = _run_with_outputs(auth_client, dataset, ["gfp"])

    items = auth_client.get(f"/api/runs/{run_id}/candidates?limit=50").json()["items"]
    assert items
    assert all(c["output"] == "GFP" for c in items)


def test_an_output_with_no_payload_sequence_is_rejected_before_queueing(auth_client, dataset):
    """Every requested outcome must have an implemented payload; partial success is misleading."""
    from apps.analyses.models import AnalysisRun

    response = auth_client.post(
        "/api/runs",
        data={
            "input_mode": "de",
            "dataset_id": str(dataset.id),
            "organism": "ecoli",
            "params": {"payload": {"outputs": ["gfp", "ampr", "apoptosis"]}},
        },
        content_type="application/json",
    )
    assert response.status_code == 422
    assert not AnalysisRun.objects.exists()
    assert "apoptosis" in response.json()["error"]["message"]
