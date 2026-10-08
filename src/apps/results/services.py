"""Importing an engine result into the Platform's durable model.

Pulled forward from Step 3 so that ``seed_demo`` and the run lifecycle share one
implementation rather than duplicating it. Step 3 calls this from
``apps/analyses/services.py`` after a successful run.

**This module does not touch run status.** Transitions belong to
``apps/analyses/services.py`` (rule 5); this only writes results.
"""

import csv
import io
import json
import logging
import math
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.common.checksums import sha256_bytes
from apps.results.models import Artifact, Candidate, CandidateMetric
from engine.contract import HIGHER_BETTER, LOWER_BETTER, SCHEMA_VERSION, SUCCEEDED, JobResult

logger = logging.getLogger(__name__)


class ResultImportError(Exception):
    """The result manifest could not be trusted or written."""


@dataclass(frozen=True)
class ImportSummary:
    candidates: int
    metrics: int
    artifacts: int


def import_job_result(run, result: JobResult, output_dir: str | Path) -> ImportSummary:
    """Write one engine result into the database, atomically.

    Either the whole result lands or none of it does — a half-imported run must be
    impossible (docs/architecture.md §6.2).

    Artifact *files* are written outside the database's control, so a rollback can leave
    orphan bytes under ``var/media/artifacts/``. That is harmless: nothing references
    them, and the run will not be marked COMPLETED.
    """
    written = []
    try:
        with transaction.atomic():
            return _import_job_result(run, result, output_dir, written)
    except Exception:
        for storage, name in reversed(written):
            try:
                storage.delete(name)
            except Exception:
                logger.exception("Unable to remove failed-import artifact for run %s", run.id)
        raise


def _import_job_result(run, result, output_dir, written):
    _verify_manifest(run, result)

    if run.candidates.exists():
        raise ResultImportError("This run already has imported results.")

    candidates_by_ref: dict[str, Candidate] = {}
    metric_rows: list[CandidateMetric] = []

    for item in result.candidates:
        candidate = Candidate.objects.create(
            run=run,
            engine_ref=item.ref,
            rank=item.rank,
            overall_score=item.overall_score,
            gate_family=item.gate_family,
            logic_type=item.logic_type,
            triggers=item.triggers,
            design=item.design,
            summary=item.summary,
            warnings=item.warnings,
            is_rejected=item.is_rejected,
            rejection_reason=item.rejection_reason,
        )
        candidates_by_ref[item.ref] = candidate

        metric_rows.extend(
            CandidateMetric(
                candidate=candidate,
                name=metric.name,
                raw_value=metric.raw_value,
                normalized_value=metric.normalized_value,
                weight=metric.weight,
                direction=metric.direction,
            )
            for metric in item.metrics
        )

    CandidateMetric.objects.bulk_create(metric_rows)

    artifact_count = _import_artifacts(run, result, Path(output_dir), candidates_by_ref, written)
    artifact_count += _write_derived_artifacts(run, result, written)

    logger.info(
        "Imported result for run %s: %d candidates, %d metrics, %d artifacts",
        run.id,
        len(candidates_by_ref),
        len(metric_rows),
        artifact_count,
    )
    return ImportSummary(
        candidates=len(candidates_by_ref), metrics=len(metric_rows), artifacts=artifact_count
    )


