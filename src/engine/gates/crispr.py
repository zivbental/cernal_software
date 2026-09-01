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
from engine.gates.tools.folding import FoldEngine


class CrisprGate(GateFamily):
    """Transcriptional control via a trigger-gated guide RNA.

    **The mechanism:** an sgRNA's spacer — the part that finds the DNA target — is
    sequestered inside a hairpin, so Cas cannot be guided anywhere. A trigger opens that
    hairpin (the same strand-displacement idea as a toehold, applied to a guide instead
    of a start codon), and the freed sgRNA directs Cas to a promoter. The map calls this
    an internally-blocked sgRNA hairpin, iSBH.

    **Why it is worth having** despite the extra machinery: the toehold and antisense
    families act on **translation** of a payload the construct carries. CRISPR acts on
    **transcription**, and can therefore regulate genes already in the genome — which is
    a different and larger class of application.

    **Eukaryotic only.** The pipeline map lists CRISPR under the eukaryotic track and not
    the prokaryotic one, which is why ``supported_hosts`` exists at all and why
    ``EngineCapabilities`` reports availability per host: the wizard must grey this out
    for *E. coli* rather than accept a submission that cannot be built.

    An unresolved design decision: the effector. dCas9 fused to an **activator** turns
    the target gene on; fused to a **repressor** it turns it off. That choice belongs in
    the plasmid layout and changes what the circuit means, so it needs a home in the run
    configuration before this family is implemented.

    Args:
        host: Must be yeast or human.
        folder: Shared ``FoldEngine``. The blocking hairpin and its opening are both
            structural predictions.
    """

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
        """External tools this family needs, checked before a run starts.

        Declaring them up front means a missing dependency fails immediately with a clear
        message, rather than part-way through an expensive run.
        """
        return [ToolRequirement(name="ViennaRNA", version="2.7")]

    def is_compatible(self, trigger_set: TriggerSet, constraints: Constraints) -> Compatibility:
        """Can this family build anything for this trigger set on this host?

        Checks the host first, because "CRISPR is not available in E. coli" is a
        different and more useful message than "not implemented yet" — the first tells
        the researcher to change organism, the second to wait.

        Returns:
            ``Compatibility.no(reason)`` in both cases while unimplemented, so the stage
            skips this family cleanly rather than raising.
        """
        if not self.supports(self.host):
            return Compatibility.no(f"CRISPR gates are not available in {self.host.value}.")
        return Compatibility.no("The CRISPR family is not implemented yet.")

    def generate_designs(
        self, trigger_set: TriggerSet, constraints: Constraints
    ) -> Iterator[GateDesign]:
        """Build a hairpin-blocked sgRNA the trigger unblocks.

        Args:
            trigger_set: One trigger.
            constraints: Length and motif limits.

        Yields:
            ``GateDesign`` per variant.

        Construction (Step 5):
            1. **Spacer.** The 20-nucleotide sequence matching the DNA target, next to a
               PAM. This is chosen from the *target gene*, not from the trigger — a
               distinction that trips people up, because every other family in this engine
               derives its sequence from the trigger.
            2. **Blocking hairpin.** A sequence pairing with the spacer so the guide
               cannot engage, with a toehold complementary to the trigger hanging off it.
            3. **Scaffold.** The constant Cas-binding region. Fixed, and **must not be
               disturbed** — folding the whole guide and finding the scaffold has changed
               shape means the design is dead regardless of how well the switching works.
            4. Vary the blocking length and toehold length, as with a toehold switch.

        Gotchas:
            * Validate the **scaffold** structure separately from the switching behaviour.
              A design that switches beautifully and misfolds the scaffold does nothing.
            * Off-target here has a second meaning the other families do not have: the
              spacer can guide Cas to unintended **genomic** sites. That is a search
              against the genome, not the transcriptome, and ``OffTargetScanner`` as
              specified does not do it. It needs its own treatment before this family
              ships.
        """
        raise NotImplementedError("Step 5")

    def evaluate_design(self, design: GateDesign) -> dict[str, float | None]:
        """Measure a guide design, on the same metric names as every other family.

        Step 5:
            * ``gate_folding_energy`` — the blocked guide's structure.
            * ``predicted_leakage`` — spacer accessibility while blocked. An exposed
              spacer means Cas is guided without any trigger.
            * ``dynamic_range`` — spacer accessibility unblocked over blocked.
            * ``trigger_accessibility`` — carried from stage 2.

        Note:
            The metric names are shared deliberately, so a CRISPR design and a toehold
            design can be ranked in one list. Where a name means something mechanically
            different — as ``predicted_leakage`` does here — the report must say so, since
            the column header cannot.
        """
        raise NotImplementedError("Step 5")

    def emit_sequence(self, design: GateDesign) -> str:
        """The synthesis-ready sequence.

        A method rather than a field read, because a family may need to append a linker
        or terminator that is not part of the switch proper.
        """
        return design.sequence
