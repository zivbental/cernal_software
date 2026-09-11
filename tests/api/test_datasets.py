"""Dataset upload — flat, owned by the uploading user (no project scoping)."""

import json

from apps.datasets.models import ValidationStatus

BAD_CSV = "gene_id,log2fc\nlacZ,not-a-number\n"
NO_EXPRESSION_CSV = "gene_id,notes\nlacZ,hello\n"


def _post(client, path, payload):
    return client.post(path, data=json.dumps(payload), content_type="application/json")


# --- Dataset upload ---------------------------------------------------------------


def test_uploading_a_good_dataset_marks_it_valid(auth_client, csv_upload, media_root):
    response = auth_client.post("/api/datasets", data={"file": csv_upload()})
    body = response.json()

    assert response.status_code == 201
    assert body["validation_status"] == ValidationStatus.VALID
    assert body["validation_report"]["rows"] == 3
    assert len(body["checksum_sha256"]) == 64


def test_upload_response_exposes_no_storage_path(auth_client, csv_upload, media_root):
    body = auth_client.post("/api/datasets", data={"file": csv_upload()}).json()

    assert "var/" not in json.dumps(body)
    assert "media" not in json.dumps(body)


def test_a_dataset_with_bad_numbers_is_marked_invalid(auth_client, csv_upload, media_root):
    body = auth_client.post("/api/datasets", data={"file": csv_upload(BAD_CSV)}).json()

    assert body["validation_status"] == ValidationStatus.INVALID
    assert any("Non-numeric" in error for error in body["validation_report"]["errors"])


def test_a_dataset_without_an_expression_column_is_invalid(auth_client, csv_upload, media_root):
    body = auth_client.post("/api/datasets", data={"file": csv_upload(NO_EXPRESSION_CSV)}).json()

    assert body["validation_status"] == ValidationStatus.INVALID
    assert any("expression column" in error for error in body["validation_report"]["errors"])


def test_an_empty_file_is_refused_outright(auth_client, csv_upload, media_root):
    response = auth_client.post("/api/datasets", data={"file": csv_upload("", "empty.csv")})

    assert response.status_code == 422
    assert "empty" in response.json()["error"]["message"]


def test_an_oversized_file_is_refused(auth_client, csv_upload, media_root, settings):
    settings.MAX_DATASET_MB = 0.0001
    response = auth_client.post("/api/datasets", data={"file": csv_upload()})

    assert response.status_code == 422
    assert "larger than" in response.json()["error"]["message"]


def test_a_dataset_used_by_a_run_cannot_be_deleted(auth_client, dataset, run):
    response = auth_client.delete(f"/api/datasets/{dataset.id}")

    assert response.status_code == 409
    assert "must not outlive" in response.json()["error"]["message"]


def test_an_unused_dataset_can_be_deleted(auth_client, dataset):
    assert auth_client.delete(f"/api/datasets/{dataset.id}").status_code == 204


def test_listing_datasets_is_scoped_to_the_owner(auth_client, other_client, dataset):
    assert [d["id"] for d in auth_client.get("/api/datasets").json()] == [str(dataset.id)]
    assert other_client.get("/api/datasets").json() == []


# --- Authorization ----------------------------------------------------------------


def test_another_users_dataset_is_invisible(other_client, dataset):
    """404, not 403 — 403 would confirm the dataset exists (§7.2)."""
    assert other_client.get(f"/api/datasets/{dataset.id}").status_code == 404


def test_another_user_cannot_delete(other_client, dataset):
    assert other_client.delete(f"/api/datasets/{dataset.id}").status_code == 404


def test_staff_can_see_everything(client, staff_user, dataset):
    client.force_login(staff_user)
    assert client.get(f"/api/datasets/{dataset.id}").status_code == 200
