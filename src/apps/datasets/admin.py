from django.contrib import admin

from apps.datasets.models import Dataset


@admin.register(Dataset)
class DatasetAdmin(admin.ModelAdmin):
    list_display = ("name", "project", "validation_status", "size_display", "created_at")
    list_filter = ("validation_status", "schema_version", "created_at")
    search_fields = ("name", "project__name", "checksum_sha256")
    list_select_related = ("project",)
    date_hierarchy = "created_at"

    # A dataset is immutable once uploaded (docs/architecture.md §5).
    readonly_fields = (
        "id",
        "checksum_sha256",
        "size_bytes",
        "created_at",
        "uploaded_by",
        "validation_report",
    )

    @admin.display(description="Size", ordering="size_bytes")
    def size_display(self, obj) -> str:
        size = obj.size_bytes or 0
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024:
                return f"{size:.0f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
