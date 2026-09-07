"""S13 — the shared Pareto-front and top-K primitives.

`ParetoFilter` exists so a "separation vs complexity" trade-off (or any other
multi-axis comparison) is expressed once, here, instead of each stage inventing its
own dominance test or its own truncation rule.
"""

from dataclasses import dataclass

from engine.store import Objective, ParetoFilter


@dataclass
class Candidate:
    name: str
    score: float
    complexity: int


# --- frontier -------------------------------------------------------------------


def test_frontier_keeps_two_candidates_that_trade_off():
    """A more accurate, more complex design and a simpler, less accurate one are both
    worth showing — neither beats the other on both axes, so a single blended score
    would hide the trade-off this class exists to preserve."""
    accurate = Candidate("accurate", score=0.90, complexity=12)
    simple = Candidate("simple", score=0.85, complexity=4)
    pf = ParetoFilter([Objective("score"), Objective("complexity", maximize=False)])

    assert pf.frontier([accurate, simple]) == [accurate, simple]


def test_frontier_drops_a_candidate_beaten_on_every_axis():
    """Complexity is minimized here, so a design only wins by being simpler if it is
    also at least as accurate — being simpler alone is not enough to survive."""
    winner = Candidate("winner", score=0.90, complexity=4)
    loser = Candidate("loser", score=0.80, complexity=6)
    pf = ParetoFilter([Objective("score"), Objective("complexity", maximize=False)])

    assert pf.frontier([winner, loser]) == [winner]


def test_frontier_keeps_identical_duplicates():
    """Domination requires strictly better on at least one axis; two candidates tied
    on every axis dominate neither each other, so both survive the filter."""
    a = Candidate("a", score=0.5, complexity=3)
    b = Candidate("b", score=0.5, complexity=3)
    pf = ParetoFilter([Objective("score"), Objective("complexity", maximize=False)])

    assert pf.frontier([a, b]) == [a, b]


def test_frontier_preserves_input_order_rather_than_ranking_the_front():
    """The non-dominated set comes back in the caller's order, not re-sorted — sorting
    it would smuggle in a preference among the front that this class deliberately
    leaves to the caller."""
    cheap = Candidate("cheap", score=0.70, complexity=1)
    accurate = Candidate("accurate", score=0.95, complexity=10)
    balanced = Candidate("balanced", score=0.85, complexity=5)
    pf = ParetoFilter([Objective("score"), Objective("complexity", maximize=False)])

    assert pf.frontier([cheap, accurate, balanced]) == [cheap, accurate, balanced]


# --- top_k ------------------------------------------------------------------------


def test_top_k_returns_the_best_k_by_key_descending():
    low = Candidate("low", score=0.2, complexity=1)
    mid = Candidate("mid", score=0.5, complexity=1)
    high = Candidate("high", score=0.9, complexity=1)
    pf = ParetoFilter([Objective("score")])

    assert pf.top_k([low, high, mid], k=2) == [high, mid]


def test_top_k_returns_everything_when_the_pool_is_smaller_than_k():
    only = Candidate("only", score=0.5, complexity=1)
    pf = ParetoFilter([Objective("score")])

    assert pf.top_k([only], k=5) == [only]


def test_top_k_breaks_ties_by_keeping_input_order():
    """Python's sort is stable; two candidates tied on `key` keep their relative input
    order rather than being shuffled by an unstable comparison — a caller that wants
    reproducible ties across a re-run supplies records in a reproducible order."""
    first = Candidate("first", score=0.5, complexity=1)
    second = Candidate("second", score=0.5, complexity=2)
    pf = ParetoFilter([Objective("score")])

    assert pf.top_k([first, second], k=2) == [first, second]
    assert pf.top_k([second, first], k=2) == [second, first]
