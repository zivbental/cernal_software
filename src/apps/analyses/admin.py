from django.contrib import admin
from django.db.models import Count
from django.utils.html import format_html

from apps.analyses.models import AnalysisRun

_STATUS_COLOURS = {
    "DRAFT": "#6b7280",
    "QUEUED": "#b45309",
    "RUNNING": "#1d4ed8",
    "COMPLETED": "#15803d",
    "FAILED": "#b91c1c",
    "CANCELLED": "#6b7280",
}


@admin.register(AnalysisRun)
class AnalysisRunAdmin(admin.ModelAdmin):
    list_display = (
        "short_id",
        "project",
        "status_badge",
        "progress_display",
        "stage",
        "candidate_count",
        "submitted_at",
    )
    list_filter = ("status", "scoring_profile", "created_at")
    search_fields = ("id", "idempotency_key", "project__name")
    list_select_related = ("project", "dataset", "created_by")
    date_hierarchy = "created_at"

    # A submitted run is immutable, and status transitions happen only in
    # apps/analyses/services.py (rules 5 and 7). Admin is for inspection, not repair.
    readonly_fields = (
        "id",
        "project",
        "dataset",
        "created_by",
        "idempotency_key",
        "params_snapshot",
        "gate_families",
        "scoring_profile",
        "seed",
        "status",
        "stage",
        "progress_pct",
        "cancel_requested",
        "engine_version",
        "error_summary",
        "warnings",
        "submitted_at",
        "started_at",
        "finished_at",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request) -> bool:
        """Runs are created by submitting an analysis, never by hand."""
        return False

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_candidates=Count("candidates"))

    @admin.display(description="Run", ordering="id")
    def short_id(self, obj) -> str:
        return str(obj.id)[:8]

    @admin.display(description="Status", ordering="status")
    def status_badge(self, obj) -> str:
        return format_html(
            '<b style="color:{}">{}</b>',
            _STATUS_COLOURS.get(obj.status, "#000"),
            obj.get_status_display(),
        )

    @admin.display(description="Progress", ordering="progress_pct")
    def progress_display(self, obj) -> str:
        return f"{obj.progress_pct}%"

    @admin.display(description="Candidates", ordering="_candidates")
    def candidate_count(self, obj) -> int:
        return obj._candidates
