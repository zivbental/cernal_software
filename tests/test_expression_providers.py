"""Provider normalization (docs §26 of the public-datasets brief).

Every test here uses a captured/fabricated response shaped exactly like the real
provider (verified live during development — see docs/public-datasets.md) — no live
network call, so CI never depends on EMBL-EBI or BV-BRC being up.
"""

from unittest.mock import patch

from apps.expression.providers.bvbrc import BVBRCProvider
from apps.expression.providers.expression_atlas import ExpressionAtlasProvider
from apps.expression.providers.yeast import YeastExpressionProvider


class _FakeResponse:
    def __init__(self, *, json_data=None, text="", content=b"", headers=None, status=200):
        self._json = json_data
        self.text = text
        self.content = content or text.encode()
        self.headers = headers or {}
        self.status_code = status

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


# --- Expression Atlas ---------------------------------------------------------------


ATLAS_EXPERIMENTS_JSON = {
    "experiments": [
        {
            "experimentAccession": "E-TEST-1",
            "experimentDescription": "A real-shaped human RNA-seq experiment",
            "species": "Homo sapiens",
            "rawExperimentType": "RNASEQ_MRNA_DIFFERENTIAL",
        },
        {
            "experimentAccession": "E-TEST-2",
            "experimentDescription": "A microarray experiment — must be excluded",
            "species": "Homo sapiens",
            "rawExperimentType": "MICROARRAY_1COLOUR_MRNA_DIFFERENTIAL",
        },
        {
            "experimentAccession": "E-TEST-3",
            "experimentDescription": "Wrong species — must be excluded",
            "species": "Mus musculus",
            "rawExperimentType": "RNASEQ_MRNA_DIFFERENTIAL",
        },
    ]
}

ATLAS_CONFIGURATION_XML = b"""<?xml version="1.0"?>
<configuration>
  <analytics>
    <contrast id="g1_g2" cttv_primary="0">
      <name>'TNF-treated' vs 'untreated'</name>
    </contrast>
  </analytics>
</configuration>
"""

ATLAS_ANALYTICS_TSV = (
    "Gene ID\tGene Name\tg1_g2.p-value\tg1_g2.log2foldchange\n"
    "ENSG00000007908\tSELE\t1.2e-10\t6.84\n"
    "ENSG00000162692\tVCAM1\tNA\t5.94\n"  # missing p-value — must not crash
    "ENSG00000090339\tICAM1\t6.2e-5\t0\n"  # log2fc of exactly 0 — still a real, tested result
    "ENSG00000999999\tNOTTESTED\t\tNA\n"  # not tested in this contrast — must be dropped
)


def test_list_experiments_filters_to_rna_seq_differential_for_the_requested_species():
    provider = ExpressionAtlasProvider()
    with patch("apps.expression.providers.expression_atlas.requests.get") as mock_get:
        mock_get.return_value = _FakeResponse(json_data=ATLAS_EXPERIMENTS_JSON)
        result = provider.list_experiments("Homo sapiens")

    assert [e["accession"] for e in result] == ["E-TEST-1"]


def test_list_comparisons_parses_contrast_direction_from_the_name():
    provider = ExpressionAtlasProvider()
    with patch("apps.expression.providers.expression_atlas.requests.get") as mock_get:
        mock_get.return_value = _FakeResponse(content=ATLAS_CONFIGURATION_XML)
        comparisons = provider.list_comparisons("E-TEST-1")

    assert len(comparisons) == 1
    comparison = comparisons[0]
    assert comparison.comparison_id == "g1_g2"
    assert comparison.experimental_condition == "TNF-treated"
    assert comparison.reference_condition == "untreated"


def test_differential_expression_drops_untested_genes_and_tolerates_missing_pvalue():
    provider = ExpressionAtlasProvider()
    with patch("apps.expression.providers.expression_atlas.requests.get") as mock_get:
        mock_get.return_value = _FakeResponse(text=ATLAS_ANALYTICS_TSV)
        rows = provider.get_differential_expression("E-TEST-1", "g1_g2")

    by_symbol = {row.gene_symbol: row for row in rows}
    assert set(by_symbol) == {"SELE", "VCAM1", "ICAM1"}  # NOTTESTED dropped, not fabricated
    assert by_symbol["SELE"].p_value == 1.2e-10
    assert by_symbol["VCAM1"].p_value is None  # missing, not 0.0 or 1.0 (CLAUDE.md §3's rule)
    assert by_symbol["ICAM1"].log2_fold_change == 0.0

    # Expression Atlas's analytics.tsv has no adjusted-p-value column at all — every row
    # says so honestly rather than treating the raw p-value as if it were FDR-corrected.
    assert all(row.adjusted_p_value is None for row in rows)


# --- BV-BRC ---------------------------------------------------------------------------


def test_bvbrc_paginates_until_a_short_page_and_tolerates_a_missing_pvalue():
    page_1 = [
        {"locus_tag": f"b{i:04d}", "gene": f"gene{i}", "log2_fc": 1.5, "p_value": None}
        for i in range(2)
    ]
    page_2 = [{"locus_tag": "b0099", "gene": "thrA", "log2_fc": -2.1, "p_value": 0.01}]

    responses = [
        _FakeResponse(json_data=page_1, headers={"Content-Range": "items 0-1/3"}),
        _FakeResponse(json_data=page_2, headers={"Content-Range": "items 2-2/3"}),
    ]

    provider = BVBRCProvider()
    with (
        patch("apps.expression.providers.bvbrc.requests.get", side_effect=responses) as mock_get,
        patch(
            "apps.expression.providers.bvbrc.PAGE_SIZE", 2
        ),  # so a 2-item page reads as "more may follow"
    ):
        rows = provider.get_differential_expression("12345")

    assert mock_get.call_count == 2
    assert len(rows) == 3
    by_gene = {row.gene_id: row for row in rows}
    assert by_gene["b0000"].p_value is None  # not every bioset carries one — must not crash
    assert by_gene["b0099"].p_value == 0.01


def test_bvbrc_skips_a_row_with_no_gene_identifier_or_no_log2fc():
    page = [
        {"locus_tag": "", "gene_id": "", "gene": "orphan", "log2_fc": 1.0},
        {"locus_tag": "b0001", "gene": "thrA", "log2_fc": None},
        {"locus_tag": "b0002", "gene": "thrB", "log2_fc": 0.5},
    ]
    response = _FakeResponse(json_data=page, headers={"Content-Range": "items 0-2/3"})

    provider = BVBRCProvider()
    with patch("apps.expression.providers.bvbrc.requests.get", return_value=response):
        rows = provider.get_differential_expression("12345")

    assert [row.gene_id for row in rows] == ["b0002"]


# --- Yeast (thin wrapper) --------------------------------------------------------------


def test_yeast_provider_scopes_expression_atlas_to_s_cerevisiae():
    """Nothing outside this module should ever need to know the backend is Atlas —
    verified here by checking the *species* it actually asks Atlas for."""
    provider = YeastExpressionProvider()
    with patch.object(ExpressionAtlasProvider, "list_experiments") as mock_list:
        mock_list.return_value = []
        provider.list_experiments()

    mock_list.assert_called_once_with("Saccharomyces cerevisiae")
