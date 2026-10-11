"""The one normalized shape every provider's raw response is converted into.

CLAUDE.md §3's rule for the engine ("a metric you could not compute is None, never 0.0")
applies here too: a provider that has no p-value for a bioset, or no adjusted p-value at
all (Expression Atlas's analytics.tsv has no such column), reports ``None`` — never a
fabricated number, never 0.0 or 1.0. See docs on each provider's real, discovered gaps.
"""

import re
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class NormalizedDeRow:
    """One gene's differential-expression result, in the shape
    ``apps.datasets.services.COLUMN_ALIASES`` already recognises — so a materialized
    public dataset validates through ``create_dataset`` exactly like an upload."""

    gene_id: str
    gene_symbol: str | None
    log2_fold_change: float
    p_value: float | None
    adjusted_p_value: float | None

    def as_row(self) -> dict[str, str]:
        """The CSV row this becomes — column names match ``COLUMN_ALIASES``' canonical
        keys directly, so no aliasing guesswork is needed when it's re-read."""
        return {
            "gene_id": self.gene_id,
            "gene_symbol": self.gene_symbol or "",
            "log2fc": repr(self.log2_fold_change),
            "pvalue": "" if self.p_value is None else repr(self.p_value),
            "padj": "" if self.adjusted_p_value is None else repr(self.adjusted_p_value),
        }


@dataclass(frozen=True, slots=True)
class NormalizedComparison:
    """One selectable ``Organism -> Experiment -> Comparison`` leaf (docs §2)."""

    comparison_id: str
    label: str
    experimental_condition: str
    reference_condition: str
    comparison_context: str = ""
    test_assay_group: str = ""
    reference_assay_group: str = ""
    test_assays: tuple[str, ...] = ()
    reference_assays: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class NormalizedExperiment:
    """One catalog entry's metadata, independent of which comparison is chosen."""

    provider: str
    organism: str
    accession: str
    title: str
    description: str
    source_url: str
    analysis_method: str = ""
    publication_doi: str = ""
    comparisons: list[NormalizedComparison] = field(default_factory=list)


CSV_FIELDNAMES = ["gene_id", "gene_symbol", "log2fc", "pvalue", "padj"]


def parse_contrast_label(label: str) -> tuple[str, str, str]:
    """Separate both contrasted conditions from a shared quoted sample context.

    Preserve time qualifiers and the raw label. An experiment title is not a contrast.
    Atlas writes e.g. 'Growth Medium' vs 'none' in 'normal'; normal applies to both sides.
    """
    experimental, separator, reference = label.strip().partition(" vs ")
    if not separator or not experimental.strip() or not reference.strip():
        raise ValueError(
            f"Contrast label has no explicit experimental vs reference pair: {label!r}"
        )
    reference, context_separator, context = reference.partition("' in '")

    def clean(value: str) -> str:
        value = value.strip()
        if value.startswith("'"):
            value = value[1:]
        if value.endswith("'"):
            value = value[:-1]
        return re.sub(r"'\s+(at|in)\s+'", r" \1 ", value).strip()

    return clean(experimental), clean(reference), clean(context) if context_separator else ""
