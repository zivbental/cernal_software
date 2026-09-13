"""Provenance for a ``Dataset`` materialized from a public transcriptomics provider.

Kept as its own table, one-to-one onto ``apps.datasets.Dataset``, rather than new fields
on ``Dataset`` itself — a public dataset's provenance is additive, opt-in metadata that
an upload never has, and ``Dataset`` stays exactly as generic and well-tested as it is
today (docs/architecture.md §5's "Dataset is the version" rule is untouched).
"""

from django.db import models

from apps.common.models import CreatedAtModel, UUIDModel
from apps.datasets.models import Dataset


class Provider(models.TextChoices):
    """Where the underlying differential-expression data actually came from.

    ``YEAST_EXPRESSION`` is a name, not a promise about the backend: yStreX (the
    resource this was meant to wrap) was unreachable when this catalog was built, so it
    is served by ``ExpressionAtlasProvider`` scoped to *S. cerevisiae* today. Nothing
    outside ``apps/expression/providers/`` is supposed to know that.
    """

    EXPRESSION_ATLAS = "expression_atlas", "EMBL-EBI Expression Atlas"
    BVBRC = "bvbrc", "BV-BRC"
    YEAST_EXPRESSION = "yeast_expression", "Yeast Expression"


class DatasetProvenance(UUIDModel, CreatedAtModel):
    """Where one materialized ``Dataset`` came from, for scientific reproducibility.

    Every field here answers docs' "the user should always be able to determine where
    the expression profile came from" requirement. ``retrieved_at`` is the sync-time
    timestamp from the bundled catalog manifest — when the data was actually pulled from
    the provider — not when this particular user happened to click "load."
    """

    dataset = models.OneToOneField(Dataset, on_delete=models.CASCADE, related_name="provenance")

    provider = models.CharField(max_length=20, choices=Provider.choices)
    organism = models.CharField(max_length=20, help_text="engine.domain.Host value, e.g. 'ecoli'.")

    experiment_accession = models.CharField(max_length=100)
    experiment_title = models.CharField(max_length=300)
    comparison_id = models.CharField(max_length=100)
    comparison_label = models.CharField(max_length=300)
    experimental_condition = models.CharField(max_length=200, blank=True)
    reference_condition = models.CharField(max_length=200, blank=True)

    source_url = models.URLField(max_length=500)
    retrieved_at = models.DateTimeField(
        help_text="When this catalog entry was synced from the provider."
    )
    analysis_method = models.CharField(max_length=200, blank=True)
    publication_doi = models.CharField(max_length=100, blank=True)

    #: Catch-all for anything provider-specific worth keeping but not worth a column —
    #: e.g. BV-BRC's bioset_id, Expression Atlas's raw contrast id. Never read by
    #: business logic; it exists so nothing a provider supplied is silently discarded.
    provider_metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [models.Index(fields=["provider", "organism"])]

    def __str__(self) -> str:
        return f"{self.experiment_accession} · {self.comparison_label}"
