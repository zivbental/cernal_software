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


# --- wobble-tolerant runs: valid sub-runs ---------------------------------------------------


def test_a_wobble_heavy_prefix_does_not_hide_an_acceptable_suffix(joint):
    a, b = "GAUAUAUUUAC", "GUGGGUGUGUU"
    assert joint._longest_complementary_run_wobble(a, b, 0.5) == (10, 5)
    assert joint.trigger_pair_too_similar(a, b, max_overlap_nt=8, wobble_max_fraction=0.5)
    # the same pair is acceptable once the wobble share is capped lower, or the run limit is higher
    assert not joint.trigger_pair_too_similar(a, b, max_overlap_nt=10, wobble_max_fraction=0.5)
    run, _ = joint._longest_complementary_run_wobble(a, b, 0.2)
    assert run < 10


def _brute_force_run(a, b, cap, is_pair):
    """Longest aligned antiparallel window whose positions all pair and wobble share <= cap."""
    b_rev = b[::-1]
    best = (0, 0)
    for shift in range(-(len(a) - 1), len(b_rev)):
        for start in range(len(a)):
            for end in range(start + 1, len(a) + 1):
                cells = [(i, i + shift) for i in range(start, end)]
                if any(not 0 <= j < len(b_rev) for _, j in cells):
                    continue
                kinds = [is_pair(a[i], b_rev[j]) for i, j in cells]
                if not all(kinds):
                    continue
                wobbles = sum(k == "wobble" for k in kinds)
                if wobbles <= cap * len(cells) + 1e-9:
                    best = max(best, (len(cells), -wobbles))
    return best[0], -best[1]


def test_wobble_run_matches_an_exhaustive_search(joint):
    import random

    def is_pair(x, y):
        if (x, y) in {("A", "U"), ("U", "A"), ("G", "C"), ("C", "G")}:
            return "wc"
        if (x, y) in {("G", "U"), ("U", "G")}:
            return "wobble"
        return None

    rng = random.Random(7)
    for _ in range(120):
        a = "".join(rng.choice("GAUC") for _ in range(rng.randint(4, 14)))
        b = "".join(rng.choice("GAUC") for _ in range(rng.randint(4, 14)))
        for cap in (0.0, 0.25, 0.5, 1.0):
            assert joint._longest_complementary_run_wobble(a, b, cap) == _brute_force_run(
                a, b, cap, is_pair
            ), (a, b, cap)


# --- zero, one and few candidates -----------------------------------------------------------


def test_rank_correlation_is_unavailable_for_fewer_than_two_candidates(stats):
    assert stats.spearman([], []) is None
    assert stats.spearman([1], [1]) is None
    assert stats.spearman([1, 2], [1, 2]) == pytest.approx(1.0)
    assert stats.spearman([1, 2, 3], [3, 2, 1]) == pytest.approx(-1.0)
    assert stats.spearman([1, 2, 3], [5, 5, 5]) is None  # no variation: undefined, not 0
    with pytest.raises(ValueError):
        stats.spearman([1, 2], [1])


def test_noise_summary_is_unavailable_without_paired_runs(stats):
    assert stats.noise_summary([]) == (None, None)
    assert stats.noise_summary([None, None]) == (None, None)
    median, p95 = stats.noise_summary([0.5])
    assert (median, p95) == (0.5, 0.5)
    median, p95 = stats.noise_summary([-1.0, 1.0, None, 2.0, 3.0])
    assert median == pytest.approx(1.5) and p95 == pytest.approx(2.0)


def test_num_text_marks_unavailable_numbers(stats):
    assert stats.num_text(None) == "n/a"
    assert stats.num_text(0.0) == "0.00"
    assert stats.num_text(12.345, 1, "%") == "12.3%"


# --- run provenance ---------------------------------------------------------------------------


def test_run_provenance_names_the_input_the_code_and_the_folding_model(stats, tmp_path):
    import hashlib

    csv_path = tmp_path / "designs.csv"
    csv_path.write_text("a,b\n1,2\n", encoding="utf-8")
    folding = {
        "viennarna_version": "2.7.2",
        "configuration": {
            "temperature_celsius": 37.0,
            "dangles": 2,
            "special_hairpins": True,
            "no_lonely_pairs": False,
            "no_gu": False,
            "no_gu_closure": False,
        },
        "energy_parameters": {"name": "turner2004", "sha256": "ab" * 32},
    }
    info = stats.run_provenance(csv_path, folding, Path(__file__).parents[3])
    assert hashlib.sha256(csv_path.read_bytes()).hexdigest() in info["input_file"]
    assert "designs.csv" in info["input_file"]
    assert "ViennaRNA 2.7.2" in info["folding_model"] and "37 °C" in info["folding_model"]
    assert "no G-U off" in info["folding_model"] and "dangles 2" in info["folding_model"]
    assert len(info["code_revision"].split()[0]) == 40  # a full git commit hash


def test_run_provenance_outside_a_git_checkout_says_so(stats, tmp_path):
    csv_path = tmp_path / "d.csv"
    csv_path.write_text("x\n", encoding="utf-8")
    folding = {
        "viennarna_version": "2.7.2",
        "configuration": {
            "temperature_celsius": 25.0,
            "dangles": 0,
            "special_hairpins": False,
            "no_lonely_pairs": True,
            "no_gu": True,
            "no_gu_closure": True,
        },
        "energy_parameters": {"name": "turner1999", "sha256": "cd" * 32},
    }
    info = stats.run_provenance(csv_path, folding, tmp_path)
    assert info["code_revision"].startswith("unavailable")
    assert "no G-U on" in info["folding_model"] and "no lonely pairs on" in info["folding_model"]
