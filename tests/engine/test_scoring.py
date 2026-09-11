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
    custom_scoring_label,
    derive_profile,
    get_profile,
    resolve_profile,
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


def test_every_default_metric_declares_a_unit():
    """docs/public-api.md §7: unit is what lets a caller tell linear from log2, or
    0-100 from 0-1, without reading CLAUDE.md §6 first."""
    for spec in DEFAULT_V1.metrics:
        assert spec.unit, f"{spec.name} has no unit"


# --- Custom scoring (docs/public-api.md §9.1, X7) ----------------------------------


def test_derive_profile_with_no_overrides_returns_something_equal_but_new():
    derived = derive_profile(DEFAULT_V1)
    assert derived.metrics == DEFAULT_V1.metrics
    assert derived.hard_filters == DEFAULT_V1.hard_filters
    assert derived.tie_breakers == DEFAULT_V1.tie_breakers


def test_weights_merge_by_name_others_keep_the_base_weight():
    derived = derive_profile(DEFAULT_V1, weights={"predicted_leakage": 4.0, "gc_content": 0.0})

    assert derived.spec("predicted_leakage").weight == 4.0
    assert derived.spec("gc_content").weight == 0.0
    # untouched
    assert derived.spec("state_separation").weight == DEFAULT_V1.spec("state_separation").weight


def test_weight_override_never_touches_direction_or_valid_range():
    """docs/public-api.md §9.1: direction and valid_range are physics and units, not
    preference — a caller widening valid_range could make its own numbers look better."""
    derived = derive_profile(DEFAULT_V1, weights={"gate_folding_energy": 9.0})
    spec = derived.spec("gate_folding_energy")

    assert spec.direction == DEFAULT_V1.spec("gate_folding_energy").direction
    assert spec.valid_range == DEFAULT_V1.spec("gate_folding_energy").valid_range


def test_hard_filters_merge_by_metric_the_base_filters_survive():
    """A caller adding one new threshold must not silently lose the base's existing
    safety filters (predicted_leakage's ceiling, state_separation's floor)."""
    derived = derive_profile(
        DEFAULT_V1, hard_filters=[{"metric": "dynamic_range", "minimum": 10.0}]
    )

    by_metric = {hf.metric: hf for hf in derived.hard_filters}
    assert by_metric["dynamic_range"].minimum == 10.0
    assert by_metric["predicted_leakage"].maximum == 0.85, "base filter must survive"
    assert by_metric["state_separation"].minimum == 0.5, "base filter must survive"


def test_hard_filter_override_replaces_the_same_metric():
    derived = derive_profile(
        DEFAULT_V1, hard_filters=[{"metric": "predicted_leakage", "maximum": 0.5}]
    )

    matching = [hf for hf in derived.hard_filters if hf.metric == "predicted_leakage"]
    assert len(matching) == 1, "override must replace, not duplicate"
    assert matching[0].maximum == 0.5


def test_tie_breakers_replace_outright_when_given():
    derived = derive_profile(DEFAULT_V1, tie_breakers=["dynamic_range"])
    assert derived.tie_breakers == ["dynamic_range"]


def test_tie_breakers_keep_the_base_when_not_given():
    derived = derive_profile(DEFAULT_V1, weights={"gc_content": 1.0})
    assert derived.tie_breakers == DEFAULT_V1.tie_breakers


def test_derived_profile_validates_and_labels_itself_custom():
    derived = derive_profile(DEFAULT_V1, weights={"gc_content": 1.0})
    derived.validate()  # must not raise
    assert derived.label.startswith("custom-")
    assert derived.name == "custom"


def test_derived_label_is_deterministic():
    a = custom_scoring_label("default", {"gc_content": 1.0}, [], None)
    b = custom_scoring_label("default", {"gc_content": 1.0}, [], None)
    assert a == b


def test_derived_label_differs_for_different_weights():
    a = custom_scoring_label("default", {"gc_content": 1.0}, [], None)
    b = custom_scoring_label("default", {"gc_content": 2.0}, [], None)
    assert a != b


def test_weight_of_zero_leaves_the_metric_measured_but_silent():
    """CLAUDE.md §3: raw values only. weight=0 stops a metric moving the rank without
    deleting its spec — the value is still measured and visible in the decomposition."""
    derived = derive_profile(DEFAULT_V1, weights={"gc_content": 0.0})
    spec = derived.spec("gc_content")
    assert spec is not None
    assert spec.weight == 0.0


def test_resolve_profile_with_no_overrides_returns_the_base():
    assert resolve_profile("default", None) is get_profile("default")
    assert resolve_profile("default", {}) is get_profile("default")


def test_resolve_profile_with_empty_blocks_returns_the_base():
    assert resolve_profile(
        "default", {"weights": {}, "hard_filters": [], "tie_breakers": []}
    ) is get_profile("default")


def test_resolve_profile_with_overrides_derives():
    profile = resolve_profile("default", {"weights": {"gc_content": 9.0}})
    assert profile.name == "custom"
    assert profile.spec("gc_content").weight == 9.0


def test_resolve_profile_unknown_base_still_raises():
    with pytest.raises(ScoringProfileError, match="Available profiles"):
        resolve_profile("nope", {"weights": {"gc_content": 1.0}})
