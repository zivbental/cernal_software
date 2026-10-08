"""Contrast meaning and retained dataset completeness are independent of study titles."""

import csv
import hashlib
import io
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from apps.expression.management.commands.sync_expression_catalog import Command
from apps.expression.providers.expression_atlas import ExpressionAtlasProvider
from apps.expression.providers.normalize import NormalizedDeRow, parse_contrast_label
from apps.expression.services import CATALOG_DIR


@pytest.mark.parametrize(
    "label, expected",
    [
        ("'Growth Medium' vs 'none' in 'normal'", ("Growth Medium", "none", "normal")),
        (
            "'ZNF804A knockdown' vs 'control' in 'neural progenitor cell'",
            ("ZNF804A knockdown", "control", "neural progenitor cell"),
        ),
        (
            "'sodium chloride 0.4 molar' at '15 minute' vs 'none' at '0 minute'",
            ("sodium chloride 0.4 molar at 15 minute", "none at 0 minute", ""),
        ),
        ("'A' vs 'B'", ("A", "B", "")),
    ],
)
def test_normalized_conditions_preserve_time_and_separate_shared_context(label, expected):
    assert parse_contrast_label(label) == expected


def test_ambiguous_label_is_rejected():
    with pytest.raises(ValueError, match="explicit experimental vs reference"):
        parse_contrast_label("arthritis study")


def test_primary_arthritis_configuration_is_a_normal_culture_contrast(monkeypatch):
    evidence = (
        Path(__file__).resolve().parents[1]
        / "docs/evidence/expression-atlas/E-GEOD-103501-configuration.xml"
    )
    monkeypatch.setattr(
        "apps.expression.providers.expression_atlas.requests.get",
        lambda *args, **kwargs: Mock(content=evidence.read_bytes()),
    )
    comparisons = ExpressionAtlasProvider().list_comparisons("E-GEOD-103501")
    selected = next(comparison for comparison in comparisons if comparison.comparison_id == "g3_g1")
    assert selected.experimental_condition == "Growth Medium"
    assert selected.reference_condition == "none"
    assert selected.comparison_context == "normal"
    assert selected.test_assay_group == "g1"
    assert selected.reference_assay_group == "g3"
    assert len(selected.test_assays) == 4
    assert len(selected.reference_assays) == 5
    disease = next(comparison for comparison in comparisons if comparison.comparison_id == "g1_g4")
    assert disease.experimental_condition == "systemic-onset juvenile idiopathic arthritis"
    assert disease.reference_condition == "normal"


def test_catalog_digests_and_statistic_counts_match_retained_files():
    manifest = json.loads((CATALOG_DIR / "manifest.json").read_text())
    for entry in manifest.values():
        content = (CATALOG_DIR / entry["csv_path"]).read_bytes()
        metadata = entry["provider_metadata"]
        assert hashlib.sha256(content).hexdigest() == metadata["csv_sha256"]
        rows = list(csv.DictReader(io.StringIO(content.decode())))
        assert len(rows) == entry["gene_count"] == metadata["retained_rows"]
        assert sum(bool(row["pvalue"]) for row in rows) == entry["genes_with_p_value"]
        assert sum(bool(row["padj"]) for row in rows) == entry["genes_with_adjusted_p_value"]
        assert metadata["source_tested_rows"] is None
        assert metadata["data_completeness"] == "historical_subset_source_total_unknown"


def test_new_sync_retains_full_analysis_rows_beyond_preview_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "apps.expression.management.commands.sync_expression_catalog.CATALOG_DIR", tmp_path
    )
    rows = [NormalizedDeRow(str(index), None, float(index), 0.01, None) for index in range(3500)]
    manifest = {}
    Command()._write_comparison(
        key="human__test__A_B",
        organism="human",
        provider="expression_atlas",
        accession="test",
        title="study",
        comparison_id="A_B",
        comparison_label="'A' vs 'B'",
        experimental_condition="A",
        reference_condition="B",
        source_url="https://www.ebi.ac.uk/",
        synced_at="2026-10-08T00:00:00+00:00",
        rows=rows,
        manifest=manifest,
    )
    entry = manifest["human__test__A_B"]
    assert entry["gene_count"] == 3500
    assert entry["provider_metadata"]["source_tested_rows"] == 3500
    assert entry["provider_metadata"]["data_completeness"] == "full_tested_rows"
    assert len(list(csv.DictReader((tmp_path / entry["csv_path"]).open()))) == 3500
