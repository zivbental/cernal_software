"""The tools that are implemented rather than stubbed.

`engine.sequences` (S6) and `engine.stages.motifs` (S7) need no scientific decision and
no ViennaRNA, so they are real code and tested as such.
`engine.gates.tools.folding.FoldEngine.mfe` is now real too, and so is
`engine.stages.folding.FoldProfiler` (docs/smoke-run.md S2/E2a-4). The rest of folding,
and off-target, codons and translation, still raise NotImplementedError until Step 5.

The tools live in different places because they are shared by different callers — see
docs/engine.md §3.3. This file tests them together because what they have in common is
that they are *finished*, which is a fact about the test suite, not about the layout.
"""

import pytest

from engine import sequences as sq
from engine.domain import AssemblyStandard
from engine.gates.toehold import _mean_unpaired
from engine.gates.tools.binding import (
    alignment_pairs,
    fixed_alignment_energy,
    longest_complementary_run,
)
from engine.gates.tools.folding import FoldEngine
from engine.stages.folding import FoldProfiler
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


# --- Circular screening (docs/plasmids.md §7.3) ------------------------------------


def _circular_fixture() -> str:
    """Ends GAA, starts TTC -> wraps to GAATTC. Bases vary so this trips no other
    rule (an all-A filler would also read as a homopolymer)."""
    return "TTC" + "ACGT" * 14 + "GAA"


def test_a_site_split_across_the_origin_is_invisible_to_a_linear_scan():
    """The failure a plasmid's assembled sequence can hide: neither end alone
    contains EcoRI, but a circular molecule reads straight through the join."""
    screener = MotifScreener(AssemblyStandard.RFC10)

    assert screener.violations(_circular_fixture()) == ()


def test_circular_true_catches_the_wrapped_site():
    screener = MotifScreener(AssemblyStandard.RFC10)
    seq = _circular_fixture()

    violations = screener.violations(seq, circular=True)

    assert [v.name for v in violations] == ["EcoRI"]
    assert violations[0].start == len(seq) - 3


def test_circular_defaults_to_off_and_does_not_change_linear_behaviour():
    screener = MotifScreener(AssemblyStandard.RFC10)
    seq = "AAGAATTCAA"  # EcoRI, fully contained, nowhere near either end

    assert screener.violations(seq) == screener.violations(seq, circular=False)
    assert screener.violations(seq, circular=True)[:1] == screener.violations(seq)[:1]


def test_circular_does_not_double_count_a_site_already_found_linearly():
    screener = MotifScreener(AssemblyStandard.RFC10)
    seq = "AAGAATTCAA"

    assert len(screener.violations(seq, circular=True)) == len(screener.violations(seq))


def test_circular_on_an_empty_sequence_is_still_empty():
    assert MotifScreener(AssemblyStandard.RFC10).violations("", circular=True) == ()


def test_violations_are_reported_in_position_order():
    screener = MotifScreener(AssemblyStandard.RFC10)
    violations = screener.violations("GAATTCAAAAAAATCTAGA")

    assert [v.start for v in violations] == sorted(v.start for v in violations)


def test_extra_motifs_can_be_supplied_without_touching_the_logic():
    """The motif sets are the scientific team's to own; the matching is not."""
    screener = MotifScreener(AssemblyStandard.RFC10, extra_motifs={"custom": "GGGGG"})
    assert any(v.name == "custom" for v in screener.violations("AAGGGGGAA"))


# --- Folding ------------------------------------------------------------------------


def test_mfe_folds_a_hairpin():
    result = FoldEngine(temperature=37.0).mfe("GGGAAACCC")
    assert result.structure == "(((...)))"
    assert result.energy == pytest.approx(-1.2, abs=0.05)


def test_mfe_is_cached_per_instance():
    folder = FoldEngine()
    assert folder.mfe("GGGAAACCC") is folder.mfe("GGGAAACCC")


def test_mfe_respects_the_instance_temperature():
    """Two designs folded at different temperatures must not land on the same energy
    axis by accident — each `FoldEngine` instance commits to one temperature."""
    warm = FoldEngine(temperature=37.0).mfe("GGGAAACCC")
    cool = FoldEngine(temperature=10.0).mfe("GGGAAACCC")
    assert cool.energy < warm.energy


def test_mfe_folds_a_complex_as_a_dimer_not_a_concatenated_strand():
    """The ON state is switch and trigger folded together, joined with `&` — a
    different (and correct) physical system from folding one merged strand."""
    switch, trigger = "GGGAAACCC", "GGGUUUCCC"

    dimer = FoldEngine().mfe(f"{switch}&{trigger}")
    concatenated = FoldEngine().mfe(switch + trigger)

    assert len(dimer.structure) == len(switch) + len(trigger)
    assert dimer.energy != concatenated.energy


