"""Results — what an analysis produced, and what researchers decided about it."""

from pathlib import PurePosixPath

from django.conf import settings
from django.db import models
from django.utils.text import get_valid_filename

from apps.common.models import CreatedAtModel, UUIDModel


def artifact_upload_path(instance: "Artifact", filename: str) -> str:
    """``var/media/artifacts/<run id>/<relative path>``.

    Subdirectories in the engine's artifact path are preserved (``sequences/x.fasta``)
    so that two artifacts with the same basename cannot collide. Path traversal and
    absolute paths are stripped: the engine is trusted today, but this becomes a network
    boundary later (docs/architecture.md §16).
    """
    parts = [
        cleaned
        for part in PurePosixPath(filename).parts
        if part not in ("", ".", "..", "/")
        and (cleaned := get_valid_filename(part)) not in ("", ".", "..")
    ]
    return f"artifacts/{instance.run_id}/{'/'.join(parts)}"


class MetricDirection(models.TextChoices):
    HIGHER_BETTER = "HIGHER_BETTER", "Higher is better"
    LOWER_BETTER = "LOWER_BETTER", "Lower is better"


class DecisionTag(models.TextChoices):
    NONE = "NONE", "No decision"
    PINNED = "PINNED", "Pinned"
    SHORTLISTED = "SHORTLISTED", "Shortlisted"
    REJECTED = "REJECTED", "Rejected"
    SYNTHESIZE = "SYNTHESIZE", "Synthesize"


class Candidate(UUIDModel):
    """One proposed circuit produced by a run.

    Rejected candidates are stored, never filtered away (rule 8) — a researcher needs to
    see what was considered and why it lost. The database enforces that: a rejected
    candidate without a reason cannot be written.
    """

    run = models.ForeignKey(
        "analyses.AnalysisRun", on_delete=models.CASCADE, related_name="candidates"
    )
    engine_ref = models.CharField(
        max_length=50,
        help_text="The engine's local candidate id, kept so a stored row can be traced "
        "back to the result manifest that produced it.",
    )

    rank = models.IntegerField(null=True, blank=True, help_text="Null for rejected candidates.")
    overall_score = models.FloatField(null=True, blank=True, help_text="0-1, higher is better.")

    gate_family = models.CharField(max_length=50)
    logic_type = models.CharField(max_length=50)

    triggers = models.JSONField(default=dict, help_text="Trigger set and expression evidence.")
    design = models.JSONField(default=dict, help_text="Sequences, structure, logic graph.")
    summary = models.TextField(blank=True)
    warnings = models.JSONField(default=list, blank=True)

    is_rejected = models.BooleanField(default=False)
    rejection_reason = models.TextField(blank=True)

    class Meta:
        ordering = ["rank", "engine_ref"]
        indexes = [
            models.Index(fields=["run", "rank"]),
            models.Index(fields=["run", "is_rejected"]),
            models.Index(fields=["gate_family"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["run", "engine_ref"], name="unique_engine_ref_per_run"),
            # Rule 8, enforced by the database rather than by convention.
            models.CheckConstraint(
                condition=models.Q(is_rejected=False) | ~models.Q(rejection_reason=""),
                name="rejected_candidates_carry_a_reason",
            ),
            models.CheckConstraint(
                condition=models.Q(is_rejected=False) | models.Q(rank__isnull=True),
                name="rejected_candidates_are_unranked",
            ),
        ]

    def __str__(self) -> str:
        position = f"#{self.rank}" if self.rank else "unranked"
        return f"{self.engine_ref} ({position})"


class CandidateMetric(models.Model):
    """One measured property, with its scoring metadata preserved.

    A table rather than a JSON blob on Candidate, so the comparison UI can sort and
    filter in SQL. Both raw and normalized values are kept: the researcher is shown the
    decomposition, not a single opaque score (design map 12).
    """

    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name="metrics")
    name = models.CharField(max_length=100)
    raw_value = models.FloatField(null=True, blank=True)
    normalized_value = models.FloatField(null=True, blank=True, help_text="0-1, 1 is best.")
    weight = models.FloatField(default=1.0)
    direction = models.CharField(max_length=20, choices=MetricDirection)

    class Meta:
        ordering = ["candidate", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["candidate", "name"], name="unique_metric_per_candidate"
            )
        ]
        indexes = [models.Index(fields=["name"])]

    def __str__(self) -> str:
        return f"{self.name}={self.raw_value}"


class ArtifactCategory(models.TextChoices):
    """How the download UI groups artifacts. Declaration order is display order."""

    SUMMARY = "summary", "Summary"
    SEQUENCES = "sequences", "Gate & switch sequences"
    PLASMIDS = "plasmids", "Plasmid sequences"
    DIAGRAMS = "diagrams", "Diagrams"
    REPORTS = "reports", "Reports"
    OTHER = "other", "Other files"


