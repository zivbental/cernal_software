"""Gate families that are designed but not yet implemented.

They are registered so that ``EngineCapabilities`` advertises them and the UI can show
them greyed out with an honest label, rather than the frontend hardcoding a list of
"coming soon" cards that nobody remembers to update when the science lands.

Each becomes a real module under ``engine/gates/`` in Step 5 or later.
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


class _PlannedFamily(GateFamily):
    """Shared body: every method refuses, because there is nothing behind it yet."""

    available = False

    def _unavailable(self) -> Compatibility:
        raise NotImplementedError(f"The {self.label} family is not implemented yet.")

    def required_tools(self) -> list[ToolRequirement]:
        return []

    def is_compatible(self, trigger_set: TriggerSet, constraints: Constraints) -> Compatibility:
        return Compatibility.no(f"{self.label} is not implemented yet.")

    def generate_designs(
        self, trigger_set: TriggerSet, constraints: Constraints
    ) -> Iterable[GateDesign]:
        return self._unavailable()

    def evaluate_design(self, design: GateDesign) -> dict[str, float | None]:
        return self._unavailable()

    def emit_sequence(self, design: GateDesign) -> str:
        return self._unavailable()

    def emit_artifacts(self, design: GateDesign, output_dir: str) -> list[ArtifactRef]:
        return self._unavailable()


class CrisprGate(_PlannedFamily):
    name = "crispr"
    version = "0.0.0-planned"
    label = "CRISPR-Cas sgRNA Gate"
    description = "Transcriptional control · iSBH"


class AntisenseGate(_PlannedFamily):
    name = "antisense"
    version = "0.0.0-planned"
    label = "Antisense Repression"
    description = "Post-transcriptional silencing"
