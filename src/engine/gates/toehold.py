"""Toehold switch gate family.

**Stub.** Signatures and structure are final; the scientific bodies land in Step 5
(docs/software-design.md §13). Each method documents what it must do so that filling it
in does not require re-deriving the design.

Reference: design map 12, "Toehold Gate" and "AND-Toehold Gate".
"""

from collections.abc import Iterable

from engine.contract import ArtifactRef
from engine.gates.base import (
    Compatibility,
    Constraints,
    GateDesign,
    GateFamily,
    ToolRequirement,
    TriggerSet,
)


class ToeholdGate(GateFamily):
    """Single-input and AND toehold switches."""

    name = "toehold"
    version = "0.1.0-stub"
    label = "Toehold Riboswitch"
    description = "Translational control · pre-mRNA"
    available = True

    def required_tools(self) -> list[ToolRequirement]:
        # Step 5: ViennaRNA (or equivalent) for MFE and accessibility prediction.
        return [ToolRequirement(name="ViennaRNA", version="2.6")]

    def is_compatible(self, trigger_set: TriggerSet, constraints: Constraints) -> Compatibility:
        """Reject unsupported arities and triggers that separate too weakly.

        Cheap structural checks only — expensive evaluation happens later, and only for
        designs that survive this gate.
        """
        raise NotImplementedError("ToeholdGate.is_compatible lands in Step 5")

    def generate_designs(
        self, trigger_set: TriggerSet, constraints: Constraints
    ) -> Iterable[GateDesign]:
        """Build switch sequences for the trigger set.

        Step 5: construct the loop and stem around each trigger's reverse complement,
        insert the RBS and start codon, and vary the toehold length across a small
        window to give the evaluator real alternatives to choose between.
        """
        raise NotImplementedError("ToeholdGate.generate_designs lands in Step 5")

    def evaluate_design(self, design: GateDesign) -> dict[str, float | None]:
        """Measure a design, returning raw values keyed by the metric names in
        ``engine.scoring.profiles.DEFAULT_V1``.

        Step 5: fold the switch with and without its trigger, derive activation and
        leakage proxies from the energy difference, and compute accessibility from the
        unpaired probability across the toehold region.
        """
        raise NotImplementedError("ToeholdGate.evaluate_design lands in Step 5")

    def emit_sequence(self, design: GateDesign) -> str:
        return design.switch_sequence

    def emit_artifacts(self, design: GateDesign, output_dir: str) -> list[ArtifactRef]:
        """Step 5: write the dot-bracket structure and a per-design summary."""
        raise NotImplementedError("ToeholdGate.emit_artifacts lands in Step 5")
