"""``parse_dge_table`` — the CSV/TSV edge, docs/integration.md GAP-1.

Fixtures below are shaped exactly like the three real input shapes docs/genes.md §2
measured: a DESeq2-style upload (mixed-case headers, a p_adj column), the bundled
example (no symbol column), and the public catalog (no p_adj column at all, some rows
with no p-value either) — using the real header row and the real first eight data rows
of ``E-CURD-149__g3_g1.csv`` for the last one, not an invented fixture.
"""

import pytest

from engine.domain import DgeRow
from engine.errors import InputValidationError
from engine.inputs import parse_dge_table

# The real header and first 8 data rows of src/apps/expression/catalog/human/
# E-CURD-149__g3_g1.csv (docs/genes.md §1's own worked example).
E_CURD_149_HEAD = b"""gene_id,gene_symbol,log2fc,pvalue,padj
ENSG00000263503,MAPK8IP1P2,-23.1,0.00613402959179577,
ENSG00000280683,LINC01242,-21.8,0.062828360921023,
ENSG00000198744,MTCO3P12,-20.9,,
ENSG00000118113,MMP8,10.0,8.38041931778982e-08,
ENSG00000137869,CYP19A1,9.3,0.000157405572268537,
ENSG00000102837,OLFM4,9.1,8.40026345156656e-06,
ENSG00000163710,PCOLCE2,9.0,0.000157405572268537,
ENSG00000227292,,8.2,0.0019745406015627,
"""


def test_parses_a_real_public_catalog_shape():
    table = parse_dge_table(E_CURD_149_HEAD, "E-CURD-149.csv")
    assert len(table) == 8
    by_id = table.by_gene_id()

    mmp8 = by_id["ENSG00000118113"]
    assert mmp8.symbol == "MMP8"
    assert mmp8.log2_fold_change == pytest.approx(10.0)
    assert mmp8.p_value == pytest.approx(8.38041931778982e-08)
    # The catalog carries no adjusted p-value column at all — never fabricated.
    assert mmp8.p_adj is None

    # A blank pvalue cell ("" between two commas) is "not tested", not 0.0 or NaN.
    mtco3p12 = by_id["ENSG00000198744"]
    assert mtco3p12.p_value is None

    # A blank symbol cell parses to "", not None — the field is a plain str.
    blank_symbol = by_id["ENSG00000227292"]
    assert blank_symbol.symbol == ""


def test_recognises_a_deseq2_style_upload_with_mixed_case_headers():
    raw = (
        b"gene_id,log2FoldChange,baseMean,pvalue,padj\n"
        b"katG,3.308,1481.6,4.144e-04,1.243e-03\n"
        b"soxS,3.852,437.3,1.027e-04,3.080e-04\n"
    )
    table = parse_dge_table(raw, "deseq2_results.csv")
    row = table.by_gene_id()["katG"]
    assert row.log2_fold_change == pytest.approx(3.308)
    assert row.base_mean == pytest.approx(1481.6)
    assert row.p_adj == pytest.approx(1.243e-03)


def test_recognises_group_mean_columns():
    raw = b"gene_id,log2fc,base_expression,target_expression,padj\nb0002,2.0,10.0,80.0,0.01\n"
    row = parse_dge_table(raw).rows[0]
    assert row.control_mean == pytest.approx(10.0)
    assert row.target_mean == pytest.approx(80.0)


def test_tsv_extension_is_tab_delimited():
    raw = b"gene_id\tlog2fc\tpadj\nb0002\t2.0\t0.01\n"
    row = parse_dge_table(raw, "results.tsv").rows[0]
    assert row.gene_id == "b0002"
    assert row.log2_fold_change == pytest.approx(2.0)


def test_a_row_with_no_gene_id_is_dropped_not_kept_with_a_blank_id():
    raw = b"gene_id,log2fc\n,3.0\nb0002,2.0\n"
    table = parse_dge_table(raw)
    assert len(table) == 1
    assert table.rows[0].gene_id == "b0002"


def test_a_row_with_no_effect_size_is_dropped():
    raw = b"gene_id,log2fc\nb0001,\nb0002,2.0\n"
    table = parse_dge_table(raw)
    assert [row.gene_id for row in table.rows] == ["b0002"]


def test_an_unparseable_number_becomes_none_not_zero():
    raw = b"gene_id,log2fc,padj\nb0002,2.0,not-a-number\n"
    row = parse_dge_table(raw).rows[0]
    assert row.p_adj is None


@pytest.mark.parametrize("blank", ["NA", "NaN", "null", "None", ""])
def test_r_and_python_null_spellings_all_become_none(blank):
    raw = f"gene_id,log2fc,padj\nb0002,2.0,{blank}\n".encode()
    row = parse_dge_table(raw).rows[0]
    assert row.p_adj is None


def test_no_header_row_raises():
    with pytest.raises(InputValidationError, match="no header row"):
        parse_dge_table(b"")


def test_no_gene_identifier_column_raises():
    with pytest.raises(InputValidationError, match="No gene identifier column"):
        parse_dge_table(b"foo,bar\n1,2\n")


def test_not_utf8_raises():
    with pytest.raises(InputValidationError, match="UTF-8"):
        parse_dge_table(b"gene_id,log2fc\n\xff\xfe,2.0\n")


def test_duplicate_gene_ids_are_both_kept_by_the_parser():
    """De-duplication is a scientific choice (which row to trust) that belongs to
    ``GeneSelector``, not this parser (docs/genes.md, the module's own docstring)."""
    raw = b"gene_id,log2fc\nb0002,2.0\nb0002,3.0\n"
    table = parse_dge_table(raw)
    assert len(table) == 2


def test_returns_a_real_dge_row_type():
    row = parse_dge_table(b"gene_id,log2fc\nb0002,2.0\n").rows[0]
    assert isinstance(row, DgeRow)
