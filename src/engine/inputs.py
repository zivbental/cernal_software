"""Shared differential-expression parsing for upload, preview and engine execution.

The first XLSX worksheet or sniffed UTF-8 text table is interpreted once. Headers
are normalized before validation; duplicate identifiers, malformed numerics and row
shapes are errors. Explicit missing statistics remain None. A missing effect size
is untested and excluded, invalidating any full-universe BH declaration.
"""

import csv
import io
import math
from pathlib import Path
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from engine.domain import DgeRow, DgeTable
from engine.errors import InputValidationError

#: Canonical column name -> the spellings researchers export under. A narrower copy of
#: ``apps.datasets.services.COLUMN_ALIASES`` — see the module docstring for why this
#: cannot simply import that table instead.
COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "gene_id": ("gene_id", "gene", "geneid", "id", "target_id", "ensembl_id", "locus_tag"),
    "gene_symbol": ("gene_symbol", "symbol", "gene_name", "genename", "hgnc_symbol"),
    "log2fc": (
        "log2fc",
        "log2foldchange",
        "log2_fold_change",
        "logfc",
        "fold_change",
        "foldchange",
        "fc",
    ),
    "base_mean": ("basemean", "base_mean"),
    "base_expression": ("base_expression", "control", "control_mean"),
    "target_expression": ("target_expression", "target", "target_mean", "treatment"),
    "padj": ("padj", "p_adj", "adj_pval", "adj_p_val", "fdr", "qvalue", "q_value"),
    "pvalue": ("pvalue", "p_value", "pval", "p"),
    "lfc_se": ("lfcse", "lfc_se", "se"),
    "stat": ("stat",),
}

#: Rows read beyond this many are dropped, and the table is returned truncated rather
#: than exhausting memory on a file the platform's own upload cap (200,000 rows,
#: ``apps.datasets.services.MAX_ROWS``) already let through. Kept generous rather than
#: matched exactly, since this parser also has to handle a public catalog dataset (3,000
#: rows) and a full uploaded transcriptome without acting as a second, disagreeing limit.
MAX_ROWS = 200_000


def _normalize(name: str) -> str:
    """Case/space/punctuation-insensitive comparison — ``log2 Fold Change``,
    ``log2FoldChange`` and ``log2_fold_change`` are the same column."""
    return "".join(ch for ch in name.lower() if ch.isalnum())


def _canonical_columns(headers: list[str]) -> dict[str, str]:
    lookup = {
        _normalize(alias): canonical
        for canonical, aliases in COLUMN_ALIASES.items()
        for alias in aliases
    }
    return {header: lookup.get(_normalize(header), header.strip().lower()) for header in headers}


def _as_float(value: str | None) -> float | None:
    """A finite number or an explicit missing value; malformed values are errors."""
    if value is None:
        return None
    text = str(value).strip()
    if text.casefold() in ("", "na", "nan", "null", "none"):
        return None
    try:
        number = float(text)
    except (ValueError, TypeError):
        raise InputValidationError(f"Invalid numeric value {text!r}.") from None
    if not math.isfinite(number):
        raise InputValidationError(f"Nonfinite numeric value {text!r} is not allowed.")
    return number


