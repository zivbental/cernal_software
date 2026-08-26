"""Shared pytest fixtures."""

import pytest
from django.core.files.base import ContentFile

DATASET_CSV = (
    "gene_id,base_expression,target_expression,log2fc,padj\n"
    "lacZ,0.82,6.41,2.97,0.0007\n"
    "katG,1.24,5.93,2.26,0.0019\n"
    "soxS,0.31,4.77,3.94,0.0002\n"
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
def project(user):
    from apps.projects.models import Project

    return Project.objects.create(
        owner=user,
        name="Demo project",
        organism="E. coli",
        biological_objective="Detect the transition and express GFP.",
    )


@pytest.fixture
def dataset(project, user, media_root):
    from apps.common.checksums import sha256_bytes
    from apps.datasets.models import Dataset, ValidationStatus

    payload = DATASET_CSV.encode()
    obj = Dataset(
        project=project,
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
def run(project, dataset, user):
    """A QUEUED run, ready to be executed."""
    from apps.analyses.models import AnalysisRun, RunStatus

    return AnalysisRun.objects.create(
        project=project,
        dataset=dataset,
        created_by=user,
        idempotency_key="test-key-001",
        params_snapshot={"max_triggers": 2},
        gate_families=["toehold"],
        scoring_profile="default",
        seed=42,
        status=RunStatus.QUEUED,
    )


@pytest.fixture
def job_result(run, dataset, tmp_path):
    """A real MockEngine result plus the directory its artifacts were written to."""
    from engine.client import MockEngine
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
        organism="E. coli",
        params={"mock": {"candidate_count": 20}},
        gate_families=["toehold"],
        scoring_profile="default",
        seed=42,
        output_dir=str(output_dir),
    )
    return MockEngine().run(request, lambda pct, stage: True), output_dir


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
