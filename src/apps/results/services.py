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
import textwrap
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.common.checksums import sha256_bytes
from apps.results.models import Artifact, Candidate, CandidateMetric
from engine.client import candidate_release_allowed
from engine.contract import HIGHER_BETTER, LOWER_BETTER, SCHEMA_VERSION, SUCCEEDED, JobResult

logger = logging.getLogger(__name__)


def artifact_release_allowed(artifact) -> bool:
    """Return whether an owned run artifact can be downloaded.

    Sequence exports are normal run deliverables. Screening audit metadata remains
    available for review, but missing optional screening evidence no longer hides the
    FASTA, GenBank or SBOL files that the run generated.
    """
    if (
        artifact.sequence_free
        or not artifact.release_required
        or artifact.kind == "safety_audit"
    ):
        return True
    if artifact.kind == "run_manifest":
        candidates = list(artifact.run.candidates.all())
        return bool(candidates) and all(candidate_release_allowed(c.design) for c in candidates)
    return bool(
        artifact.candidate_id
        and artifact.kind
        in {"sequence_fasta", "plasmid_fasta", "genbank", "sbol", "structure_plot"}
        and candidate_release_allowed(artifact.candidate.design)
    )


class ResultImportError(Exception):
    """The result manifest could not be trusted or written."""


@dataclass(frozen=True)
class ImportSummary:
    candidates: int
    metrics: int
    artifacts: int


def import_job_result(
    run,
    result: JobResult,
    output_dir: str | Path,
    *,
    prepare: Callable[[], None] | None = None,
    finalize: Callable[[], None] | None = None,
) -> ImportSummary:
    """Write one engine result into the database, atomically.

    Either the whole result lands or none of it does — a half-imported run must be
    impossible (docs/architecture.md §6.2).

    Saved artifact bytes are removed when an exception rolls this transaction back,
    including cooperative process termination. Hard process termination or failed
    storage deletion can leave unreferenced bytes for the orphan cleanup command.
    """
    written = []
    try:
        with transaction.atomic():
            if prepare is not None:
                prepare()
            summary = _import_job_result(run, result, output_dir, written)
            if finalize is not None:
                finalize()
            return summary
    except BaseException:
        for storage, name in reversed(written):
            try:
                storage.delete(name)
            except BaseException:
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
            sequence_free=ref.sequence_free,
            release_required=ref.release_required,
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
        sequence_free=True,
    )
    _write_platform_artifact(
        run,
        kind="run_manifest",
        filename="manifest.json",
        written=written,
        content=json.dumps(build_run_manifest(run, result), indent=2, default=str, allow_nan=False)
        + "\n",
        media_type="application/json",
        # With no generated candidates this contains original submitted inputs and
        # provenance only, already accessible through the owned run configuration.
        sequence_free=not result.candidates,
    )
    return 2


def _write_platform_artifact(
    run,
    *,
    kind: str,
    filename: str,
    content: str,
    media_type: str,
    written,
    sequence_free: bool = False,
) -> Artifact:
    payload = content.encode("utf-8")
    artifact = Artifact(
        run=run,
        kind=kind,
        media_type=media_type,
        checksum_sha256=sha256_bytes(payload),
        size_bytes=len(payload),
        sequence_free=sequence_free,
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
    # A two-input AND run also reports what its ON/OFF numbers came from. The columns exist only
    # when some candidate has them, so a single-input export is byte-for-byte what it was.
    has_and = any((candidate.design or {}).get("and_gate") for candidate in candidates)

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
            *(AND_CSV_COLUMNS if has_and else []),
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
                *(_and_csv_cells(candidate) if has_and else []),
            ]
        )

    return buffer.getvalue()


def build_run_summary_pdf(run) -> bytes:
    """Build a designed, sequence-free PDF summary from a run's stored results."""
    candidates = Candidate.objects.filter(run=run)
    candidate_count = candidates.count()
    ranked_count = candidates.filter(rank__isnull=False).count()
    ranked_candidates = list(
        candidates.filter(rank__isnull=False)
        .order_by("rank")
        .values_list("rank", "engine_ref", "overall_score")[:20]
    )
    organism_names = {
        "ecoli": "E. coli",
        "yeast": "Yeast",
        "human": "Human",
        "c_acnes": "C. acnes",
    }
    submitted = timezone.localtime(run.submitted_at).strftime("%Y-%m-%d %H:%M %Z") if run.submitted_at else "Not recorded"
    organism = organism_names.get(run.organism, run.organism or "Unknown")
    input_mode = run.get_input_mode_display() if hasattr(run, "get_input_mode_display") else run.input_mode
    return _build_run_summary_pdf(
        run=run,
        candidate_count=candidate_count,
        ranked_count=ranked_count,
        ranked_candidates=ranked_candidates,
        organism=organism,
        input_mode=input_mode,
        submitted=submitted,
    )


