"""Versioned scoring profiles.

A profile declares *exactly* how candidates are compared: which metrics count, how they
are normalized, how they are weighted, and what disqualifies a candidate outright. The
profile name and version are recorded on every run, so a score is always interpretable
after the fact (design map 12).

Metric definitions here are **provisional**. The scientific team owns the final set and
its thresholds; this profile exists so the scoring machinery is exercised end to end
before the real pipeline lands.
"""

from dataclasses import dataclass, field

from engine.contract import HIGHER_BETTER, LOWER_BETTER
from engine.errors import ScoringProfileError

#: What to do when a metric is missing for a candidate.
TREAT_AS_WORST = "worst"
SKIP = "skip"


@dataclass(frozen=True, slots=True)
class MetricSpec:
    """The declaration of one metric, per design map 12."""

    name: str
    direction: str
    weight: float
    valid_range: tuple[float, float]
    missing_behavior: str = TREAT_AS_WORST
    description: str = ""


@dataclass(frozen=True, slots=True)
class HardFilter:
    """A disqualifying threshold. Failing one rejects the candidate before ranking."""

    metric: str
    minimum: float | None = None
    maximum: float | None = None
    reason: str = ""


@dataclass(frozen=True, slots=True)
class ScoringProfile:
    name: str
    version: str
    metrics: list[MetricSpec]
    hard_filters: list[HardFilter] = field(default_factory=list)
    tie_breakers: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        return f"{self.name}-{self.version}"

    def spec(self, metric_name: str) -> MetricSpec | None:
        for spec in self.metrics:
            if spec.name == metric_name:
                return spec
        return None

    def validate(self) -> None:
        """Fail loudly on an inconsistent profile rather than producing a silent bad score."""
        if not self.metrics:
            raise ScoringProfileError(f"Profile '{self.label}' declares no metrics.")

        names = [spec.name for spec in self.metrics]
        if len(names) != len(set(names)):
            raise ScoringProfileError(f"Profile '{self.label}' declares a metric twice.")

        total = sum(spec.weight for spec in self.metrics)
        if total <= 0:
            raise ScoringProfileError(f"Profile '{self.label}' has non-positive total weight.")

        for spec in self.metrics:
            low, high = spec.valid_range
            if low >= high:
                raise ScoringProfileError(
                    f"Metric '{spec.name}' in '{self.label}' has an empty valid_range."
                )
            if spec.direction not in (HIGHER_BETTER, LOWER_BETTER):
                raise ScoringProfileError(
                    f"Metric '{spec.name}' in '{self.label}' has an unknown direction."
                )

        for hard_filter in self.hard_filters:
            if self.spec(hard_filter.metric) is None:
                raise ScoringProfileError(
                    f"Hard filter in '{self.label}' references unknown metric "
                    f"'{hard_filter.metric}'."
                )


DEFAULT_V1 = ScoringProfile(
    name="default",
    version="v1",
    metrics=[
        MetricSpec(
            name="state_separation",
            direction=HIGHER_BETTER,
            weight=3.0,
            valid_range=(0.0, 10.0),
            description="Differential expression between base and target state (log2 fold).",
        ),
        MetricSpec(
            name="trigger_accessibility",
            direction=HIGHER_BETTER,
            weight=2.0,
            valid_range=(0.0, 1.0),
            description="Predicted fraction of the trigger region free of self-structure.",
        ),
        MetricSpec(
            name="gate_folding_energy",
            direction=LOWER_BETTER,
            weight=2.0,
            valid_range=(-60.0, 0.0),
            description="Predicted MFE of the gate in kcal/mol. More negative is more stable.",
        ),
        MetricSpec(
            name="predicted_leakage",
            direction=LOWER_BETTER,
            weight=2.5,
            valid_range=(0.0, 1.0),
            description="Proxy for OFF-state activation.",
        ),
        MetricSpec(
            name="orthogonality",
            direction=HIGHER_BETTER,
            weight=1.5,
            valid_range=(0.0, 1.0),
            description="Predicted independence from other gates in the same circuit.",
        ),
        MetricSpec(
            name="gc_content",
            direction=HIGHER_BETTER,
            weight=0.5,
            valid_range=(30.0, 70.0),
            description="Percent GC of the assembled construct. Extremes hurt synthesis.",
        ),
        MetricSpec(
            name="dynamic_range",
            direction=HIGHER_BETTER,
            weight=2.0,
            valid_range=(1.0, 500.0),
            description="Predicted ON/OFF fold change.",
        ),
        MetricSpec(
            name="predicted_success_rate",
            direction=HIGHER_BETTER,
            weight=1.0,
            valid_range=(0.0, 1.0),
            description="Model confidence that the construct behaves as designed in vivo.",
        ),
        MetricSpec(
            name="circuit_complexity",
            direction=LOWER_BETTER,
            weight=1.0,
            valid_range=(1.0, 10.0),
            description="Component count penalty. Simpler circuits are easier to build.",
        ),
    ],
    hard_filters=[
        HardFilter(
            metric="predicted_leakage",
            maximum=0.85,
            reason="Predicted OFF-state leakage above the acceptable threshold.",
        ),
        HardFilter(
            metric="state_separation",
            minimum=0.5,
            reason="Insufficient separation between base and target state.",
        ),
    ],
    tie_breakers=["state_separation", "predicted_leakage"],
)

PROFILES: dict[str, ScoringProfile] = {DEFAULT_V1.name: DEFAULT_V1}


def get_profile(name: str) -> ScoringProfile:
    """Look up a profile by name, validating it before returning."""
    try:
        profile = PROFILES[name]
    except KeyError:
        known = ", ".join(sorted(PROFILES)) or "none"
        raise ScoringProfileError(
            f"Unknown scoring profile '{name}'. Available profiles: {known}."
        ) from None
    profile.validate()
    return profile


def available_profiles() -> list[str]:
    return sorted(PROFILES)
