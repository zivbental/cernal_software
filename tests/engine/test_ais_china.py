"""The AIS-China adapter: the vendoring contract and the three data traps at the seam.

The energy-model guarantee lives in ``test_ais_china_energy_model.py``. This file covers the
rest: that the vendored code is byte-identical to the pinned, unmodified upstream commit
(the condition of the collaboration — docs/collaborations.md), that only ATCC 6919 is
reachable, and that the three measured traps in their data (UTF-8 BOM, two same-shaped
codon tables with different meanings, 1-based inclusive coordinates) are handled at the
boundary rather than assumed.
"""

import csv
import importlib
import inspect
from pathlib import Path

import pytest

from engine import sequences
from engine.gates.tools.ais_china import (
    DEFAULT_ROOT,
    HOST_ID,
    PINNED_COMMIT,
    REFERENCE_VERSION,
    STRATEGY_IDS,
    VENDORED_TREE_SHA256,
    AisChinaCodons,
    _convert_edit,
    vendored_tree_sha256,
)

REPO = Path(__file__).resolve().parents[2]
HOST_DIR = DEFAULT_ROOT / "data/hosts" / HOST_ID / REFERENCE_VERSION

#: 57 codons (GFP N-terminus) with a terminal stop, in RNA. AT-rich on purpose: every
#: optimized variant has to move towards the host's ~60% GC, so edits are plentiful.
CDS = (
    "AUGAGUAAAGGAGAAGAACUUUUCACUGGAGUUGUCCCAAUUCUUGUUGAAUUAGAUGGUGAUGUUAAUGGGCACAAAUUUUCUGUC"
    "AGUGGAGAGGGUGAAGGUGAUGCAACAUACGGAAAACUUACCCUUAAAUUUAUUUGCACUACUGGAAAAUAA"
)
STRATEGIES = ["host_sampling", "cai_max", "tai_max"]


@pytest.fixture(scope="module")
def codons() -> AisChinaCodons:
    return AisChinaCodons()


@pytest.fixture(scope="module")
def run(codons):
    return codons.optimize(CDS, seed=42, strategies=STRATEGIES)


# --- the vendored tree is the pinned, unmodified upstream content --------------------


def test_the_vendored_library_is_present_where_the_adapter_looks():
    assert (DEFAULT_ROOT / "codon_v2" / "pipeline.py").is_file(), (
        "vendor/ais-china-codon-optimization-v2 is empty. It is vendored into this "
        "repository (see its PROVENANCE.md), not a submodule, so a normal clone has it."
    )


def test_the_vendored_tree_is_byte_identical_to_what_was_recorded():
    """The collaboration's condition: their code is used as an unmodified library.

    Apache-2.0 §4(b) requires modified files to carry notices. CERNAL states instead that
    there are none, so this has to be machine-checked rather than asserted in prose.

    This replaces two earlier tests that ran ``git rev-parse HEAD`` and
    ``git status --porcelain`` inside ``vendor/`` when it was a submodule. Both would now
    *skip*, because there is no ``.git`` there any more — and a provenance check that
    quietly skips is worse than none, because it reads as green forever. Hashing the bytes
    is also strictly stronger: a gitlink only claims the submodule sits at a commit, while
    this verifies what will actually be imported and read.

    A deliberate update means re-copying from upstream, then updating
    ``VENDORED_TREE_SHA256``, ``PINNED_COMMIT`` and ``PROVENANCE.md`` together.
    """
    assert vendored_tree_sha256() == VENDORED_TREE_SHA256, (
        "The vendored AIS-China tree does not match VENDORED_TREE_SHA256. Either a file "
        "under vendor/ais-china-codon-optimization-v2 was edited -- which breaks the "
        "'used unmodified' statement the collaboration rests on -- or the tree was "
        "updated without updating that constant, PINNED_COMMIT and PROVENANCE.md."
    )


def test_provenance_records_the_upstream_repository_and_commit():
    """Vendored code without recorded provenance is indistinguishable from our own."""
    text = (DEFAULT_ROOT / "PROVENANCE.md").read_text(encoding="utf-8")
    assert "gitlab.igem.org/2026/software/ais-china/codon-optimization-v2" in text
    assert PINNED_COMMIT in text
    assert VENDORED_TREE_SHA256 in text
    assert "Apache-2.0" in text


