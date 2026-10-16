"""Per-hairpin Open of the AND sampler (``_sampled_and_parallel.and_state``).

``open_frac_sampled`` is E[min(r_A / L_A, r_B / L_B)]: each hairpin's longest open run as a
fraction of its own stem, the smaller of the two per structure, then the mean. The older
min(r_A, r_B) / min(L_A, L_B) cannot tell "both fully open" from "the long stem half open and the
short stem fully open" when the stems differ; these tests pin that difference with a fake engine, so
no folding is involved.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

NOTEBOOK_DIR = Path(__file__).parents[3] / "src/engine/gates/notebooks/toehold_and"

L_A, L_B = 21, 12
# fused layout: stem_up A | loop | stem_down A | stem_up B | loop | stem_down B
UP_A, DOWN_A = (0, L_A), (L_A + 4, 2 * L_A + 4)
UP_B = (2 * L_A + 4, 2 * L_A + 4 + L_B)
DOWN_B = (UP_B[1] + 4, UP_B[1] + 4 + L_B)
N = DOWN_B[1]


def _structure(closed_a: int, closed_b: int) -> str:
    """Dot-bracket where the first ``closed_a`` nt of stem_up A (``closed_b`` of B) are paired
    to the end of their own stem_down, the rest of both stems open."""
    chars = ["."] * N
    for up, down, closed in ((UP_A, DOWN_A, closed_a), (UP_B, DOWN_B, closed_b)):
        for k in range(closed):
            chars[up[0] + k] = "("
            chars[down[1] - 1 - k] = ")"
    return "".join(chars)


class _FakeEngine:
    def __init__(self, structures):
        self._structures = structures

    def sample_structures(self, strands, n, seed=None, first_strand=None):
        return list(self._structures)

    def base_pair_probabilities(self, strands):
        return [[0.0] * N for _ in range(N)]


@pytest.fixture(scope="module")
def sampled(monkeypatch_module):
    monkeypatch_module.syspath_prepend(str(NOTEBOOK_DIR))
    spec = importlib.util.spec_from_file_location(
        "_sampled_and_parallel_under_test", NOTEBOOK_DIR / "_sampled_and_parallel.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def monkeypatch_module():
    with pytest.MonkeyPatch.context() as mp:
        yield mp


def _state(sampled, structures):
    job = sampled.AndJob(
        key="t",
        fused="A" * N,
        trigger_a="",
        trigger_b="",
        stem_up_a=UP_A,
        stem_down_a=DOWN_A,
        stem_up_b=UP_B,
        stem_down_b=DOWN_B,
        temperature=37.0,
        n_samples=len(structures),
        seed=1,
    )
    return sampled.and_state(_FakeEngine(structures), "x", None, job)


def test_long_half_open_stem_is_not_hidden_behind_a_short_open_one(sampled):
    # A: 9 of 21 nt closed, 12 open (57%); B: fully open (100%). Same run in nt (12 and 12).
    state = _state(sampled, [_structure(closed_a=9, closed_b=0)])
    assert state["open_sampled"] == 12  # min(r_A, r_B) in nt, kept for the sampler check
    assert state["open_frac_sampled"] == pytest.approx(12 / 21)
    assert state["open_sampled"] / min(L_A, L_B) == pytest.approx(1.0)  # what the old ON read


def test_both_fully_open_is_one_and_both_closed_is_zero(sampled):
    assert _state(sampled, [_structure(0, 0)])["open_frac_sampled"] == pytest.approx(1.0)
    assert _state(sampled, [_structure(L_A, L_B)])["open_frac_sampled"] == pytest.approx(0.0)


def test_the_minimum_is_taken_per_structure_not_on_the_means(sampled):
    # half the draws open only A, half only B: each hairpin is open on average, never both at once
    state = _state(sampled, [_structure(0, L_B), _structure(L_A, 0)])
    assert state["open_frac_sampled"] == pytest.approx(0.0)
    assert state["run_a_sampled"] > 0 and state["run_b_sampled"] > 0
