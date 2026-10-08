"""Dataset upload and validation.

Validation here is **shallow and synchronous**: readable file, expected columns, sane
row count, parseable numerics. Deep scientific validation belongs to the engine and
happens at run time (docs/architecture.md §5). Duplicating scientific truth on the
Platform side is exactly what design map 04 warns against.
"""

import logging
from pathlib import Path

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction

from apps.common.checksums import sha256_upload
from apps.datasets.models import Dataset, ValidationStatus

logger = logging.getLogger(__name__)

#: What we will attempt to parse.
SUPPORTED_SUFFIXES = (".csv", ".tsv", ".txt", ".xlsx")

#: Bundled datasets a researcher can try the product with, so evaluating CERNAL does
#: not require having your own differential-expression results to hand.
EXAMPLES: dict[str, dict[str, str]] = {
    "ecoli-oxidative-stress": {
        "filename": "ecoli_oxidative_stress.csv",
        "label": "E. coli — lactose metabolism to oxidative stress",
        "description": (
            "50 genes from a differential-expression analysis comparing standard growth "
            "with oxidative stress. Twenty stress-response genes are up-regulated, "
            "fifteen metabolic and motility genes down, and fifteen housekeeping genes "
            "are unchanged."
        ),
    },
}

EXAMPLES_DIR = Path(__file__).resolve().parent / "examples"


class DatasetValidationError(Exception):
    """The upload could not be accepted at all (as opposed to failing validation)."""


@transaction.atomic
def create_example_dataset(*, user, key: str = "ecoli-oxidative-stress"):
    """Copy a bundled example dataset into one the user owns.

    Goes through exactly the same checksum and validation path as an upload, so an
    example run is indistinguishable from a real one downstream.
    """
    try:
        example = EXAMPLES[key]
    except KeyError:
        known = ", ".join(sorted(EXAMPLES))
        raise DatasetValidationError(
            f"Unknown example dataset '{key}'. Available: {known}."
        ) from None

    source = EXAMPLES_DIR / example["filename"]
    if not source.is_file():
        raise DatasetValidationError("That example dataset is missing from this install.")

    return create_dataset(
        uploaded_file=SimpleUploadedFile(
            example["filename"], source.read_bytes(), content_type="text/csv"
        ),
        user=user,
        name=example["filename"],
    )


@transaction.atomic
def create_dataset(*, uploaded_file, user, name: str | None = None) -> Dataset:
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
    # The *storage* filename is the uploaded file's own name, never dataset.name — the
    # latter is a free-form display string (a caller can pass an arbitrary long one,
    # e.g. apps.expression.services.materialize_public_dataset's "<experiment title> —
    # <comparison label>") with no length discipline appropriate for a filesystem path.
    # Conflating the two is what tripped dataset_upload_path's max_length guard for
    # long display names before that guard existed.
    dataset.file.save(uploaded_file.name, uploaded_file, save=False)
    dataset.save()

    logger.info(
        "Dataset %s uploaded by %s: %s (%d rows)",
        dataset.id,
        user,
        dataset.validation_status,
        report.get("rows", 0),
    )
    return dataset


def validate_expression_file(uploaded_file) -> dict:
    """Use the engine's parser for synchronous validation of every input row."""
    import tempfile

    from engine.client import inspect_expression_input

    filename = getattr(uploaded_file, "name", "") or "expression.csv"
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        return {"rows": 0, "columns": [], "errors": ["Use CSV, TSV, TXT or XLSX."], "warnings": []}
    try:
        with tempfile.TemporaryDirectory(prefix="cernal-upload-validation-") as directory:
            source = Path(directory) / f"input{suffix}"
            with source.open("wb") as handle:
                for chunk in uploaded_file.chunks():
                    handle.write(chunk)
            report = inspect_expression_input(str(source), limit=0)
    finally:
        uploaded_file.seek(0)
    return {
        "rows": report["row_count"],
        "columns": report["columns"],
        "detected_columns": {name: name for name in report["columns"]},
        "errors": report["errors"],
        "warnings": report["warnings"],
        "format": suffix.lstrip("."),
        "selected_sheet": report["selected_sheet"],
    }


#: §24 of the public-datasets brief: never render 20k rows in the browser at once. This
#: caps what a single preview request returns; a public dataset's own curated catalog
#: already stores at most this many rows per comparison (sync_expression_catalog.py), so
#: an uploaded file is the only case this cap actually trims.
PREVIEW_ROW_LIMIT = 2000


def preview_expression_rows(dataset, *, limit: int = PREVIEW_ROW_LIMIT) -> dict:
    """Parsed, ranked rows for any dataset using the shared engine parser.

    Ranked by |log2FC| descending (the default sort task brief §13 asks for) *before*
    capping, so a truncated table still shows the most differentially expressed genes,
    not just whichever happened to come first in the file.
    """
    from engine.client import inspect_expression_input

    report = inspect_expression_input(dataset.file.path, limit=None)
    if report["errors"]:
        raise DatasetValidationError(" ".join(report["errors"]))
    parsed = [
        {
            "gene_id": row["gene_id"],
            "gene_symbol": row.get("gene_symbol") or None,
            "log2fc": row.get("log2fc"),
            "pvalue": row.get("pvalue"),
            "padj": row.get("padj"),
        }
        for row in report["preview"]
    ]
    parsed.sort(key=lambda row: abs(row["log2fc"]), reverse=True)
    total = len(parsed)
    capped = parsed[: max(0, min(limit, PREVIEW_ROW_LIMIT))]
    return {"rows": capped, "total_rows": total, "truncated": total > len(capped)}


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
    storage, filename = dataset.file.storage, dataset.file.name
    with transaction.atomic():
        dataset.delete()
        transaction.on_commit(lambda: storage.delete(filename))
