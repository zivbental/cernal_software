"""Fetch and bundle a real reference transcriptome — Q1's first answer.

Run this offline, ahead of time, the same way ``tools/gen_api_surface.py`` and
``manage.py sync_expression_catalog`` are — the running application never fetches from
NCBI itself (docs/public-datasets.md §1's same architectural principle, applied here):

    uv run python tools/sync_transcriptome.py

Fetches each accession below live from NCBI's public E-utilities, extracts every
annotated CDS by its locus tag, and writes one FASTA file per host under
``src/engine/data/transcriptomes/`` — the file ``engine.transcriptome.load_transcriptome``
reads at request time. Re-run this to refresh an entry or add a new host; nothing else
needs to change except ``engine.transcriptome.HOSTS``.

**Why locus tags, not gene symbols.** The public dataset catalog's *E. coli* comparisons
use the NCBI locus tag (``b0002``) as the stable join key, and its yeast comparisons use
SGD's systematic ORF name (``YAL037C-A``) — NCBI's own ``locus_tag`` qualifier for yeast
*is* that systematic name, so the same extraction logic joins both without a
host-specific case. Symbols are reused across paralogues and annotation builds
(docs/genes.md, ``DgeRow.symbol``'s own docstring); keying this bundle by locus tag is
what makes the join in ``engine.pipeline`` a plain dict lookup either way.

**CDS only, not the full transcript.** Bacterial and yeast GenBank annotation does not
carry separate 5'/3' UTR features the way, say, human annotation does, so the CDS *is*
the practical unit available for either host bundled here. A trigger window chosen from
a CDS is dense with in-frame start/stop codons compared to a UTR (docs/triggers.md §4,
ROADMAP.md Q14) — a known, stated limitation of this first cut, not a hidden one.

**Human is out of scope here, deliberately** (docs/ROADMAP.md Q1, revisited after this
file was written) — human genes are heavily spliced, so a genomic CDS extraction like
this one is the wrong tool; a real answer needs actual mature mRNA/CDS records (RefSeq
``NM_`` transcripts) and an isoform-choice decision this file does not make.
"""

import io
import sys
from pathlib import Path

import requests
from Bio import SeqIO

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = REPO_ROOT / "src" / "engine" / "data" / "transcriptomes"

#: host key (matches ``engine.domain.Host.value``) -> (label, NCBI nuccore accessions).
#: A single-chromosome genome (E. coli) is one accession; a multi-chromosome one
#: (yeast: 16 nuclear chromosomes + the mitochondrial genome) is fetched and merged
#: chromosome by chromosome — every accession below was looked up live via NCBI
#: esearch/esummary, not typed from memory (docs/genes.md's own rule for a bundled
#: reference, applied here the same way CLAUDE.md §1 applies it to code).
ACCESSIONS: dict[str, tuple[str, tuple[str, ...]]] = {
    "ecoli": (
        "Escherichia coli str. K-12 substr. MG1655",
        ("NC_000913.3",),
    ),
    "yeast": (
        "Saccharomyces cerevisiae S288C",
        (
            "NC_001133.9",  # chromosome I
            "NC_001134.8",  # chromosome II
            "NC_001135.5",  # chromosome III
            "NC_001136.10",  # chromosome IV
            "NC_001137.3",  # chromosome V
            "NC_001138.5",  # chromosome VI
            "NC_001139.9",  # chromosome VII
            "NC_001140.6",  # chromosome VIII
            "NC_001141.2",  # chromosome IX
            "NC_001142.9",  # chromosome X
            "NC_001143.9",  # chromosome XI
            "NC_001144.5",  # chromosome XII
            "NC_001145.3",  # chromosome XIII
            "NC_001146.8",  # chromosome XIV
            "NC_001147.6",  # chromosome XV
            "NC_001148.4",  # chromosome XVI
            "NC_001224.1",  # mitochondrion
        ),
    ),
}

EUTILS_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
LINE_WIDTH = 70


def fetch_genbank(accession: str) -> str:
    """The full GenBank flat-file text for ``accession``, fetched live from NCBI."""
    response = requests.get(
        EUTILS_URL,
        params={"db": "nuccore", "id": accession, "rettype": "gbwithparts", "retmode": "text"},
        timeout=180,
    )
    response.raise_for_status()
    return response.text


def extract_cds(genbank_text: str) -> list[tuple[str, str]]:
    """``(locus_tag, CDS nucleotide sequence)`` for every annotated CDS, first-wins on a
    duplicate locus tag (a handful of genes carry more than one CDS feature — a
    programmed ribosomal frameshift, for one — and the first annotated is kept rather
    than silently overwritten by the second)."""
    record = SeqIO.read(io.StringIO(genbank_text), "genbank")
    entries: list[tuple[str, str]] = []
    seen: set[str] = set()
    for feature in record.features:
        if feature.type != "CDS":
            continue
        locus_tags = feature.qualifiers.get("locus_tag")
        if not locus_tags:
            continue
        locus_tag = locus_tags[0]
        if locus_tag in seen:
            continue
        seen.add(locus_tag)
        sequence = str(feature.location.extract(record.seq)).upper()
        entries.append((locus_tag, sequence))
    return entries


def write_fasta(entries: list[tuple[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="ascii") as handle:
        for locus_tag, sequence in sorted(entries):
            handle.write(f">{locus_tag}\n")
            for i in range(0, len(sequence), LINE_WIDTH):
                handle.write(sequence[i : i + LINE_WIDTH] + "\n")


def main(only: str | None = None) -> None:
    targets = {only: ACCESSIONS[only]} if only else ACCESSIONS
    for host, (organism, accessions) in targets.items():
        entries: list[tuple[str, str]] = []
        seen: set[str] = set()
        for accession in accessions:
            print(f"Fetching {accession} ({organism})...", file=sys.stderr)
            genbank_text = fetch_genbank(accession)
            for locus_tag, sequence in extract_cds(genbank_text):
                if locus_tag in seen:
                    # Real for yeast's own systematic names (e.g. a gene annotated on
                    # both a chromosome and, rarely, a resolved duplicated region) —
                    # first-fetched wins, same convention extract_cds already uses
                    # within one accession.
                    continue
                seen.add(locus_tag)
                entries.append((locus_tag, sequence))
        out_path = OUTPUT_DIR / f"{host}.fasta"
        write_fasta(entries, out_path)
        print(
            f"wrote {out_path} — {len(entries)} CDS from {len(accessions)} accession(s)",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main(only=sys.argv[1] if len(sys.argv) > 1 else None)
