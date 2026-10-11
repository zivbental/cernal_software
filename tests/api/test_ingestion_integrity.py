"""Upload, preview and execution share a single deterministic input parser."""

import io
import json

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from openpyxl import Workbook

from apps.datasets.services import create_dataset, preview_expression_rows, validate_expression_file
from engine.client import inspect_expression_input


@pytest.fixture(autouse=True)
def isolated_upload_storage(media_root):
    return media_root


@pytest.mark.parametrize(
    "name,content",
    [
        ("study.csv", " gene_id , log2fc , padj \n b0005 , 2.0 ,0.01\n"),
        ("study.tsv", "gene_id\tlog2fc\tpadj\nb0005\t2.0\t0.01\n"),
        ("study.txt", "gene_id\tlog2fc\tpadj\nb0005\t2.0\t0.01\n"),
    ],
)
def test_upload_preview_engine_normalize_identically(user, name, content):
    dataset = create_dataset(
        uploaded_file=SimpleUploadedFile(name, content.encode()),
        user=user,
        name="display label with misleading .xlsx",
    )
    assert dataset.is_usable, dataset.validation_report
    preview = preview_expression_rows(dataset)
    inspected = inspect_expression_input(dataset.file.path, limit=None)
    row = preview["rows"][0]
    assert row["gene_id"] == inspected["preview"][0]["gene_id"] == "b0005"
    assert row["log2fc"] == inspected["preview"][0]["log2fc"] == 2
    assert row["padj"] == 0.01
    json.dumps(preview, allow_nan=False)


@pytest.mark.parametrize(
    "content",
    [
        " gene_id , log2fc \nb0005,not-number\n",
        "gene_id,log2fc\nb0005,inf\n",
        "gene_id,log2fc\nb0005,-inf\n",
        "gene_id,log2fc\nb0005,NaN\n",
        "gene_id,base_expression\nb0005,10\n",
        "gene_id,log2fc\n,2\n",
        "gene_id,log2fc,log2FoldChange\nb0005,2,3\n",
        "gene_id,log2fc\nb0005,2,extra\n",
    ],
)
def test_bad_content_never_becomes_a_usable_dataset(user, content):
    dataset = create_dataset(
        uploaded_file=SimpleUploadedFile("invalid.csv", content.encode()), user=user
    )
    assert not dataset.is_usable
    assert dataset.validation_report["errors"]


def test_multisheet_first_sheet_is_shared_despite_different_active_sheet(user):
    workbook = Workbook()
    workbook.active.append(["gene_id", "log2fc"])
    workbook.active.append(["b0005", 2])
    second = workbook.create_sheet("other")
    second.append(["gene_id", "log2fc"])
    second.append(["b0022", 5])
    workbook.active = 1
    buffer = io.BytesIO()
    workbook.save(buffer)
    dataset = create_dataset(
        uploaded_file=SimpleUploadedFile("table.xlsx", buffer.getvalue()),
        user=user,
        name="my study.csv",
    )
    assert dataset.is_usable
    assert dataset.validation_report["selected_sheet"] == 0
    assert dataset.validation_report["format"] == "xlsx"
    assert preview_expression_rows(dataset)["rows"][0]["gene_id"] == "b0005"
    assert inspect_expression_input(dataset.file.path)["preview"][0]["gene_id"] == "b0005"


def test_validation_checks_rows_after_former_5000_row_sample():
    content = (
        "gene_id,log2fc\n" + "".join(f"gene{i},2\n" for i in range(5001)) + "last,not-number\n"
    )
    report = validate_expression_file(SimpleUploadedFile("large.csv", content.encode()))
    assert report["errors"]


def test_preview_sorts_full_table_before_capping(user):
    content = "gene_id,log2fc\n" + "".join(f"gene{i},1\n" for i in range(2010)) + "strongest,100\n"
    dataset = create_dataset(
        uploaded_file=SimpleUploadedFile("large.csv", content.encode()), user=user
    )
    preview = preview_expression_rows(dataset)
    assert preview["rows"][0]["gene_id"] == "strongest"
    assert preview["total_rows"] == 2011
    assert len(preview["rows"]) == 2000
    assert preview["truncated"]
