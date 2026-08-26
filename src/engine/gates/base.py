"""The GateFamily interface.

Every switch chemistry implements this. It is the one real class hierarchy in the engine
— everything else is data or a function (docs/engine.md §2.1).

The types it works with live in ``engine.domain``; the scientific primitives it calls
live in ``engine.tools``. A family **is** a gate and **uses** folding, which is why one
is inheritance and the other composition.
"""

from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import ClassVar

from engine.contract import ArtifactRef
from engine.domain import (
    Compatibility,
    Constraints,
    GateDesign,
    GateKind,
    Host,
    ToolRequirement,
    TriggerSet,
)


class GateFamily(ABC):
    """Base class for every switch chemistry.

    Subclasses set the class variables and implement the five methods. Bump ``version``
    whenever generation or evaluation changes in a way that alters output — it is
    recorded on results, and it is what makes an old design traceable.
    """

    name: ClassVar[str] = ""
    version: ClassVar[str] = ""
    kind: ClassVar[GateKind]

    #: How the family presents itself, surfaced through EngineCapabilities so the UI
    #: renders what the engine says rather than a hardcoded list.
    label: ClassVar[str] = ""
    description: ClassVar[str] = ""

    #: Availability is a function of gate and host: CRISPR is eukaryotic only.
    supported_hosts: ClassVar[frozenset[Host]] = frozenset()

    #: 1 for a single-input switch, 2 for AND.
    max_inputs: ClassVar[int] = 1

    #: False while a family is designed but not selectable. Step 5 flips these.
    available: ClassVar[bool] = False

    def supports(self, host: Host) -> bool:
        """Whether this family can be used for this organism.

        Both conditions matter: a family may be implemented but wrong for the host
        (CRISPR in E. coli), or right for the host but not yet implemented.
        """
        return self.available and host in self.supported_hosts

    @abstractmethod
    def required_tools(self) -> list[ToolRequirement]:
        """External tools this family needs. Checked before a run starts."""

    @abstractmethod
    def is_compatible(self, trigger_set: TriggerSet, constraints: Constraints) -> Compatibility:
        """Can this family realise this trigger set? Cheap checks only — expensive
        evaluation happens later, and only for designs that survive this."""

    @abstractmethod
    def generate_designs(
        self, trigger_set: TriggerSet, constraints: Constraints
    ) -> Iterator[GateDesign]:
        """Produce candidate realisations. **Yields**, because a family exploring a
        length window across thousands of trigger sets produces far too many designs to
        hold in a list."""

    @abstractmethod
    def evaluate_design(self, design: GateDesign) -> dict[str, float | None]:
        """Measure a design. Returns **raw** values keyed by metric name.

        Normalization and weighting belong to ``engine.scoring`` — a family that scored
        its own designs could not be compared with another family, which is the central
        problem design map 12 identifies.
        """

    @abstractmethod
    def emit_sequence(self, design: GateDesign) -> str:
        """The synthesis-ready sequence for this design."""

    def emit_artifacts(self, design: GateDesign, output_dir: str) -> list[ArtifactRef]:
        """Family-specific files. Optional — the default produces none."""
        return []

    def describe(self, design: GateDesign) -> str:
        """One-line human summary. Overridable, with a reasonable default."""
        features = ", ".join(t.symbol for t in design.trigger_set.activators)
        return f"{design.trigger_set.logic_type} {self.name} gate on {features}"

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.name}-{self.version}>"
