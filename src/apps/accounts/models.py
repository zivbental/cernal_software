from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

from apps.common.models import TimestampedModel, UUIDModel


class User(AbstractUser):
    """Custom user model.

    Intentionally empty. Defined at Step 0, before the first migration, because
    swapping AUTH_USER_MODEL after migrations exist is a painful Django migration.
    See docs/architecture.md §5.
    """


#: Two risk levels, no more (ADR 0006; docs/public-api.md §6). `design` implies `read` —
#: enforced in apps/accounts/services.py, not here, since a model has no business
#: encoding a permission hierarchy.
class ApiKeyScope(models.TextChoices):
    READ = "read", "Read"
    DESIGN = "design", "Design"


class ApiKey(UUIDModel, TimestampedModel):
    """A long-lived credential for a non-browser client (ADR 0006).

    The secret is never stored. Only its SHA-256 digest is, alongside a short public
    prefix used for lookup and display — so a key can be identified in a log or a UI
    without the log ever containing something that authenticates.
    """

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="api_keys"
    )
    label = models.CharField(max_length=100, help_text='"laptop", "snakemake-prod"')
    prefix = models.CharField(
        max_length=16,
        db_index=True,
        unique=True,
        help_text="e.g. cern_live_7Kd2 — the first 14 characters of the secret.",
    )
    key_hash = models.CharField(max_length=64, unique=True, help_text="sha256 hexdigest.")

    scopes = models.JSONField(default=list, help_text='["read"] or ["read", "design"].')
    max_concurrent_runs = models.PositiveSmallIntegerField(default=2)
    rate_per_minute = models.PositiveSmallIntegerField(default=60)

    expires_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["owner", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.label} ({self.prefix}…)"

    @property
    def is_active(self) -> bool:
        now = timezone.now()
        return self.revoked_at is None and (self.expires_at is None or self.expires_at > now)

    def has_scope(self, scope: str) -> bool:
        """``design`` implies ``read`` — there is no operation ``read`` cannot do that
        a ``design``-scoped key should be denied."""
        if scope == ApiKeyScope.READ:
            return ApiKeyScope.READ in self.scopes or ApiKeyScope.DESIGN in self.scopes
        return scope in self.scopes