def _verify_manifest(run, result: JobResult) -> None:
    """Validate identity, finite measurements and references before creating any row."""
    if result.schema_version != SCHEMA_VERSION:
        raise ResultImportError("The result schema version is incompatible.")
    if result.status != SUCCEEDED or result.error:
        raise ResultImportError("Only a succeeded result without an error can be imported.")
    if not result.engine_version:
        raise ResultImportError("The result is missing its engine version.")
    expected = run.dataset.checksum_sha256 if run.dataset_id else ""
    if result.input_checksum != expected:
        raise ResultImportError(
            "The engine reported a different input checksum than the dataset that was submitted."
        )
    if result.params != run.params_snapshot:
        raise ResultImportError("The engine reported a different configuration than was submitted.")
    try:
        json.dumps(result.params, allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise ResultImportError(
            "The result configuration must contain finite JSON values."
        ) from exc
    refs = set()
    ranks = set()
    for candidate in result.candidates:
        if not candidate.ref or candidate.ref in refs:
            raise ResultImportError("Candidate references must be nonempty and unique.")
        refs.add(candidate.ref)
        if candidate.is_rejected and (candidate.rank is not None or not candidate.rejection_reason):
            raise ResultImportError("Rejected candidates must be unranked and include a reason.")
        if candidate.rank is not None:
            if type(candidate.rank) is not int or candidate.rank < 1 or candidate.rank in ranks:
                raise ResultImportError("Candidate ranks must be positive and unique.")
            ranks.add(candidate.rank)
        _check_number(candidate.overall_score, "overall_score", minimum=0, maximum=1)
        try:
            json.dumps([candidate.triggers, candidate.design], allow_nan=False)
        except (ValueError, TypeError) as exc:
            raise ResultImportError("Candidate data must contain finite JSON values.") from exc
        names = set()
        for metric in candidate.metrics:
            if not metric.name or metric.name in names:
                raise ResultImportError("Metric names must be nonempty and unique per candidate.")
            names.add(metric.name)
            _check_number(metric.raw_value, "raw_value")
            _check_number(metric.normalized_value, "normalized_value", minimum=0, maximum=1)
            _check_number(metric.weight, "weight", minimum=0, nullable=False)
            if metric.direction not in (HIGHER_BETTER, LOWER_BETTER):
                raise ResultImportError("The result contains an unknown metric direction.")
    paths = set()
    for artifact in result.artifacts:
        if artifact.path in paths:
            raise ResultImportError("Artifact paths must be unique.")
        paths.add(artifact.path)
        if not re.fullmatch(r"[0-9a-f]{64}", artifact.checksum_sha256 or ""):
            raise ResultImportError("Every artifact requires a SHA-256 digest.")
        if artifact.candidate_ref and artifact.candidate_ref not in refs:
            raise ResultImportError(
                f"Artifact '{artifact.path}' refers to unknown candidate "
                f"'{artifact.candidate_ref}'."
            )


def _check_number(value, name, *, minimum=None, maximum=None, nullable=True):
    if value is None and nullable:
        return
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ResultImportError(f"{name} must be finite numeric data.")
    if (minimum is not None and value < minimum) or (maximum is not None and value > maximum):
        raise ResultImportError(f"{name} is outside its permitted range.")


def _artifact_source(output_dir, path):
    if not isinstance(path, str) or not path or "\\" in path:
        raise ResultImportError("Artifact paths must be nonempty relative POSIX paths.")
    relative = PurePosixPath(path)
    if relative.is_absolute() or PureWindowsPath(path).drive or ".." in relative.parts:
        raise ResultImportError("Artifact paths must stay inside the output directory.")
    root = output_dir.resolve()
    source = (root / relative).resolve()
    if not source.is_relative_to(root):
        raise ResultImportError("Artifact paths must stay inside the output directory.")
    if not source.is_file():
        raise ResultImportError(f"The engine referenced an artifact it did not write: {path}")
    return source


def _import_artifacts(
    run, result: JobResult, output_dir: Path, candidates_by_ref: dict[str, Candidate], written
) -> int:
    count = 0
    # Check all sources and bytes before persisting any artifact.
    verified = []
    for ref in result.artifacts:
        source = _artifact_source(output_dir, ref.path)
        payload = source.read_bytes()
        if sha256_bytes(payload) != ref.checksum_sha256:
            raise ResultImportError(f"Artifact '{ref.path}' failed its checksum on import.")
        verified.append((ref, payload))

    for ref, payload in verified:
        candidate = candidates_by_ref.get(ref.candidate_ref) if ref.candidate_ref else None
        if ref.candidate_ref and candidate is None:
            raise ResultImportError(
                f"Artifact '{ref.path}' refers to unknown candidate '{ref.candidate_ref}'."
            )

        artifact = Artifact(
            run=run,
            candidate=candidate,
            kind=ref.kind,
            media_type=ref.media_type,
            checksum_sha256=ref.checksum_sha256 or sha256_bytes(payload),
            size_bytes=len(payload),
        )
        artifact.file.save(ref.path, ContentFile(payload), save=False)
        written.append((artifact.file.storage, artifact.file.name))
        artifact.save()
        count += 1

    return count


def _write_derived_artifacts(run, result: JobResult, written) -> int:
    """Platform-native artifacts computed from what was just imported, not written by
    the engine — a summary table and a run manifest, so a downloaded archive is
    self-documenting without needing the web app open next to it.

    ``result`` (not ``run.engine_version``) is the source for engine version: this
    runs strictly before the caller transitions the run to COMPLETED and stamps that
    field (rule 5, apps/analyses/services.py), so ``run`` itself is still mid-flight.
    """
    _write_platform_artifact(
        run,
        kind="summary_table",
        filename="summary.csv",
        written=written,
        content=build_candidates_csv(run),
        media_type="text/csv",
    )
    _write_platform_artifact(
        run,
        kind="run_manifest",
        filename="manifest.json",
        written=written,
        content=json.dumps(build_run_manifest(run, result), indent=2, default=str, allow_nan=False)
        + "\n",
        media_type="application/json",
    )
    return 2


def _write_platform_artifact(
    run, *, kind: str, filename: str, content: str, media_type: str, written
) -> Artifact:
    payload = content.encode("utf-8")
    artifact = Artifact(
        run=run,
        kind=kind,
        media_type=media_type,
        checksum_sha256=sha256_bytes(payload),
        size_bytes=len(payload),
    )
    artifact.file.save(filename, ContentFile(payload), save=False)
    written.append((artifact.file.storage, artifact.file.name))
    artifact.save()
    return artifact


def build_candidates_csv(run) -> str:
    """A flat candidate x metric table, for a spreadsheet or a lab notebook.

    The one place that decides what "the summary table" contains — used both by
    ``GET /api/runs/{id}/export.csv`` and to materialize the ``summary_table``
    artifact at import time, so the two never drift apart.
    """
    candidates = (
        Candidate.objects.filter(run=run)
        .prefetch_related("metrics")
        .order_by(F("rank").asc(nulls_last=True), "engine_ref")
    )
    metric_names = sorted(
        {
            name
            for candidate in candidates
            for name in (metric.name for metric in candidate.metrics.all())
        }
    )

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "candidate",
            "rank",
            "overall_score",
            "gate_family",
            "logic_type",
            "rejected",
            "rejection_reason",
            *[f"{name}_raw" for name in metric_names],
            *[f"{name}_normalized" for name in metric_names],
        ]
    )

    for candidate in candidates:
        by_name = {metric.name: metric for metric in candidate.metrics.all()}
        writer.writerow(
            [
                candidate.engine_ref,
                candidate.rank if candidate.rank is not None else "",
                candidate.overall_score if candidate.overall_score is not None else "",
                candidate.gate_family,
                candidate.logic_type,
                "yes" if candidate.is_rejected else "no",
                candidate.rejection_reason,
                *[
                    _csv_number(getattr(by_name.get(name), "raw_value", None))
                    for name in metric_names
                ],
                *[
                    _csv_number(getattr(by_name.get(name), "normalized_value", None))
                    for name in metric_names
                ],
            ]
        )

    return buffer.getvalue()