def _build_run_summary_pdf(*, run, candidate_count, ranked_count, ranked_candidates, organism, input_mode, submitted):
    """Draw a compact two-page-or-less report with a clear score overview."""
    page_size = 9
    page_count = max(1, math.ceil(len(ranked_candidates) / page_size))
    pages = []
    for page_index in range(page_count):
        commands = []
        _pdf_rect(commands, 0, 0, 595, 842, (1.0, 1.0, 1.0))
        _pdf_rect(commands, 0, 740, 595, 102, (0.13, 0.11, 0.11))
        _pdf_rect(commands, 0, 740, 7, 102, (0.76, 0.13, 0.17))
        _pdf_text(commands, 42, 815, "CERNAL  /  RNA LOGIC DESIGN", 8, bold=True, color=(0.96, 0.78, 0.78))
        _pdf_text(commands, 42, 783, "Run summary", 23, bold=True, color=(1.0, 1.0, 1.0))
        _pdf_text(commands, 42, 760, f"Run: {run.name or 'Unnamed run'}", 9, color=(0.88, 0.87, 0.87), max_chars=48)
        _pdf_text(commands, 440, 812, "RUN ID", 7, bold=True, color=(0.79, 0.77, 0.77))
        _pdf_text(commands, 440, 794, str(run.id)[:12], 10, bold=True, color=(1.0, 1.0, 1.0))

        if page_index == 0:
            cards = [
                ("ORGANISM", organism),
                ("INPUT", input_mode),
                ("RANKED", str(ranked_count)),
                ("ENGINE", run.engine_version or "Not recorded"),
            ]
            for index, (label, value) in enumerate(cards):
                x = 40 + index * 130
                _pdf_card(commands, x, 650, 122, 64)
                _pdf_text(commands, x + 11, 697, label, 7, bold=True, color=(0.49, 0.45, 0.45))
                _pdf_text(commands, x + 11, 675, value, 10, bold=True, color=(0.15, 0.13, 0.13), max_chars=17)
            _pdf_text(commands, 40, 612, "Candidate overview", 16, bold=True, color=(0.14, 0.12, 0.12))
            _pdf_text(commands, 40, 594, f"{candidate_count} designs produced / {ranked_count} included in the ranking", 9, color=(0.43, 0.40, 0.40))
            section_y = 556
        else:
            _pdf_text(commands, 40, 690, "Candidate overview  /  continued", 16, bold=True, color=(0.14, 0.12, 0.12))
            section_y = 654

        _pdf_text(commands, 50, section_y, "RANK", 7, bold=True, color=(0.49, 0.45, 0.45))
        _pdf_text(commands, 100, section_y, "CANDIDATE", 7, bold=True, color=(0.49, 0.45, 0.45))
        _pdf_text(commands, 482, section_y, "SCORE", 7, bold=True, color=(0.49, 0.45, 0.45))
        start = page_index * page_size
        page_candidates = ranked_candidates[start : start + page_size]
        if not page_candidates:
            _pdf_card(commands, 40, section_y - 75, 515, 54)
            _pdf_text(commands, 55, section_y - 52, "No ranked candidates were produced for this run.", 10, color=(0.43, 0.40, 0.40))
        for row_index, (rank, engine_ref, overall_score) in enumerate(page_candidates):
            y = section_y - 34 - row_index * 31
            _pdf_rect(commands, 40, y - 9, 515, 27, (0.98, 0.97, 0.97) if row_index % 2 == 0 else (1.0, 1.0, 1.0))
            _pdf_rect(commands, 40, y - 9, 31, 27, (0.76, 0.13, 0.17))
            _pdf_text(commands, 48, y, str(rank), 9, bold=True, color=(1.0, 1.0, 1.0))
            _pdf_text(commands, 84, y, engine_ref, 9, color=(0.15, 0.13, 0.13), max_chars=34)
            bar_x, bar_width = 354, 94
            _pdf_rect(commands, bar_x, y - 1, bar_width, 5, (0.89, 0.87, 0.87))
            if overall_score is not None:
                _pdf_rect(commands, bar_x, y - 1, bar_width * min(1.0, max(0.0, float(overall_score))), 5, (0.76, 0.13, 0.17))
                score_label = f"{overall_score * 100:.1f}%"
            else:
                score_label = "Unmeasured"
            _pdf_text(commands, 468, y, score_label, 9, bold=True, color=(0.15, 0.13, 0.13))

        if page_index == 0:
            _pdf_card(commands, 40, 112, 515, 65, fill=(0.98, 0.96, 0.96))
            _pdf_text(commands, 54, 155, "SEQUENCE FILES", 7, bold=True, color=(0.66, 0.12, 0.16))
            _pdf_text(commands, 54, 136, "Available sequence exports: switch FASTA, full-plasmid FASTA and annotated GenBank.", 9, color=(0.20, 0.18, 0.18), max_chars=91)
        _pdf_line(commands, 40, 54, 555, 54, (0.89, 0.87, 0.87))
        _pdf_text(commands, 40, 37, f"Submitted: {submitted}", 7, color=(0.49, 0.45, 0.45), max_chars=58)
        _pdf_text(commands, 482, 37, f"{page_index + 1} / {page_count}", 7, color=(0.49, 0.45, 0.45))
        pages.append(commands)

    return _serialize_pdf_pages(pages)


