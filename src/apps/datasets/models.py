"""Dataset — an immutable uploaded expression matrix."""

from django.conf import settings
from django.db import models
from django.utils.text import get_valid_filename

from apps.common.models import CreatedAtModel, UUIDModel

#: FileField.file's default max_length is 100 (Django's default for the DB column
#: storing the relative path) — "datasets/" (9) + a UUID4 (36) + "/" (1) already spends
#: 46 of that. Capped well short of the ~54 that leaves, so even a long extension has
#: room: a filename that busts the column's max_length doesn't get truncated cleanly —
#: Django's own uniquifying retry loop can't converge past max_length and raises
#: SuspiciousFileOperation("Storage can not find an available filename") instead,
#: turning a long display name into an unhandled 500 (found via
#: apps.expression.services.materialize_public_dataset passing "<experiment title> —
#: <comparison label>" as a filename — three real curated comparisons had titles long
#: enough to trip this).
_MAX_FILENAME_STEM = 40


def dataset_upload_path(instance: "Dataset", filename: str) -> str:
    """``var/media/datasets/<dataset id>/<filename>``.

    Namespaced by id so two uploads of the same filename never collide.
    """
    stem, dot, ext = filename.rpartition(".")
    stem = stem if dot else filename
    safe_stem = get_valid_filename(stem)[:_MAX_FILENAME_STEM]
    safe_ext = f".{get_valid_filename(ext)}" if dot else ""
    return f"datasets/{instance.id}/{safe_stem}{safe_ext}"


class ValidationStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    VALID = "VALID", "Valid"
    INVALID = "INVALID", "Invalid"


class Dataset(UUIDModel, CreatedAtModel):
    """An uploaded input file.

    **Immutable.** Re-uploading creates a new row — the Dataset *is* the version, which
    is why the design maps' separate ``DatasetVersion`` table is not needed here
    (docs/architecture.md §5). A run holds a PROTECT reference, so a dataset that has
    been analysed can never be deleted out from under its results.
    """

    name = models.CharField(max_length=200)
    file = models.FileField(upload_to=dataset_upload_path)
    checksum_sha256 = models.CharField(
        max_length=64,
        editable=False,
        help_text="Computed once on upload and never recomputed.",
    )
    size_bytes = models.BigIntegerField(editable=False, default=0)
    schema_version = models.CharField(
        max_length=20,
        default="1",
        help_text="The input format this file was validated against.",
    )
    validation_status = models.CharField(
        max_length=10, choices=ValidationStatus, default=ValidationStatus.PENDING
    )
    validation_report = models.JSONField(
        default=dict,
        blank=True,
        help_text="Detected columns, row counts, errors and warnings.",
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="datasets"
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["uploaded_by", "-created_at"]),
            models.Index(fields=["validation_status"]),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def is_usable(self) -> bool:
        """Only a validated dataset may be submitted for analysis."""
        return self.validation_status == ValidationStatus.VALID