# --- Joint accessibility: p_open (S2) -----------------------------------------------

# An 18-bp stem closed by Kim's inhibitory loop, padded so the arms have real context.
STEM = "GGACAGGAUGUCCCAUGC"
HAIRPIN = "GGG" + STEM + "CAAGAACUUAGACAA" + sq.reverse_complement(STEM) + "AAAA"
ARM = (3, 21)  # the 18-nt ascending arm, 0-based half-open


def test_p_open_collapses_over_a_paired_stem_arm():
    """The whole point of the joint form: an arm locked in a stem is not merely
    unlikely to be open, it is astronomically unlikely, and the average over bases
    (0.0013 here) hides that by twelve orders of magnitude."""
    assert FoldEngine().p_open(HAIRPIN, ARM) == pytest.approx(3.4e-22, rel=0.25)


def test_p_open_is_far_below_one_even_for_a_completely_unstructured_span():
    """Holding N named bases open at once costs entropy even with nothing to pair
    against, which is why `p_open` must never be compared against a threshold that was
    calibrated for a per-base average."""
    unstructured = "A" * 20 + STEM + "A" * 20
    folder = FoldEngine()

    wide = folder.p_open(unstructured, (20, 38))
    narrow = folder.p_open(unstructured, (20, 24))

    assert wide == pytest.approx(1.6e-4, rel=0.3)
    assert narrow == pytest.approx(1.4e-3, rel=0.3)
    assert wide < narrow < 0.01


def test_p_open_constrains_the_window_of_the_first_strand_not_the_concatenation():
    """The only thing that catches an off-by-one, because a shifted window still folds
    and still scores. Opening the switch's own stem must cost more than opening a span
    of the same length that is already unpaired."""
    switch, trigger = HAIRPIN, "GGGUUUCCC"
    folder = FoldEngine()

    complex_ = f"{switch}&{trigger}"
    assert folder.p_open(complex_, ARM) < folder.p_open(complex_, (54, 58))

    with pytest.raises(ValueError):
        folder.p_open(f"{switch}&{trigger}", (0, len(switch) + 5))
    with pytest.raises(ValueError):
        folder.p_open(switch, (10, 10))


def test_p_open_is_invariant_to_rotating_the_strand_order():
    """ViennaRNA's multi-strand ensemble depends on strand order only up to rotation, so
    `_strand_orders` may enumerate one representative per circular class."""
    switch, a, b = HAIRPIN, "GGGUUUCCC", "AUGCAUGCAUGC"
    folder = FoldEngine()

    assert folder.partition(f"{switch}&{a}&{b}") == pytest.approx(
        folder.partition(f"{a}&{b}&{switch}"), abs=1e-6
    )


def test_p_open_sums_over_every_strand_ordering():
    """Summed, so the answer does not depend on the order the caller happened to pass —
    and the spread between orderings is real (2.75 kcal/mol on a realistic triple), so
    picking one silently would be picking a number."""
    switch, a, b = HAIRPIN, "GGGUUUCCC", "AUGCAUGCAUGC"
    folder = FoldEngine()

    assert folder.p_open(f"{switch}&{a}&{b}", ARM) == pytest.approx(
        folder.p_open(f"{switch}&{b}&{a}", ARM), rel=1e-9
    )
    assert len(folder.p_open_by_order(f"{switch}&{a}&{b}", ARM)[0]) == 2
    assert len(folder.p_open_by_order(switch, ARM)[0]) == 1


# --- Ensemble defect (S2) ------------------------------------------------------------


def test_ensemble_defect_is_small_against_the_structure_the_sequence_actually_folds_into():
    folder = FoldEngine()
    sequence = "GGGGAAAACCCC"

    defect = folder.ensemble_defect(sequence, folder.mfe(sequence).structure)

    assert 0.0 <= defect < 0.2 * len(sequence)


def test_ensemble_defect_is_a_raw_count_not_a_fraction():
    """ViennaRNA's own function divides by length despite its name; this method's
    contract is the count, because callers normalise it themselves for
    `structure_deviation` and would otherwise divide twice."""
    sequence = "GGGGAAAACCCC"

    defect = FoldEngine().ensemble_defect(sequence, "." * len(sequence))

    assert defect == pytest.approx(0.6395 * len(sequence), rel=0.05)
    assert defect > 1.0


