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
(``apps/expression/catalog/ecoli/*.csv``) and every real DESeq2/edgeR export use the
NCBI locus tag (``b0002``) as the stable join key — symbols are reused across paralogues
and annotation builds (docs/genes.md, `DgeRow.symbol`'s own docstring). Keying this
bundle the same way is what makes the join in ``engine.pipeline`` a plain dict lookup.

**CDS only, not the full transcript.** *E. coli* GenBank annotation does not carry
separate 5'/3' UTR features the way eukaryotic annotation does, so the CDS *is* the
practical unit available. A trigger window chosen from a CDS is dense with in-frame
start/stop codons compared to a UTR (docs/triggers.md §4, ROADMAP.md Q14) — a known,
stated limitation of this first cut, not a hidden one.
"""

import io
import sys
from pathlib import Path

import requests
from Bio import SeqIO

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = REPO_ROOT / "src" / "engine" / "data" / "transcriptomes"

#: host key (matches ``engine.domain.Host.value``) -> (NCBI nuccore accession, label).
#: E. coli K-12 MG1655 — the same strain every promoter/terminator/backbone default in
#: ``stages/plasmids.py`` already targets, so a run's genetic background is now
#: consistent end to end, not just at the plasmid-construction step.
ACCESSIONS: dict[str, tuple[str, str]] = {
    "ecoli": ("NC_000913.3", "Escherichia coli str. K-12 substr. MG1655"),
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
    for host, (accession, organism) in targets.items():
        print(f"Fetching {accession} ({organism})...", file=sys.stderr)
        genbank_text = fetch_genbank(accession)
        entries = extract_cds(genbank_text)
        out_path = OUTPUT_DIR / f"{host}.fasta"
        write_fasta(entries, out_path)
        print(f"wrote {out_path} — {len(entries)} CDS from {accession}", file=sys.stderr)


if __name__ == "__main__":
    main(only=sys.argv[1] if len(sys.argv) > 1 else None)
