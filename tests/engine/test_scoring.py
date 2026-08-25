"""Scoring, normalization and profile validation.

This is the machinery that makes candidates from different gate families comparable
(design map 12), so its edge cases — missing values, out-of-range measurements,
direction handling — are the ones worth pinning down.
"""

import pytest

from engine.contract import HIGHER_BETTER, LOWER_BETTER, MetricValue
from engine.errors import ScoringProfileError
from engine.scoring.normalize import (
    build_metrics,
    failed_filter,
    normalize_value,
    rank_candidates,
    weighted_score,
)
from engine.scoring.profiles import (
    DEFAULT_V1,
    SKIP,
    TREAT_AS_WORST,
    HardFilter,
    MetricSpec,
    ScoringProfile,
    available_profiles,
    get_profile,
)

HIGHER = MetricSpec("h", HIGHER_BETTER, weight=1.0, valid_range=(0.0, 10.0))
LOWER = MetricSpec("l", LOWER_BETTER, weight=1.0, valid_range=(0.0, 10.0))


# --- Normalization ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(0.0, 0.0), (5.0, 0.5), (10.0, 1.0)],
)
def test_higher_better_maps_upward(raw, expected):
    assert normalize_value(raw, HIGHER) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(0.0, 1.0), (5.0, 0.5), (10.0, 0.0)],
)
def test_lower_better_is_inverted(raw, expected):
    """1.0 is always better, whichever direction the raw metric runs."""
    assert normalize_value(raw, LOWER) == pytest.approx(expected)


def test_out_of_range_values_are_clamped_not_rejected():
    """An out-of-range measurement is still evidence; hard filters do the rejecting."""
    assert normalize_value(-5.0, HIGHER) == 0.0
    assert normalize_value(99.0, HIGHER) == 1.0


def test_missing_raw_value_normalizes_to_none():
    assert normalize_value(None, HIGHER) is None


# --- Weighted score ---------------------------------------------------------------


def test_weighted_score_respects_weights():
    profile = ScoringProfile(
        name="t",
        version="1",
        metrics=[
            MetricSpec("a", HIGHER_BETTER, weight=3.0, valid_range=(0.0, 1.0)),
            MetricSpec("b", HIGHER_BETTER, weight=1.0, valid_range=(0.0, 1.0)),
        ],
    )
    metrics = build_metrics({"a": 1.0, "b": 0.0}, profile)
    assert weighted_score(metrics, profile) == pytest.approx(0.75)


def test_missing_metric_treated_as_worst_drags_the_score_down():
    profile = ScoringProfile(
        name="t",
        version="1",
        metrics=[
            MetricSpec("a", HIGHER_BETTER, 1.0, (0.0, 1.0), missing_behavior=TREAT_AS_WORST),
            MetricSpec("b", HIGHER_BETTER, 1.0, (0.0, 1.0), missing_behavior=TREAT_AS_WORST),
        ],
    )
    metrics = build_metrics({"a": 1.0}, profile)
    assert weighted_score(metrics, profile) == pytest.approx(0.5)


def test_missing_metric_marked_skip_is_excluded_from_both_sides():
    profile = ScoringProfile(
        name="t",
        version="1",
        metrics=[
            MetricSpec("a", HIGHER_BETTER, 1.0, (0.0, 1.0), missing_behavior=TREAT_AS_WORST),
            MetricSpec("b", HIGHER_BETTER, 1.0, (0.0, 1.0), missing_behavior=SKIP),
        ],
    )
    metrics = build_metrics({"a": 1.0}, profile)
    assert weighted_score(metrics, profile) == pytest.approx(1.0)


def test_score_is_none_when_every_metric_is_skipped():
    profile = ScoringProfile(
        name="t",
        version="1",
        metrics=[MetricSpec("a", HIGHER_BETTER, 1.0, (0.0, 1.0), missing_behavior=SKIP)],
    )
    assert weighted_score(build_metrics({}, profile), profile) is None


