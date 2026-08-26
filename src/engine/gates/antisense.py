"""Antisense NOT gate.

**Stub.** Bodies land in Step 5.

An antisense RNA silences the payload while its trigger is present, so the circuit fires
when the trigger is *absent* — the inverting element the map's NOT logic needs.
"""

from collections.abc import Iterator
from typing import ClassVar

from engine.domain import (
    Compatibility,
    Constraints,
    GateDesign,
    GateKind,
    Host,
    ToolRequirement,
    TriggerSet,
)
from engine.gates.base import GateFamily
from engine.tools.codons import CodonOptimizer
from engine.tools.folding import FoldEngine


class AntisenseNotGate(GateFamily):
    """Post-transcriptional silencing, inverting."""

    name = "antisense"
    version = "0.0.0-planned"
    kind = GateKind.ANTISENSE_NOT
    label = "Antisense Repression"
    description = "Post-transcriptional silencing"
    supported_hosts: ClassVar[frozenset[Host]] = frozenset({Host.ECOLI, Host.YEAST, Host.HUMAN})
    max_inputs = 1
    available = False

    def __init__(self, host: Host, folder: FoldEngine, codons: CodonOptimizer) -> None:
        self.host = host
        self.folder = folder
        self.codons = codons

    def required_tools(self) -> list[ToolRequirement]:
        return [ToolRequirement(name="ViennaRNA", version="2.7")]

    def is_compatible(self, trigger_set: TriggerSet, constraints: Constraints) -> Compatibility:
        return Compatibility.no("The antisense family is not implemented yet.")

    def generate_designs(
        self, trigger_set: TriggerSet, constraints: Constraints
    ) -> Iterator[GateDesign]:
        """Step 5: extend the CDS with an antisense region complementary to the trigger,
        using CodonOptimizer so the extension does not disturb the protein."""
        raise NotImplementedError("Step 5")

    def evaluate_design(self, design: GateDesign) -> dict[str, float | None]:
        raise NotImplementedError("Step 5")

    def emit_sequence(self, design: GateDesign) -> str:
        return design.sequence