def test_gitattributes_keeps_git_from_rewriting_their_bytes():
    """`* text=auto` would silently convert their CRLF files to LF on commit.

    This is not cosmetic and it is not hypothetical — it happened while vendoring. Their
    own ``config/rna_model.json`` records ``energy_parameter_sha256`` over the **CRLF**
    bytes of ``config/rna_turner2004.par``; the LF version hashes to something else
    entirely. Normalised, a fresh clone would fail the energy-model guard and
    ``VENDORED_TREE_SHA256``, and the "no modifications" statement Apache-2.0 §4(b) asks
    for would be false, because a line-ending conversion is a modification.

    ``VENDORED_TREE_SHA256`` catches the damage on a fresh checkout, which is where CI
    runs. This test names the cause, so whoever hits it knows to look at `.gitattributes`
    rather than at their own copy of the files.
    """
    rules = (REPO / ".gitattributes").read_text(encoding="utf-8")
    assert "vendor/ais-china-codon-optimization-v2/** -text" in rules, (
        "`.gitattributes` no longer exempts the vendored AIS-China tree from line-ending "
        "normalisation. Restore `vendor/ais-china-codon-optimization-v2/** -text`, then "
        "re-stage the tree (git rm -r --cached, git add) so the blobs hold their bytes."
    )


def test_their_license_file_travels_with_their_code():
    """Apache-2.0 §4(a): redistribution must carry the license."""
    assert "Apache License" in (DEFAULT_ROOT / "LICENSE").read_text(encoding="utf-8")


# --- one host only ----------------------------------------------------------------------


def test_only_atcc_6919_is_exposed(codons, run):
    """Their config declares two strains and we leave it alone; the restriction is ours."""
    assert set(codons._refs.hosts) == {HOST_ID, "kpa171202_GCF_000008345.1"}, (
        "their defaults.json changed; re-check which hosts the adapter should expose"
    )
    parameters = set(inspect.signature(AisChinaCodons.optimize).parameters)
    assert not parameters & {"host_id", "source_host_id", "request", "raw"}
    assert run.provenance.host_id == HOST_ID
    assert run.provenance.assembly == "GCF_008728435.1"
    assert run.provenance.accession == "NZ_CP044255.1"
    assert run.provenance.reference_version == "2026-09-06.v1"


def test_their_strategy_vocabulary_is_the_one_the_adapter_validates_against():
    AisChinaCodons()  # registers codon_v2 from the pinned submodule
    assert tuple(importlib.import_module("codon_v2.config").STRATEGIES) == STRATEGY_IDS


# --- trap 1: the UTF-8 BOM ---------------------------------------------------------------


@pytest.mark.parametrize("name", ["host_codon_counts.csv", "cai_weights.csv"])
def test_their_csvs_carry_a_utf8_bom(name):
    """Measured at the pinned commit: reading them as plain ``utf-8`` corrupts the header.

    The adapter never parses these files itself — it consumes the tables their loader
    parsed with ``utf-8-sig`` — so this test documents the trap, and fails if a bump
    removes the BOM so the assumption can be revisited.
    """
    raw = (HOST_DIR / name).read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    plain = next(csv.reader(raw.decode("utf-8").splitlines()))
    clean = next(csv.reader(raw.decode("utf-8-sig").splitlines()))
    assert plain[0] == "﻿codon"
    assert clean[0] == "codon"


def test_tables_are_keyed_by_clean_rna_codons(codons):
    sense = {c for c, aa in sequences.CODON_TABLE.items() if aa != "*"}
    assert set(codons.usage_frequencies()) == sense
    assert set(codons.cai_relative_adaptiveness()) == sense


def test_their_genetic_code_is_cernals_standard_code(codons):
    """Table 11 differs from the standard table only in its start codons, never in the
    amino acid a sense codon encodes — so ``sequences.CODON_TABLE`` is the one authority."""
    theirs = {sequences.to_rna(c): aa for c, aa in codons._sequence.AA.items()}
    ours = {c: aa for c, aa in sequences.CODON_TABLE.items() if aa != "*"}
    assert theirs == ours


