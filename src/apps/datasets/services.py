"""Dataset upload and validation.

Validation here is **shallow and synchronous**: readable file, expected columns, sane
row count, parseable numerics. Deep scientific validation belongs to the engine and
happens at run time (docs/software-design.md §5). Duplicating scientific truth on the
Platform side is exactly what design map 04 warns against.
"""

import csv
import io
import logging

from django.conf import settings
from django.db import transaction

from apps.common.checksums import sha256_upload
from apps.datasets.models import Dataset, ValidationStatus

logger = logging.getLogger(__name__)

#: Every dataset must identify its features.
REQUIRED_COLUMNS = frozenset({"gene_id"})

#: At least one of these must be present, and must parse as a number.
EXPRESSION_COLUMNS = ("log2fc", "base_expression", "target_expression")

#: Columns validated as numeric when present.
NUMERIC_COLUMNS = frozenset({*EXPRESSION_COLUMNS, "padj", "pvalue"})

MAX_ROWS = 200_000
SAMPLE_ROWS = 5_000


class DatasetValidationError(Exception):
    """The upload could not be accepted at all (as opposed to failing validation)."""


@transaction.atomic
def create_dataset(*, project, uploaded_file, user, name: str | None = None) -> Dataset:
    """Store an upload, checksum it, and validate it — all before returning.

    The dataset is immutable once written, so everything that can be known about it is
    established here.
    """
    size = uploaded_file.size
    limit = settings.MAX_DATASET_MB * 1024 * 1024
    if size > limit:
        raise DatasetValidationError(
            f"The file is larger than the {settings.MAX_DATASET_MB} MB limit."
        )
    if size == 0:
        raise DatasetValidationError("The file is empty.")

    checksum = sha256_upload(uploaded_file)
    report = validate_expression_file(uploaded_file)
    uploaded_file.seek(0)

    dataset = Dataset(
        project=project,
        name=name or uploaded_file.name,
        checksum_sha256=checksum,
        size_bytes=size,
        schema_version="1",
        validation_status=(
            ValidationStatus.VALID if not report["errors"] else ValidationStatus.INVALID
        ),
        validation_report=report,
        uploaded_by=user,
    )
    dataset.file.save(dataset.name, uploaded_file, save=False)
    dataset.save()

    logger.info(
        "Dataset %s uploaded to project %s: %s (%d rows)",
        dataset.id,
        project.id,
        dataset.validation_status,
        report.get("rows", 0),
    )
    return dataset


def validate_expression_file(uploaded_file) -> dict:
    """Inspect a CSV upload. Returns a report; never raises for bad *content*.

    Errors mean the file cannot be analysed. Warnings mean it can, but something looks
    off and the researcher should know.
    """
    report: dict = {"rows": 0, "columns": [], "errors": [], "warnings": []}

    try:
        raw = uploaded_file.read()
    finally:
        uploaded_file.seek(0)

    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        report["errors"].append("The file is not valid UTF-8 text. Export it as CSV and retry.")
        return report

    reader = csv.DictReader(io.StringIO(text))
    columns = [name.strip() for name in (reader.fieldnames or [])]
    report["columns"] = columns

    if not columns:
        report["errors"].append("The file has no header row.")
        return report

    present = {name.lower() for name in columns}

    missing = sorted(REQUIRED_COLUMNS - present)
    if missing:
        report["errors"].append(f"Missing required column(s): {', '.join(missing)}.")

    available_expression = [name for name in EXPRESSION_COLUMNS if name in present]
    if not available_expression:
        report["errors"].append(
            "No expression column found. Expected at least one of: "
            f"{', '.join(EXPRESSION_COLUMNS)}."
        )

    numeric_present = sorted(NUMERIC_COLUMNS & present)
    bad_numbers: list[str] = []
    seen_ids: set[str] = set()
    duplicates = 0
    rows = 0

    for index, row in enumerate(reader, start=2):
        rows += 1
        if rows > MAX_ROWS:
            report["errors"].append(f"The file has more than {MAX_ROWS:,} rows.")
            break

        if rows <= SAMPLE_ROWS:
            gene_id = (row.get("gene_id") or "").strip()
            if gene_id:
                if gene_id in seen_ids:
                    duplicates += 1
                seen_ids.add(gene_id)

            for column in numeric_present:
                value = (row.get(column) or "").strip()
                if value in ("", "NA", "NaN", "null"):
                    continue
                try:
                    float(value)
                except ValueError:
                    if len(bad_numbers) < 5:
                        bad_numbers.append(f"row {index}, column '{column}': {value!r}")

    report["rows"] = rows

    if rows == 0:
        report["errors"].append("The file has a header but no data rows.")
    if bad_numbers:
        report["errors"].append(
            "Non-numeric values in numeric columns — " + "; ".join(bad_numbers) + "."
        )
    if duplicates:
        report["warnings"].append(
            f"{duplicates} duplicate gene_id value(s) in the first {SAMPLE_ROWS:,} rows."
        )
    if rows > SAMPLE_ROWS:
        report["warnings"].append(f"Only the first {SAMPLE_ROWS:,} rows were checked in detail.")

    return report


def delete_dataset(dataset) -> None:
    """Remove a dataset that no run has used.

    A dataset referenced by a run is PROTECTed at the database level; this turns that
    into a clear message rather than an IntegrityError.
    """
    if dataset.runs.exists():
        raise DatasetValidationError(
            "This dataset has been analysed and cannot be deleted. "
            "Results must not outlive the input that produced them."
        )
    dataset.delete()
