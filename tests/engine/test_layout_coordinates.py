"""``FoldEngine.layout_coordinates`` -- one 2D point per base, for drawing a structure.

Taken verbatim from ``offer/fold-engine-p-open``; its own tests live on that branch's
notebooks, so this pins the contract callers here rely on. Kept in a file of its own
rather than appended to ``test_tools.py``, which that branch also extends.
"""

import math

import pytest

from engine.gates.tools.folding import FoldEngine

HAIRPIN = "(((...)))"
TWO_HAIRPINS = "(((...)))..(((...)))"


@pytest.fixture
def folder() -> FoldEngine:
    return FoldEngine(temperature=37.0)


@pytest.mark.parametrize("structure", [HAIRPIN, TWO_HAIRPINS, "." * 12])
def test_one_point_per_base_with_no_trailing_padding_point(folder, structure):
    """ViennaRNA's vector is one entry longer than the structure; that padding point
    must be trimmed here so no caller draws a stray base at the origin."""
    points = folder.layout_coordinates(structure)
    assert len(points) == len(structure)


def test_points_are_finite_xy_pairs(folder):
    for x, y in folder.layout_coordinates(TWO_HAIRPINS):
        assert math.isfinite(x)
        assert math.isfinite(y)


def test_no_two_bases_are_drawn_on_the_same_spot(folder):
    points = folder.layout_coordinates(TWO_HAIRPINS)
    assert len({(round(x, 6), round(y, 6)) for x, y in points}) == len(points)


def test_base_pair_partners_are_drawn_closer_than_the_ends_of_the_loop(folder):
    """In a hairpin the paired stem is a ladder: a base and its partner sit one rung
    apart, far closer than the two ends of the whole molecule would if it were a line."""
    points = folder.layout_coordinates(HAIRPIN)
    rung = math.dist(points[0], points[len(HAIRPIN) - 1])
    stretched_line = 1.0 * (len(HAIRPIN) - 1) * math.dist(points[0], points[1])
    assert rung < stretched_line


def test_layout_is_deterministic(folder):
    assert folder.layout_coordinates(TWO_HAIRPINS) == folder.layout_coordinates(TWO_HAIRPINS)