def test_ensemble_defect_rejects_a_target_of_the_wrong_length():
    with pytest.raises(ValueError):
        FoldEngine().ensemble_defect("GGGGAAAACCCC", "((((....)))")


# --- Fixed-alignment duplex energy (S3) ----------------------------------------------

DUPLEX_A = "GGGAAACCCUUUAG"
DUPLEX_B = "CUAAAGGGUUUCCC"  # exact reverse complement of DUPLEX_A


def test_fixed_alignment_energy_matches_the_free_fold_when_the_alignment_is_the_best_one():
    """The known answer. A perfect duplex has nothing better to do than pair straight
    through, so forcing that register must agree with letting ViennaRNA choose it."""
    folder = FoldEngine(temperature=37.0)

    forced = fixed_alignment_energy(DUPLEX_A, DUPLEX_B, folder)

    assert forced == pytest.approx(-22.8, abs=0.05)
    assert forced == pytest.approx(folder.mfe(f"{DUPLEX_A}&{DUPLEX_B}").energy, abs=0.05)


def test_fixed_alignment_energy_weakens_as_mismatches_are_added():
    folder = FoldEngine()

    perfect = fixed_alignment_energy(DUPLEX_A, DUPLEX_B, folder)
    one_off = fixed_alignment_energy(DUPLEX_A, "CUAAAGGGUUACCC", folder)
    ragged = fixed_alignment_energy(DUPLEX_A, "CAUAGGCGUAACGC", folder)

    assert perfect < one_off < ragged


def test_fixed_alignment_energy_never_returns_viennarnas_sentinel():
    """ViennaRNA signals an unevaluable structure by *returning* 1e5 rather than raising,
    so a try/except catches nothing and two such values subtract to 0.00 — which passes a
    `>= 0` gate. Every stem energy in the upstream scripts reads as a pass for this
    reason. `None` is the only safe answer."""
    folder = FoldEngine()

    for probe in (DUPLEX_A, "AAAAAAAAAAAAAA", "GUGUGUGUGUGUGU"):
        value = fixed_alignment_energy(probe, DUPLEX_B, folder)
        assert value is None or abs(value) < 1e4


def test_fixed_alignment_energy_is_zero_when_no_position_can_pair():
    """A real answer — the strands simply do not interact — and distinct from `None`,
    which means the model could not tell us."""
    assert fixed_alignment_energy("AAAA", "AAAA", FoldEngine()) == 0.0


def test_fixed_alignment_energy_requires_equal_lengths():
    """Truncating silently would score a shorter duplex than the design describes."""
    with pytest.raises(ValueError):
        fixed_alignment_energy("AAAA", "AAA", FoldEngine())


def test_alignment_pairs_counts_gu_wobbles():
    """A duplex scored on Watson-Crick pairs alone reads as broken while it still holds;
    on this project that produced a knockout retaining a fully wobble-paired run."""
    assert alignment_pairs("GGGG", "UUUU") == [True, True, True, True]


def test_structure_energy_rejects_a_structure_that_still_carries_the_separator():
    """The one-character mistake behind the sentinel: `eval_structure` wants the
    separator-free structure even though the compound was built with `&`."""
    folder = FoldEngine()
    strands = f"{DUPLEX_A}&{DUPLEX_B}"

    assert folder.structure_energy(strands, "(" * 14 + ")" * 14) == pytest.approx(-22.8, abs=0.05)
    with pytest.raises(ValueError):
        folder.structure_energy(strands, "(" * 14 + "&" + ")" * 14)


# --- Accessibility profiling (stages/folding.py, S1) --------------------------------

PROFILER_SEQUENCE = "AACUUGUUGGCCCAGUGUGAAUCGCUUAAGGGUUAAGCUAGCUAGCUAGC"


def test_profile_is_one_probability_per_position():
    profile = FoldProfiler().profile(PROFILER_SEQUENCE)

    assert len(profile) == len(PROFILER_SEQUENCE)
    assert all(0.0 <= p <= 1.0 for p in profile)


def test_profile_is_cached_per_transcript():
    """`openness` is called many times per gene; profiling per window would be
    quadratic (the class's own docstring)."""
    profiler = FoldProfiler()
    first = profiler.profile(PROFILER_SEQUENCE)
    second = profiler.profile(PROFILER_SEQUENCE)

    assert first == second
    assert first is not second, "a shared mutable list would let one caller corrupt another's view"


def test_openness_is_the_mean_of_the_requested_slice():
    profiler = FoldProfiler()
    profile = profiler.profile(PROFILER_SEQUENCE)

    assert profiler.openness(PROFILER_SEQUENCE, 0, 10) == pytest.approx(sum(profile[0:10]) / 10)