def parse_dge_table(
    raw: bytes, filename: str = "dge.csv", *, hypothesis_universe_complete: bool | None = None
) -> DgeTable:
    """Parse differential-expression CSV, TSV, TXT, or XLSX into a ``DgeTable``.

    Args:
        raw: The file's raw bytes, exactly as uploaded or fetched — decoding and
            delimiter sniffing happen here, not before, so nothing upstream needs to
            guess an encoding.
        filename: Used only to choose the delimiter from the extension (``.tsv``/
            ``.txt`` are tab-separated; everything else, including a public dataset's
            materialized CSV, is comma-separated).

    Returns:
        A ``DgeTable`` in file order. Explicitly missing effect sizes are excluded;
        malformed values, empty identifiers and duplicates are rejected. Completeness
        is unknown unless a caller explicitly declares the tested hypothesis universe.

    Raises:
        InputValidationError: the file cannot be decoded as UTF-8, has no header row, or
            has no recognisable gene-identifier column at all — in every case there is
            nothing downstream could possibly filter or rank.
    """
    suffix = Path(filename).suffix.lower()
    workbook = None
    if suffix == ".xlsx":
        try:
            workbook = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
            sheet_rows = workbook.worksheets[0].iter_rows(values_only=True)
            headers = [str(value or "").strip() for value in next(sheet_rows, ())]
            reader = (
                dict(zip(headers, (None if v is None else str(v) for v in values), strict=False))
                for values in sheet_rows
            )
        except (
            BadZipFile,
            InvalidFileException,
            KeyError,
            ValueError,
            IndexError,
            TypeError,
            ParseError,
        ) as exc:
            if workbook is not None:
                workbook.close()
            raise InputValidationError(
                "The spreadsheet could not be read as an XLSX workbook."
            ) from exc
    else:
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise InputValidationError(
                "The differential-expression file is not valid UTF-8 text."
            ) from exc
        delimiter = "\t" if suffix in (".tsv", ".txt") else ","
        try:
            delimiter = csv.Sniffer().sniff(text[:8192], delimiters=",\t;").delimiter
        except csv.Error:
            pass
        csv_reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        headers = list(csv_reader.fieldnames or [])
        reader = csv_reader

    if not headers:
        raise InputValidationError("The differential-expression file has no header row.")

    canonical = _canonical_columns(headers)
    normalized = list(canonical.values())
    if any(not header.strip() for header in headers) or len(set(normalized)) != len(headers):
        if workbook is not None:
            workbook.close()
        raise InputValidationError("Blank or duplicate normalized column headers are not allowed.")
    if "gene_id" not in canonical.values():
        if workbook is not None:
            workbook.close()
        raise InputValidationError(
            "No gene identifier column found. Recognised names include: gene_id, gene, "
            "ensembl_id, locus_tag."
        )
    if "log2fc" not in normalized:
        if workbook is not None:
            workbook.close()
        raise InputValidationError("A log2 fold change column is required (log2fc).")

    try:
        rows: list[DgeRow] = []
        seen_ids: set[str] = set()
        for index, raw_row in enumerate(reader):
            if index >= MAX_ROWS:
                raise InputValidationError(f"Input exceeds the {MAX_ROWS:,}-row limit.")
            if None in raw_row or any(value is None for value in raw_row.values()):
                # Blank XLSX cells are legitimate missing values. DictReader None values
                # indicate fewer cells than the header, which is a malformed text row.
                if suffix != ".xlsx":
                    raise InputValidationError(f"Row {index + 2}: cell count differs from header.")
            row = {
                canonical.get(key, key): value for key, value in raw_row.items() if key is not None
            }

            gene_id = (row.get("gene_id") or "").strip()
            log2fc = _as_float(row.get("log2fc"))
            if not gene_id:
                raise InputValidationError(f"Row {index + 2}: gene identifier is required.")
            if gene_id in seen_ids:
                raise InputValidationError(
                    f"Row {index + 2}: duplicate gene identifier {gene_id!r}."
                )
            seen_ids.add(gene_id)
            if log2fc is None:
                # Not "not tested" — this row cannot be identified or has no effect size to
                # rank on at all, so there is nothing a downstream stage could do with it.
                continue

            parsed = DgeRow(
                gene_id=gene_id,
                log2_fold_change=log2fc,
                symbol=(row.get("gene_symbol") or "").strip(),
                p_adj=_as_float(row.get("padj")),
                p_value=_as_float(row.get("pvalue")),
                base_mean=_as_float(row.get("base_mean")),
                control_mean=_as_float(row.get("base_expression")),
                target_mean=_as_float(row.get("target_expression")),
                lfc_se=_as_float(row.get("lfc_se")),
                stat=_as_float(row.get("stat")),
            )
            for name in ("p_adj", "p_value"):
                value = getattr(parsed, name)
                if value is not None and not 0 <= value <= 1:
                    raise InputValidationError(f"Row {index + 2}: {name} must be between 0 and 1.")
            for name in ("base_mean", "control_mean", "target_mean", "lfc_se"):
                value = getattr(parsed, name)
                if value is not None and value < 0:
                    raise InputValidationError(f"Row {index + 2}: {name} must be nonnegative.")
            rows.append(parsed)
    except (
        BadZipFile,
        InvalidFileException,
        KeyError,
        IndexError,
        TypeError,
        ParseError,
        csv.Error,
    ) as exc:
        raise InputValidationError(
            "The table contains malformed spreadsheet or delimited data."
        ) from exc
    finally:
        if workbook is not None:
            workbook.close()

    return DgeTable(
        rows=tuple(rows),
        hypothesis_universe_complete=(
            hypothesis_universe_complete if len(rows) == len(seen_ids) else False
        ),
        source_row_count=len(seen_ids),
        columns=tuple(canonical.values()),
    )
