"""Project — a researcher's biological objective and the work done against it."""

from django.conf import settings
from django.db import models

from apps.common.models import TimestampedModel, UUIDModel


class Project(UUIDModel, TimestampedModel):
    """A biological objective plus the datasets and runs pursuing it.

    Editing a project never rewrites a submitted run: runs snapshot their configuration
    at submission time (docs/architecture.md §5, rule 7).
    """

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="projects",
    )
    name = models.CharField(max_length=200)
    organism = models.CharField(max_length=100, help_text="e.g. E. coli")
    biological_objective = models.TextField(
        blank=True,
        help_text="Base state, target state, and the logic behaviour being designed for.",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["owner", "name"], name="unique_project_name_per_owner")
        ]
        indexes = [models.Index(fields=["owner", "-created_at"])]

    def __str__(self) -> str:
        return self.name
