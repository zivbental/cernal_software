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
from engine.tools.codons import CodonOptimizer
from engine.tools.folding import FoldEngine
from engine.tools.translation import TranslationScorer


class ToeholdGate(GateFamily):
    """Single-input toehold switch.

    Closed in the OFF state; the trigger binds the exposed toehold and opens the stem,
    freeing the RBS or Kozak region so translation can start.
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
        # every caller shares one instance (docs/engine-design.md §5a).
        self.host = host
        self.folder = folder
        self.translation = translation
        self.codons = codons

    def required_tools(self) -> list[ToolRequirement]:
        return [ToolRequirement(name="ViennaRNA", version="2.7")]

    def is_compatible(self, trigger_set: TriggerSet, constraints: Constraints) -> Compatibility:
        """Reject unsupported arities and triggers that separate too weakly.

        Step 5: check `arity <= max_inputs`, the host is supported, and each trigger
        clears `constraints.min_separation`.
        """
        raise NotImplementedError("Step 5")

    def generate_designs(
        self, trigger_set: TriggerSet, constraints: Constraints
    ) -> Iterator[GateDesign]:
        """Build switch sequences for this trigger set.

        Step 5: construct the loop and stem around the trigger's reverse complement,
        insert the RBS (prokaryotic) or Kozak (eukaryotic) region and the start codon,
        and vary toehold length across `toehold_lengths` so the evaluator has real
        alternatives to choose between.
        """
        raise NotImplementedError("Step 5")

    def evaluate_design(self, design: GateDesign) -> dict[str, float | None]:
        """Measure a design, returning raw values keyed by the metric names in
        ``engine.scoring.profiles``.

        Step 5: fold the switch with and without its trigger, derive activation and
        leakage proxies from the energy difference, and take accessibility from the
        unpaired probability across the toehold region.
        """
        raise NotImplementedError("Step 5")

    def emit_sequence(self, design: GateDesign) -> str:
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
        """Step 5: build a switch that only opens when both triggers are present —
        typically a serial stem where the first trigger exposes the second toehold."""
        raise NotImplementedError("Step 5")
