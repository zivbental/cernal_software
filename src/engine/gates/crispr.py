"""CRISPR-derived sgRNA gate.

**Stub.** Bodies land in Step 5.

Eukaryotic only — the pipeline map lists CRISPR under the eukaryotic track and not the
prokaryotic one, which is why availability is per host rather than a single flag.
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
from engine.tools.folding import FoldEngine


class CrisprGate(GateFamily):
    """Transcriptional control via a trigger-gated sgRNA (iSBH)."""

    name = "crispr"
    version = "0.0.0-planned"
    kind = GateKind.CRISPR
    label = "CRISPR-Cas sgRNA Gate"
    description = "Transcriptional control · iSBH"
    supported_hosts: ClassVar[frozenset[Host]] = frozenset({Host.YEAST, Host.HUMAN})
    max_inputs = 1
    available = False

    def __init__(self, host: Host, folder: FoldEngine) -> None:
        self.host = host
        self.folder = folder

    def required_tools(self) -> list[ToolRequirement]:
        return [ToolRequirement(name="ViennaRNA", version="2.7")]

    def is_compatible(self, trigger_set: TriggerSet, constraints: Constraints) -> Compatibility:
        if not self.supports(self.host):
            return Compatibility.no(f"CRISPR gates are not available in {self.host.value}.")
        return Compatibility.no("The CRISPR family is not implemented yet.")

    def generate_designs(
        self, trigger_set: TriggerSet, constraints: Constraints
    ) -> Iterator[GateDesign]:
        """Step 5: build a hairpin-blocked sgRNA that the trigger unblocks, plus the
        effector choice — activator or repressor."""
        raise NotImplementedError("Step 5")

    def evaluate_design(self, design: GateDesign) -> dict[str, float | None]:
        raise NotImplementedError("Step 5")

    def emit_sequence(self, design: GateDesign) -> str:
        return design.sequence
