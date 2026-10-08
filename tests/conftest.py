"""Shared pytest fixtures."""

import dataclasses

import pytest
from django.core.files.base import ContentFile


@pytest.fixture
def screening_released(monkeypatch):
    """Provision screening for the duration of one test, so the release gate opens.

    Production is fail-closed and stays that way: no local screening adapter is
    provisioned, so ``fail_closed_release`` returns ``HOLD_SYSTEM`` and the pipeline
    writes the design table and audit manifests but no sequence-bearing artifact
    (``pipeline.py``'s release check). That is correct, and it is also why nothing
    downstream of the gate — FASTA, GenBank, SBOL, and the Platform's import and
    download path for them — would otherwise be exercised by any test.

    This flips only ``release_allowed`` on the result the real gate produced, leaving
    the audit manifest and its recomputed digest exactly as screening wrote them, so a
    test still sees genuine evidence rather than a fabricated clean screen. It is the
    same seam ``tests/engine/test_pipeline.py`` uses for the SBOL export.
    """
    import engine.pipeline as pipeline_module

    real = pipeline_module.fail_closed_release

    def allow(reference, sequence, *, host_context):
        return dataclasses.replace(
            real(reference, sequence, host_context=host_context), release_allowed=True
        )

    monkeypatch.setattr(pipeline_module, "fail_closed_release", allow)


# Real MG1655 locus tags, because LocalEngine joins a DE table against the bundled
# reference transcriptome by locus tag (docs/genes.md) — gene symbols raise an
# identifier-namespace failure. Deliberately three of the *shortest* real CDSs
# (297 + 276 + 324 nt): every test reaching this fixture runs a real compile, and
# trigger scanning cost scales with transcript length, so picking lacZ-sized genes
# here multiplied the Platform suite's runtime several-fold for no extra coverage —
# these tests assert that candidates and artifacts exist, never which gene produced
# them.
DATASET_CSV = (
    "gene_id,base_expression,target_expression,log2fc,padj\n"
    "b0005,0.82,6.41,2.97,0.0007\n"
    "b0022,1.24,5.93,2.26,0.0019\n"
    "b4062,0.31,4.77,3.94,0.0002\n"
)


@pytest.fixture
def user(db):
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create_user(
        username="researcher",
        email="researcher@example.org",
        password="test-password-123",
    )


@pytest.fixture
def other_user(db):
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create_user(
        username="someone-else",
        password="test-password-123",
    )


@pytest.fixture
def staff_user(db):
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create_superuser(
        username="admin",
        email="admin@example.org",
        password="test-password-123",
    )


@pytest.fixture
def media_root(tmp_path, settings):
    """Keep uploaded files out of var/ during tests."""
    settings.MEDIA_ROOT = tmp_path / "media"
    return settings.MEDIA_ROOT


@pytest.fixture
def dataset(user, media_root):
    from apps.common.checksums import sha256_bytes
    from apps.datasets.models import Dataset, ValidationStatus

    payload = DATASET_CSV.encode()
    obj = Dataset(
        name="expression.csv",
        checksum_sha256=sha256_bytes(payload),
        size_bytes=len(payload),
        validation_status=ValidationStatus.VALID,
        uploaded_by=user,
    )
    obj.file.save(obj.name, ContentFile(payload), save=False)
    obj.save()
    return obj


@pytest.fixture
def run(dataset, user):
    """A QUEUED run, ready to be executed."""
    from apps.analyses.models import AnalysisRun, RunStatus

    return AnalysisRun.objects.create(
        dataset=dataset,
        organism="ecoli",
        created_by=user,
        idempotency_key="test-key-001",
        params_snapshot={"max_triggers": 2},
        gate_families=["toehold"],
        scoring_profile="default",
        seed=42,
        status=RunStatus.QUEUED,
    )


@pytest.fixture
def job_result(run, dataset, tmp_path, screening_released):
    """A real engine result plus the directory its artifacts were written to.

    Depends on ``screening_released`` so the run produces its sequence-bearing
    artifacts too — the Platform's artifact import, listing and download paths are
    what most consumers of this fixture are testing, and with the gate closed there
    would be nothing but a design table and audit manifests to import.
    """
    from engine.client import LocalEngine
    from engine.contract import INPUT_DE, SCHEMA_VERSION, JobRequest

    output_dir = tmp_path / "engine-out"
    request = JobRequest(
        schema_version=SCHEMA_VERSION,
        run_id=str(run.id),
        idempotency_key=run.idempotency_key,
        input_mode=INPUT_DE,
        trigger_sequence="",
        input_path=dataset.file.path,
        input_checksum=dataset.checksum_sha256,
        organism="ecoli",
        params=run.params_snapshot,
        gate_families=run.gate_families,
        scoring_profile="default",
        seed=42,
        output_dir=str(output_dir),
    )
    result = LocalEngine().run(request, lambda pct, stage: True)
    assert result.status == "succeeded", result.error
    assert result.accepted, "The shared completed-run fixture must produce a real candidate."
    return result, output_dir


@pytest.fixture
def auth_client(client, user):
    """A client logged in as ``user``."""
    client.force_login(user)
    return client


@pytest.fixture
def other_client(other_user):
    """A client logged in as somebody who owns nothing.

    Its own Client instance, not the shared ``client`` fixture: a test that uses both
    this and ``auth_client`` would otherwise have one force_login silently override the
    other, and the authorization assertion would pass for the wrong reason.
    """
    from django.test import Client

    instance = Client()
    instance.force_login(other_user)
    return instance


@pytest.fixture
def completed_run(run, job_result):
    """A run with results already imported."""
    from apps.analyses.models import RunStatus
    from apps.results.services import import_job_result

    result, output_dir = job_result
    import_job_result(run, result, output_dir)

    run.status = RunStatus.COMPLETED
    run.progress_pct = 100
    run.stage = "Completed"
    run.engine_version = result.engine_version
    run.save()
    return run


@pytest.fixture
def csv_upload():
    """Factory for in-memory CSV uploads."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    def _make(content: str = DATASET_CSV, name: str = "expression.csv"):
        return SimpleUploadedFile(name, content.encode(), content_type="text/csv")

    return _make
