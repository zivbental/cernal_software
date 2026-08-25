"""Authorization helpers.

v1 has one rule: an object is yours, or you are staff. There is no other permission
logic — but there is no endpoint without this check either (docs/software-design.md
§7.2).

Missing and forbidden both return **404**. Returning 403 for an object that exists but
is not yours confirms its existence to someone who should not know.
"""

from django.db.models import Model

from api.errors import NotFound

#: How to reach the owning user from each model.
_OWNER_PATHS: dict[str, str] = {
    "projects.Project": "owner",
    "datasets.Dataset": "project__owner",
    "analyses.AnalysisRun": "project__owner",
    "results.Candidate": "run__project__owner",
    "results.Artifact": "run__project__owner",
    "results.Annotation": "candidate__run__project__owner",
}


def owned_queryset(model: type[Model], user):
    """Every row of ``model`` this user may see."""
    label = f"{model._meta.app_label}.{model.__name__}"
    try:
        path = _OWNER_PATHS[label]
    except KeyError:  # pragma: no cover — a new model needs an explicit decision
        raise NotImplementedError(
            f"{label} has no ownership path. Add one to api/auth.py before exposing it."
        ) from None

    queryset = model._default_manager.all()
    if user.is_staff:
        return queryset
    return queryset.filter(**{path: user})


def get_owned(model: type[Model], pk, user, *, select_related: tuple[str, ...] = ()):
    """Fetch one object the user owns, or raise ``NotFound``."""
    queryset = owned_queryset(model, user)
    if select_related:
        queryset = queryset.select_related(*select_related)

    obj = queryset.filter(pk=pk).first()
    if obj is None:
        raise NotFound(f"No {model.__name__.lower()} with that id.")
    return obj
