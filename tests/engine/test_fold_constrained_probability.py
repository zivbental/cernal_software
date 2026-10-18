"""``FoldEngine.constrained_probability`` -- exact joint probability of forced pairs."""

import pytest

from engine.gates.tools.folding import FoldEngine

# A stable hairpin: GGGGGG stem, UUUU loop, CCCCCC stem (6 bp).
HAIRPIN = "GGGGGGAAAACCCCCC"


@pytest.fixture(scope="module")
def folder() -> FoldEngine:
    return FoldEngine(temperature=37.0)


def test_single_pair_matches_bpp_entry(folder):
    # Same quantity by two routes (pf-ratio vs. the bpp matrix); they differ only by
    # ViennaRNA's partition-function scaling, ~3e-6, hence the 1e-5 tolerance.
    bpp = folder.base_pair_probabilities(HAIRPIN)
    for i, j in [(0, 15), (2, 13), (5, 10)]:
        probability = folder.constrained_probability(HAIRPIN, [(i, j)])
        assert probability is not None
        assert probability == pytest.approx(bpp[i][j], abs=1e-5)


def test_probability_in_unit_interval_and_monotone(folder):
    one = folder.constrained_probability(HAIRPIN, [(2, 13)])
    two = folder.constrained_probability(HAIRPIN, [(2, 13), (3, 12)])
    assert one is not None and two is not None
    assert 0.0 < two <= one <= 1.0


def test_works_on_two_strand_complex(folder):
    probability = folder.constrained_probability("GGGGGG&CCCCCC", [(0, 11), (1, 10)])
    assert probability is not None
    assert 0.0 < probability <= 1.0


def test_empty_forced_pairs_is_none(folder):
    assert folder.constrained_probability(HAIRPIN, []) is None


def test_infeasible_pair_is_none_not_zero(folder):
    # Adjacent positions cannot pair (hairpin loop minimum).
    assert folder.constrained_probability(HAIRPIN, [(5, 6)]) is None
