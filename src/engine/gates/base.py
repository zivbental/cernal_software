"""The GateFamily interface.

Every gate chemistry — toehold, AND-toehold, CRISPR-derived — implements this same
interface. That is what lets a new logic family be added without touching the pipeline,
the scoring machinery or any Platform code (design map 12).

The types here are **engine-internal**: they never cross the Platform boundary. Only
``engine.contract`` types do.
"""

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import ClassVar

from engine.contract import ArtifactRef, MetricValue


@dataclass(frozen=True, slots=True)
class Trigger:
    """One input signal: a gene or feature whose expression drives the gate."""

    feature_id: str
    sequence: str
    base_expression: float
    target_expression: float

    @property
    def separation(self) -> float:
        """Log2-fold-ish separation between the two states."""
        return self.target_expression - self.base_expression


@dataclass(frozen=True, slots=True)
class TriggerSet:
    """The inputs to one candidate circuit. Size determines the logic arity."""

    triggers: tuple[Trigger, ...]

    @property
    def arity(self) -> int:
        return len(self.triggers)

    @property
    def logic_type(self) -> str:
        return {1: "single-input", 2: "AND", 3: "AND3"}.get(self.arity, f"AND{self.arity}")


@dataclass(frozen=True, slots=True)
class Constraints:
    """Biological and practical limits the researcher configured for a run."""

    max_triggers: int = 2
    min_separation: float = 0.5
    forbidden_motifs: tuple[str, ...] = ()
    max_gate_length: int = 200


@dataclass(frozen=True, slots=True)
class Compatibility:
    """Whether a family can realise a trigger set, and why not if it cannot."""

    ok: bool
    reason: str = ""

    @classmethod
    def yes(cls) -> "Compatibility":
        return cls(ok=True)

    @classmethod
    def no(cls, reason: str) -> "Compatibility":
        return cls(ok=False, reason=reason)


@dataclass(frozen=True, slots=True)
class GateDesign:
    """One concrete realisation of a trigger set in a particular gate chemistry."""

    ref: str
    family: str
    trigger_set: TriggerSet
    switch_sequence: str
    structure: str = ""
    properties: dict = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ToolRequirement:
    """An external scientific tool this family needs, and the version it was validated at."""

    name: str
    version: str
    optional: bool = False


class GateFamily(ABC):
    """Base class for every gate chemistry.

    Subclasses must set ``name`` and ``version``. ``version`` is recorded on results, so
    a design can always be traced back to the rules that produced it — bump it whenever
    generation or evaluation logic changes in a way that alters output.
    """

    name: ClassVar[str] = ""
    version: ClassVar[str] = ""

    #: How the family presents itself. Surfaced through EngineCapabilities so the UI
    #: renders what the engine says rather than a hardcoded list (§3).
    label: ClassVar[str] = ""
    description: ClassVar[str] = ""

    #: False while a family is planned but not selectable. Step 5 flips these.
    available: ClassVar[bool] = False

    @abstractmethod
    def required_tools(self) -> list[ToolRequirement]:
        """External tools this family needs. Checked before a run starts."""

    @abstractmethod
    def is_compatible(self, trigger_set: TriggerSet, constraints: Constraints) -> Compatibility:
        """Can this family realise this trigger set under these constraints?"""

    @abstractmethod
    def generate_designs(
        self, trigger_set: TriggerSet, constraints: Constraints
    ) -> Iterable[GateDesign]:
        """Produce candidate realisations. May yield zero designs."""

    @abstractmethod
    def evaluate_design(self, design: GateDesign) -> dict[str, float | None]:
        """Measure a design. Returns raw metric values keyed by metric name.

        Normalization and weighting are *not* done here — that is the scoring layer's
        job, so that families stay comparable (design map 12).
        """

    @abstractmethod
    def emit_sequence(self, design: GateDesign) -> str:
        """The synthesis-ready nucleotide sequence for this design."""

    @abstractmethod
    def emit_artifacts(self, design: GateDesign, output_dir: str) -> list[ArtifactRef]:
        """Write any family-specific files (structure plots, design tables)."""

    def describe(self, design: GateDesign, metrics: list[MetricValue]) -> str:
        """One-line human summary. Overridable, with a reasonable default."""
        features = ", ".join(t.feature_id for t in design.trigger_set.triggers)
        return f"{design.trigger_set.logic_type} {self.name} gate on {features}"

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.name}-{self.version}>"
