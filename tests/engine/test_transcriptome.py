"""``engine.transcriptome`` — the bundled reference transcriptome, Q1's first answer.

No network access here: this reads the real, checked-in FASTA files
(``engine/data/transcriptomes/*.fasta``), produced once by ``tools/sync_transcriptome.py``
from real NCBI RefSeq records. If this file fails, either a data file is
missing/corrupted or the bundled sequences no longer match what the public dataset
catalog's comparisons expect to join against.
"""

import pytest

from engine.domain import Host
from engine.errors import InputValidationError
from engine.transcriptome import available_hosts, load_transcriptome


def test_ecoli_and_yeast_are_available():
    assert Host.ECOLI in available_hosts()
    assert Host.YEAST in available_hosts()


def test_human_is_not_available():
    """Deliberate, not an oversight — a genomic CDS extraction is the wrong tool for a
    heavily-spliced genome (``tools/sync_transcriptome.py``'s own docstring)."""
    assert Host.HUMAN not in available_hosts()


@pytest.mark.parametrize(("host", "min_genes"), [(Host.ECOLI, 4000), (Host.YEAST, 5000)])
def test_loads_thousands_of_real_genes(host, min_genes):
    transcriptome = load_transcriptome(host)
    assert len(transcriptome) > min_genes


def test_a_known_real_ecoli_gene_is_present_and_is_rna():
    transcriptome = load_transcriptome(Host.ECOLI)
    thrA = transcriptome["b0002"]
    assert thrA.startswith("AUG")  # a CDS starts with a start codon
    assert set(thrA) <= set("ACGU")  # RNA, not DNA — no 'T'


def test_a_known_real_yeast_gene_is_present_and_is_rna():
    """YIR019C (MUC1) — real, appears in the bundled public yeast catalog
    (``apps/expression/catalog/yeast/E-GEOD-59814__g1_g2.csv``) under this exact
    systematic name, confirming the join key matches real data, not just the fetch."""
    transcriptome = load_transcriptome(Host.YEAST)
    muc1 = transcriptome["YIR019C"]
    assert muc1.startswith("AUG")
    assert set(muc1) <= set("ACGU")


@pytest.mark.parametrize("host", [Host.ECOLI, Host.YEAST])
def test_repeated_calls_return_the_same_cached_object(host):
    first = load_transcriptome(host)
    second = load_transcriptome(host)
    assert first is second


def test_an_unbundled_host_raises_naming_the_limitation():
    with pytest.raises(InputValidationError, match="No reference transcriptome"):
        load_transcriptome(Host.HUMAN)
