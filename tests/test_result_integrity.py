"""Strict result-boundary validation and lossless exports."""

import csv
import io
from pathlib import Path
from unittest.mock import patch

import pytest

from apps.results.models import Artifact, CandidateMetric
from apps.results.services import ResultImportError, build_candidates_csv, import_job_result
from engine.contract import ArtifactRef, CandidateResult, JobResult, MetricValue


def empty_result(run, **overrides):
    values = {
        "schema_version": "1",
        "engine_version": "test",
        "status": "succeeded",
        "input_checksum": run.dataset.checksum_sha256,
        "params": run.params_snapshot,
    }
    return JobResult(**{**values, **overrides})


@pytest.mark.parametrize(
    "overrides",
    [
        {"schema_version": "999"},
        {"input_checksum": ""},
        {"params": {"changed": True}},
        {"status": "failed"},
        {"engine_version": ""},
    ],
)
def test_invalid_manifest_identity_is_rejected_before_persistence(run, tmp_path, overrides):
    with pytest.raises(ResultImportError):
        import_job_result(run, empty_result(run, **overrides), tmp_path)
    assert not run.candidates.exists()
    assert not run.artifacts.exists()


@pytest.mark.parametrize(
    "path", ["../outside.txt", "/etc/passwd", "C:/outside.txt", "sub\\outside.txt"]
)
def test_artifact_path_escape_is_rejected(run, tmp_path, path):
    artifact = ArtifactRef("test", path, "text/plain", "0" * 64)
    with pytest.raises(ResultImportError, match=r"path|directory"):
        import_job_result(run, empty_result(run, artifacts=[artifact]), tmp_path)
    assert not run.artifacts.exists()


def test_symlink_escape_is_rejected(run, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("private")
    output = tmp_path / "output"
    output.mkdir()
    (output / "linked.txt").symlink_to(outside)
    artifact = ArtifactRef("test", "linked.txt", "text/plain", "0" * 64)
    with pytest.raises(ResultImportError, match="directory"):
        import_job_result(run, empty_result(run, artifacts=[artifact]), output)
    assert not run.artifacts.exists()


def test_missing_artifact_digest_is_rejected(run, tmp_path):
    (tmp_path / "x.txt").write_text("content")
    artifact = ArtifactRef("test", "x.txt", "text/plain", "")
    with pytest.raises(ResultImportError, match="SHA-256"):
        import_job_result(run, empty_result(run, artifacts=[artifact]), tmp_path)


def make_candidate(metrics=(), **overrides):
    values = {
        "ref": "candidate-1",
        "rank": 1,
        "overall_score": 0.5,
        "gate_family": "toehold",
        "logic_type": "single",
        "triggers": {},
        "design": {},
        "summary": "test",
        "metrics": list(metrics),
    }
    return CandidateResult(**{**values, **overrides})


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_measurements_are_rejected(run, tmp_path, value):
    metric = MetricValue("test", value, 0.5, 1, "HIGHER_BETTER")
    with pytest.raises(ResultImportError, match="finite"):
        import_job_result(run, empty_result(run, candidates=[make_candidate([metric])]), tmp_path)
    assert not CandidateMetric.objects.exists()


def test_duplicate_candidate_references_are_rejected(run, tmp_path):
    candidate = make_candidate()
    with pytest.raises(ResultImportError, match="unique"):
        import_job_result(run, empty_result(run, candidates=[candidate, candidate]), tmp_path)


def test_failed_storage_import_removes_saved_bytes_and_rows(run, tmp_path, media_root):
    real_save = Artifact.save
    calls = 0

    def fail_second(obj, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected storage failure")
        return real_save(obj, *args, **kwargs)

    with patch.object(Artifact, "save", fail_second), pytest.raises(OSError):
        import_job_result(run, empty_result(run), tmp_path)
    assert not Artifact.objects.exists()
    assert not [
        path for path in Path(media_root).rglob("*") if path.is_file() and "artifacts" in path.parts
    ]


def test_csv_preserves_zero_negative_positive_and_missing_values(run, tmp_path):
    metrics = [
        MetricValue("zero", 0, 0, 1, "LOWER_BETTER"),
        MetricValue("missing", None, None, 1, "HIGHER_BETTER"),
        MetricValue("negative", -1.5, 0.25, 1, "HIGHER_BETTER"),
        MetricValue("positive", 2, 1, 1, "HIGHER_BETTER"),
    ]
    import_job_result(run, empty_result(run, candidates=[make_candidate(metrics)]), tmp_path)
    exported = build_candidates_csv(run)
    row = next(csv.DictReader(io.StringIO(exported)))
    assert row["zero_raw"] == row["zero_normalized"] == "0.0"
    assert row["missing_raw"] == row["missing_normalized"] == ""
    assert row["negative_raw"] == "-1.5"
    assert row["positive_raw"] == "2.0"
    assert run.artifacts.get(kind="summary_table").file.read().decode() == exported
