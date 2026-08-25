"""Projects."""

from uuid import UUID

from django.db import IntegrityError
from django.db.models import Count
from ninja import Router, Status

from api.auth import get_owned, owned_queryset
from api.errors import Conflict
from api.schemas import ProjectIn, ProjectOut, ProjectPatch
from apps.projects.models import Project

router = Router()


def _with_counts(queryset):
    return queryset.annotate(
        dataset_count=Count("datasets", distinct=True),
        run_count=Count("runs", distinct=True),
    )


@router.get("", response=list[ProjectOut])
def list_projects(request):
    return _with_counts(owned_queryset(Project, request.user))


@router.post("", response={201: ProjectOut})
def create_project(request, payload: ProjectIn):
    try:
        project = Project.objects.create(owner=request.user, **payload.dict())
    except IntegrityError:
        raise Conflict("You already have a project with that name.") from None
    return Status(201, _with_counts(Project.objects.filter(pk=project.pk)).get())


@router.get("/{project_id}", response=ProjectOut)
def get_project(request, project_id: UUID):
    get_owned(Project, project_id, request.user)
    return _with_counts(owned_queryset(Project, request.user).filter(pk=project_id)).get()


@router.patch("/{project_id}", response=ProjectOut)
def update_project(request, project_id: UUID, payload: ProjectPatch):
    project = get_owned(Project, project_id, request.user)

    changed = payload.dict(exclude_unset=True)
    for field, value in changed.items():
        if value is not None:
            setattr(project, field, value)

    try:
        project.save()
    except IntegrityError:
        raise Conflict("You already have a project with that name.") from None

    return _with_counts(Project.objects.filter(pk=project.pk)).get()


@router.delete("/{project_id}", response={204: None})
def delete_project(request, project_id: UUID):
    project = get_owned(Project, project_id, request.user)

    if project.runs.exists():
        raise Conflict(
            "This project has analysis runs and cannot be deleted. "
            "Results must not outlive the project that produced them."
        )

    project.delete()
    return Status(204, None)
