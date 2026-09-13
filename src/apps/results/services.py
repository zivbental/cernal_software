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
from dataclasses import dataclass
from pathlib import Path

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

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
    impossible (docs/architecture.md §6.2).

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
    artifact_count += _write_derived_artifacts(run, result)

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
    """Confirm the engine computed against what we actually submitted.

    A direct-trigger run has no dataset and therefore no checksum to compare — the
    sequence travelled inside the immutable submission itself.
    """
    if run.dataset is None:
        return

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


def _write_derived_artifacts(run, result: JobResult) -> int:
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
        content=build_candidates_csv(run),
        media_type="text/csv",
    )
    _write_platform_artifact(
        run,
        kind="run_manifest",
        filename="manifest.json",
        content=json.dumps(build_run_manifest(run, result), indent=2, default=str) + "\n",
        media_type="application/json",
    )
    return 2


def _write_platform_artifact(
    run, *, kind: str, filename: str, content: str, media_type: str
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
    artifact.save()
    return artifact


def build_candidates_csv(run) -> str:
    """A flat candidate x metric table, for a spreadsheet or a lab notebook.

    The one place that decides what "the summary table" contains — used both by
    ``GET /api/runs/{id}/export.csv`` and to materialize the ``summary_table``
    artifact at import time, so the two never drift apart.
    """
    candidates = (
        Candidate.objects.filter(run=run).prefetch_related("metrics").order_by("rank", "engine_ref")
    )
    metric_names = sorted(
        {
            name
            for candidate in candidates
            for name in candidate.metrics.values_list("name", flat=True)
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
                *[getattr(by_name.get(name), "raw_value", "") or "" for name in metric_names],
                *[
                    getattr(by_name.get(name), "normalized_value", "") or ""
                    for name in metric_names
                ],
            ]
        )

    return buffer.getvalue()


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
