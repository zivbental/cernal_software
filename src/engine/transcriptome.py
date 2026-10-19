"""Pinned, offline reference sequences and identifier aliases for all four hosts.

E. coli, yeast, and C. acnes use bundled reference CDSs. Human uses mature Ensembl
release 116 cDNA and noncoding transcripts, preferring MANE Select, then canonical,
then longest transcripts. Sync tools record source checksums and provenance beside
FASTA files; running applications never need a provider request to resolve a gene.
"""

import gzip
import hashlib
import io
import json
from collections.abc import Iterator
from contextlib import contextmanager
from functools import cache
from pathlib import Path
from typing import BinaryIO

from Bio import SeqIO

from engine import sequences as sq
from engine.domain import Host
from engine.errors import InputValidationError

_DATA_DIR = Path(__file__).resolve().parent / "data" / "transcriptomes"
_MANIFEST_PATH = Path(__file__).resolve().parents[2] / "data" / "manifest.json"
_REFERENCE_PREFIX = "src/engine/data/transcriptomes"

#: Host -> bundled FASTA filename. Extend this, and re-run
#: ``tools/sync_transcriptome.py``, to add another organism — nothing else changes.
#: Human uses mature Ensembl transcripts selected by tools/sync_human_transcriptome.py.
_FILES: dict[Host, str] = {
    Host.HUMAN: "human.fasta.gz",
    Host.ECOLI: "ecoli.fasta",
    Host.YEAST: "yeast.fasta",
    # The AIS-China team's own QC-passing CDS set for C. acnes ATCC 6919 (2,312 records,
    # NCBI locus tags, assembly GCF_008728435.1) — the same shape and the same CDS-only
    # limitation as the two above, so it needs no special handling here. It is a copy of
    # vendor/ais-china-codon-optimization-v2/data/hosts/atcc6919_GCF_008728435.1/
    # 2026-09-06.v1/reference_cds.fasta, kept here so this module stays self-contained
    # rather than reaching into vendor/. tests/engine/test_transcriptome.py asserts the
    # two are byte-identical, so the copy cannot drift when the vendored tree is updated.
    Host.C_ACNES: "c_acnes.fasta",
}


def _reference_error(host: Host, filename: str, reason: str) -> InputValidationError:
    return InputValidationError(
        f"The {host.value} reference file {filename} is missing or corrupt ({reason}). "
        "Run python tools/install_data.py from the repository root to install "
        "the pinned reference data."
    )


@contextmanager
def _verified_reference_file(path: Path, host: Host) -> Iterator[BinaryIO]:
    """Verify the installed bytes, then parse through the same open file handle."""
    try:
        manifest = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
        entries = manifest["files"]
        if not isinstance(entries, list):
            raise ValueError("manifest files must be a list")
        key = f"{_REFERENCE_PREFIX}/{path.name}"
        matches = [
            entry for entry in entries if isinstance(entry, dict) and entry.get("path") == key
        ]
        if len(matches) != 1:
            raise ValueError(f"manifest must contain exactly one entry for {key}")
        entry = matches[0]
        expected_hash, expected_size = entry["sha256"], entry["size"]
        if (
            not isinstance(expected_hash, str)
            or len(expected_hash) != 64
            or any(char not in "0123456789abcdef" for char in expected_hash)
            or type(expected_size) is not int
            or expected_size < 0
        ):
            raise ValueError(f"invalid manifest checksum or size for {key}")
    except (OSError, UnicodeError, ValueError, TypeError, KeyError) as exc:
        raise _reference_error(host, path.name, "reference manifest is missing or invalid") from exc

    try:
        with path.open("rb") as handle:
            if handle.seek(0, io.SEEK_END) != expected_size:
                raise _reference_error(host, path.name, "size does not match data/manifest.json")
            handle.seek(0)
            if hashlib.file_digest(handle, "sha256").hexdigest() != expected_hash:
                raise _reference_error(host, path.name, "SHA-256 does not match data/manifest.json")
            handle.seek(0)
            yield handle
    except (OSError, EOFError, UnicodeError, ValueError) as exc:
        raise _reference_error(host, path.name, "file is missing or unreadable") from exc


@cache
def load_transcriptome(host: Host) -> dict[str, str]:
    """Every bundled transcript for ``host``, as RNA, keyed by gene id.

    Loaded once per process and cached — this is a ~4 MB file for *E. coli* alone, and
    nothing about it changes between requests within one process (``cache`` needs a
    hashable argument, which is why this takes a ``Host`` enum member rather than a
    string).

    Args:
        host: The organism. ``available_hosts()`` names which are bundled today.

    Returns:
        Gene id (NCBI locus tag, e.g. ``"b0002"``) to its CDS sequence, uppercase RNA.
        Human sequences include annotated UTRs and splice junctions; the other
        hosts currently use CDS sequences without UTRs.

    Raises:
        InputValidationError: the reference is unavailable or fails integrity checks.
    """
    filename = _FILES.get(host)
    if filename is None:
        raise InputValidationError(
            f"No reference transcriptome is bundled for {host.value}. Only "
            f"{', '.join(sorted(h.value for h in _FILES))} today (docs/ROADMAP.md Q1)."
        )
    path = _DATA_DIR / filename
    with _verified_reference_file(path, host) as raw:
        handle = (
            gzip.open(raw, "rt", encoding="utf-8")
            if path.suffix == ".gz"
            else io.TextIOWrapper(raw, encoding="utf-8")
        )
        with handle:
            return {
                record.id: sq.to_rna(str(record.seq)) for record in SeqIO.parse(handle, "fasta")
            }


@cache
def reference_metadata(host: Host) -> dict:
    path = _DATA_DIR / f"{host.value}.json"
    with _verified_reference_file(path, host) as handle:
        metadata = json.load(handle)
        if not isinstance(metadata, dict):
            raise _reference_error(host, path.name, "metadata must be a JSON object")
        return metadata


def resolve_gene_id(host: Host, identifier: str) -> str:
    if not isinstance(identifier, str):
        raise InputValidationError("A reference gene identifier must be text.")
    identifier = identifier.strip()
    reference = load_transcriptome(host)
    if identifier in reference:
        return identifier
    # Versions refer to the same stable Ensembl gene; never truncate arbitrary symbols.
    if identifier.startswith("ENSG") and identifier.split(".")[0] in reference:
        return identifier.split(".")[0]
    metadata = reference_metadata(host)
    if identifier in metadata.get("ambiguous_aliases", []):
        raise InputValidationError(
            f"Gene symbol {identifier!r} is ambiguous; use a stable gene ID."
        )
    resolved = metadata.get("aliases", {}).get(identifier)
    if resolved in reference:
        return resolved
    raise InputValidationError(
        f"Gene {identifier!r} was not found in the {host.value} reference. "
        "Use a reference gene ID or an unambiguous gene symbol."
    )


def gene_reference(host: Host, identifier: str) -> dict:
    gene_id = resolve_gene_id(host, identifier)
    metadata = reference_metadata(host)
    info = metadata.get("genes", {}).get(gene_id, {})
    return {
        "organism": host.value,
        "gene_id": gene_id,
        "gene_symbol": info.get("symbol", ""),
        "sequence": load_transcriptome(host)[gene_id],
        "transcript_id": info.get("transcript_id", gene_id),
        "reference_release": str(metadata.get("release", "bundled")),
        "selection_method": metadata.get("selection_policy", "reference CDS"),
    }


def available_hosts() -> tuple[Host, ...]:
    """Which hosts have a bundled reference transcriptome today."""
    return tuple(_FILES)
