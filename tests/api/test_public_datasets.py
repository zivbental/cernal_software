"""Public dataset catalog + materialize + preview (docs/public-datasets.md).

Mirrors tests/api/test_example_and_outputs.py's shape exactly — a curated catalog entry
should be indistinguishable from a bundled example once materialized.
"""

import json

from apps.datasets.models import Dataset, ValidationStatus

ECOLI_COMPARISON_KEY = "ecoli__88048__42635036"  # Ampicillin treatment — real, curated


def test_organisms_are_advertised_unauthenticated(client, db):
    body = client.get("/api/public-datasets/organisms").json()

    keys = {o["key"] for o in body}
    assert keys == {"human", "yeast", "ecoli"}


def test_experiments_are_listed_per_organism_unauthenticated(client, db):
    body = client.get("/api/public-datasets/experiments?organism=ecoli").json()

    assert len(body) == 5
    assert all(e["organism"] == "ecoli" for e in body)


def test_comparisons_are_listed_per_experiment(client, db):
    body = client.get("/api/public-datasets/comparisons?experiment=ecoli__88048").json()

    assert len(body) == 1
    assert body[0]["comparison_key"] == ECOLI_COMPARISON_KEY


def test_comparison_info_is_the_full_info_card(client, db):
    body = client.get(f"/api/public-datasets/{ECOLI_COMPARISON_KEY}").json()

    assert body["provider"] == "bvbrc"
    assert body["organism"] == "ecoli"
    assert body["source_url"].startswith("https://www.bv-brc.org/")
    assert body["gene_count"] > 0


def test_an_unknown_comparison_key_is_a_422_naming_the_conflict(client, db):
    response = client.get("/api/public-datasets/not-a-real-key")

    assert response.status_code == 422
    assert "not-a-real-key" in response.json()["error"]["message"]


def test_materializing_a_public_dataset_requires_authentication(client, db):
    response = client.post(
        "/api/public-datasets/materialize",
        data=json.dumps({"comparison_key": ECOLI_COMPARISON_KEY}),
        content_type="application/json",
    )
    assert response.status_code == 401


def test_a_public_dataset_can_be_materialized(auth_client, user, media_root):
    """Same standard test_an_example_can_be_loaded holds create_example_dataset to."""
    response = auth_client.post(
        "/api/public-datasets/materialize",
        data=json.dumps({"comparison_key": ECOLI_COMPARISON_KEY}),
        content_type="application/json",
    )
    body = response.json()

    assert response.status_code == 201
    assert body["validation_status"] == ValidationStatus.VALID
    assert len(body["checksum_sha256"]) == 64
    assert body["provenance"]["provider"] == "bvbrc"
    assert body["provenance"]["experiment_accession"] == "88048"

    dataset = Dataset.objects.get(pk=body["id"])
    assert dataset.uploaded_by_id == user.id
    assert dataset.file.storage.exists(dataset.file.name)


def test_an_uploaded_dataset_has_no_provenance(auth_client, media_root):
    from django.core.files.uploadedfile import SimpleUploadedFile

    response = auth_client.post(
        "/api/datasets",
        data={"file": SimpleUploadedFile("de.csv", b"gene_id,log2fc\nlacZ,2.1\n")},
    )
    assert response.json()["provenance"] is None


def test_materializing_an_unknown_key_is_a_422(auth_client):
    response = auth_client.post(
        "/api/public-datasets/materialize",
        data=json.dumps({"comparison_key": "not-a-real-key"}),
        content_type="application/json",
    )
    assert response.status_code == 422
    assert "not-a-real-key" in response.json()["error"]["message"]


# --- preview (shared by public and uploaded datasets) --------------------------------


def test_preview_ranks_by_absolute_log2fc_descending(auth_client, dataset, media_root):
    """`dataset` fixture (tests/conftest.py) is a small, valid, already-uploaded CSV."""
    response = auth_client.get(f"/api/datasets/{dataset.id}/preview")
    body = response.json()

    assert response.status_code == 200
    values = [abs(row["log2fc"]) for row in body["rows"] if row["log2fc"] is not None]
    assert values == sorted(values, reverse=True)
    assert body["total_rows"] == len(body["rows"])  # small fixture, nothing truncated
    assert body["truncated"] is False


def test_preview_of_a_public_dataset_keeps_gene_symbol_separate_from_gene_id(
    auth_client, user, media_root
):
    from apps.expression.services import materialize_public_dataset

    dataset = materialize_public_dataset(user=user, comparison_key=ECOLI_COMPARISON_KEY)
    response = auth_client.get(f"/api/datasets/{dataset.id}/preview")
    body = response.json()

    assert response.status_code == 200
    assert body["rows"]
    first = body["rows"][0]
    assert first["gene_id"] and first["gene_symbol"]
    assert first["gene_id"] != first["gene_symbol"]  # b#### locus tag, not a repeat of the symbol


def test_preview_is_owner_scoped(auth_client, other_client, dataset, media_root):
    """404, not 403, for someone else's dataset (architecture.md §7.2)."""
    response = other_client.get(f"/api/datasets/{dataset.id}/preview")
    assert response.status_code == 404