def _pdf_safe(text, max_chars=None):
    value = unicodedata.normalize("NFKD", str(text)).encode("ascii", "replace").decode("ascii")
    if max_chars is not None:
        value = textwrap.shorten(value, width=max_chars, placeholder="...")
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)").replace("\n", " ")


def _pdf_text(commands, x, y, text, size, *, bold=False, color=(0.15, 0.13, 0.13), max_chars=None):
    font = "F2" if bold else "F1"
    red, green, blue = color
    safe = _pdf_safe(text, max_chars=max_chars)
    commands.append(
        f"BT /{font} {size} Tf {red:.3f} {green:.3f} {blue:.3f} rg 1 0 0 1 {x:.2f} {y:.2f} Tm ({safe}) Tj ET"
    )


def _pdf_rect(commands, x, y, width, height, fill, *, stroke=(0.90, 0.88, 0.88)):
    red, green, blue = fill
    stroke_red, stroke_green, stroke_blue = stroke
    commands.append(
        f"q {red:.3f} {green:.3f} {blue:.3f} rg {stroke_red:.3f} {stroke_green:.3f} {stroke_blue:.3f} RG 0.6 w {x:.2f} {y:.2f} {width:.2f} {height:.2f} re B Q"
    )


def _pdf_card(commands, x, y, width, height, *, fill=(0.98, 0.97, 0.97)):
    _pdf_rect(commands, x, y, width, height, fill)


def _pdf_line(commands, x1, y1, x2, y2, color):
    red, green, blue = color
    commands.append(f"q {red:.3f} {green:.3f} {blue:.3f} RG 0.7 w {x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S Q")


def _serialize_pdf_pages(pages: list[list[str]]) -> bytes:
    """Serialize vector PDF pages using only the Python standard library."""
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"",  # Filled after the page objects have been numbered.
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
    ]
    page_refs = []
    for page_index, commands in enumerate(pages, start=1):
        page_number = 5 + (page_index - 1) * 2
        content_number = page_number + 1
        page_refs.append(f"{page_number} 0 R")
        stream = "\n".join(commands).encode("ascii")
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {content_number} 0 R >>".encode("ascii")
        )
        objects.append(
            f"<< /Length {len(stream)} >>\nstream\n".encode("ascii")
            + stream
            + b"\nendstream"
        )
    objects[1] = (
        f"<< /Type /Pages /Kids [{' '.join(page_refs)}] /Count {len(page_refs)} >>".encode("ascii")
    )

    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{number} 0 obj\n".encode("ascii"))
        output.extend(body)
        output.extend(b"\nendobj\n")
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    return bytes(output)


#: Added to the candidates table for a two-input AND run. Percentages are of each hairpin's own
#: stem (100 = both stems fully open together); an unmeasured value is an empty cell, never 0.
AND_CSV_COLUMNS = [
    "and_on_pct",
    "and_off_pct",
    "and_off_source",
    "and_on_minus_off_pp",
    "and_tied_group",
    "and_delta_g_kcal_per_mol",
    "and_sampler_checks_failed",
    "and_controls_found",
]


def _and_csv_cells(candidate) -> list:
    """The AND columns of one candidate row (empty for a candidate without diagnostics)."""
    info = (candidate.design or {}).get("and_gate") or {}
    if not info:
        return [""] * len(AND_CSV_COLUMNS)
    states = info.get("states") or {}
    failed = sum(1 for state in states.values() if state.get("verified") is False)
    tied = info.get("tied_group")
    return [
        _csv_number(info.get("on_pct")),
        _csv_number(info.get("off_pct")),
        _csv_number(info.get("off_source")),
        _csv_number(info.get("on_minus_off_pp")),
        "" if tied is None else ("yes" if tied else "no"),
        _csv_number(info.get("delta_g_kcal_per_mol")),
        failed if states else "",
        _csv_number((info.get("controls") or {}).get("found")),
    ]


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
        "scientific_provenance": getattr(result, "scientific_provenance", {}),
        "warnings": list(result.warnings),
        "candidate_count": run.candidates.count(),
        "submitted_at": run.submitted_at,
        "started_at": run.started_at,
        "finished_at": timezone.now(),
    }