def test_openness_of_an_empty_segment_is_zero_not_a_division_error():
    assert FoldProfiler().openness(PROFILER_SEQUENCE, 5, 5) == 0.0


def test_openness_window_covers_the_whole_sequence_for_a_direct_trigger():
    """A `direct` submission profiles the pasted sequence as its own transcript
    (docs/smoke-run.md S2) — the whole-sequence case must not be a special case."""
    profiler = FoldProfiler()
    whole = profiler.openness(PROFILER_SEQUENCE, 0, len(PROFILER_SEQUENCE))
    profile = profiler.profile(PROFILER_SEQUENCE)

    assert whole == pytest.approx(sum(profile) / len(profile))


def test_longest_complementary_run_counts_wobbles():
    """A knockout scored on Watson-Crick pairs alone produced, on this project, a variant
    that read as disabled while retaining a fully wobble-paired 8-nt run — a negative
    control that was not one, and that could not be recognised as such from the
    experimental result."""
    assert longest_complementary_run("GGGG", "UUUU") == 4
    assert longest_complementary_run("GGGG", "CCCC") == 4


def test_longest_complementary_run_finds_the_longest_unbroken_stretch():
    """Contiguity is the point: scattered pairs do not let a trigger nucleate. Here four
    of five positions pair, but the break in the middle leaves a longest run of two — a
    total count would have reported four and called this trigger viable."""
    assert longest_complementary_run("GGAGG", "CCACC") == 2
    assert longest_complementary_run("AAAA", "AAAA") == 0


# --- p_open against answers that are known without folding ---------------------------


def test_p_open_is_exactly_one_where_pairing_is_impossible():
    """A poly-A stretch has nothing to pair with, so the joint probability that a window
    inside it is open is 1 and the opening cost is 0. If this drifts, the constrained and
    unconstrained partition functions are no longer being compared on the same ensemble."""
    folder = FoldEngine(temperature=37.0)

    assert folder.p_open("A" * 40, (5, 35)) == pytest.approx(1.0, abs=1e-9)


def test_p_open_prices_a_stem_and_not_its_loop():
    """The same molecule, two windows: opening ten base pairs is expensive, opening the
    hairpin loop they close is free. A p_open that ignored its window argument, or indexed
    it wrongly, would return the same number for both."""
    folder = FoldEngine(temperature=37.0)
    hairpin = "GGGGGGGGGGAAAACCCCCCCCCC"

    on_stem = folder.p_open(hairpin, (0, 10))
    on_loop = folder.p_open(hairpin, (10, 14))

    assert on_stem < 1e-12
    assert on_loop == pytest.approx(1.0, abs=1e-6)


def test_p_open_enumerates_one_ordering_per_circular_class():
    """(n-1)! orderings: one for a dimer, two for a three-strand tube. The switch is kept
    first so a window into it never needs remapping — if that changed, the constraint would
    land on a trigger instead."""
    folder = FoldEngine(temperature=37.0)
    switch, trigger_a, trigger_b = "GGGAAACCCAAAGGGUUUCCC", "GGGAAACCC", "AAAGGGUUU"
    window = (2, 8)

    assert len(folder.p_open_by_order(f"{switch}&{trigger_a}", window)[0]) == 1
    assert len(folder.p_open_by_order(f"{switch}&{trigger_a}&{trigger_b}", window)[0]) == 2
    for order in FoldEngine._strand_orders(f"{switch}&{trigger_a}&{trigger_b}"):
        assert order.split("&")[0] == switch


def test_mean_unpaired_matches_a_raw_pair_probability_sum():
    """`_mean_unpaired` reads the shared matrix; this recomputes the same quantity straight
    from ViennaRNA's 1-indexed upper-triangular output. They must agree exactly, because a
    disagreement would mean the matrix conversion has an off-by-one."""
    folder = FoldEngine(temperature=37.0)
    strands = "GGGGGGGGGGAAAACCCCCCCCCC&GGGGGGGGGG"
    span = (0, 10)

    from_shared = _mean_unpaired(folder.base_pair_probabilities(strands), *span)

    compound = folder._compound(strands)
    compound.pf()
    raw = compound.bpp()
    total = len(raw) - 1
    expected = [
        max(
            0.0,
            1.0 - sum(raw[min(i + 1, j)][max(i + 1, j)] for j in range(1, total + 1) if j != i + 1),
        )
        for i in range(*span)
    ]
    assert from_shared == pytest.approx(sum(expected) / len(expected), abs=1e-12)
