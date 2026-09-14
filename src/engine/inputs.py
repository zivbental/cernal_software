"""Differential-expression input parsing — the edge where a CSV becomes a ``DgeTable``.

Nothing else in the engine may read a raw file. Stages take typed records, never a
path, a DataFrame or a dict of strings (CLAUDE.md §6 — "CSVs are exports, never the
inter-stage interface"; docs/integration.md GAP-1: "nothing in ``src/engine/`` converts
``JobRequest.input_path`` into ``CountMatrix`` / ``DgeTable`` / ``SampleMetadata``").
This module is that edge for the DGE table, and it is the only one — everything
downstream of :func:`parse_dge_table` sees a ``DgeTable`` of ``DgeRow`` records.

**Deliberately independent of ``apps.datasets.services``.** The engine may never import
Django or ``apps`` (CLAUDE.md §4, machine-checked by ``tests/test_boundary.py``), so the
column-alias table below is a second, narrower copy of the platform's own
``COLUMN_ALIASES`` (``src/apps/datasets/services.py``) — only the columns ``DgeRow`` has
a field for. **Keep the two in sync**: a header spelling the platform's upload validator
accepts but this parser does not recognise is a file that validates on upload and then
silently drops that column here, which is exactly the kind of two-implementations-of-one-
thing failure CLAUDE.md §1 warns about, made unavoidable only by the Platform⇄Engine
boundary itself.

Unlike the platform's validator, this module never *rejects* a file for looking odd —
that shallow, synchronous check already happened at upload time
(docs/modalities.md §A1). Its job is narrower and stricter: turn recognised columns into
typed, correctly-``None``d values, and drop only the rows that cannot be identified or
carry no effect size at all — there is nothing to rank a gene on without a fold change.
"""

import csv
import io
from pathlib import Path

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
    """A parsed number, or ``None`` — never ``0.0`` for something that did not parse.

    ``""``, ``NA``, ``NaN`` and ``null`` are DESeq2's and R's own spellings of "not
    tested" (docs/genes.md §3); an unparseable string is treated the same way rather
    than raised on, since the platform's own upload validation already rejected a file
    with genuinely broken numerics before this parser ever sees it.
    """
    if value is None:
        return None
    text = value.strip()
    if text in ("", "NA", "NaN", "nan", "null", "None"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_dge_table(raw: bytes, filename: str = "dge.csv") -> DgeTable:
    """Parse a differential-expression CSV or TSV into a ``DgeTable``.

    Args:
        raw: The file's raw bytes, exactly as uploaded or fetched — decoding and
            delimiter sniffing happen here, not before, so nothing upstream needs to
            guess an encoding.
        filename: Used only to choose the delimiter from the extension (``.tsv``/
            ``.txt`` are tab-separated; everything else, including a public dataset's
            materialized CSV, is comma-separated).

    Returns:
        A ``DgeTable``. A row missing a usable ``gene_id`` or ``log2_fold_change`` is
        dropped — there is no identifier to join on, or no effect size to rank on — but
        every other column is ``None`` when the file does not carry it, never a
        fabricated number. Rows are returned in file order; a duplicate ``gene_id`` is
        kept (not deduplicated here — ``DgeTable.by_gene_id()`` already documents that a
        later row wins, and ``GeneSelector`` is where a scientific choice about
        duplicates belongs, not a parser).

    Raises:
        InputValidationError: the file cannot be decoded as UTF-8, has no header row, or
            has no recognisable gene-identifier column at all — in every case there is
            nothing downstream could possibly filter or rank.
    """
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise InputValidationError(
            "The differential-expression file is not valid UTF-8 text."
        ) from exc

    suffix = Path(filename).suffix.lower()
    delimiter = "\t" if suffix in (".tsv", ".txt") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    headers = [name.strip() for name in (reader.fieldnames or [])]
    if not headers:
        raise InputValidationError("The differential-expression file has no header row.")

    canonical = _canonical_columns(headers)
    if "gene_id" not in canonical.values():
        raise InputValidationError(
            "No gene identifier column found. Recognised names include: gene_id, gene, "
            "ensembl_id, locus_tag."
        )

    rows: list[DgeRow] = []
    for index, raw_row in enumerate(reader):
        if index >= MAX_ROWS:
            break
        row = {canonical.get(key, key): value for key, value in raw_row.items() if key is not None}

        gene_id = (row.get("gene_id") or "").strip()
        log2fc = _as_float(row.get("log2fc"))
        if not gene_id or log2fc is None:
            # Not "not tested" — this row cannot be identified or has no effect size to
            # rank on at all, so there is nothing a downstream stage could do with it.
            continue

        rows.append(
            DgeRow(
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
        )

    return DgeTable(rows=tuple(rows))
