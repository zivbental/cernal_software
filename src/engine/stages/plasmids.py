"""Stage 5 — plasmid construction.

Turns a winning circuit into something a synthesis company can actually make.

Everything before this was sequence design. This stage is **assembly**: laying the parts
onto a backbone in the right order with the right flanking elements, and checking the
result against an iGEM assembly standard. A circuit that cannot be ordered is not a
result.

The output is the first artefact a researcher would put money behind, so the compliance
check matters more than it looks. A single unnoticed restriction site turns a plasmid
order into a wasted month.
"""

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
    """Assembles a circuit onto a backbone and checks it can be built.

    Args:
        screener: Shared ``MotifScreener``. Must be configured with the same standard
            passed below, or the check and the claim disagree.
        codons: Shared ``CodonOptimizer``. Used to rewrite a payload whose opening codons
            disturb the switch, and to adapt the payload to the host.
        standard: The assembly standard to enforce. RFC10 forbids EcoRI, XbaI, SpeI,
            PstI and NotI inside a part; RFC1000 (Type IIS) forbids BsaI and SapI.
        backbone: Fixed segments every construct shares — origin of replication,
            selection marker for the plasmid itself, and so on. Distinct from the
            circuit's payload.
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
        """Lay out one circuit as an orderable construct.

        Args:
            circuit: A ranked circuit from stage 4, with its switch designs.
            outcome: What the circuit should express when it fires.

        Returns:
            ``PlasmidDesign`` with its segments, full sequence, and any standard
            violations. **Violations are recorded, not silently repaired** — a researcher
            needs to know the construct they are about to order has a problem, and
            quietly mutating their design is worse than reporting it.

        Assembly order (Step 5):
            promoter, then switch, then payload, then terminator, then backbone. Each is
            a ``Segment`` with its ``kind``, so the frontend's plasmid map can label and
            colour them, and lengths stay honest.

            * **Promoter** — constitutive. The switch does the regulating, not the
              promoter; a regulated promoter on top would confound the logic.
            * **Switch** — from ``circuit.designs``. For a multi-input circuit there are
              several, each needing its own promoter and terminator.
            * **Payload** — from ``payload_segment(outcome)``, in frame with the switch's
              start codon. This is the join most likely to go wrong.
            * **Terminator** — stops transcription. Without one, read-through into the
              next element quietly breaks the circuit.
            * **Backbone** — origin and plasmid selection marker.

        Then check:
            1. ``screener.violations`` over the **assembled** sequence. This is the step
               that catches sites formed *across a junction* — neither part contains
               EcoRI, and joining them creates one. Screening parts individually misses
               it entirely, and it is the classic assembly failure.
            2. Reading frame continuity from the switch's AUG through the payload.
            3. Total length against what synthesis vendors accept.

        On repair:
            When a violation lands inside a coding region, ``codons.variants`` can often
            remove it without changing the protein — worth attempting, and worth
            reporting that it happened. When it lands in a structural region, do not
            touch it: changing a stem to remove a restriction site silently breaks the
            switch that was validated in stage 3.
        """
        raise NotImplementedError("Step 5")

    def payload_segment(self, outcome: DesiredOutcome) -> Segment:
        """The coding sequence for the chosen output.

        Args:
            outcome: GFP, mCherry, Luciferase, antibiotic resistance, apoptosis inducer,
                or a custom sequence.

        Returns:
            A ``Segment`` of kind ``PAYLOAD``.

        Note:
            **Every output is equivalent.** A reporter and a selective marker are the same
            kind of construct with a different payload — there is no structural
            difference, and the earlier version of this engine emitted a separate
            ``marker`` segment which made markers look like second-class add-ons. They are
            not: when a marker is selected, it *is* the payload.

        Implementation (Step 5):
            Hold the standard coding sequences in a table, run each through
            ``codons.translation_score`` for the host, and use ``codons.variants`` when
            the opening codons interfere with the switch's stem. A custom sequence comes
            from ``params["payload"]["custom_sequence"]`` and must be validated like any
            other input — in frame, no internal stops, no forbidden motifs.
        """
        raise NotImplementedError("Step 5")