# --- trap 2: relative frequency vs relative adaptiveness ---------------------------------


def test_usage_frequencies_sum_to_one_per_family_and_adaptiveness_peaks_at_one(codons):
    freq = codons.usage_frequencies()
    cai = codons.cai_relative_adaptiveness()
    multi = 0
    for amino_acid in sorted({aa for aa in sequences.CODON_TABLE.values() if aa != "*"}):
        family = [c for c, aa in sequences.CODON_TABLE.items() if aa == amino_acid]
        assert sum(freq[c] for c in family) == pytest.approx(1.0, abs=1e-9)
        assert max(cai[c] for c in family) == pytest.approx(1.0, abs=1e-12)
        if len(family) > 1:
            multi += 1
            # Same shape, different quantity: the two cannot be the same table.
            assert sum(cai[c] for c in family) > 1.0 + 1e-9
    assert multi == 18


def test_each_accessor_refuses_the_other_tables_semantics(codons, monkeypatch):
    """If a bump swaps the columns, the accessor raises rather than return the wrong table."""
    tables = dict(codons._host.tables)
    monkeypatch.setattr(codons._host, "tables", {**tables, "sampling": tables["cai"]})
    with pytest.raises(RuntimeError, match="not a relative-frequency table"):
        codons.usage_frequencies()
    monkeypatch.setattr(codons._host, "tables", {**tables, "cai": tables["sampling"]})
    with pytest.raises(RuntimeError, match="not a relative-adaptiveness table"):
        codons.cai_relative_adaptiveness()


def test_an_unavailable_reference_table_raises_instead_of_returning_empty(codons, monkeypatch):
    monkeypatch.setattr(codons._host, "tables", {})
    with pytest.raises(RuntimeError, match="unavailable"):
        codons.usage_frequencies()


# --- trap 3: 1-based inclusive coordinates ---------------------------------------------


def test_edits_are_zero_indexed_half_open_and_round_trip(run):
    assert run.candidates, "no candidates; the test below would be vacuous"
    for candidate in run.candidates:
        assert candidate.edits
        for edit in candidate.edits:
            assert edit.end - edit.start == 3
            assert edit.start == 3 * edit.codon_index
            assert run.input_sequence[edit.start : edit.end] == edit.before
            assert candidate.sequence[edit.start : edit.end] == edit.after
        # Applying only the reported edits to the input reproduces the candidate exactly.
        rebuilt = list(run.input_sequence)
        for edit in candidate.edits:
            rebuilt[edit.start : edit.end] = edit.after
        assert "".join(rebuilt) == candidate.sequence


def test_the_one_based_to_half_open_conversion_is_exact():
    original, candidate = "ATGAAAGGG", "ATGAAGGGG"
    raw = {
        "codon_position": 2,
        "nt_start": 4,
        "nt_end": 6,
        "before": "AAA",
        "after": "AAG",
        "amino_acid": "K",
    }
    edit = _convert_edit(raw, original, candidate)
    assert (edit.codon_index, edit.start, edit.end) == (1, 3, 6)
    assert original[edit.start : edit.end] == "AAA"


@pytest.mark.parametrize(
    "shift",
    [-1, 1],
    ids=["start-off-by-minus-one", "start-off-by-plus-one"],
)
def test_an_off_by_one_in_their_coordinates_raises_rather_than_misattributes(shift):
    raw = {
        "codon_position": 2,
        "nt_start": 4 + shift,
        "nt_end": 6 + shift,
        "before": "AAA",
        "after": "AAG",
        "amino_acid": "K",
    }
    with pytest.raises(RuntimeError, match="round trip"):
        _convert_edit(raw, "ATGAAAGGG", "ATGAAGGGG")


def test_locked_codons_are_zero_indexed_at_our_edge(codons):
    run = codons.optimize(CDS, seed=42, strategies=["cai_max"], locked_codons=[1, 2])
    for candidate in run.candidates:
        assert all(edit.codon_index not in (1, 2) for edit in candidate.edits)


# --- results ---------------------------------------------------------------------------


