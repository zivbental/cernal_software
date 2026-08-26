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


def test_an_example_can_be_loaded_into_a_project(auth_client, project, media_root):
    """It must be a real, validated dataset — not a special case downstream."""
    response = auth_client.post(
        f"/api/projects/{project.id}/datasets/example",
        data=json.dumps({"key": "ecoli-oxidative-stress"}),
        content_type="application/json",
    )
    body = response.json()

    assert response.status_code == 201
    assert body["validation_status"] == ValidationStatus.VALID
    assert body["validation_report"]["rows"] == 50
    assert len(body["checksum_sha256"]) == 64

    dataset = Dataset.objects.get(pk=body["id"])
    assert dataset.project_id == project.id
    assert dataset.file.storage.exists(dataset.file.name)


def test_an_example_run_completes_like_any_other(
    auth_client, project, media_root, django_capture_on_commit_callbacks
):
    from apps.analyses.tasks import run_analysis

    dataset = auth_client.post(
        f"/api/projects/{project.id}/datasets/example",
        data=json.dumps({"key": "ecoli-oxidative-stress"}),
        content_type="application/json",
    ).json()

    with django_capture_on_commit_callbacks():
        run = auth_client.post(
            f"/api/projects/{project.id}/runs",
            data=json.dumps(
                {
                    "input_mode": "de",
                    "dataset_id": dataset["id"],
                    "params": {"mock": {"candidate_count": 6}},
                }
            ),
            content_type="application/json",
        ).json()

    run_analysis(run["id"])
    assert auth_client.get(f"/api/runs/{run['id']}").json()["status"] == "COMPLETED"


def test_an_unknown_example_key_names_the_available_ones(auth_client, project):
    response = auth_client.post(
        f"/api/projects/{project.id}/datasets/example",
        data=json.dumps({"key": "does-not-exist"}),
        content_type="application/json",
    )

    assert response.status_code == 422
    assert "ecoli-oxidative-stress" in response.json()["error"]["message"]


def test_cannot_load_an_example_into_another_users_project(other_client, project):
    response = other_client.post(
        f"/api/projects/{project.id}/datasets/example",
        data=json.dumps({"key": "ecoli-oxidative-stress"}),
        content_type="application/json",
    )
    assert response.status_code == 404


# --- Outputs ----------------------------------------------------------------------


def _run_with_outputs(client, project, dataset, outputs, count=12):
    from apps.analyses.tasks import run_analysis

    run = client.post(
        f"/api/projects/{project.id}/runs",
        data=json.dumps(
            {
                "input_mode": "de",
                "dataset_id": str(dataset.id),
                "params": {
                    "payload": {"outputs": outputs, "custom_sequence": None},
                    "mock": {"candidate_count": count},
                },
            }
        ),
        content_type="application/json",
    ).json()
    run_analysis(run["id"])
    return run["id"]


def test_the_candidate_list_says_what_each_one_expresses(
    auth_client, project, dataset, media_root, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks():
        run_id = _run_with_outputs(auth_client, project, dataset, ["gfp"])

    items = auth_client.get(f"/api/runs/{run_id}/candidates?limit=50").json()["items"]
    assert items
    assert all(c["output"] == "GFP" for c in items)


def test_selecting_several_outputs_produces_plasmids_for_each(
    auth_client, project, dataset, media_root, django_capture_on_commit_callbacks
):
    """They are equivalent choices, so none of them is a sub-case of another."""
    with django_capture_on_commit_callbacks():
        run_id = _run_with_outputs(
            auth_client, project, dataset, ["gfp", "ampr", "apoptosis"], count=12
        )

    items = auth_client.get(
        f"/api/runs/{run_id}/candidates?limit=100&include_rejected=true"
    ).json()["items"]

    assert {c["output"] for c in items} == {"GFP", "AmpR", "Apoptosis inducer"}