#: Every artifact ``kind`` the engine or the platform can produce, mapped to the
#: category the download UI groups it under and a human label. An unmapped kind
#: (a new engine artifact nobody has taught this table about yet) falls back to
#: OTHER with a title-cased version of its own name — still downloadable, just not
#: specially grouped, so nothing the engine writes is ever silently hidden from the
#: download UI while this table catches up.
_KIND_INFO: dict[str, tuple[str, str]] = {
    "summary_table": (ArtifactCategory.SUMMARY, "Summary table — every candidate, every metric"),
    "design_table": (ArtifactCategory.SUMMARY, "Candidate list (engine export)"),
    "run_manifest": (ArtifactCategory.SUMMARY, "Run configuration"),
    "sequence_fasta": (ArtifactCategory.SEQUENCES, "Switch sequence (FASTA)"),
    "genbank": (ArtifactCategory.PLASMIDS, "Plasmid sequence (GenBank)"),
    "structure_plot": (ArtifactCategory.DIAGRAMS, "Structure diagram"),
    "logic_graph": (ArtifactCategory.DIAGRAMS, "Logic circuit diagram"),
    "report": (ArtifactCategory.REPORTS, "Report (PDF)"),
}


def filter_by_category(queryset, category: str):
    """Narrow an ``Artifact`` queryset to one category.

    ``category`` is a Python property, not a database column, so this is a query
    against ``kind`` instead. ``OTHER`` matches any kind ``_KIND_INFO`` does not
    know about, rather than nothing — an artifact is never invisible to every
    category just because this table has not caught up with a new engine kind yet.
    """
    mapped_kinds = list(_KIND_INFO)
    if category == ArtifactCategory.OTHER:
        return queryset.exclude(kind__in=mapped_kinds)
    kinds = [
        kind for kind, (kind_category, _label) in _KIND_INFO.items() if kind_category == category
    ]
    return queryset.filter(kind__in=kinds)


class Artifact(UUIDModel, CreatedAtModel):
    """A file produced by a run.

    Served only through an authorized download view, never by a static file handler
    (docs/architecture.md §7.2).
    """

    run = models.ForeignKey(
        "analyses.AnalysisRun", on_delete=models.CASCADE, related_name="artifacts"
    )
    candidate = models.ForeignKey(
        Candidate,
        on_delete=models.CASCADE,
        related_name="artifacts",
        null=True,
        blank=True,
        help_text="Null for run-level artifacts.",
    )
    kind = models.CharField(
        max_length=50,
        help_text=(
            "summary_table, design_table, run_manifest, sequence_fasta, genbank, "
            "structure_plot, logic_graph, report — see _KIND_INFO for how each is "
            "categorized and labelled for download."
        ),
    )
    file = models.FileField(upload_to=artifact_upload_path)
    media_type = models.CharField(max_length=100)
    checksum_sha256 = models.CharField(max_length=64, editable=False)
    size_bytes = models.BigIntegerField(editable=False, default=0)

    class Meta:
        ordering = ["kind", "id"]
        indexes = [
            models.Index(fields=["run", "kind"]),
            models.Index(fields=["candidate"]),
        ]

    def __str__(self) -> str:
        return f"{self.kind}: {self.file.name}"

    @property
    def category(self) -> str:
        return _KIND_INFO.get(self.kind, (ArtifactCategory.OTHER, ""))[0]

    @property
    def label(self) -> str:
        default = self.kind.replace("_", " ").capitalize()
        return _KIND_INFO.get(self.kind, (ArtifactCategory.OTHER, default))[1] or default

    @property
    def display_name(self) -> str:
        """The original filename, without the ``artifacts/<run id>/`` storage prefix."""
        return self.file.name.rsplit("/", 1)[-1] if self.file else ""


class Annotation(UUIDModel, CreatedAtModel):
    """A researcher's note or decision about a candidate.

    UUID primary key like every other API-exposed model: annotation ids appear in URLs,
    and a sequential integer would leak how many decisions have been recorded.

    Product-owned and entirely independent of engine output, so decisions survive
    re-runs and re-imports (design map 03).
    """

    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name="annotations")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="annotations"
    )
    text = models.TextField(blank=True)
    decision_tag = models.CharField(max_length=20, choices=DecisionTag, default=DecisionTag.NONE)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["candidate", "-created_at"]),
            models.Index(fields=["decision_tag"]),
        ]

    def __str__(self) -> str:
        return f"{self.get_decision_tag_display()} by {self.author}"
