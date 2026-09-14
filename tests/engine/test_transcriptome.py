"""``engine.transcriptome`` — the bundled reference transcriptome, Q1's first answer.

No network access here: this reads the real, checked-in FASTA
(``engine/data/transcriptomes/ecoli.fasta``), produced once by
``tools/sync_transcriptome.py`` from a real NCBI RefSeq record. If this file fails,
either that data file is missing/corrupted or the bundled sequences no longer match
what the public dataset catalog's *E. coli* comparisons expect to join against.
"""

import pytest

from engine.domain import Host
from engine.errors import InputValidationError
from engine.transcriptome import available_hosts, load_transcriptome


def test_ecoli_is_available():
    assert Host.ECOLI in available_hosts()


def test_loads_thousands_of_real_genes():
    transcriptome = load_transcriptome(Host.ECOLI)
    assert len(transcriptome) > 4000


def test_a_known_real_gene_is_present_and_is_rna():
    transcriptome = load_transcriptome(Host.ECOLI)
    thrA = transcriptome["b0002"]
    assert thrA.startswith("AUG")  # a CDS starts with a start codon
    assert set(thrA) <= set("ACGU")  # RNA, not DNA — no 'T'


def test_repeated_calls_return_the_same_cached_object():
    first = load_transcriptome(Host.ECOLI)
    second = load_transcriptome(Host.ECOLI)
    assert first is second


def test_an_unbundled_host_raises_naming_the_limitation():
    with pytest.raises(InputValidationError, match="No reference transcriptome"):
        load_transcriptome(Host.YEAST)
