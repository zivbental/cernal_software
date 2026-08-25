"""Abstract base models shared across the Platform apps.

UUID primary keys throughout: identifiers appear in URLs and are handed to the engine,
so they must not leak row counts or be guessable by increment.
"""

import uuid

from django.db import models


class UUIDModel(models.Model):
    """Primary key that is safe to expose externally."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class CreatedAtModel(models.Model):
    """For records that are written once and never updated."""

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        abstract = True


class TimestampedModel(CreatedAtModel):
    """For records that are edited after creation."""

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
