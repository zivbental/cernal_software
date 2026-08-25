from django.contrib import admin
from django.db.models import Count

from apps.projects.models import Project


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "organism", "dataset_count", "run_count", "created_at")
    list_filter = ("organism", "created_at")
    search_fields = ("name", "organism", "biological_objective", "owner__username")
    readonly_fields = ("id", "created_at", "updated_at")
    list_select_related = ("owner",)
    date_hierarchy = "created_at"

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(
                _datasets=Count("datasets", distinct=True), _runs=Count("runs", distinct=True)
            )
        )

    @admin.display(description="Datasets", ordering="_datasets")
    def dataset_count(self, obj) -> int:
        return obj._datasets

    @admin.display(description="Runs", ordering="_runs")
    def run_count(self, obj) -> int:
        return obj._runs
