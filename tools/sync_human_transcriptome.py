"""Bundle mature Human RNA sequences from pinned Ensembl GRCh38 release 116.

Prefer MANE Select, then Ensembl canonical, then the longest annotated transcript.
All sequences come from spliced cDNA, including noncoding genes; never genomic DNA.
Maintainer-only rebuild: uv run python tools/sync_human_transcriptome.py
Normal setup installs the exact published bytes with tools/install_data.py instead.
"""

import gzip
import hashlib
import json
import re
import tempfile
from pathlib import Path

import requests
from Bio import SeqIO

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "var" / "reference-cache"
OUTPUT = ROOT / "src" / "engine" / "data" / "transcriptomes"
BASE = "https://ftp.ensembl.org/pub/release-116"
SOURCES = {
    "cdna": BASE + "/fasta/homo_sapiens/cdna/Homo_sapiens.GRCh38.cdna.all.fa.gz",
    "ncrna": BASE + "/fasta/homo_sapiens/ncrna/Homo_sapiens.GRCh38.ncrna.fa.gz",
    "gtf": BASE + "/gtf/homo_sapiens/Homo_sapiens.GRCh38.116.gtf.gz",
}
# Checksums recorded with the original, reviewed release-116 reference. Keep these
# independent of generated human.json: a corrupt download must never become a pin.
SOURCE_SHA256 = {
    "cdna": "683eb19310c40bf1396e4718f45afa2ce86755717c0990f47a171f535d248ea1",
    "ncrna": "7f03bb303e939517b322f7887a74c1ee15bbb82a6affbb54f0be84e82f89cff1",
    "gtf": "ed992f0eac7197d9627bda618f8f831ba355c95bd5d0796af785387d462828b6",
}


def download(url: str, expected_sha256: str) -> Path:
    for directory in (CACHE, *CACHE.parents):
        if directory.is_symlink():
            raise ValueError(f"Unsafe reference cache directory: {directory} is a symlink.")
    if CACHE.exists() and not CACHE.is_dir():
        raise ValueError(f"Unsafe reference cache path: {CACHE} is not a directory.")
    CACHE.mkdir(parents=True, exist_ok=True)
    target = CACHE / url.rsplit("/", 1)[1]
    if target.is_symlink() or (target.exists() and not target.is_file()):
        raise ValueError(f"Unsafe cached reference: {target} must be a regular file.")
    if target.exists():
        with target.open("rb") as handle:
            actual = hashlib.file_digest(handle, "sha256").hexdigest()
        if actual != expected_sha256:
            raise ValueError(
                f"Cached reference {target} failed SHA-256 verification: "
                f"expected {expected_sha256}, got {actual}. "
                "Remove this cache file and retry the download."
            )
        return target
    partial = None
    print(f"Downloading {url}", flush=True)
    try:
        digest = hashlib.sha256()
        with requests.get(url, stream=True, timeout=(30, 180)) as response:
            response.raise_for_status()
            with tempfile.NamedTemporaryFile(
                mode="wb", prefix=f".{target.name}.", suffix=".partial", dir=CACHE, delete=False
            ) as handle:
                partial = Path(handle.name)
                for chunk in response.iter_content(1024 * 1024):
                    handle.write(chunk)
                    digest.update(chunk)
        actual = digest.hexdigest()
        if actual != expected_sha256:
            raise ValueError(
                f"Downloaded reference {url} failed SHA-256 verification: "
                f"expected {expected_sha256}, got {actual}."
            )
        partial.replace(target)
    finally:
        if partial is not None:
            partial.unlink(missing_ok=True)
    return target


def transcript_annotations(path: Path) -> dict:
    annotations = {}
    with gzip.open(path, "rt") as handle:
        for line in handle:
            if line.startswith("#"):
                continue
            columns = line.rstrip().split("\t")
            if len(columns) != 9 or columns[2] != "transcript":
                continue
            pairs = re.findall(r'(\w+) "([^"]*)";', columns[8])
            attrs = dict(pairs)
            tags = {value for key, value in pairs if key == "tag"}
            transcript = attrs["transcript_id"].split(".")[0]
            rank = 0 if "MANE_Select" in tags else 1 if "Ensembl_canonical" in tags else 2
            annotations[transcript] = {
                "gene_id": attrs["gene_id"].split(".")[0],
                "symbol": attrs.get("gene_name", ""),
                "biotype": attrs.get("transcript_biotype", ""),
                "priority": rank,
            }
    return annotations


def main():
    files = {key: download(url, SOURCE_SHA256[key]) for key, url in SOURCES.items()}
    print("Reading transcript annotations", flush=True)
    annotations = transcript_annotations(files["gtf"])
    selected = {}
    for source in ("cdna", "ncrna"):
        with gzip.open(files[source], "rt") as handle:
            for record in SeqIO.parse(handle, "fasta"):
                transcript = record.id.split(".")[0]
                annotation = annotations.get(transcript)
                if annotation is None:
                    continue
                sequence = str(record.seq).upper()
                if set(sequence) - set("ACGT"):
                    continue
                gene = annotation["gene_id"]
                key = (annotation["priority"], -len(sequence), transcript)
                if gene not in selected or key < selected[gene][0]:
                    selected[gene] = (key, sequence, {**annotation, "transcript_id": record.id})
    OUTPUT.mkdir(parents=True, exist_ok=True)
    fasta = OUTPUT / "human.fasta.gz"
    metadata = {}
    aliases = {}
    collisions = set()
    # Gzip mtime=0 and sorted records make rebuilding byte-for-byte reproducible.
    temporary_fasta = fasta.with_suffix(".gz.partial")
    with (
        temporary_fasta.open("wb") as raw,
        gzip.GzipFile(filename="human.fasta", fileobj=raw, mode="wb", mtime=0) as handle,
    ):
        for gene, (_, sequence, info) in sorted(selected.items()):
            handle.write(f">{gene}\n{sequence}\n".encode("ascii"))
            metadata[gene] = info
            for alias in (
                info["symbol"],
                info["transcript_id"],
                info["transcript_id"].split(".")[0],
            ):
                if not alias:
                    continue
                if alias in aliases and aliases[alias] != gene:
                    collisions.add(alias)
                aliases[alias] = gene
    temporary_fasta.replace(fasta)
    for alias in collisions:
        aliases.pop(alias, None)
    manifest = {
        "assembly": "GRCh38.p14",
        "release": 116,
        "selection_policy": "MANE_Select, Ensembl_canonical, longest transcript, transcript ID",
        "sources": SOURCES,
        "source_sha256": {
            key: hashlib.file_digest(path.open("rb"), "sha256").hexdigest()
            for key, path in files.items()
        },
        "sequence_sha256": hashlib.file_digest(fasta.open("rb"), "sha256").hexdigest(),
        "genes": metadata,
        "aliases": aliases,
        "ambiguous_aliases": sorted(collisions),
    }
    (OUTPUT / "human.json").write_text(json.dumps(manifest, sort_keys=True) + "\n")
    print(f"Bundled {len(selected)} Human genes in {fasta}", flush=True)


if __name__ == "__main__":
    main()
