"""Candidates, artifacts, annotations and exports."""

import zipfile
from io import BytesIO
from uuid import UUID

from django.db.models import F
from django.http import FileResponse, HttpResponse
from ninja import Query, Router, Status
from ninja.pagination import LimitOffsetPagination, paginate

from api.auth import get_owned
from api.errors import NotFound, ValidationFailed
from api.schemas import AnnotationIn, AnnotationOut, ArtifactOut, CandidateDetailOut, CandidateOut
from api.security import require_scope
from apps.accounts.models import ApiKeyScope
from apps.analyses.models import AnalysisRun
from apps.results.models import (
    Annotation,
    Artifact,
    ArtifactCategory,
    Candidate,
    DecisionTag,
    filter_by_category,
)
from apps.results.services import build_candidates_csv

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
):
    get_owned(AnalysisRun, run_id, request.user)

    field = sort.lstrip("-")
    if field not in SORTABLE:
        raise ValidationFailed(f"Cannot sort by '{field}'.", detail={"sortable": sorted(SORTABLE)})

    queryset = Candidate.objects.filter(run_id=run_id)
    if not include_rejected:
        queryset = queryset.filter(is_rejected=False)
    if gate_family:
        queryset = queryset.filter(gate_family=gate_family)

    return queryset.order_by(_nulls_last(field, descending=sort.startswith("-")), "engine_ref")


@router.get("/candidates/{candidate_id}", response=CandidateDetailOut)
def get_candidate(request, candidate_id: UUID):
    return get_owned(Candidate, candidate_id, request.user, select_related=("run",))


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

    if not artifact.file or not artifact.file.storage.exists(artifact.file.name):
        raise NotFound("That artifact is no longer stored.")

    response = FileResponse(
        artifact.file.open("rb"),
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


@router.get("/runs/{run_id}/artifacts/download", url_name="artifacts_download_zip")
def download_artifacts_zip(
    request,
    run_id: UUID,
    category: str | None = Query(default=None),
    ids: str | None = Query(default=None, description="Comma-separated artifact ids."),
):
    """Everything, one category, or a hand-picked set — always as a single .zip.

    ``ids`` wins if both are given. Neither given means every artifact this run has.
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
    if not artifacts:
        raise NotFound("No matching artifacts were found for this run.")

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        used_names: set[str] = set()
        for artifact in artifacts:
            if not artifact.file or not artifact.file.storage.exists(artifact.file.name):
                continue
            arcname = _unique_arcname(f"{artifact.category}/{artifact.display_name}", used_names)
            with artifact.file.open("rb") as handle:
                archive.writestr(arcname, handle.read())

    buffer.seek(0)
    response = HttpResponse(buffer.getvalue(), content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="run-{str(run.id)[:8]}-{label}.zip"'
    return response


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
