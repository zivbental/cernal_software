"""Importing an engine result into the durable model.

The load-bearing guarantee is atomicity: a half-imported run must be impossible
(docs/software-design.md §6.2).
"""

import dataclasses

import pytest

from apps.common.checksums import sha256_file
from apps.results.models import Artifact, Candidate, CandidateMetric
from apps.results.services import ResultImportError, import_job_result


def test_import_writes_candidates_metrics_and_artifacts(run, job_result):
    result, output_dir = job_result

    summary = import_job_result(run, result, output_dir)

    assert summary.candidates == len(result.candidates)
    assert summary.metrics == sum(len(c.metrics) for c in result.candidates)
    assert summary.artifacts == len(result.artifacts)
    assert run.candidates.count() == summary.candidates


def test_imported_candidates_keep_their_engine_ref(run, job_result):
    result, output_dir = job_result
    import_job_result(run, result, output_dir)

    assert set(run.candidates.values_list("engine_ref", flat=True)) == {
        c.ref for c in result.candidates
    }


def test_rejected_candidates_are_imported_with_their_reasons(run, job_result):
    """Rule 8 survives the trip through the database."""
    result, output_dir = job_result
    import_job_result(run, result, output_dir)

    rejected = run.candidates.filter(is_rejected=True)
    assert rejected.count() == len(result.rejected)
    for candidate in rejected:
        assert candidate.rejection_reason
        assert candidate.rank is None


def test_metric_decomposition_survives_the_import(run, job_result):
    result, output_dir = job_result
    import_job_result(run, result, output_dir)

    candidate = run.candidates.first()
    metrics = {m.name: m for m in candidate.metrics.all()}
    assert "state_separation" in metrics
    assert metrics["state_separation"].weight > 0
    assert metrics["state_separation"].direction in ("HIGHER_BETTER", "LOWER_BETTER")


def test_artifact_bytes_are_stored_and_checksums_still_match(run, job_result):
    result, output_dir = job_result
    import_job_result(run, result, output_dir)

    for artifact in run.artifacts.all():
        assert artifact.file.storage.exists(artifact.file.name)
        assert sha256_file(artifact.file.path) == artifact.checksum_sha256
        assert artifact.size_bytes > 0


def test_candidate_artifacts_are_linked_to_their_candidate(run, job_result):
    result, output_dir = job_result
    import_job_result(run, result, output_dir)

    fastas = run.artifacts.filter(kind="sequence_fasta")
    assert fastas.exists()
    for artifact in fastas:
        assert artifact.candidate is not None

    tables = run.artifacts.filter(kind="design_table")
    assert tables.exists()
    for artifact in tables:
        assert artifact.candidate is None, "run-level artifacts must not claim a candidate"


def test_artifact_subdirectories_are_preserved(run, job_result):
    result, output_dir = job_result
    import_job_result(run, result, output_dir)

    names = [a.file.name for a in run.artifacts.all()]
    assert any("/sequences/" in name for name in names)


# --- Rejection paths --------------------------------------------------------------


def test_a_checksum_mismatch_aborts_the_import(run, job_result):
    result, output_dir = job_result
    tampered = dataclasses.replace(result, input_checksum="0" * 64)

    with pytest.raises(ResultImportError, match="different input checksum"):
        import_job_result(run, tampered, output_dir)

    assert run.candidates.count() == 0


def test_a_missing_artifact_file_aborts_the_whole_import(run, job_result):
    """Atomicity: no candidates may survive a failed import."""
    result, output_dir = job_result
    (output_dir / result.artifacts[0].path).unlink()

    with pytest.raises(ResultImportError, match="did not write"):
        import_job_result(run, result, output_dir)

    assert Candidate.objects.count() == 0
    assert CandidateMetric.objects.count() == 0
    assert Artifact.objects.count() == 0


def test_a_corrupted_artifact_aborts_the_whole_import(run, job_result):
    result, output_dir = job_result
    (output_dir / result.artifacts[0].path).write_text("tampered")

    with pytest.raises(ResultImportError, match="failed its checksum"):
        import_job_result(run, result, output_dir)

    assert Candidate.objects.count() == 0


def test_an_artifact_naming_an_unknown_candidate_aborts_the_import(run, job_result):
    result, output_dir = job_result
    artifacts = list(result.artifacts)
    artifacts[-1] = dataclasses.replace(artifacts[-1], candidate_ref="ghost")
    broken = dataclasses.replace(result, artifacts=artifacts)

    with pytest.raises(ResultImportError, match="unknown candidate"):
        import_job_result(run, broken, output_dir)

    assert Candidate.objects.count() == 0


def test_importing_twice_is_refused(run, job_result):
    """Re-import must not duplicate results; Step 3 clears the run first if it retries."""
    result, output_dir = job_result
    import_job_result(run, result, output_dir)

    with pytest.raises(ResultImportError, match="already has imported results"):
        import_job_result(run, result, output_dir)


def test_import_does_not_change_run_status(run, job_result):
    """Rule 5: transitions belong to apps/analyses/services.py, not here."""
    result, output_dir = job_result
    before = run.status

    import_job_result(run, result, output_dir)
    run.refresh_from_db()

    assert run.status == before
