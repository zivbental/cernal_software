"""Dataset upload and listing.

Upload is synchronous: the file is checksummed and validated before the response
returns, so a researcher learns immediately whether it is usable.
"""

from uuid import UUID

from ninja import File, Form, Router, Status
from ninja.files import UploadedFile

from api.auth import get_owned, owned_queryset
from api.errors import Conflict, ValidationFailed
from api.schemas import DatasetOut
from apps.datasets.models import Dataset
from apps.datasets.services import DatasetValidationError, create_dataset, delete_dataset
from apps.projects.models import Project

router = Router()


@router.get("/projects/{project_id}/datasets", response=list[DatasetOut])
def list_datasets(request, project_id: UUID):
    get_owned(Project, project_id, request.user)
    return owned_queryset(Dataset, request.user).filter(project_id=project_id)


@router.post("/projects/{project_id}/datasets", response={201: DatasetOut})
def upload_dataset(
    request,
    project_id: UUID,
    file: UploadedFile = File(...),
    name: str = Form(default=""),
):
    project = get_owned(Project, project_id, request.user)

    try:
        dataset = create_dataset(
            project=project, uploaded_file=file, user=request.user, name=name or None
        )
    except DatasetValidationError as exc:
        raise ValidationFailed(str(exc)) from None

    return Status(201, dataset)


@router.get("/datasets/{dataset_id}", response=DatasetOut)
def get_dataset(request, dataset_id: UUID):
    return get_owned(Dataset, dataset_id, request.user)


@router.delete("/datasets/{dataset_id}", response={204: None})
def remove_dataset(request, dataset_id: UUID):
    dataset = get_owned(Dataset, dataset_id, request.user)

    try:
        delete_dataset(dataset)
    except DatasetValidationError as exc:
        raise Conflict(str(exc)) from None

    return Status(204, None)
