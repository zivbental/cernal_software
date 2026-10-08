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


def test_all_organisms_have_a_reference():
    assert set(available_hosts()) == set(Host)


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


def test_missing_reference_file_has_a_useful_error(monkeypatch, tmp_path):
    import engine.transcriptome as module

    module.load_transcriptome.cache_clear()
    monkeypatch.setattr(module, "_DATA_DIR", tmp_path)
    with pytest.raises(InputValidationError, match=r"not available|No reference|could not|missing"):
        module.load_transcriptome(Host.HUMAN)
    module.load_transcriptome.cache_clear()


# ---------------------------------------------------------------------------
# C. acnes: the bundled copy must not drift from the vendored original
# ---------------------------------------------------------------------------


def test_c_acnes_transcriptome_matches_the_vendored_reference_cds():
    """``c_acnes.fasta`` is a copy of the AIS-China team's own QC-passing CDS set.

    ``engine.transcriptome`` keeps its data under ``src/engine/data/transcriptomes/``
    rather than reaching into ``vendor/``, so the file exists twice. That is a drift
    hazard: update the vendored tree and the engine's copy silently becomes a different
    transcriptome, while every gene id still resolves and nothing raises.

    The comparison is on **parsed records**, not bytes, and deliberately so. The vendored
    original is CRLF and exempt from line-ending normalisation
    (``.gitattributes``: ``vendor/** -text``), while this copy is LF like ``ecoli.fasta``
    and ``yeast.fasta``. Comparing bytes would fail for a reason that has nothing to do
    with the sequences. What has to match is the biology: the same gene ids mapping to the
    same coding sequences.
    """
    from Bio import SeqIO

    from engine.gates.tools.ais_china import DEFAULT_ROOT, HOST_ID, REFERENCE_VERSION

    vendored = DEFAULT_ROOT / "data/hosts" / HOST_ID / REFERENCE_VERSION / "reference_cds.fasta"
    assert vendored.is_file(), f"the vendored reference CDS is missing at {vendored}"

    theirs = {r.id: str(r.seq).upper().replace("T", "U") for r in SeqIO.parse(vendored, "fasta")}
    ours = load_transcriptome(Host.C_ACNES)

    assert ours == theirs, (
        "src/engine/data/transcriptomes/c_acnes.fasta no longer matches the vendored "
        "reference_cds.fasta. Re-copy it from "
        f"{vendored.relative_to(DEFAULT_ROOT.parents[1])} and convert CRLF to LF."
    )
