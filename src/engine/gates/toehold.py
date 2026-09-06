"""Toehold switches — single input, and two-input AND.

**``ToeholdAndGate`` is a stub.** Its ``generate_designs`` raises ``NotImplementedError``
and is deliberately not touched here — the serial-stem AND construction is separate work
(docs/ROADMAP.md E4 note on ``ToeholdAndGate`` bodies). ``ToeholdGate``'s methods below are
written generically against ``self.max_inputs`` / ``self.kind`` / ``self.host`` precisely so
``ToeholdAndGate`` can keep inheriting ``is_compatible`` unmodified once it exists for real,
the same way it already inherits ``emit_sequence``.

Reference: design map 12, and the pipeline map's Switches Design stage.
"""

import math
from collections.abc import Iterator
from typing import ClassVar

from engine import sequences as sq
from engine.domain import (
    Compatibility,
    Constraints,
    GateDesign,
    GateKind,
    Host,
    ToolRequirement,
    Track,
    TriggerSet,
)
from engine.gates.base import GateFamily
from engine.gates.tools.binding import hybridization_energy
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

    **Provenance and simplifications**, in the same spirit as ``AntisenseNotGate``'s
    docstring — this is an engine-native construction of the mechanism described above
    and in ``modalities.md`` §C1 / Green et al. 2014, not a port of an external run:

    * Unlike ``AntisenseNotGate``, this gate takes **no payload argument**. The switch's
      own hairpin does not need to know the downstream gene's sequence — only that
      whatever follows starts translating from the ``AUG`` this gate places at the very
      end of its emitted sequence. A caller downstream (``PlasmidBuilder``) fuses the
      real payload after it.
    * The descending stem is built as the reverse complement of the ascending stem, then
      its **last 3 nt are forced to read ``AUG``** (Green et al.'s own design: the start
      codon is placed at a fixed position even where that costs a mismatch or two against
      perfect stem pairing, rather than searched for). This gate does not run
      ``CodonOptimizer.variants`` to hunt for an AUG-compatible stem instead — that search
      is exactly what ``codons`` is held for and is not invoked here (S8 is still a stub;
      see ``docs/ROADMAP.md`` Q4/Q5).
    * ``predicted_success_rate``'s ΔG sigmoid reuses ``AntisenseNotGate``'s placeholder
      reference/steepness (``_DG_REFERENCE_KCAL`` / ``_DG_STEEPNESS``) rather than a
      toehold-specific calibration, which does not exist yet either. Both families use the
      same shape for the same reason: a monotonic 0-1 squash of ΔG_bind with no real data
      to fit it to. Revisit together once wet-lab ON/OFF data exists for either mechanism.
    * ``translation`` (``TranslationScorer``) is accepted, per the fixed constructor
      signature, but not called: every one of its methods is still
      ``NotImplementedError`` (S9, ``docs/engine.md`` §9). Calling it would only convert a
      documented gap into a crash. ``translation_score`` is therefore not one of the keys
      ``evaluate_design`` returns — consistent with "return ``None`` /omit rather than a
      sentinel" for a metric that cannot yet be computed.

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
    version = "0.1.0"
    kind = GateKind.TOEHOLD
    label = "Toehold Riboswitch"
    description = "Translational control · pre-mRNA"
    supported_hosts: ClassVar[frozenset[Host]] = frozenset({Host.ECOLI, Host.YEAST, Host.HUMAN})
    max_inputs = 1
    available = True

    #: Toehold lengths to explore per trigger. Widening this multiplies the search space.
    toehold_lengths: ClassVar[tuple[int, ...]] = (12, 15, 18)

    #: Minimum nucleotides left for the stem once the toehold is peeled off the binding
    #: region. Below this there is no real duplex left to hold the AUG and resist opening
    #: on its own — the design would be all toehold and no hairpin.
    MIN_STEM_LENGTH: ClassVar[int] = 6

    #: E. coli Shine-Dalgarno consensus, sitting in the loop where it stays accessible in
    #: both OFF and ON. Matches ``AntisenseNotGate.RBS_PROKARYOTIC`` — same conserved
    #: element, same organism, no reason for the two families to disagree about it.
    RBS_PROKARYOTIC: ClassVar[str] = "AGGAGGA"

    #: Kozak context for the eukaryotic track. Matches ``AntisenseNotGate.KOZAK_EUKARYOTIC``.
    KOZAK_EUKARYOTIC: ClassVar[str] = "GCCACC"

    #: Binding-energy sigmoid. See the class docstring's provenance note: shared,
    #: unvalidated placeholder with ``AntisenseNotGate``, not a toehold-specific fit.
    _DG_REFERENCE_KCAL: ClassVar[float] = -15.0
    _DG_STEEPNESS: ClassVar[float] = 2.0

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

    def _loop_element(self) -> str:
        """The conserved translation-initiation element sitting in the loop.

        Never engineered, and identical in role to ``AntisenseNotGate._loop_element`` —
        reachable in the loop regardless of which state the switch is in, unlike the
        stem either side of it.
        """
        if self.host.track is Track.PROKARYOTIC:
            return self.RBS_PROKARYOTIC
        return self.KOZAK_EUKARYOTIC

    def required_tools(self) -> list[ToolRequirement]:
        """External tools this family needs, checked before a run starts.

        Declaring them up front means a missing dependency fails immediately with a clear
        message, rather than part-way through an expensive run.
        """
        return [ToolRequirement(name="ViennaRNA", version="2.7")]

    def is_compatible(self, trigger_set: TriggerSet, constraints: Constraints) -> Compatibility:
        """Can this family build anything for this trigger set?

        **Cheap checks only** — nothing here folds. A toehold switch opens when its
        trigger is *present*, so every input must be an activator (no repressors: this
        gate has no inverting mechanism, unlike ``AntisenseNotGate``), and there must be
        exactly ``self.max_inputs`` of them — read generically rather than hardcoded so
        ``ToeholdAndGate`` (``max_inputs = 2``) keeps this check correct by inheritance.

        ``constraints.min_separation`` (a gene's log2 fold change) is not checked here —
        ``TriggerCandidate`` does not carry that field; separation is already enforced
        upstream, at the stage that produced the trigger, not re-derivable from what
        reaches a gate family.
        """
        if trigger_set.repressors or len(trigger_set.activators) != self.max_inputs:
            return Compatibility.no(
                f"This gate takes exactly {self.max_inputs} input(s), and every one of "
                "them must be an activator — this chemistry has no inverting mechanism, "
                f"so a trigger that must be absent cannot drive it. Got "
                f"{len(trigger_set.activators)} activator(s) and "
                f"{len(trigger_set.repressors)} repressor(s)."
            )
        if self.host not in self.supported_hosts:
            return Compatibility.no(f"Toehold switches are not offered for {self.host.value}.")

        loop = self._loop_element()
        min_footprint = min(self.toehold_lengths) + self.MIN_STEM_LENGTH
        for trigger in trigger_set.activators:
            if trigger.length < min_footprint:
                return Compatibility.no(
                    f"The trigger is {trigger.length} nt, too short to build a toehold "
                    f"switch — this gate needs at least {min_footprint} nt to fit the "
                    "shortest toehold plus a real stem."
                )
            # Switch length is toehold + 2*stem + loop, and stem = trigger_length -
            # toehold_length — the stem appears twice (ascending and descending arms are
            # separate stretches of sequence, not two views of one), so widening the
            # toehold *shrinks* the switch: 2*trigger_length - toehold_length + loop_length.
            # The largest toehold_length gives the smallest switch, so that is the cheap,
            # optimistic bound worth checking here — generate_designs still checks every
            # variant against the real limit; this only rejects the clearly hopeless case
            # where even that best case cannot fit.
            tightest_switch_length = 2 * trigger.length - max(self.toehold_lengths) + len(loop)
            if tightest_switch_length > constraints.max_switch_length:
                return Compatibility.no(
                    f"The trigger is {trigger.length} nt; even the smallest toehold "
                    f"switch built from it ({tightest_switch_length} nt) would exceed "
                    f"the {constraints.max_switch_length} nt switch-length limit."
                )
        return Compatibility.yes()

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
        trigger = trigger_set.activators[0]
        binding_region = sq.reverse_complement(trigger.sequence)
        loop = self._loop_element()
        design_index = 0

        for toehold_length in self.toehold_lengths:
            stem_length = len(binding_region) - toehold_length
            if stem_length < self.MIN_STEM_LENGTH:
                continue

            toehold_arm = binding_region[:toehold_length]
            stem_top = binding_region[toehold_length:]
            # Descending stem: complementary to stem_top, so the two form the OFF-state
            # hairpin — except its last 3 nt, forced to the start codon regardless of what
            # perfect complementarity would have put there (Green et al.'s own design; see
            # the class docstring's provenance note).
            stem_bottom = sq.reverse_complement(stem_top)[:-3] + sq.START_CODON

            switch = toehold_arm + stem_top + loop + stem_bottom
            if len(switch) > constraints.max_switch_length:
                continue

            design_index += 1
            yield GateDesign(
                design_id=f"toehold-{trigger.trigger_id}-{design_index:04d}",
                gate_kind=self.kind,
                host=self.host,
                trigger_set=trigger_set,
                sequence=switch,
                architecture={
                    "toehold_length": toehold_length,
                    "stem_length": stem_length,
                    "loop_length": len(loop),
                    "loop_element": loop,
                    "track": self.host.track.value,
                },
            )

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
        architecture = design.architecture
        toehold_length = architecture["toehold_length"]
        stem_length = architecture["stem_length"]
        loop_length = architecture["loop_length"]

        loop_start = toehold_length + stem_length
        loop_end = loop_start + loop_length
        aug_start = loop_end + stem_length - 3
        initiation_start, initiation_end = loop_start, aug_start + 3

        trigger = design.trigger_set.activators[0]
        switch = design.sequence

        off_matrix = self.folder.base_pair_probabilities(switch)
        off_accessibility = _mean_unpaired(off_matrix, initiation_start, initiation_end)

        on_matrix = self.folder.base_pair_probabilities(f"{switch}&{trigger.sequence}")
        on_accessibility = _mean_unpaired(on_matrix, initiation_start, initiation_end)
        open_run = _longest_open_run(on_matrix, initiation_start, initiation_end)

        gate_folding_energy = self.folder.mfe(switch).energy

        binding_dg = hybridization_energy(switch, trigger.sequence, self.folder)
        predicted_success_rate = self._binding_energy_factor(binding_dg)

        # Opposite of AntisenseNotGate's leakage/dynamic_range: here the trigger's ABSENCE
        # is the OFF state, so leakage is the initiation region's residual openness alone,
        # and dynamic_range is ON over that (docs/ROADMAP.md line 321's "opposite
        # biological event between toehold and antisense", same metric names).
        predicted_leakage = off_accessibility
        dynamic_range = on_accessibility / max(predicted_leakage, 1e-3)

        return {
            "gate_folding_energy": gate_folding_energy,
            "predicted_leakage": predicted_leakage,
            "dynamic_range": dynamic_range,
            "trigger_accessibility": trigger.accessibility,
            "predicted_success_rate": predicted_success_rate,
            "gc_content": sq.gc_content(switch),
            "initiation_open_run_nt": float(open_run),
        }

    def _binding_energy_factor(self, binding_dg: float) -> float:
        """Sigmoid mapping ΔG_bind (kcal/mol, more negative is stronger) onto 0-1.

        Shared, unvalidated placeholder with ``AntisenseNotGate._binding_energy_factor``
        — see the class docstring's provenance note.
        """
        x = (binding_dg - self._DG_REFERENCE_KCAL) / self._DG_STEEPNESS
        x = max(-50.0, min(50.0, x))  # clamp: math.exp overflows well before this
        return 1.0 / (1.0 + math.exp(x))

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


def _mean_unpaired(matrix: list[list[float]], start: int, end: int) -> float:
    """Mean P(unpaired) over ``[start, end)`` from a ``base_pair_probabilities`` matrix.

    Identical in shape to ``antisense._mean_unpaired`` — see that module for the full
    rationale (a dimer matrix's row sum already covers pairing to either strand).
    """
    n = len(matrix)
    end = min(end, n)
    if end <= start:
        return 0.0
    unpaired = [max(0.0, 1.0 - sum(matrix[i])) for i in range(start, end)]
    return sum(unpaired) / len(unpaired)


def _longest_open_run(
    matrix: list[list[float]], start: int, end: int, threshold: float = 0.5
) -> int:
    """Longest contiguous run of positions unpaired at ``threshold`` or above in ``[start, end)``.

    Identical in shape to ``antisense._longest_open_run`` — mean openness treats one open
    base between two paired ones the same as a long open stretch; a ribosome footprint
    needs the latter.
    """
    n = len(matrix)
    end = min(end, n)
    best = current = 0
    for i in range(start, end):
        unpaired = max(0.0, 1.0 - sum(matrix[i]))
        if unpaired >= threshold:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best
