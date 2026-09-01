"""The tools that are implemented rather than stubbed.

`engine.sequences` (S6) and `engine.stages.motifs` (S7) need no scientific decision and
no ViennaRNA, so they are real code and tested as such. The folding, off-target, codon
and translation tools raise NotImplementedError until Step 5.

The two live in different places because they are shared by different callers — see
docs/engine.md §3.3. This file tests them together because what they have in common is
that they are *finished*, which is a fact about the test suite, not about the layout.
"""

import pytest

from engine import sequences as sq
from engine.domain import AssemblyStandard
from engine.stages.motifs import MotifScreener

GFP_START = "AUGGCUAGCAAGGGCGAGGAGCUGUUCACC"


# --- Sequence facts ---------------------------------------------------------------


def test_dna_is_accepted_and_converted():
    """Researchers paste DNA as often as RNA; failing on T would be hostile."""
    assert sq.to_rna("atggctagc") == "AUGGCUAGC"
    assert sq.to_dna("AUGGCUAGC") == "ATGGCTAGC"


def test_reverse_complement_round_trips():
    assert sq.reverse_complement(sq.reverse_complement(GFP_START)) == GFP_START


def test_reverse_complement_is_what_a_binding_site_is_built_from():
    assert sq.reverse_complement("AUGC") == "GCAU"


@pytest.mark.parametrize(
    ("sequence", "expected"),
    [("GGCC", 100.0), ("AAUU", 0.0), ("ACGU", 50.0), ("", 0.0)],
)
def test_gc_content(sequence, expected):
    assert sq.gc_content(sequence) == pytest.approx(expected)


def test_translation_stops_at_a_stop_codon():
    assert sq.translate("AUGGCUAGCUAAGGGCGA") == "MAS"


def test_translation_can_read_through_when_asked():
    assert sq.translate("AUGGCUAGCUAAGGG", stop_at_stop=False) == "MAS*G"


def test_unknown_codons_become_x_rather_than_raising():
    assert "X" in sq.translate("AUGNNNGCU")


def test_finding_every_aug_including_overlaps():
    """An alternative AUG upstream of the intended one produces a different protein,
    so overlapping matches must be found."""
    assert sq.find_augs("AUGAUGGCU") == (0, 3)


def test_augs_can_be_restricted_to_one_frame():
    """AUGGCUAUGA has AUGs at 0 and 6; only 6 is a multiple of 3 away from frame 0
    alongside it, so both are in frame while an offset one is not."""
    assert sq.find_augs("AUGGCUAUGA") == (0, 6)
    assert sq.find_augs("AUGGCUAUGA", frame=0) == (0, 6)
    assert sq.find_augs("AAUGGCUAUG", frame=0) == ()


def test_in_frame_stops_are_found_and_out_of_frame_ones_are_not():
    """A switch's coding region must contain no in-frame STOP."""
    assert sq.find_stops("AUGGCUUAAGGG") == (6,)
    assert sq.find_stops("AUGGCCUAAAGG", frame=1) == ()


def test_longest_homopolymer():
    """Runs above about five nucleotides cause synthesis trouble."""
    assert sq.longest_homopolymer("ACGGGGGGUA") == ("G", 6)
    assert sq.longest_homopolymer("") == ("", 0)


def test_hamming_requires_equal_lengths():
    assert sq.hamming("ACGU", "ACGA") == 1
    with pytest.raises(ValueError, match="same length"):
        sq.hamming("ACG", "ACGU")


def test_windows_are_the_basis_of_trigger_scanning():
    assert sq.windows("ACGUACGU", 4, step=4) == [(0, "ACGU"), (4, "ACGU")]
    assert sq.windows("ACG", 8) == []


def test_valid_rna_rejects_dna():
    assert sq.is_valid_rna("ACGU")
    assert not sq.is_valid_rna("ACGT")
    assert not sq.is_valid_rna("")


# --- Motif screening --------------------------------------------------------------


def test_rfc10_restriction_sites_are_caught():
    screener = MotifScreener(AssemblyStandard.RFC10)
    violations = screener.violations("AAGAATTCAA")  # EcoRI

    assert [v.name for v in violations] == ["EcoRI"]
    assert violations[0].start == 2


def test_sites_are_matched_after_converting_rna_to_dna():
    """Designs are RNA; the standards are written in DNA. Screening must bridge that."""
    screener = MotifScreener(AssemblyStandard.RFC10)
    assert screener.violations("AAGAAUUCAA")  # same EcoRI site, written as RNA


def test_the_standard_selects_the_motif_set():
    rfc10 = MotifScreener(AssemblyStandard.RFC10)
    rfc1000 = MotifScreener(AssemblyStandard.RFC1000)

    bsai = "AAGGTCTCAA"
    assert not rfc10.violations(bsai)
    assert rfc1000.violations(bsai)


def test_long_homopolymers_are_flagged():
    screener = MotifScreener(AssemblyStandard.RFC10, max_homopolymer=5)
    violations = screener.violations("ACGAAAAAAAGC")

    assert any(v.kind == "homopolymer" for v in violations)


def test_a_clean_sequence_is_compliant():
    assert MotifScreener(AssemblyStandard.RFC10).is_compliant("AUGGGCAGCGGUAUC")


def test_violations_are_reported_in_position_order():
    screener = MotifScreener(AssemblyStandard.RFC10)
    violations = screener.violations("GAATTCAAAAAAATCTAGA")

    assert [v.start for v in violations] == sorted(v.start for v in violations)


def test_extra_motifs_can_be_supplied_without_touching_the_logic():
    """The motif sets are the scientific team's to own; the matching is not."""
    screener = MotifScreener(AssemblyStandard.RFC10, extra_motifs={"custom": "GGGGG"})
    assert any(v.name == "custom" for v in screener.violations("AAGGGGGAA"))
