"""EMBL-EBI Expression Atlas — differential RNA-seq experiments (docs §5 of the brief).

Sourced from the FTP mirror, not the HTML UI or the JSON search endpoint's query
params — verified live that ``?species=``/``?experimentType=`` on
``https://www.ebi.ac.uk/gxa/json/experiments`` are silently ignored (the endpoint
returns the *entire* cross-species catalog regardless), so species/type filtering
happens client-side here, once, at sync time. The per-experiment files under
``http://ftp.ebi.ac.uk/pub/databases/microarray/data/atlas/experiments/{accession}/``
are the real, stable, documented resource (docs/gxa/download's "FTP" section) — plain
files, no auth, no rate limit encountered.

**Discovered limitation, not assumed:** ``{accession}-analytics.tsv`` has no
adjusted-p-value column — only ``{contrast}.p-value`` and
``{contrast}.log2foldchange``. Every row this provider emits has
``adjusted_p_value=None``. Reporting Atlas's raw p-value as if it were already
FDR-corrected would be exactly the kind of invented precision CLAUDE.md §3 warns against.
"""

from __future__ import annotations

import csv
import io
import logging
import xml.etree.ElementTree as ET

import requests

from apps.expression.providers.normalize import NormalizedComparison, NormalizedDeRow

logger = logging.getLogger(__name__)

FTP_BASE = "http://ftp.ebi.ac.uk/pub/databases/microarray/data/atlas/experiments"
EXPERIMENTS_JSON = "https://www.ebi.ac.uk/gxa/json/experiments"
TIMEOUT = 30


class ExpressionAtlasProvider:
    """``list_experiments`` / ``list_comparisons`` / ``get_differential_expression`` —
    the shape the brief asks for, adapted to what the real API actually returns."""

    name = "expression_atlas"

    def list_experiments(self, species: str) -> list[dict]:
        """Every RNA-seq differential-expression experiment for one species.

        Never baseline/TPM-only, and never microarray — filtering on
        ``rawExperimentType == "RNASEQ_MRNA_DIFFERENTIAL"`` (not the looser
        ``experimentType == "Differential"``, which also matches microarray and
        proteomics experiments) is what the task's "RNA-seq differential expression
        only" requirement actually means, *and* it's what keeps every accession this
        returns fetchable: a microarray experiment's analytics file is named
        ``{accession}_{array-design}-analytics.tsv`` (platform-suffixed — discovered by
        listing a 404'ing accession's real FTP directory), not the plain
        ``{accession}-analytics.tsv`` this provider fetches. Filtering here means never
        needing to discover that filename at all.
        """
        response = requests.get(EXPERIMENTS_JSON, timeout=TIMEOUT)
        response.raise_for_status()
        experiments = response.json().get("experiments", [])
        return [
            {
                "accession": exp["experimentAccession"],
                "title": exp["experimentDescription"],
                "species": exp["species"],
            }
            for exp in experiments
            if exp.get("species") == species
            and exp.get("rawExperimentType") == "RNASEQ_MRNA_DIFFERENTIAL"
        ]

    def list_comparisons(self, accession: str) -> list[NormalizedComparison]:
        """Parse ``{accession}-configuration.xml``'s ``<contrast>`` elements.

        Each contrast's ``<name>`` is documented (and verified) as ``'A' vs 'B'`` —
        the experimental condition first, the reference second; positive log2FC means
        higher expression in A (docs §2's direction requirement).
        """
        url = f"{FTP_BASE}/{accession}/{accession}-configuration.xml"
        response = requests.get(url, timeout=TIMEOUT)
        response.raise_for_status()
        root = ET.fromstring(response.content)

        comparisons = []
        for contrast in root.iter("contrast"):
            contrast_id = contrast.get("id")
            name_el = contrast.find("name")
            if contrast_id is None or name_el is None or not name_el.text:
                continue
            experimental, _, reference = name_el.text.partition(" vs ")
            comparisons.append(
                NormalizedComparison(
                    comparison_id=contrast_id,
                    label=name_el.text,
                    experimental_condition=experimental.strip(" '"),
                    reference_condition=reference.strip(" '"),
                )
            )
        return comparisons

    def get_differential_expression(
        self, accession: str, contrast_id: str
    ) -> list[NormalizedDeRow]:
        """Parse ``{accession}-analytics.tsv``, selecting one contrast's two columns.

        One file holds every contrast in the experiment side by side
        (``{id}.p-value``, ``{id}.log2foldchange``); most files have exactly one.
        """
        url = f"{FTP_BASE}/{accession}/{accession}-analytics.tsv"
        response = requests.get(url, timeout=TIMEOUT)
        response.raise_for_status()

        reader = csv.DictReader(io.StringIO(response.text), delimiter="\t")
        pvalue_col = f"{contrast_id}.p-value"
        log2fc_col = f"{contrast_id}.log2foldchange"

        rows: list[NormalizedDeRow] = []
        for record in reader:
            raw_fc = record.get(log2fc_col)
            if raw_fc in (None, "", "NA"):
                continue  # not tested in this contrast — not the same as "no change"
            try:
                log2fc = float(raw_fc)
            except ValueError:
                continue

            raw_p = record.get(pvalue_col)
            pvalue = None
            if raw_p not in (None, "", "NA"):
                try:
                    pvalue = float(raw_p)
                except ValueError:
                    pvalue = None

            gene_id = record.get("Gene ID", "").strip()
            if not gene_id:
                continue

            rows.append(
                NormalizedDeRow(
                    gene_id=gene_id,
                    gene_symbol=(record.get("Gene Name") or "").strip() or None,
                    log2_fold_change=log2fc,
                    p_value=pvalue,
                    adjusted_p_value=None,  # not present in this file format — see module docstring
                )
            )
        return rows
