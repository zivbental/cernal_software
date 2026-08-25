"""Importing an engine result into the Platform's durable model.

Pulled forward from Step 3 so that ``seed_demo`` and the run lifecycle share one
implementation rather than duplicating it. Step 3 calls this from
``apps/analyses/services.py`` after a successful run.

**This module does not touch run status.** Transitions belong to
``apps/analyses/services.py`` (rule 5); this only writes results.
"""

import logging
from dataclasses import dataclass
from pathlib import Path

from django.core.files.base import ContentFile
from django.db import transaction

from apps.common.checksums import sha256_bytes
from apps.results.models import Artifact, Candidate, CandidateMetric
from engine.contract import JobResult

logger = logging.getLogger(__name__)


class ResultImportError(Exception):
    """The result manifest could not be trusted or written."""


@dataclass(frozen=True)
class ImportSummary:
    candidates: int
    metrics: int
    artifacts: int


@transaction.atomic
def import_job_result(run, result: JobResult, output_dir: str | Path) -> ImportSummary:
    """Write one engine result into the database, atomically.

    Either the whole result lands or none of it does — a half-imported run must be
    impossible (docs/software-design.md §6.2).

    Artifact *files* are written outside the database's control, so a rollback can leave
    orphan bytes under ``var/media/artifacts/``. That is harmless: nothing references
    them, and the run will not be marked COMPLETED.
    """
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

    artifact_count = _import_artifacts(run, result, Path(output_dir), candidates_by_ref)

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
    """Confirm the engine computed against what we actually submitted."""
    expected = run.dataset.checksum_sha256
    if expected and result.input_checksum and result.input_checksum != expected:
        raise ResultImportError(
            "The engine reported a different input checksum than the dataset that was submitted."
        )


def _import_artifacts(
    run, result: JobResult, output_dir: Path, candidates_by_ref: dict[str, Candidate]
) -> int:
    count = 0

    for ref in result.artifacts:
        source = output_dir / ref.path
        if not source.is_file():
            raise ResultImportError(
                f"The engine referenced an artifact it did not write: {ref.path}"
            )

        payload = source.read_bytes()
        if ref.checksum_sha256 and sha256_bytes(payload) != ref.checksum_sha256:
            raise ResultImportError(f"Artifact '{ref.path}' failed its checksum on import.")

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
        artifact.save()
        count += 1

    return count
