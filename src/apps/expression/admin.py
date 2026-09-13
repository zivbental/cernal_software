from django.contrib import admin

from apps.expression.models import DatasetProvenance


@admin.register(DatasetProvenance)
class DatasetProvenanceAdmin(admin.ModelAdmin):
    list_display = (
        "experiment_accession",
        "comparison_label",
        "provider",
        "organism",
        "created_at",
    )
    list_filter = ("provider", "organism")
    search_fields = (
        "experiment_accession",
        "experiment_title",
        "comparison_label",
        "dataset__name",
    )
    list_select_related = ("dataset",)
    date_hierarchy = "created_at"

    # Provenance describes a fact about the past sync — never edited after the fact.
    readonly_fields = (
        "id",
        "dataset",
        "provider",
        "organism",
        "experiment_accession",
        "experiment_title",
        "comparison_id",
        "comparison_label",
        "experimental_condition",
        "reference_condition",
        "source_url",
        "retrieved_at",
        "analysis_method",
        "publication_doi",
        "provider_metadata",
        "created_at",
    )
