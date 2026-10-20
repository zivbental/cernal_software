"""Candidates, artifacts, annotations and exports."""

import shutil
import zipfile
from tempfile import SpooledTemporaryFile
from uuid import UUID

from django.core.files import File
from django.db.models import F
from django.http import FileResponse, HttpResponse, JsonResponse
from ninja import Query, Router, Status
from ninja.pagination import LimitOffsetPagination, paginate

from api.auth import get_owned
from api.errors import Conflict, NotFound, ValidationFailed
from api.schemas import (
    AnnotationIn,
    AnnotationOut,
    ArtifactOut,
    CandidateDetailOut,
    CandidateOut,
    CandidateStructureOut,
)
from api.security import require_scope
from apps.accounts.models import ApiKeyScope
from apps.analyses.models import AnalysisRun
from apps.common.checksums import sha256_upload
from apps.results.models import (
    Annotation,
    Artifact,
    ArtifactCategory,
    Candidate,
    DecisionTag,
    filter_by_category,
)
from apps.results.services import artifact_release_allowed, build_candidates_csv, build_run_summary_pdf
from engine.client import candidate_release_allowed, layout_stored_structure

router = Router()

#: Only these may be sorted on. An open sort parameter is an invitation to probe the
#: schema and to write expensive queries.
SORTABLE = {
    "rank",
    "overall_score",
    "gate_family",
    "logic_type",
    "engine_ref",
}


def _nulls_last(field: str, *, descending: bool):
    """Order by a field, keeping NULLs at the end in both directions.

    Rejected candidates have no rank and no score, so without this they would lead an
    ascending list.
    """
    expression = F(field)
    return expression.desc(nulls_last=True) if descending else expression.asc(nulls_last=True)


@router.get("/runs/{run_id}/candidates", response=list[CandidateOut])
@paginate(LimitOffsetPagination)
def list_candidates(
    request,
    run_id: UUID,
    sort: str = Query(default="rank"),
    gate_family: str | None = Query(default=None),
    include_rejected: bool = Query(default=False),
    output: str | None = Query(default=None),
    min_score: float | None = Query(default=None, ge=0, le=1),
    top_n: int | None = Query(default=None, ge=1, le=1000),
):
    get_owned(AnalysisRun, run_id, request.user)

    field = sort.lstrip("-")
    if field not in SORTABLE:
        raise ValidationFailed(f"Cannot sort by '{field}'.", detail={"sortable": sorted(SORTABLE)})

    queryset = Candidate.objects.filter(run_id=run_id)
    if not include_rejected:
        queryset = queryset.filter(is_rejected=False)
    # Select the globally best accepted results before display sorting/filtering
    # and pagination. Omission preserves access to the complete stored run.
    if top_n is not None:
        queryset = queryset.filter(is_rejected=False, rank__lte=top_n)
    if gate_family:
        queryset = queryset.filter(gate_family=gate_family)
    if output:
        queryset = queryset.filter(design__logic_graph__output__iexact=output)
    if min_score is not None:
        queryset = queryset.filter(overall_score__gte=min_score)

    return queryset.order_by(_nulls_last(field, descending=sort.startswith("-")), "engine_ref")


@router.get("/candidates/{candidate_id}", response=CandidateDetailOut)
def get_candidate(request, candidate_id: UUID):
    return get_owned(Candidate, candidate_id, request.user, select_related=("run",))


@router.get("/candidates/{candidate_id}/structure", response=CandidateStructureOut)
def get_candidate_structure(request, candidate_id: UUID):
    """Draw the stored primary switch; this does not predict or recompute a fold."""
    candidate = get_owned(Candidate, candidate_id, request.user, select_related=("run",))
    design = candidate.design
    if not candidate_release_allowed(design):
        result = layout_stored_structure(None, None)
        result["reason"] = "Sequence disclosure is withheld pending matching release approval."
        return result
    if not isinstance(design, dict):
        return layout_stored_structure(design, design)
    return layout_stored_structure(
        design.get("switch_sequence"),
        design.get("structure"),
        structure_kind=design.get("structure_kind"),
    )


@router.get("/runs/{run_id}/artifacts", response=list[ArtifactOut])
def list_artifacts(request, run_id: UUID):
    get_owned(AnalysisRun, run_id, request.user)
    return Artifact.objects.filter(run_id=run_id).select_related("candidate")


