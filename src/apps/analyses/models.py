"""AnalysisRun — one immutable submission and its lifecycle."""

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.common.models import TimestampedModel, UUIDModel


class RunStatus(models.TextChoices):
    """Six product-facing states (docs/software-design.md §6).

    The engine has many more internal stages; those are *mapped* into ``stage``, never
    copied into this vocabulary.
    """

    DRAFT = "DRAFT", "Draft"
    QUEUED = "QUEUED", "Queued"
    RUNNING = "RUNNING", "Running"
    COMPLETED = "COMPLETED", "Completed"
    FAILED = "FAILED", "Failed"
    CANCELLED = "CANCELLED", "Cancelled"


#: Once a run reaches one of these it never transitions again.
TERMINAL_STATUSES = frozenset({RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED})

#: The only legal transitions. Enforced by apps/analyses/services.py in Step 3 — this
#: table is the specification, so it lives with the model rather than in the service.
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    RunStatus.DRAFT: frozenset({RunStatus.QUEUED, RunStatus.CANCELLED}),
    RunStatus.QUEUED: frozenset({RunStatus.RUNNING, RunStatus.FAILED, RunStatus.CANCELLED}),
    RunStatus.RUNNING: frozenset({RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}),
    RunStatus.COMPLETED: frozenset(),
    RunStatus.FAILED: frozenset(),
    RunStatus.CANCELLED: frozenset(),
}


class AnalysisRun(UUIDModel, TimestampedModel):
    """One submitted analysis.

    **Immutable once submitted.** ``params_snapshot`` is frozen at submission, so
    editing the project afterwards affects future runs only (rule 7). Status changes
    happen only in ``apps/analyses/services.py`` (rule 5).
    """

    project = models.ForeignKey("projects.Project", on_delete=models.PROTECT, related_name="runs")
    dataset = models.ForeignKey("datasets.Dataset", on_delete=models.PROTECT, related_name="runs")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="runs"
    )

    # --- Immutable submission snapshot ---
    idempotency_key = models.CharField(
        max_length=64,
        unique=True,
        help_text="Re-submitting with the same key returns the existing run rather than "
        "launching a second computation.",
    )
    params_snapshot = models.JSONField(
        default=dict,
        help_text="The complete normalized configuration, frozen at submission time.",
    )
    gate_families = models.JSONField(default=list)
    scoring_profile = models.CharField(max_length=50, default="default")
    seed = models.IntegerField(null=True, blank=True)

    # --- Lifecycle ---
    status = models.CharField(max_length=12, choices=RunStatus, default=RunStatus.DRAFT)
    stage = models.CharField(
        max_length=100, blank=True, help_text="Human-readable current stage, shown to the user."
    )
    progress_pct = models.IntegerField(
        default=0, validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    cancel_requested = models.BooleanField(
        default=False,
        help_text="Cancellation is cooperative; the engine checks this between stages.",
    )

    # --- Outcome ---
    engine_version = models.CharField(max_length=50, blank=True)
    error_summary = models.TextField(
        blank=True, help_text="Safe to show a researcher. No tracebacks, no paths."
    )
    warnings = models.JSONField(default=list, blank=True)

    submitted_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["project", "-created_at"]),
            models.Index(fields=["status"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(progress_pct__gte=0) & models.Q(progress_pct__lte=100),
                name="progress_pct_within_bounds",
            )
        ]

    def __str__(self) -> str:
        return f"Run {str(self.id)[:8]} ({self.get_status_display()})"

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES

    @property
    def is_active(self) -> bool:
        return self.status in (RunStatus.QUEUED, RunStatus.RUNNING)

    def can_transition_to(self, status: str) -> bool:
        return status in ALLOWED_TRANSITIONS.get(self.status, frozenset())