def _csv_number(value):
    return "" if value is None else value


def build_run_manifest(run, result: JobResult) -> dict:
    """The run's full configuration and provenance, as JSON.

    Everything a researcher would need to cite or reproduce this run from the
    downloaded archive alone, with no need to have the web app open.

    Written moments before the run is transitioned to COMPLETED (rule 5,
    apps/analyses/services.py), so ``status``/``engine_version``/``finished_at`` come
    from ``result`` and the current instant rather than from ``run``, which has not
    been stamped with them yet.
    """
    return {
        "run_id": str(run.id),
        "status": "COMPLETED",
        "organism": run.organism or None,
        "input_mode": run.input_mode,
        "trigger_sequence": run.trigger_sequence or None,
        "dataset": run.dataset.name if run.dataset else None,
        "dataset_id": str(run.dataset_id) if run.dataset_id else None,
        "input_checksum": result.input_checksum,
        "dataset_validation": run.dataset.validation_report if run.dataset_id else None,
        "schema_version": result.schema_version,
        "gate_families": run.gate_families,
        "scoring_profile": run.scoring_profile,
        "seed": run.seed,
        "engine_version": result.engine_version,
        "params": run.params_snapshot,
        "warnings": list(result.warnings),
        "candidate_count": run.candidates.count(),
        "submitted_at": run.submitted_at,
        "started_at": run.started_at,
        "finished_at": timezone.now(),
    }