@router.get("/artifacts/{artifact_id}/download", url_name="artifact_download")
def download_artifact(request, artifact_id: UUID):
    """Serve an artifact after checking ownership.

    Artifacts are never handed to a static file handler: that would make every artifact
    world-readable to anyone who guessed the path (docs/architecture.md §7.2).
    """
    artifact = get_owned(Artifact, artifact_id, request.user, select_related=("run",))
    if not artifact_release_allowed(artifact):
        raise Conflict("Sequence-bearing artifact is withheld pending release approval.")

    if not artifact.file or not artifact.file.storage.exists(artifact.file.name):
        raise NotFound("That artifact is no longer stored.")

    snapshot = _verified_artifact_snapshot(artifact)
    if not artifact_release_allowed(artifact):
        snapshot.close()
        raise Conflict("Sequence-bearing artifact is withheld pending release approval.")
    response = FileResponse(
        snapshot,
        content_type=artifact.media_type or "application/octet-stream",
        as_attachment=True,
        filename=artifact.file.name.rsplit("/", 1)[-1],
    )
    response["X-Content-Type-Options"] = "nosniff"
    return response


@router.get("/runs/{run_id}/export.csv", url_name="export_csv")
def export_candidates_csv(request, run_id: UUID):
    """A flat candidate x metric table, for a spreadsheet or a lab notebook."""
    run = get_owned(AnalysisRun, run_id, request.user)

    response = HttpResponse(build_candidates_csv(run), content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="run-{str(run.id)[:8]}-candidates.csv"'
    return response


@router.get("/runs/{run_id}/export.pdf", url_name="export_run_summary_pdf")
def export_run_summary_pdf(request, run_id: UUID):
    """Download a sequence-free PDF overview for any completed run."""
    run = get_owned(AnalysisRun, run_id, request.user)
    response = HttpResponse(build_run_summary_pdf(run), content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="run-{str(run.id)[:8]}-summary.pdf"'
    )
    response["X-Content-Type-Options"] = "nosniff"
    return response


@router.get("/runs/{run_id}/artifacts/download", url_name="artifacts_download_zip")
def download_artifacts_zip(
    request,
    run_id: UUID,
    category: str | None = Query(default=None),
    ids: str | None = Query(default=None, description="Comma-separated artifact ids."),
    available_only: bool = Query(
        default=False,
        description="Include only artifacts currently approved for download.",
    ),
):
    """Everything, one category, available artifacts, or a hand-picked set as one .zip.

    ``ids`` wins if both are given. Neither given means every artifact this run has.
    ``available_only`` removes artifacts held pending release approval, so a partial
    archive can still be downloaded without exposing held files.
    Entries are filed under ``<category>/<display name>`` inside the archive, so the
    zip is organized the same way the download UI is, regardless of engine storage
    paths.
    """
    run = get_owned(AnalysisRun, run_id, request.user)
    queryset = Artifact.objects.filter(run=run)

    label = "all"
    if ids:
        try:
            wanted = [UUID(value.strip()) for value in ids.split(",") if value.strip()]
        except ValueError:
            raise ValidationFailed("'ids' must be a comma-separated list of UUIDs.") from None
        queryset = queryset.filter(id__in=wanted)
        label = "selected"
    elif category:
        if category not in ArtifactCategory.values:
            raise ValidationFailed(
                f"Unknown category '{category}'.", detail={"allowed": ArtifactCategory.values}
            )
        queryset = filter_by_category(queryset, category)
        label = category

    artifacts = list(queryset)
    if available_only:
        artifacts = [artifact for artifact in artifacts if artifact_release_allowed(artifact)]
        if not ids and not category:
            label = "available"
    include_summary_pdf = not ids and category in (None, ArtifactCategory.REPORTS)
    if not artifacts and not include_summary_pdf:
        raise NotFound("No matching artifacts were found for this run.")

    withheld = [artifact for artifact in artifacts if not artifact_release_allowed(artifact)]
    if withheld:
        raise Conflict(
            "This archive contains artifacts withheld pending release approval.",
            detail={"withheld_artifact_ids": [str(artifact.id) for artifact in withheld]},
        )

    missing = [
        artifact
        for artifact in artifacts
        if not artifact.file or not artifact.file.storage.exists(artifact.file.name)
    ]
    if missing:
        raise Conflict(
            "This archive is incomplete because stored artifacts are missing.",
            detail={"missing_artifact_ids": [str(artifact.id) for artifact in missing]},
        )
    buffer = SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+b")
    try:
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            used_names: set[str] = set()
            for artifact in artifacts:
                arcname = _unique_arcname(
                    f"{artifact.category}/{artifact.display_name}", used_names
                )
                with (
                    _verified_artifact_snapshot(artifact) as handle,
                    archive.open(arcname, "w", force_zip64=True) as entry,
                ):
                    shutil.copyfileobj(handle, entry, length=1024 * 1024)
            if include_summary_pdf:
                archive.writestr(
                    _unique_arcname("reports/run-summary.pdf", used_names),
                    build_run_summary_pdf(run),
                )
        if any(not artifact_release_allowed(artifact) for artifact in artifacts):
            raise Conflict("Sequence release approval expired while preparing this archive.")
        buffer.seek(0)
    except OSError:
        buffer.close()
        raise Conflict(
            "This archive could not be completed because artifact storage is unavailable."
        ) from None
    except BaseException:
        buffer.close()
        raise
    response = FileResponse(buffer, content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="run-{str(run.id)[:8]}-{label}.zip"'

    return response


def _verified_artifact_snapshot(artifact):
    """Serve only the exact imported bytes; never reopen storage after verification."""
    snapshot = SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+b")
    try:
        with artifact.file.open("rb") as source:
            shutil.copyfileobj(source, snapshot, length=1024 * 1024)
        snapshot.seek(0)
        if sha256_upload(File(snapshot)) != artifact.checksum_sha256:
            raise Conflict("Stored artifact bytes no longer match their recorded checksum.")
        return snapshot
    except OSError:
        snapshot.close()
        raise Conflict("Stored artifact is unavailable.") from None
    except BaseException:
        snapshot.close()
        raise


def _unique_arcname(name: str, used: set[str]) -> str:
    """Two artifacts can share a display name (docs/architecture.md §16 notes this is
    already possible on disk); a zip cannot hold two entries at the same path."""
    if name not in used:
        used.add(name)
        return name
    stem, _, ext = name.rpartition(".")
    for n in range(2, 10_000):
        candidate = f"{stem} ({n}).{ext}" if ext else f"{name} ({n})"
        if candidate not in used:
            used.add(candidate)
            return candidate
    raise AssertionError("unreachable: exhausted 10000 disambiguation attempts")


# --- Annotations ------------------------------------------------------------------


@router.get("/candidates/{candidate_id}/annotations", response=list[AnnotationOut])
def list_annotations(request, candidate_id: UUID):
    get_owned(Candidate, candidate_id, request.user)
    return Annotation.objects.filter(candidate_id=candidate_id).select_related("author")


@router.post("/candidates/{candidate_id}/annotations", response={201: AnnotationOut})
def create_annotation(request, candidate_id: UUID, payload: AnnotationIn):
    require_scope(request, ApiKeyScope.DESIGN)
    candidate = get_owned(Candidate, candidate_id, request.user)

    if payload.decision_tag not in DecisionTag.values:
        raise ValidationFailed(
            f"Unknown decision tag '{payload.decision_tag}'.",
            detail={"allowed": list(DecisionTag.values)},
        )

    annotation = Annotation.objects.create(
        candidate=candidate,
        author=request.user,
        text=payload.text,
        decision_tag=payload.decision_tag,
    )
    return Status(201, annotation)


@router.delete("/annotations/{annotation_id}", response={204: None})
def delete_annotation(request, annotation_id: UUID):
    require_scope(request, ApiKeyScope.DESIGN)
    annotation = get_owned(Annotation, annotation_id, request.user)
    annotation.delete()
    return Status(204, None)


@router.get("/runs/{run_id}/review.json", url_name="review_export")
def export_review(request, run_id: UUID):
    """Owned, attributed research decisions; exporting is not synthesis approval."""
    get_owned(AnalysisRun, run_id, request.user)
    notes = Annotation.objects.filter(candidate__run_id=run_id).select_related(
        "candidate", "author"
    )
    body = [
        {
            "id": str(note.id),
            "candidate_id": str(note.candidate_id),
            "engine_ref": note.candidate.engine_ref,
            "author": note.author.username,
            "text": note.text,
            "decision_tag": note.decision_tag,
            "created_at": note.created_at.isoformat(),
        }
        for note in notes.order_by("created_at", "id")
    ]
    response = JsonResponse({"run_id": str(run_id), "annotations": body})
    response["Content-Disposition"] = f'attachment; filename="run-{str(run_id)[:8]}-review.json"'
    return response
