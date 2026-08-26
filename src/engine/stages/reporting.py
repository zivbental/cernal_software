"""Stage 6 — the compiler's output.

S14. Assembles the evidence a user needs in order to decide whether to order a plasmid.
"""

from engine.contract import ArtifactRef
from engine.domain import CircuitCandidate, GateDesign, PlasmidDesign


class StructureRenderer:
    """Structure and circuit figures."""

    def render_structure(self, design: GateDesign, output_dir: str) -> ArtifactRef:
        """A secondary-structure diagram from the dot-bracket notation."""
        raise NotImplementedError("Step 5")

    def render_circuit(self, circuit: CircuitCandidate, output_dir: str) -> ArtifactRef:
        """A logic diagram. The frontend draws its own from `logic_graph`; this is for
        the PDF, which has no JavaScript."""
        raise NotImplementedError("Step 5")


class ReportBuilder:
    """Designs, structures, confusion tables, separation margins, flags and caveats."""

    def __init__(self, renderer: StructureRenderer) -> None:
        self.renderer = renderer

    def build(
        self,
        circuits: list[CircuitCandidate],
        plasmids: list[PlasmidDesign],
        output_dir: str,
    ) -> list[ArtifactRef]:
        """Every artifact a run produces.

        Step 5: FASTA and GenBank per plasmid, a candidate table as CSV, structure and
        circuit figures, and the PDF report — read-me, abstract, top candidates with
        their confusion tables and flags, and the legal notes.
        """
        raise NotImplementedError("Step 5")
