"""Stage 5 — plasmid construction."""

from engine.domain import (
    AssemblyStandard,
    CircuitCandidate,
    DesiredOutcome,
    PlasmidDesign,
    Segment,
)
from engine.tools.codons import CodonOptimizer
from engine.tools.motifs import MotifScreener


class PlasmidBuilder:
    """Lay the winning circuit's parts onto a backbone.

    Promoters, terminators, effector domains and the output gene; check
    assembly-standard compliance; export an orderable sequence.
    """

    def __init__(
        self,
        screener: MotifScreener,
        codons: CodonOptimizer,
        standard: AssemblyStandard = AssemblyStandard.RFC10,
        backbone: tuple[Segment, ...] = (),
    ) -> None:
        self.screener = screener
        self.codons = codons
        self.standard = standard
        self.backbone = backbone

    def build(self, circuit: CircuitCandidate, outcome: DesiredOutcome) -> PlasmidDesign:
        """Assemble and check.

        Step 5: order the segments — promoter, switch, payload, terminator, backbone —
        substitute the payload for `outcome`, screen the assembled sequence for
        prohibited sites, and record any violations rather than silently repairing them.
        """
        raise NotImplementedError("Step 5")

    def payload_segment(self, outcome: DesiredOutcome) -> Segment:
        """The coding sequence for the chosen output.

        Every output is equivalent: a reporter and a selective marker are the same kind
        of construct with a different payload.
        """
        raise NotImplementedError("Step 5")