def test_unknown_metrics_are_ignored_rather_than_crashing():
    """A gate family emitting an extra metric must not break scoring."""
    profile = ScoringProfile(
        name="t", version="1", metrics=[MetricSpec("a", HIGHER_BETTER, 1.0, (0.0, 1.0))]
    )
    metrics = [
        MetricValue("a", 1.0, 1.0, 1.0, HIGHER_BETTER),
        MetricValue("surprise", 5.0, 0.5, 9.0, HIGHER_BETTER),
    ]
    assert weighted_score(metrics, profile) == pytest.approx(1.0)


def test_build_metrics_reports_the_whole_decomposition_including_gaps():
    metrics = build_metrics({"state_separation": 4.0}, DEFAULT_V1)

    assert len(metrics) == len(DEFAULT_V1.metrics)
    missing = [m for m in metrics if m.raw_value is None]
    assert missing, "metrics absent from the input must still appear, as gaps"


# --- Hard filters -----------------------------------------------------------------


def test_hard_filter_catches_a_maximum_breach():
    profile = ScoringProfile(
        name="t",
        version="1",
        metrics=[MetricSpec("leak", LOWER_BETTER, 1.0, (0.0, 1.0))],
        hard_filters=[HardFilter("leak", maximum=0.5, reason="Too leaky.")],
    )
    breach = failed_filter({"leak": 0.9}, profile)
    assert breach is not None and breach.reason == "Too leaky."


def test_hard_filter_passes_a_good_candidate():
    profile = ScoringProfile(
        name="t",
        version="1",
        metrics=[MetricSpec("leak", LOWER_BETTER, 1.0, (0.0, 1.0))],
        hard_filters=[HardFilter("leak", maximum=0.5, reason="Too leaky.")],
    )
    assert failed_filter({"leak": 0.1}, profile) is None


def test_hard_filter_ignores_a_missing_measurement():
    """Absence of evidence is not grounds for rejection here."""
    assert failed_filter({}, DEFAULT_V1) is None


# --- Ranking ----------------------------------------------------------------------


def test_ranks_are_contiguous_and_best_first():
    assert rank_candidates([("a", 0.1), ("b", 0.9), ("c", 0.5)]) == {"b": 1, "c": 2, "a": 3}


def test_unscored_candidates_are_not_ranked():
    ranks = rank_candidates([("a", 0.5), ("b", None)])
    assert ranks == {"a": 1}


def test_ties_break_deterministically_by_ref():
    assert rank_candidates([("z", 0.5), ("a", 0.5)]) == {"a": 1, "z": 2}


# --- Profiles ---------------------------------------------------------------------


def test_the_default_profile_is_valid():
    get_profile("default").validate()
    assert "default" in available_profiles()


def test_unknown_profile_names_the_available_ones():
    with pytest.raises(ScoringProfileError, match="Available profiles"):
        get_profile("nope")


def test_profile_with_duplicate_metrics_is_rejected():
    profile = ScoringProfile(
        name="t",
        version="1",
        metrics=[
            MetricSpec("a", HIGHER_BETTER, 1.0, (0.0, 1.0)),
            MetricSpec("a", HIGHER_BETTER, 1.0, (0.0, 1.0)),
        ],
    )
    with pytest.raises(ScoringProfileError, match="twice"):
        profile.validate()


def test_profile_with_empty_range_is_rejected():
    profile = ScoringProfile(
        name="t", version="1", metrics=[MetricSpec("a", HIGHER_BETTER, 1.0, (1.0, 1.0))]
    )
    with pytest.raises(ScoringProfileError, match="empty valid_range"):
        profile.validate()


def test_filter_referencing_an_unknown_metric_is_rejected():
    profile = ScoringProfile(
        name="t",
        version="1",
        metrics=[MetricSpec("a", HIGHER_BETTER, 1.0, (0.0, 1.0))],
        hard_filters=[HardFilter("ghost", maximum=1.0)],
    )
    with pytest.raises(ScoringProfileError, match="unknown metric"):
        profile.validate()
