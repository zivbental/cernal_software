"""FoldEngine.sample_structures: indexing, reproducibility, calibration."""

from __future__ import annotations

import math
from collections import Counter

import pytest

from engine.gates.tools.folding import FoldEngine

# A real eukaryotic toehold switch (through its Kozak) and its trigger, stem_up = 17..29,
# stem_down = 39..51. The order switch-then-trigger is the one ViennaRNA's pbacktrack gets wrong.
SWITCH = "GUCAGAUCAGUUAGAAAAGGGGUUUUGAGAACGAAACAACUUAAAACCCCUGCCACC"
TRIGGER = "CUCAGAAUUCCUUUUCUAACU"
STEM_UP, STEM_DOWN = (17, 29), (39, 51)
COMPLEX = f"{SWITCH}&{TRIGGER}"


@pytest.fixture(scope="module")
def folder() -> FoldEngine:
    return FoldEngine(temperature=37.0)


def test_structures_cover_the_concatenation_without_the_separator(folder):
    samples = folder.sample_structures(COMPLEX, 50, seed=1)
    assert samples
    assert {len(s) for s in samples} == {len(SWITCH) + len(TRIGGER)}


def test_same_seed_gives_the_same_draws(folder):
    assert folder.sample_structures(COMPLEX, 100, seed=7) == folder.sample_structures(
        COMPLEX, 100, seed=7
    )


def test_draw_frequencies_match_boltzmann_probabilities(folder):
    samples = folder.sample_structures(COMPLEX, 4000, seed=3)
    g = folder.partition(COMPLEX)
    for structure, count in Counter(samples).most_common(3):
        energy = folder.structure_energy(COMPLEX, structure)
        expected = math.exp(-(energy - g) / folder.rt)
        assert count / len(samples) == pytest.approx(expected, abs=0.06)


def test_stem_marginal_matches_the_exact_matrix(folder):
    samples = folder.sample_structures(COMPLEX, 4000, seed=5)
    bpp = folder.base_pair_probabilities(COMPLEX)
    length = STEM_UP[1] - STEM_UP[0]
    exact_open = 1 - sum(bpp[i][j] for i in range(*STEM_UP) for j in range(*STEM_DOWN)) / length
    sampled_open = 0.0
    for structure in samples:
        stack, partner = [], {}
        for i, char in enumerate(structure):
            if char == "(":
                stack.append(i)
            elif char == ")":
                j = stack.pop()
                partner[i], partner[j] = j, i
        sampled_open += (
            sum(1 for i in range(*STEM_UP) if not STEM_DOWN[0] <= partner.get(i, -1) < STEM_DOWN[1])
            / length
        )
    assert sampled_open / len(samples) == pytest.approx(exact_open, abs=0.02)


@pytest.mark.parametrize("first_strand", [None, 0, 1, 2])
def test_three_strands_map_back_to_the_callers_order(folder, first_strand):
    complex_ = f"{SWITCH}&{TRIGGER}&{TRIGGER[::-1]}"
    samples = folder.sample_structures(complex_, 20, seed=2, first_strand=first_strand)
    assert samples
    for structure in samples:
        assert len(structure) == len(SWITCH) + 2 * len(TRIGGER)
        assert folder.structure_energy(complex_, structure) is not None


def test_a_first_strand_outside_the_strands_is_refused(folder):
    with pytest.raises(ValueError):
        folder.sample_structures(COMPLEX, 5, first_strand=2)
