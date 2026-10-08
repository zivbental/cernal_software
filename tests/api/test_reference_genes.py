"""Resolve a gene and freeze its transcript when submitting through either API."""

import pytest

from apps.analyses.models import AnalysisRun

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    ("host", "symbol", "gene"),
    [
        ("human", "SELE", "ENSG00000007908"),
        ("ecoli", "thrA", "b0002"),
        ("yeast", "CDC28", "YBR160W"),
        ("c_acnes", "dnaA", "F6X01_RS00005"),
    ],
)
def test_lookup_and_submit_gene(client, user, host, symbol, gene):
    client.force_login(user)
    response = client.get("/api/reference-genes/resolve", {"organism": host, "gene": symbol})
    assert response.status_code == 200, response.content
    reference = response.json()
    assert reference["gene_id"] == gene
    response = client.post(
        "/api/runs",
        {
            "input_mode": "gene",
            "gene_id": symbol,
            "organism": host,
            "params": {
                "organism": host,
                "payload": {"outputs": ["other"], "custom_sequence": "ATGGCTGCTTAA"},
                "budget": {"max_designs": 3},
            },
        },
        content_type="application/json",
    )
    assert response.status_code == 202, response.content
    run = AnalysisRun.objects.get(pk=response.json()["id"])
    assert run.input_mode == "gene"
    assert run.dataset is None
    assert run.trigger_sequence == reference["sequence"]
    assert run.params_snapshot["gene_reference"]["gene_id"] == gene


def test_unknown_gene_is_rejected_before_queueing(client, user):
    client.force_login(user)
    response = client.post(
        "/api/runs",
        {
            "input_mode": "gene",
            "gene_id": "UNKNOWN",
            "organism": "human",
        },
        content_type="application/json",
    )
    assert response.status_code == 422
    assert not AnalysisRun.objects.exists()


def test_design_gene_input_uses_the_same_frozen_reference(client, user):
    client.force_login(user)
    response = client.post(
        "/api/design",
        {
            "gene_id": "SELE",
            "organism": "human",
            "gate_families": ["eukaryotic_toehold"],
        },
        content_type="application/json",
    )
    assert response.status_code == 202, response.content
    run = AnalysisRun.objects.get()
    assert run.input_mode == "gene"
    assert run.params_snapshot["gene_reference"]["gene_id"] == "ENSG00000007908"
    assert len(run.trigger_sequence) == 3875


@pytest.mark.parametrize(
    ("host", "gene"),
    [
        ("ecoli", "b0005"),
        ("yeast", "YER085C"),
        ("human", "ENSG00000201966"),
        ("c_acnes", "F6X01_RS12590"),
    ],
)
@pytest.mark.parametrize("format_name", ["csv", "tsv", "txt", "xlsx"])
def test_uploaded_formats_run_end_to_end(auth_client, media_root, host, gene, format_name):
    import io

    from django.core.files.uploadedfile import SimpleUploadedFile
    from openpyxl import Workbook

    from apps.analyses.services import execute_run

    workbook = Workbook()
    workbook.active.append(["gene_id", "log2fc", "padj"])
    workbook.active.append([gene, 3.2, 0.001])
    buffer = io.BytesIO()
    workbook.save(buffer)
    workbook.close()
    if format_name == "xlsx":
        payload = buffer.getvalue()
    else:
        delimiter = "," if format_name == "csv" else "\t"
        payload = (
            delimiter.join(["gene_id", "log2fc", "padj"])
            + "\n"
            + delimiter.join([gene, "3.2", "0.001"])
            + "\n"
        ).encode()
    response = auth_client.post(
        "/api/datasets",
        data={"file": SimpleUploadedFile(f"expression.{format_name}", payload)},
    )
    assert response.status_code == 201, response.content
    data = response.json()
    assert data["validation_status"] == "VALID"
    response = auth_client.post(
        "/api/runs",
        {
            "input_mode": "de",
            "dataset_id": data["id"],
            "organism": host,
            "params": {
                "organism": host,
                "payload": {"outputs": ["other"], "custom_sequence": "ATGGCTGCTTAA"},
                "budget": {"max_designs": 3},
            },
        },
        content_type="application/json",
    )
    assert response.status_code == 202, response.content
    run = AnalysisRun.objects.get(pk=response.json()["id"])
    execute_run(str(run.id))
    run.refresh_from_db()
    assert run.status == "COMPLETED", run.error_summary
    assert run.progress_pct == 100
    assert run.candidates.exists()
    assert run.artifacts.exists()
