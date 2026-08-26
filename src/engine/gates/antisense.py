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
    """Post-transcriptional silencing. The pipeline's inverting element.

    **The mechanism:** an antisense RNA complementary to the payload's ribosome binding
    site and start region pairs with it and blocks translation. So expression is ON by
    default and switched OFF when the trigger appears — the opposite of a toehold, and
    the reason this family exists.

    That inversion is what makes ``NOT`` buildable, and therefore what lets a circuit use
    a **down-regulated** gene as an input. Without it, only UP genes are usable and half
    the differential-expression signal is wasted.

    Two ways to wire it, and the choice is the scientific team's:

    * the trigger transcript **is** the antisense, acting directly on the payload; or
    * the trigger drives expression of a separate antisense RNA.

    The first is simpler and needs no extra transcriptional unit; the second gives
    amplification. The design rules differ, so settle this before implementing.

    Args:
        host: Prokaryotic and eukaryotic silencing differ in efficiency and in what
            counts as sufficient complementarity.
        folder: Shared ``FoldEngine``. Both the antisense and its target must be
            accessible for the duplex to form.
        codons: Shared ``CodonOptimizer``. Extending a CDS with an antisense region must
            not change the protein, which is exactly what synonymous rewriting is for.
    """

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
        """External tools this family needs, checked before a run starts.

        Declaring them up front means a missing dependency fails immediately with a clear
        message, rather than part-way through an expensive run.
        """
        return [ToolRequirement(name="ViennaRNA", version="2.7")]

    def is_compatible(self, trigger_set: TriggerSet, constraints: Constraints) -> Compatibility:
        """Can this family invert this trigger set?

        Step 5: one input only; the trigger must be long enough to form a stable duplex
        with the target region (substantially longer than a toehold needs); and the
        trigger must be accessible, since a structured antisense will not pair.

        Returns:
            ``Compatibility.no(reason)`` while unimplemented, so the stage skips this
            family cleanly rather than raising.
        """
        return Compatibility.no("The antisense family is not implemented yet.")

    def generate_designs(
        self, trigger_set: TriggerSet, constraints: Constraints
    ) -> Iterator[GateDesign]:
        """Build an antisense element that silences the payload when the trigger is present.

        Args:
            trigger_set: One trigger, which becomes the silencing input.
            constraints: Limits on length and motifs.

        Yields:
            ``GateDesign`` per variant, varying the complementary region's length and
            offset.

        Construction (Step 5):
            1. **Choose the target region** on the payload — the RBS and start codon
               region, since blocking initiation is more reliable than blocking
               elongation.
            2. **Build the complement** to that region, sized so the duplex is stable at
               the working temperature but not so long that it forms secondary structure
               of its own.
            3. **Check accessibility on both sides.** A duplex needs both strands
               reachable. Use ``folder`` on the payload in its own context, not in
               isolation.
            4. **Rewrite if needed.** Where the antisense region overlaps coding
               sequence, ``codons.variants`` can adjust the pairing without changing the
               protein — this is the main reason ``CodonOptimizer`` is a dependency here.

        Gotcha:
            An antisense NOT is ON by default. That inverts the safety argument: a
            **failed** antisense gate expresses the payload rather than staying dark. For
            a reporter that is harmless; for an apoptosis inducer it is not, and the
            report must say so.
        """
        raise NotImplementedError("Step 5")

    def evaluate_design(self, design: GateDesign) -> dict[str, float | None]:
        """Measure a silencing design.

        Returns raw values on the same metric names as every other family, so the two can
        be ranked together (docs/engine-classes.md §4a).

        Step 5:
            * ``gate_folding_energy`` — the antisense element's own structure. A
              self-structured antisense cannot pair.
            * ``predicted_leakage`` — here it means **residual expression when the
              trigger IS present**, the inverse of a toehold's leakage. Same metric name,
              same direction (lower is better), opposite biological event. Note it in the
              report, or a reader will misinterpret the column.
            * ``dynamic_range`` — expression without the trigger over expression with it.
            * ``trigger_accessibility`` — carried from stage 2, not recomputed.
        """
        raise NotImplementedError("Step 5")

    def emit_sequence(self, design: GateDesign) -> str:
        """The synthesis-ready sequence.

        A method rather than a field read, because a family may need to append a linker
        or terminator that is not part of the switch proper.
        """
        return design.sequence
