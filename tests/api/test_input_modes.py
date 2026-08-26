"""Direct-trigger submissions and the widened upload formats (Step 4 §6.2)."""

import io
import json

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.analyses.models import AnalysisRun, InputMode, RunStatus

TRIGGER = "AUGGCUAGCAAGGGCGAGGAGCUGUUCACCGGGGUG"


def _submit(client, project, **payload):
    return client.post(
        f"/api/projects/{project.id}/runs",
        data=json.dumps(payload),
        content_type="application/json",
    )


# --- Direct trigger mode ----------------------------------------------------------


def test_a_run_can_be_submitted_without_any_dataset(
    auth_client, project, django_capture_on_commit_callbacks
):
    """Discovery is skipped: the researcher already knows the transcript."""
    with django_capture_on_commit_callbacks():
        response = _submit(auth_client, project, input_mode="direct", trigger_sequence=TRIGGER)
    body = response.json()

    assert response.status_code == 202
    assert body["input_mode"] == InputMode.DIRECT
    assert body["dataset_id"] is None
    assert body["status"] == RunStatus.QUEUED


def test_a_direct_run_executes_end_to_end(
    auth_client, project, media_root, django_capture_on_commit_callbacks
):
    from apps.analyses.tasks import run_analysis

    with django_capture_on_commit_callbacks():
        run_id = _submit(
            auth_client,
            project,
            input_mode="direct",
            trigger_sequence=TRIGGER,
            params={"mock": {"candidate_count": 6}},
        ).json()["id"]

    run_analysis(run_id)

    status = auth_client.get(f"/api/runs/{run_id}").json()
    assert status["status"] == RunStatus.COMPLETED
    assert status["counts"]["candidates"] == 6


def test_dna_is_accepted_and_normalized_to_rna(
    auth_client, project, django_capture_on_commit_callbacks
):
    """Researchers paste DNA as often as RNA; silently failing on T would be hostile."""
    with django_capture_on_commit_callbacks():
        run_id = _submit(
            auth_client,
            project,
            input_mode="direct",
            trigger_sequence="ATGGCTAGCAAGGGCGAGGAGCTGTTCACCGGGGTG",
        ).json()["id"]

    stored = AnalysisRun.objects.get(pk=run_id).trigger_sequence
    assert "T" not in stored
    assert stored.startswith("AUGGCUAGC")


def test_whitespace_in_a_pasted_sequence_is_ignored(
    auth_client, project, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks():
        run_id = _submit(
            auth_client,
            project,
            input_mode="direct",
            trigger_sequence="AUGGCUAGC AAGGGCGAG\nGAGCUGUUC ACCGGGGUG",
        ).json()["id"]

    assert AnalysisRun.objects.get(pk=run_id).trigger_sequence == TRIGGER


@pytest.mark.parametrize(
    ("sequence", "expected"),
    [
        ("", "Paste the trigger"),
        ("ACGU", "too short"),
        ("AUGGCUAGCAAGGGCGAGGAGCUGXXZZ", "only A, C, G, U"),
    ],
)
def test_a_bad_trigger_sequence_is_refused(auth_client, project, sequence, expected):
    response = _submit(auth_client, project, input_mode="direct", trigger_sequence=sequence)

    assert response.status_code == 422
    assert expected in response.json()["error"]["message"]


def test_a_de_run_still_requires_a_dataset(auth_client, project):
    response = _submit(auth_client, project, input_mode="de")

    assert response.status_code == 422
    assert "dataset is required" in response.json()["error"]["message"]


def test_the_database_refuses_a_run_with_two_input_sources(project, dataset, user):
    """A DIRECT run holding a dataset is contradictory; the constraint says so."""
    from django.db import IntegrityError, transaction

    with pytest.raises(IntegrityError), transaction.atomic():
        AnalysisRun.objects.create(
            project=project,
            created_by=user,
            idempotency_key="contradictory",
            input_mode=InputMode.DIRECT,
            dataset=dataset,
        )


# --- Upload formats ---------------------------------------------------------------


def _upload(client, project, content, name):
    payload = content if isinstance(content, bytes) else content.encode()
    return client.post(
        f"/api/projects/{project.id}/datasets",
        data={"file": SimpleUploadedFile(name, payload)},
    )


def test_a_tsv_upload_is_parsed(auth_client, project, media_root):
    tsv = "gene_id\tlog2fc\tpadj\nlacZ\t2.97\t0.0007\nkatG\t2.26\t0.0019\n"
    body = _upload(auth_client, project, tsv, "de.tsv").json()

    assert body["validation_status"] == "VALID"
    assert body["validation_report"]["rows"] == 2


def test_deseq2_column_names_are_recognised(auth_client, project, media_root):
    """DESeq2, edgeR and Excel all spell it differently, and none of them are wrong."""
    csv_text = "gene\tlog2FoldChange\tbaseMean\tpadj\nlacZ\t2.97\t120.4\t0.0007\n"
    body = _upload(auth_client, project, csv_text, "deseq2.tsv").json()

    assert body["validation_status"] == "VALID"
    detected = body["validation_report"]["detected_columns"]
    assert detected["gene"] == "gene_id"
    assert detected["log2FoldChange"] == "log2fc"
    assert detected["baseMean"] == "base_expression"


def test_an_xlsx_upload_is_parsed(auth_client, project, media_root):
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["gene_id", "log2FoldChange", "padj"])
    sheet.append(["lacZ", 2.97, 0.0007])
    sheet.append(["katG", 2.26, 0.0019])
    buffer = io.BytesIO()
    workbook.save(buffer)

    body = _upload(auth_client, project, buffer.getvalue(), "de.xlsx").json()

    assert body["validation_status"] == "VALID"
    assert body["validation_report"]["rows"] == 2


def test_a_spreadsheet_named_csv_gets_a_useful_message(auth_client, project, media_root):
    """A common, confusing mistake — say what is actually wrong."""
    from openpyxl import Workbook

    buffer = io.BytesIO()
    Workbook().save(buffer)

    body = _upload(auth_client, project, buffer.getvalue(), "de.csv").json()

    assert body["validation_status"] == "INVALID"
    assert any("Excel workbook" in e for e in body["validation_report"]["errors"])


def test_an_unrecognised_expression_column_names_what_is_accepted(auth_client, project, media_root):
    body = _upload(auth_client, project, "gene_id,notes\nlacZ,hello\n", "de.csv").json()

    assert body["validation_status"] == "INVALID"
    assert any("log2FoldChange" in e for e in body["validation_report"]["errors"])


# --- Cross-project run listing ----------------------------------------------------


def test_recent_runs_are_listed_across_projects(auth_client, run):
    body = auth_client.get("/api/runs?limit=5").json()
    assert [r["id"] for r in body] == [str(run.id)]


def test_another_users_runs_are_not_listed(other_client, run):
    assert other_client.get("/api/runs").json() == []
