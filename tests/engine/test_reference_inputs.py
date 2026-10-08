"""Real reference resolution and formats accepted by the upload platform."""

import hashlib
import io
from pathlib import Path

import pytest
from openpyxl import Workbook

from engine.domain import Host
from engine.errors import InputValidationError
from engine.inputs import parse_dge_table
from engine.transcriptome import gene_reference, reference_metadata, resolve_gene_id


@pytest.mark.parametrize(
    ("host", "symbol", "gene"),
    [
        (Host.HUMAN, "SELE", "ENSG00000007908"),
        (Host.ECOLI, "thrA", "b0002"),
        (Host.YEAST, "CDC28", "YBR160W"),
        (Host.C_ACNES, "dnaA", "F6X01_RS00005"),
    ],
)
def test_symbols_resolve_to_real_reference_sequences(host, symbol, gene):
    ref = gene_reference(host, symbol)
    assert ref["gene_id"] == gene
    assert ref["gene_symbol"] == symbol
    assert len(ref["sequence"]) > 100
    assert set(ref["sequence"]) <= set("ACGU")
    assert resolve_gene_id(host, gene) == gene


def test_human_reference_is_pinned_and_uses_mane_select():
    ref = gene_reference(Host.HUMAN, "ENSG00000007908.99")
    assert ref["transcript_id"] == "ENST00000333360.12"
    meta = reference_metadata(Host.HUMAN)
    assert meta["release"] == 116
    assert meta["genes"][ref["gene_id"]]["priority"] == 0
    path = Path(__file__).resolve().parents[2] / "src/engine/data/transcriptomes/human.fasta.gz"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == meta["sequence_sha256"]


@pytest.mark.parametrize("host", list(Host))
def test_unknown_gene_has_a_useful_error(host):
    with pytest.raises(InputValidationError, match="not found"):
        resolve_gene_id(host, "not_a_real_gene_identifier")


@pytest.mark.parametrize(
    ("suffix", "delimiter"),
    [
        ("csv", ","),
        ("tsv", "\t"),
        ("txt", "\t"),
        ("txt", ","),
        ("csv", ";"),
    ],
)
def test_delimited_formats_match(suffix, delimiter):
    raw = delimiter.join([" Gene ID ", "log2 Fold Change", "P_adj"])
    raw += "\n" + delimiter.join(["SELE", "2.5", "0.001"]) + "\n"
    table = parse_dge_table(raw.encode(), f"input.{suffix}")
    assert table.rows[0].gene_id == "SELE"
    assert table.rows[0].log2_fold_change == 2.5
    assert table.rows[0].p_adj == 0.001


def test_xlsx_matches_csv():
    workbook = Workbook()
    workbook.active.append(["gene_id", "log2fc", "padj"])
    workbook.active.append(["SELE", 2.5, 0.001])
    buffer = io.BytesIO()
    workbook.save(buffer)
    workbook.close()
    assert parse_dge_table(buffer.getvalue(), "input.xlsx") == parse_dge_table(
        b"gene_id,log2fc,padj\nSELE,2.5,0.001\n"
    )


def test_corrupt_xlsx_reports_input_error():
    with pytest.raises(InputValidationError, match="spreadsheet"):
        parse_dge_table(b"not a workbook", "bad.xlsx")


@pytest.mark.parametrize("identifier", [None, 123, {"gene": "SELE"}])
def test_nontext_gene_identifier_is_an_input_error(identifier):
    with pytest.raises(InputValidationError, match="must be text"):
        resolve_gene_id(Host.HUMAN, identifier)
