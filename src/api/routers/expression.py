"""Curated public transcriptomics datasets — organism -> experiment -> comparison
(docs/public-datasets.md). Read-only catalog browsing needs no key (like
``/example-datasets``); materializing a comparison into a real ``Dataset`` needs a
session or API key, same as any other write.
"""

from ninja import Router, Status

from api.errors import ValidationFailed
from api.schemas import (
    DatasetOut,
    MaterializePublicDatasetIn,
    OrganismOut,
    PublicComparisonOut,
    PublicDatasetInfoOut,
    PublicExperimentOut,
)
from apps.datasets.services import DatasetValidationError
from apps.expression.services import (
    get_comparison_info,
    list_comparisons,
    list_experiments,
    list_organisms,
    materialize_public_dataset,
)

router = Router()


@router.get("/public-datasets/organisms", response=list[OrganismOut], auth=None)
def organisms(request):
    return list_organisms()


@router.get("/public-datasets/experiments", response=list[PublicExperimentOut], auth=None)
def experiments(request, organism: str):
    return list_experiments(organism)


@router.get("/public-datasets/comparisons", response=list[PublicComparisonOut], auth=None)
def comparisons(request, experiment: str):
    return list_comparisons(experiment)


# Literal paths must be registered before the "/{comparison_key}" wildcard below —
# Django's URL resolver matches patterns in registration order and a wildcard segment
# matches a literal string like "materialize" just as happily, so a POST here would
# otherwise hit the GET-only wildcard route first and get a bare 405.
@router.post("/public-datasets/materialize", response={201: DatasetOut})
def materialize(request, payload: MaterializePublicDatasetIn):
    """Copy one curated comparison into a real, owned Dataset — same shape as
    ``POST /api/datasets/example``, generalized from one bundled key to the full
    catalog."""
    try:
        dataset = materialize_public_dataset(
            user=request.user, comparison_key=payload.comparison_key
        )
    except DatasetValidationError as exc:
        raise ValidationFailed(str(exc)) from None

    return Status(201, dataset)


@router.get("/public-datasets/{comparison_key}", response=PublicDatasetInfoOut, auth=None)
def comparison_info(request, comparison_key: str):
    try:
        return get_comparison_info(comparison_key)
    except DatasetValidationError as exc:
        raise ValidationFailed(str(exc)) from None
