"""Toehold switches — single input, and two-input AND.

**Stubs.** Signatures and structure are final; the bodies land in Step 5. Each docstring
records what the method owes its caller, so filling it in is a scientific problem rather
than an architectural one.

Reference: design map 12, and the pipeline map's Switches Design stage.
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
from engine.gates.tools.codons import CodonOptimizer
from engine.gates.tools.folding import FoldEngine
from engine.gates.tools.translation import TranslationScorer


class ToeholdGate(GateFamily):
    """Single-input toehold switch.

    **The mechanism, because every method below only makes sense against it:**

    A toehold switch is an mRNA that will not translate itself until told to. It folds
    into a hairpin. The ribosome binding site sits in the **loop** — reachable — while
    the **start codon** is buried in the **stem**, so the ribosome can bind but cannot
    start. Hanging off the 5' end is a single-stranded **toehold**, complementary to the
    trigger.

    When the trigger appears, it pairs with the toehold and then unzips the stem by
    branch migration. The start codon is freed, translation begins, and the payload
    downstream is expressed.

    So a good design is one where:

    * the OFF hairpin is **stable enough** that nothing translates without the trigger
      (low leakage), and
    * trigger binding is **more favourable still**, so the stem actually opens (high
      dynamic range).

    Those two pull against each other, which is why this is a search rather than a
    formula: a stem stable enough to be truly dark is often too stable to open.

    Args:
        host: Decides RBS-in-loop (prokaryotic) versus Kozak (eukaryotic). Held as a
            parameter rather than a subclass until the method bodies actually diverge
            (docs/engine.md §2.4).
        folder: Shared ``FoldEngine``. Never constructed here — the cache only helps if
            everyone shares one instance.
        translation: Shared ``TranslationScorer``, for initiation strength.
        codons: Shared ``CodonOptimizer``, for linker and payload rewriting.

    Reference: Green et al., "Toehold switches: de-novo-designed regulators of gene
    expression" (2014), and the pipeline map's Switches Design stage.
    """

    name = "toehold"
    version = "0.1.0-stub"
    kind = GateKind.TOEHOLD
    label = "Toehold Riboswitch"
    description = "Translational control · pre-mRNA"
    supported_hosts: ClassVar[frozenset[Host]] = frozenset({Host.ECOLI, Host.YEAST, Host.HUMAN})
    max_inputs = 1
    available = True

    #: Toehold lengths to explore per trigger. Widening this multiplies the search space.
    toehold_lengths: ClassVar[tuple[int, ...]] = (12, 15, 18)

    def __init__(
        self,
        host: Host,
        folder: FoldEngine,
        translation: TranslationScorer,
        codons: CodonOptimizer,
    ) -> None:
        # Tools are handed in, never constructed here: FoldEngine's cache only helps if
        # every caller shares one instance (docs/engine.md §2.4).
        self.host = host
        self.folder = folder
        self.translation = translation
        self.codons = codons

    def required_tools(self) -> list[ToolRequirement]:
        """External tools this family needs, checked before a run starts.

        Declaring them up front means a missing dependency fails immediately with a clear
        message, rather than part-way through an expensive run.
        """
        return [ToolRequirement(name="ViennaRNA", version="2.7")]

    def is_compatible(self, trigger_set: TriggerSet, constraints: Constraints) -> Compatibility:
        """Can this family build anything for this trigger set?

        **Cheap checks only.** This runs for every trigger set against every family, and
        its whole purpose is to avoid the expensive work in ``generate_designs``. Nothing
        here should fold.

        Args:
            trigger_set: The proposed inputs.
            constraints: The researcher's limits.

        Returns:
            ``Compatibility.yes()``, or ``Compatibility.no(reason)``. **The reason is
            shown to the researcher**, so write it for them: "this gate takes one input,
            two were given", not "arity mismatch".

        What to check (Step 5):
            * ``trigger_set.arity <= self.max_inputs``.
            * ``self.host in self.supported_hosts``.
            * Each trigger clears ``constraints.min_separation`` — a trigger that barely
              differs between states cannot drive a switch however well it folds.
            * Trigger length is within the window this chemistry can build a toehold
              against. Far too short and there is nothing to nucleate on; far too long and
              the stem cannot accommodate it.
        """
        raise NotImplementedError("Step 5")

    def generate_designs(
        self, trigger_set: TriggerSet, constraints: Constraints
    ) -> Iterator[GateDesign]:
        """Build candidate switches for one trigger set.

        Args:
            trigger_set: Its single activator supplies the sequence the toehold must
                recognise.
            constraints: ``max_switch_length`` caps the construct.

        Yields:
            ``GateDesign`` per variant, with ``sequence``, the intended ``dot_bracket``,
            and the architecture parameters recorded in ``architecture`` so a design can
            be traced back to how it was built.

            **Yields rather than returns.** Three toehold lengths across thousands of
            trigger sets is tens of thousands of designs, and the validator will discard
            most of them.

        Construction (Step 5):
            1. **Binding region** — ``sequences.reverse_complement(trigger.sequence)``.
               This is what the trigger pairs with, and it becomes the toehold plus part
               of the stem.
            2. **Split it.** The first ``toehold_len`` nucleotides stay single-stranded
               as the toehold; the rest forms the ascending side of the stem.
            3. **Loop.** Insert the RBS (prokaryotic) or leave the Kozak context
               (eukaryotic) in the loop, where it is accessible in the OFF state.
            4. **Descending stem.** Complementary to the ascending side, and containing
               the start codon so it is sequestered until the stem opens.
            5. **Linker.** In frame, joining the switch to the payload. Keep it low in
               structure and free of stop codons; ``codons`` can rewrite it if it
               interferes.
            6. **Target structure.** Emit the dot-bracket the design is *meant* to fold
               into. The validator compares against it, so a design without one cannot be
               checked.

            Vary ``toehold_lengths`` and yield one design per length. Widening that tuple
            multiplies the whole search space — it is the cheapest knob for trading
            runtime against quality.

        Note:
            Two designs from the same trigger differ only in toehold length, so they share
            most of their sequence. That is precisely why ``FoldEngine`` caches: the
            validator will fold overlapping sequences repeatedly.
        """
        raise NotImplementedError("Step 5")

    def evaluate_design(self, design: GateDesign) -> dict[str, float | None]:
        """Measure one design.

        Args:
            design: A generated switch.

        Returns:
            **Raw** values keyed by the metric names in ``engine.scoring.profiles`` —
            ``gate_folding_energy``, ``predicted_leakage``, ``dynamic_range``,
            ``trigger_accessibility``, ``gc_content``, and so on. Return ``None`` for a
            metric that could not be computed rather than a sentinel like ``-1``; the
            scoring layer handles missing values explicitly, and a sentinel silently
            becomes a real number.

            **Do not normalise, weight or filter here.** That belongs to
            ``engine.scoring``, and a family that scored its own designs could not be
            compared against another family — the central problem design map 12
            identifies.

        What to compute (Step 5):
            * ``mfe_off`` — ``folder.mfe(switch)``. The OFF hairpin. Should be strongly
              negative.
            * ``mfe_on`` — fold the switch with the trigger present. The stem should be
              open.
            * ``gate_folding_energy`` — ``mfe_off``, the metric the profile already
              declares.
            * ``predicted_leakage`` — a proxy for OFF-state translation. The accessible
              fraction of the start codon in the OFF ensemble is the natural measure:
              base-pair probabilities from ``folder``, read at the AUG. A start codon
              never quite sequestered is a leaky switch.
            * ``dynamic_range`` — ON over OFF. Derived from the difference between the two
              accessibilities, not the two energies; energy difference is not linear in
              expression.
            * ``trigger_accessibility`` — already measured in stage 2 and carried on the
              trigger. Read it, do not recompute it, or the two disagree.
            * ``translation_score`` — ``self.translation.score(...)`` at the start codon.
            * ``binding_site_off_target`` — supplied by the validator; do not re-scan.

        Gotcha:
            Fold the ON state as a **dimer** (``cofold`` with the ``&`` separator), not as
            a concatenated single strand. Concatenation gives a plausible-looking number
            that means nothing.
        """
        raise NotImplementedError("Step 5")

    def emit_sequence(self, design: GateDesign) -> str:
        """The synthesis-ready sequence.

        A method rather than a field read, because a family may need to append a linker
        or terminator that is not part of the switch proper.
        """
        return design.sequence


class ToeholdAndGate(ToeholdGate):
    """Two-input AND toehold.

    Inherits from ToeholdGate rather than GateFamily because an AND toehold *is* a
    toehold — same chemistry, more inputs.

    Both triggers may come from the same gene: the pipeline map is explicit that "2
    inputs can be of the same gene or trigger", so nothing here may deduplicate.
    """

    name = "toehold_and"
    version = "0.1.0-stub"
    kind = GateKind.TOEHOLD_AND
    label = "AND Toehold"
    description = "Two-input translational AND"
    max_inputs = 2

    def generate_designs(
        self, trigger_set: TriggerSet, constraints: Constraints
    ) -> Iterator[GateDesign]:
        """Build a switch that opens only when **both** triggers are present.

        Args:
            trigger_set: Exactly two activators. They may come from the same gene.
            constraints: As for the single-input case.

        Yields:
            ``GateDesign`` per architecture variant.

        Construction (Step 5):
            The usual approach is a **serial** stem: the first trigger opens an outer
            hairpin, which exposes the toehold for the second, which opens the inner
            hairpin holding the start codon. Either trigger alone leaves the construct
            closed, which is the AND.

            Two things to get right, and both are easy to miss:

            * **Order matters.** Trigger A outer with B inner is a different construct
              from the reverse, and they will not perform the same. Generate both and let
              scoring decide.
            * **The intermediate state is real.** With only the first trigger present the
              switch sits half-open. If the start codon is already accessible there, the
              gate is an OR wearing an AND's shape — and it will pass every check that
              only looks at the fully-open and fully-closed states. **Evaluate the
              single-trigger states explicitly**, and treat leakage in them as
              disqualifying.

        Note:
            Both triggers may come from one gene. Nothing here may deduplicate by
            ``gene_id`` — the pipeline map calls this out explicitly.
        """
        raise NotImplementedError("Step 5")
