"""Build stable gene/symbol lookup metadata from the same NCBI reference genomes."""

import io
import json
import time
from pathlib import Path

from Bio import SeqIO
from requests.exceptions import HTTPError
from sync_transcriptome import ACCESSIONS, fetch_genbank

OUTPUT = Path(__file__).resolve().parents[1] / "src/engine/data/transcriptomes"
CACHE = Path(__file__).resolve().parents[1] / "var/reference-cache"


def extract(accession):
    print(f"Reading aliases from {accession}", flush=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    cached = CACHE / f"{accession}.gb"
    if not cached.is_file():
        for attempt in range(6):
            try:
                text = fetch_genbank(accession)
                cached.write_text(text)
                time.sleep(0.5)
                break
            except HTTPError as exc:
                if exc.response.status_code != 429 or attempt == 5:
                    raise
                time.sleep(2**attempt)
    record = SeqIO.read(io.StringIO(cached.read_text()), "genbank")
    genes = {}
    aliases = []
    for feature in record.features:
        if feature.type != "CDS" or not feature.qualifiers.get("locus_tag"):
            continue
        gene = feature.qualifiers["locus_tag"][0]
        symbol = (feature.qualifiers.get("gene") or [""])[0]
        genes[gene] = {"symbol": symbol, "accession": accession}
        names = [symbol]
        names += [
            name.strip()
            for value in feature.qualifiers.get("gene_synonym", [])
            for name in value.split(";")
        ]
        aliases += [(name, gene) for name in names if name]
    return genes, aliases


def main():
    targets = {**ACCESSIONS, "c_acnes": ("C. acnes ATCC 6919", ("NZ_CP044255.1",))}
    for host, (_, accessions) in targets.items():
        ids = {record.id for record in SeqIO.parse(OUTPUT / f"{host}.fasta", "fasta")}
        genes, aliases, collisions = {}, {}, set()
        for records, names in map(extract, accessions):
            genes.update({key: value for key, value in records.items() if key in ids})
            for name, gene in names:
                if gene not in ids:
                    continue
                if name in aliases and aliases[name] != gene:
                    collisions.add(name)
                aliases[name] = gene
        for alias in collisions:
            aliases.pop(alias, None)
        (OUTPUT / f"{host}.json").write_text(
            json.dumps(
                {
                    "sources": list(accessions),
                    "selection_policy": "reference CDS",
                    "genes": genes,
                    "aliases": aliases,
                    "ambiguous_aliases": sorted(collisions),
                },
                sort_keys=True,
            )
            + "\n"
        )
        print(f"Bundled {len(aliases)} {host} aliases", flush=True)


if __name__ == "__main__":
    main()
