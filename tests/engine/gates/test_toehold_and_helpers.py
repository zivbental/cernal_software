"""Regression tests for the helper modules behind ``eu_and_v3.ipynb``.

The helpers live beside the notebook (a directory, not a package), so they are loaded by path.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

NOTEBOOK_DIR = Path(__file__).parents[3] / "src/engine/gates/notebooks/toehold_and"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, NOTEBOOK_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def joint():
    return _load("_joint_state_parallel")


# --- trigger pair complementarity screen ----------------------------------------------------


@pytest.mark.parametrize(
    ("a", "b", "expected_run"),
    [
        ("A" * 12, "U" * 12, 12),  # fully Watson-Crick complementary
        ("GGGGAAAACCCC", "GGGGUUUUCCCC", 12),  # reverse complement of itself with A/U swap
        ("GAUCGAUCAAAA", "UUUUGAUCGAUC", 12),  # arbitrary full duplex
        ("A" * 12, "A" * 12, 0),  # negative control: identical, not complementary
        ("G" * 12, "G" * 12, 0),  # negative control
    ],
)
def test_wobble_helper_finds_watson_crick_duplexes(joint, a, b, expected_run):
    run, wobble = joint._longest_complementary_run_wobble(a, b, 0.0)
    assert run == expected_run
    assert wobble == 0


def test_wobble_helper_agrees_with_the_exact_helper_without_wobble(joint):
    for a, b in [("ACGUACGUAGCU", "AGCUACGUACGU"), ("A" * 12, "U" * 12), ("GCGC", "GCGC")]:
        run, _ = joint._longest_complementary_run_wobble(a, b, 0.0)
        assert run == joint._longest_complementary_run(a, b)


def test_wobble_pairs_extend_a_duplex_only_when_allowed(joint):
    a, b = "GGGGGGGGGGGG", "UUUUUUUUUUUU"  # G pairs with U only as a wobble
    assert joint._longest_complementary_run_wobble(a, b, 0.0) == (0, 0)
    assert joint._longest_complementary_run_wobble(a, b, 1.0) == (12, 12)
    mixed_run, mixed_wobble = joint._longest_complementary_run_wobble(
        "GGGGAAAACCCC", "UUUUUUUUCCCC", 0.5
    )
    assert mixed_run > 0 and mixed_wobble <= mixed_run / 2


def test_trigger_pair_screen_rejects_a_fully_complementary_pair(joint):
    assert joint.trigger_pair_too_similar(
        "A" * 12, "U" * 12, max_overlap_nt=8, wobble_max_fraction=0.0
    )
    assert joint.trigger_pair_too_similar(
        "A" * 12, "U" * 12, max_overlap_nt=8, wobble_max_fraction=0.25
    )


def test_trigger_pair_screen_rejects_identical_and_accepts_unrelated_pairs(joint):
    same = "ACGUACGUACGUAC"
    assert joint.trigger_pair_too_similar(same, same, max_overlap_nt=8, wobble_max_fraction=0.25)
    assert not joint.trigger_pair_too_similar(
        "A" * 16, "G" * 16, max_overlap_nt=8, wobble_max_fraction=0.0
    )


# --- empty control pool ---------------------------------------------------------------------


def test_fake_trigger_picker_returns_nothing_for_a_pool_of_only_the_real_design(joint):
    pool = [{"rank": 1, "trigger": "ACGUACGUACGUACGU"}]
    assert joint.pick_fake_triggers(("ACGUACGUACGUACGU",), {1}, pool, 5, max_overlap_nt=8) == []


# --- verification tolerance and report statistics -------------------------------------------


@pytest.fixture(scope="module")
def stats():
    return _load("_report_stats")


SIGMA, FLOOR = 4.0, 0.02


def _state(sampled, matrix, sd, n=2000, run=None):
    return {
        "run_nt_sampled": sampled if run is None else run,
        "open_nt_sampled": sampled,
        "open_nt_matrix": matrix,
        "open_nt_sd": sd,
        "n_drawn": n,
    }


def test_a_measured_zero_sd_is_kept_not_replaced_by_the_fallback(stats):
    tol = stats.verification_tolerance(0.0, 2000, default_sd=6.0, sigma=SIGMA, floor_nt=FLOOR)
    assert tol == pytest.approx(FLOOR)


def test_a_missing_sd_falls_back_to_the_conservative_value(stats):
    for missing in (None, float("nan")):
        tol = stats.verification_tolerance(
            missing, 2000, default_sd=6.0, sigma=SIGMA, floor_nt=FLOOR
        )
        assert tol == pytest.approx(SIGMA * 6.0 / 2000**0.5 + FLOOR)


def test_zero_variance_disagreement_fails_verification_single(stats):
    # every draw is the same structure (sd 0) but the matrix says 0.3 nt on average open
    assert not stats.state_ok(_state(0.0, 0.3, 0.0), 12, sigma=SIGMA, floor_nt=FLOOR)
    # the same disagreement with the sd missing is tolerated only because the sd is unknown
    assert stats.state_ok(_state(0.0, 0.3, None), 12, sigma=SIGMA, floor_nt=FLOOR)
    assert stats.state_ok(_state(0.0, 0.01, 0.0), 12, sigma=SIGMA, floor_nt=FLOOR)


def _and_state(sampled, matrix, sd, name="alone"):
    return {
        "open_sampled": sampled,
        "run_a_sampled": sampled,
        "run_b_sampled": sampled,
        "k_a_sampled": sampled,
        "k_b_sampled": sampled,
        "k_a_matrix": matrix,
        "k_b_matrix": matrix,
        "k_a_sd": sd,
        "k_b_sd": sd,
        "n_drawn": 2000,
    }


def test_zero_variance_disagreement_fails_verification_and(stats):
    for name in ("alone", "+A", "+B", "+A+B"):
        assert not stats.state_ok_and(
            _and_state(0.0, 0.3, 0.0), name, 12, 12, sigma=SIGMA, floor_nt=FLOOR
        ), name
        assert stats.state_ok_and(
            _and_state(0.0, 0.3, None), name, 12, 12, sigma=SIGMA, floor_nt=FLOOR
        ), name
        assert stats.state_ok_and(
            _and_state(0.0, 0.0, 0.0), name, 12, 12, sigma=SIGMA, floor_nt=FLOOR
        ), name


def test_missing_samples_are_never_verified(stats):
    assert not stats.state_ok(_state(None, 0.3, 0.0), 12, sigma=SIGMA, floor_nt=FLOOR)
    state = _and_state(None, 0.3, 0.0)
    assert not stats.state_ok_and(state, "alone", 12, 12, sigma=SIGMA, floor_nt=FLOOR)


def test_medians_of_an_empty_column_are_unavailable_not_zero_or_an_error(stats):
    assert stats.median_or_none([]) is None
    assert stats.median_or_none([None, None]) is None
    assert stats.median_text([], unit="%") == "n/a"
    assert stats.median_text([None], unit="%") == "n/a"
    assert stats.median_text([1.0, None, 3.0], unit="%") == "2.0%"
    assert stats.pct_text(None) == "n/a"
    assert stats.pct_text(0.0) == "0.0%"


# --- AUG before the second hairpin's stem_down ----------------------------------------------


@pytest.fixture
def construct(monkeypatch):
    monkeypatch.syspath_prepend(str(NOTEBOOK_DIR))
    return _load("_switch_construct")


def _built(fused: str, stem_down_b: tuple[int, int]) -> dict:
    return {"fused": fused, "domains_3p": {"stem_down": stem_down_b}}


def test_an_aug_before_the_second_stem_down_is_reported(construct):
    fused = "CCCAUGCCC" + "CCCCCCCCCCCC" + "GGGGGGGGGGGGGGGGGG" + "AUGAAA"
    assert construct.upstream_augs(_built(fused, (21, 30))) == (3,)


def test_the_payload_start_codon_after_the_second_stem_down_is_not_reported(construct):
    fused = "C" * 30 + "GCCACC" + "AUGGUG"
    assert construct.upstream_augs(_built(fused, (20, 30))) == ()


def test_an_aug_in_the_second_hairpins_toehold_or_stem_up_counts(construct):
    fused = "C" * 10 + "AUG" + "C" * 30
    assert construct.upstream_augs(_built(fused, (25, 37))) == (10,)


def test_an_aug_that_starts_at_the_stem_down_start_is_not_upstream(construct):
    fused = "C" * 20 + "AUG" + "C" * 20
    assert construct.upstream_augs(_built(fused, (20, 32))) == ()


def test_overlapping_and_repeated_augs_are_all_listed(construct):
    fused = "AUGAUGC" + "C" * 20
    assert construct.upstream_augs(_built(fused, (15, 25))) == (0, 3)
