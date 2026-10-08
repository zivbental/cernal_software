"""Bundle mature Human RNA sequences from pinned Ensembl GRCh38 release 116.

Prefer MANE Select, then Ensembl canonical, then the longest annotated transcript.
All sequences come from spliced cDNA, including noncoding genes; never genomic DNA.
Run offline once: .venv/bin/python tools/sync_human_transcriptome.py
"""

import gzip
import hashlib
import json
import re
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


def download(url: str) -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    target = CACHE / url.rsplit("/", 1)[1]
    if target.is_file():
        return target
    partial = target.with_suffix(".partial")
    print(f"Downloading {url}", flush=True)
    with requests.get(url, stream=True, timeout=(30, 180)) as response:
        response.raise_for_status()
        with partial.open("wb") as handle:
            for chunk in response.iter_content(1024 * 1024):
                handle.write(chunk)
    partial.replace(target)
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
    files = {key: download(url) for key, url in SOURCES.items()}
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
