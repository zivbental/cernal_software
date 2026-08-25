"""Projects and dataset upload."""

import json

from apps.datasets.models import ValidationStatus

BAD_CSV = "gene_id,log2fc\nlacZ,not-a-number\n"
NO_EXPRESSION_CSV = "gene_id,notes\nlacZ,hello\n"


def _post(client, path, payload):
    return client.post(path, data=json.dumps(payload), content_type="application/json")


# --- Projects ---------------------------------------------------------------------


def test_create_and_list_a_project(auth_client):
    created = _post(auth_client, "/api/projects", {"name": "Switch A", "organism": "E. coli"})
    assert created.status_code == 201

    listing = auth_client.get("/api/projects").json()
    assert [p["name"] for p in listing] == ["Switch A"]
    assert listing[0]["dataset_count"] == 0


def test_duplicate_project_name_is_a_conflict(auth_client, project):
    response = _post(auth_client, "/api/projects", {"name": project.name, "organism": "E. coli"})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


def test_patch_updates_only_what_was_sent(auth_client, project):
    response = auth_client.patch(
        f"/api/projects/{project.id}",
        data=json.dumps({"organism": "S. cerevisiae"}),
        content_type="application/json",
    )
    body = response.json()

    assert response.status_code == 200
    assert body["organism"] == "S. cerevisiae"
    assert body["name"] == project.name


def test_a_project_with_runs_cannot_be_deleted(auth_client, project, run):
    response = auth_client.delete(f"/api/projects/{project.id}")

    assert response.status_code == 409
    assert "cannot be deleted" in response.json()["error"]["message"]


def test_an_empty_project_can_be_deleted(auth_client, project):
    assert auth_client.delete(f"/api/projects/{project.id}").status_code == 204


# --- Authorization ----------------------------------------------------------------


def test_another_users_project_is_invisible(other_client, project):
    """404, not 403 — 403 would confirm the project exists (§7.2)."""
    assert other_client.get(f"/api/projects/{project.id}").status_code == 404
    assert other_client.get("/api/projects").json() == []


def test_another_user_cannot_modify_or_delete(other_client, project):
    assert (
        other_client.patch(
            f"/api/projects/{project.id}",
            data=json.dumps({"name": "hijacked"}),
            content_type="application/json",
        ).status_code
        == 404
    )
    assert other_client.delete(f"/api/projects/{project.id}").status_code == 404


def test_staff_can_see_everything(client, staff_user, project):
    client.force_login(staff_user)
    assert client.get(f"/api/projects/{project.id}").status_code == 200


# --- Dataset upload ---------------------------------------------------------------


def test_uploading_a_good_dataset_marks_it_valid(auth_client, project, csv_upload, media_root):
    response = auth_client.post(f"/api/projects/{project.id}/datasets", data={"file": csv_upload()})
    body = response.json()

    assert response.status_code == 201
    assert body["validation_status"] == ValidationStatus.VALID
    assert body["validation_report"]["rows"] == 3
    assert len(body["checksum_sha256"]) == 64


def test_upload_response_exposes_no_storage_path(auth_client, project, csv_upload, media_root):
    body = auth_client.post(
        f"/api/projects/{project.id}/datasets", data={"file": csv_upload()}
    ).json()

    assert "var/" not in json.dumps(body)
    assert "media" not in json.dumps(body)


def test_a_dataset_with_bad_numbers_is_marked_invalid(auth_client, project, csv_upload, media_root):
    body = auth_client.post(
        f"/api/projects/{project.id}/datasets", data={"file": csv_upload(BAD_CSV)}
    ).json()

    assert body["validation_status"] == ValidationStatus.INVALID
    assert any("Non-numeric" in error for error in body["validation_report"]["errors"])


def test_a_dataset_without_an_expression_column_is_invalid(
    auth_client, project, csv_upload, media_root
):
    body = auth_client.post(
        f"/api/projects/{project.id}/datasets", data={"file": csv_upload(NO_EXPRESSION_CSV)}
    ).json()

    assert body["validation_status"] == ValidationStatus.INVALID
    assert any("expression column" in error for error in body["validation_report"]["errors"])


def test_an_empty_file_is_refused_outright(auth_client, project, csv_upload, media_root):
    response = auth_client.post(
        f"/api/projects/{project.id}/datasets", data={"file": csv_upload("", "empty.csv")}
    )

    assert response.status_code == 422
    assert "empty" in response.json()["error"]["message"]


def test_an_oversized_file_is_refused(auth_client, project, csv_upload, media_root, settings):
    settings.MAX_DATASET_MB = 0.0001
    response = auth_client.post(f"/api/projects/{project.id}/datasets", data={"file": csv_upload()})

    assert response.status_code == 422
    assert "larger than" in response.json()["error"]["message"]


def test_a_dataset_used_by_a_run_cannot_be_deleted(auth_client, dataset, run):
    response = auth_client.delete(f"/api/datasets/{dataset.id}")

    assert response.status_code == 409
    assert "must not outlive" in response.json()["error"]["message"]


def test_an_unused_dataset_can_be_deleted(auth_client, dataset):
    assert auth_client.delete(f"/api/datasets/{dataset.id}").status_code == 204


def test_cannot_upload_into_another_users_project(other_client, project, csv_upload, media_root):
    response = other_client.post(
        f"/api/projects/{project.id}/datasets", data={"file": csv_upload()}
    )
    assert response.status_code == 404
