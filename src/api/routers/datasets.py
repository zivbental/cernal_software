"""Dataset upload and listing.

Upload is synchronous: the file is checksummed and validated before the response
returns, so a researcher learns immediately whether it is usable.
"""

from uuid import UUID

from ninja import File, Form, Router, Status
from ninja.files import UploadedFile
from ninja.security import django_auth

from api.auth import get_owned, owned_queryset
from api.errors import Conflict, ValidationFailed
from api.schemas import DatasetOut, ExampleDatasetOut, UseExampleIn
from apps.datasets.models import Dataset
from apps.datasets.services import (
    EXAMPLES,
    DatasetValidationError,
    create_dataset,
    create_example_dataset,
    delete_dataset,
)

router = Router()


@router.get("/datasets", response=list[DatasetOut])
def list_datasets(request):
    return owned_queryset(Dataset, request.user)


@router.post("/datasets", response={201: DatasetOut})
def upload_dataset(
    request,
    file: UploadedFile = File(...),
    name: str = Form(default=""),
):
    try:
        dataset = create_dataset(uploaded_file=file, user=request.user, name=name or None)
    except DatasetValidationError as exc:
        raise ValidationFailed(str(exc)) from None

    return Status(201, dataset)


@router.get("/example-datasets", response=list[ExampleDatasetOut], auth=None)
def list_examples(request):
    """Datasets bundled with the app, so the product can be tried without your own data."""
    return [
        ExampleDatasetOut(key=key, label=example["label"], description=example["description"])
        for key, example in sorted(EXAMPLES.items())
    ]


@router.post("/datasets/example", response={201: DatasetOut})
def use_example_dataset(request, payload: UseExampleIn):
    """Copy a bundled example into a real, validated dataset the user can submit a run against."""
    try:
        dataset = create_example_dataset(user=request.user, key=payload.key)
    except DatasetValidationError as exc:
        raise ValidationFailed(str(exc)) from None

    return Status(201, dataset)


@router.get("/datasets/{dataset_id}", response=DatasetOut)
def get_dataset(request, dataset_id: UUID):
    return get_owned(Dataset, dataset_id, request.user)


@router.delete("/datasets/{dataset_id}", response={204: None}, auth=django_auth)
def remove_dataset(request, dataset_id: UUID):
    """Session-authenticated only (docs/public-api.md §13, §6): destructive
    operations stay in the web UI, where a human is present — a leaked API key must
    not be able to delete anything, whatever scope it carries."""
    dataset = get_owned(Dataset, dataset_id, request.user)

    try:
        delete_dataset(dataset)
    except DatasetValidationError as exc:
        raise Conflict(str(exc)) from None

    return Status(204, None)
