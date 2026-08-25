from django.contrib import admin
from django.utils.html import format_html

from apps.results.models import Annotation, Artifact, Candidate, CandidateMetric


class CandidateMetricInline(admin.TabularInline):
    model = CandidateMetric
    extra = 0
    can_delete = False
    readonly_fields = ("name", "raw_value", "normalized_value", "weight", "direction")

    def has_add_permission(self, request, obj=None) -> bool:
        return False


class AnnotationInline(admin.TabularInline):
    """Researcher decisions. Editable — unlike engine output, these are product-owned."""

    model = Annotation
    extra = 0
    fields = ("author", "decision_tag", "text", "created_at")
    readonly_fields = ("created_at",)


class ArtifactInline(admin.TabularInline):
    model = Artifact
    extra = 0
    fk_name = "candidate"
    can_delete = False
    fields = ("kind", "file", "media_type", "size_bytes")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None) -> bool:
        return False


@admin.register(Candidate)
class CandidateAdmin(admin.ModelAdmin):
    list_display = (
        "engine_ref",
        "run_link",
        "rank",
        "score_display",
        "gate_family",
        "logic_type",
        "verdict",
    )
    list_filter = ("gate_family", "logic_type", "is_rejected")
    search_fields = ("engine_ref", "summary", "run__id")
    list_select_related = ("run",)
    inlines = [CandidateMetricInline, ArtifactInline, AnnotationInline]

    # Engine output is a record of what was computed. It is not editable.
    readonly_fields = (
        "id",
        "run",
        "engine_ref",
        "rank",
        "overall_score",
        "gate_family",
        "logic_type",
        "triggers",
        "design",
        "summary",
        "warnings",
        "is_rejected",
        "rejection_reason",
    )

    def has_add_permission(self, request) -> bool:
        return False

    @admin.display(description="Run", ordering="run")
    def run_link(self, obj) -> str:
        return str(obj.run_id)[:8]

    @admin.display(description="Score", ordering="overall_score")
    def score_display(self, obj) -> str:
        return "—" if obj.overall_score is None else f"{obj.overall_score:.4f}"

    @admin.display(description="Verdict", ordering="is_rejected")
    def verdict(self, obj) -> str:
        if not obj.is_rejected:
            return format_html('<span style="color:#15803d">{}</span>', "accepted")
        return format_html(
            '<span style="color:#b91c1c" title="{}">{}</span>',
            obj.rejection_reason,
            "rejected",
        )


@admin.register(Artifact)
class ArtifactAdmin(admin.ModelAdmin):
    list_display = ("kind", "run_link", "candidate", "media_type", "size_bytes", "created_at")
    list_filter = ("kind", "media_type", "created_at")
    search_fields = ("run__id", "checksum_sha256")
    list_select_related = ("run", "candidate")
    readonly_fields = ("id", "checksum_sha256", "size_bytes", "created_at")

    @admin.display(description="Run", ordering="run")
    def run_link(self, obj) -> str:
        return str(obj.run_id)[:8]


@admin.register(Annotation)
class AnnotationAdmin(admin.ModelAdmin):
    list_display = ("candidate", "author", "decision_tag", "created_at")
    list_filter = ("decision_tag", "created_at")
    search_fields = ("text", "author__username", "candidate__engine_ref")
    list_select_related = ("candidate", "author")
    readonly_fields = ("created_at",)


@admin.register(CandidateMetric)
class CandidateMetricAdmin(admin.ModelAdmin):
    list_display = ("candidate", "name", "raw_value", "normalized_value", "weight", "direction")
    list_filter = ("name", "direction")
    search_fields = ("name", "candidate__engine_ref")
    list_select_related = ("candidate",)
