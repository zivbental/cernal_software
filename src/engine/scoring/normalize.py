"""Turning heterogeneous raw metrics into comparable normalized values.

The rule from design map 12: preserve gate-specific raw metrics, map only scientifically
justified dimensions onto a shared 0-1 axis, and report the decomposition rather than a
single opaque score.

Normalization here is min-max within a metric's declared ``valid_range``, inverted for
LOWER_BETTER metrics, so that **1.0 is always better** regardless of direction.
"""

from engine.contract import LOWER_BETTER, MetricValue
from engine.scoring.profiles import SKIP, TREAT_AS_WORST, HardFilter, MetricSpec, ScoringProfile


def normalize_value(raw: float | None, spec: MetricSpec) -> float | None:
    """Map a raw value onto 0-1 where 1.0 is best. ``None`` if it cannot be normalized.

    Values outside ``valid_range`` are clamped rather than rejected: an out-of-range
    measurement is still evidence, and hard filters are the mechanism for disqualifying
    a candidate.
    """
    if raw is None:
        return None

    low, high = spec.valid_range
    clamped = min(max(raw, low), high)
    fraction = (clamped - low) / (high - low)

    return 1.0 - fraction if spec.direction == LOWER_BETTER else fraction


def build_metrics(
    raw_values: dict[str, float | None], profile: ScoringProfile
) -> list[MetricValue]:
    """Build the full metric list for one candidate, in profile order.

    Every metric the profile declares appears in the output, even if the raw value is
    missing — the researcher sees the whole decomposition, including its gaps.
    """
    return [
        MetricValue(
            name=spec.name,
            raw_value=raw_values.get(spec.name),
            normalized_value=normalize_value(raw_values.get(spec.name), spec),
            weight=spec.weight,
            direction=spec.direction,
        )
        for spec in profile.metrics
    ]


def weighted_score(metrics: list[MetricValue], profile: ScoringProfile) -> float | None:
    """Weighted mean of normalized values, on 0-1.

    Missing metrics follow their spec's ``missing_behavior``: ``TREAT_AS_WORST``
    contributes 0.0 at full weight, ``SKIP`` removes the metric from both numerator and
    denominator. Returns ``None`` if every metric was skipped.
    """
    numerator = 0.0
    denominator = 0.0

    for metric in metrics:
        spec = profile.spec(metric.name)
        if spec is None:
            continue

        if metric.normalized_value is None:
            if spec.missing_behavior == SKIP:
                continue
            if spec.missing_behavior == TREAT_AS_WORST:
                denominator += spec.weight
                continue

        numerator += metric.normalized_value * spec.weight
        denominator += spec.weight

    if denominator == 0:
        return None
    return numerator / denominator


def failed_filter(
    raw_values: dict[str, float | None], profile: ScoringProfile
) -> HardFilter | None:
    """Return the first hard filter this candidate fails, or ``None`` if it passes all."""
    for hard_filter in profile.hard_filters:
        raw = raw_values.get(hard_filter.metric)
        if raw is None:
            continue
        if hard_filter.minimum is not None and raw < hard_filter.minimum:
            return hard_filter
        if hard_filter.maximum is not None and raw > hard_filter.maximum:
            return hard_filter
    return None


def rank_candidates(scored: list[tuple[str, float | None]]) -> dict[str, int]:
    """Assign contiguous 1-based ranks, best first. Unscored candidates are not ranked."""
    ordered = sorted(
        (item for item in scored if item[1] is not None),
        key=lambda item: (-item[1], item[0]),
    )
    return {ref: position for position, (ref, _score) in enumerate(ordered, start=1)}
