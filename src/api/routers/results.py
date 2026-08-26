"""Candidates, artifacts, annotations and exports."""

import csv
import io
from uuid import UUID

from django.db.models import F
from django.http import FileResponse, HttpResponse
from ninja import Query, Router, Status
from ninja.pagination import LimitOffsetPagination, paginate

from api.auth import get_owned
from api.errors import NotFound, ValidationFailed
from api.schemas import AnnotationIn, AnnotationOut, ArtifactOut, CandidateDetailOut, CandidateOut
from apps.analyses.models import AnalysisRun
from apps.results.models import Annotation, Artifact, Candidate, DecisionTag

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
    return get_owned(Candidate, candidate_id, request.user, select_related=("run", "run__project"))


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

    response = HttpResponse(buffer.getvalue(), content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="run-{str(run.id)[:8]}-candidates.csv"'
    return response


# --- Annotations ------------------------------------------------------------------


@router.get("/candidates/{candidate_id}/annotations", response=list[AnnotationOut])
def list_annotations(request, candidate_id: UUID):
    get_owned(Candidate, candidate_id, request.user)
    return Annotation.objects.filter(candidate_id=candidate_id).select_related("author")


@router.post("/candidates/{candidate_id}/annotations", response={201: AnnotationOut})
def create_annotation(request, candidate_id: UUID, payload: AnnotationIn):
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
    annotation = get_owned(Annotation, annotation_id, request.user)
    annotation.delete()
    return Status(204, None)