def test_candidates_encode_the_same_protein_in_rna(run):
    reference = sequences.translate(run.input_sequence, stop_at_stop=False)
    for candidate in run.candidates:
        assert sequences.is_valid_rna(candidate.sequence)
        assert len(candidate.sequence) == len(run.input_sequence)
        assert sequences.translate(candidate.sequence, stop_at_stop=False) == reference
        assert candidate.constraints_passed
    assert run.provenance.pinned_commit == PINNED_COMMIT


def test_a_seeded_run_is_reproducible_and_wall_clock_free(codons, run):
    again = codons.optimize(CDS, seed=42, strategies=STRATEGIES)
    assert again == run
    other = codons.optimize(CDS, seed=43, strategies=["host_sampling"])
    assert other.candidates != tuple(c for c in run.candidates if "host_sampling" in c.strategies)
    for record in (run, run.original, run.provenance):
        assert not {"created_utc", "elapsed_seconds"} & set(type(record).__slots__)


def test_a_strategy_that_found_nothing_is_reported_not_dropped(codons):
    """``rna_start`` has no feasible variant for this CDS under the host's hard GC bounds."""
    run = codons.optimize(CDS, seed=42, strategies=["rna_start", "cai_max"])
    by_id = {s.strategy_id: s for s in run.strategies}
    assert set(by_id) == {"rna_start", "cai_max"}
    assert by_id["rna_start"].returned_count == 0
    assert by_id["rna_start"].status != "completed"
    assert by_id["cai_max"].returned_count == 1
    assert run.status == "partial_results"


def test_an_unmeasurable_metric_is_none_with_a_reason_never_zero(run):
    for candidate in (run.original, *run.candidates):
        harmonization = candidate.metric("harmonization")
        assert harmonization.value is None
        assert harmonization.status == "unavailable"
        assert harmonization.reason
        for metric in candidate.metrics:
            if metric.status != "ok":
                assert metric.value is None


def test_gc_is_percent_and_rna_is_an_opening_energy(run):
    gc = run.original.metric("gc")
    assert gc.unit == "%"
    assert gc.value == pytest.approx(sequences.gc_content(run.input_sequence[:-3]), abs=1e-9)
    assert run.original.metric("rna").unit == "kcal/mol"


def test_harmonize_runs_only_when_a_source_reference_is_supplied(codons):
    without = codons.optimize(CDS, seed=42, strategies=["harmonize"])
    outcome = without.strategies[0]
    assert outcome.status == "unavailable"
    assert outcome.reason == "source_reference_or_comparable_positions_missing"

    # A made-up source organism with a different preference in each family: the n-th codon
    # of a family is the favourite. Real callers pass counts for their payload's host.
    source = {}
    for amino_acid in {aa for aa in sequences.CODON_TABLE.values() if aa != "*"}:
        family = sorted(c for c, aa in sequences.CODON_TABLE.items() if aa == amino_acid)
        for rank, codon in enumerate(family):
            source[codon] = 10.0 * (rank + 1)
    with_source = codons.optimize(
        CDS, seed=42, strategies=["harmonize"], source_codon_counts=source, source_name="toy"
    )
    assert with_source.strategies[0].status != "unavailable"


# --- bad input is a ValueError, not a silent fallback ------------------------------------


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"strategies": ["nope"]}, "unknown strategies"),
        ({"seed": True}, "seed must be an int"),
        ({"seed": 2**40}, "seed"),
        ({"strategies": []}, "at least one"),
    ],
)
def test_bad_arguments_raise_value_error(codons, kwargs, message):
    arguments = {"seed": 1, **kwargs}
    with pytest.raises(ValueError, match=message):
        codons.optimize(CDS, **arguments)


@pytest.mark.parametrize("cds", ["AUGAA", "AUGUAAAAAUAA", "AUGNNNUAA", ""])
def test_malformed_cds_raises_value_error(codons, cds):
    with pytest.raises(ValueError, match=r"\[cds\]"):
        codons.optimize(cds, seed=1)


def test_a_missing_vendored_tree_says_how_to_fix_it(tmp_path):
    with pytest.raises(FileNotFoundError, match="working tree is incomplete"):
        AisChinaCodons(root=tmp_path)
