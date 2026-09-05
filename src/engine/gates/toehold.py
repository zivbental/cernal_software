"""Toehold switches — single input, and two-input AND.

**Stubs.** Signatures and structure are final; the bodies land in Step 5. Each docstring
records what the method owes its caller, so filling it in is a scientific problem rather
than an architectural one.

**Provenance (``ToeholdGate``).** The domain architecture and dot-bracket construction
below are a port of a validated NUPACK-based generator built outside this repo
(``prokaryotic_switch_generator.py``): a 5' leader, a toehold, an ascending stem split by
a 3-nt bulge, a loop carrying the ribosome binding site (or Kozak context), a matching
descending stem, the start-codon bulge, and a linker — the Watson-Crick-derived
construction path of that generator, re-expressed against this repo's ``FoldEngine``
(ViennaRNA) and its ``GateFamily`` contract. The source generator's other half — running
NUPACK's ``tube_design`` to *solve* for the loop's undesigned nucleotides and to report
``ensemble_defect``/target-complex concentration as design-quality proxies — could not be
ported: this repo folds only through ``FoldEngine`` (ViennaRNA; see
``tests/engine/test_house_rules.py::test_only_the_two_folding_adapters_import_a_folding_library``),
and has no NUPACK sequence-design step. Where the two genuinely diverge, the divergence is
called out inline rather than silently guessed — see the port's open questions.

Reference: design map 12, and the pipeline map's Switches Design stage.
"""

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
    version = "0.1.0"
    kind = GateKind.TOEHOLD
    label = "Toehold Riboswitch"
    description = "Translational control · pre-mRNA"
    supported_hosts: ClassVar[frozenset[Host]] = frozenset({Host.ECOLI, Host.YEAST, Host.HUMAN})
    max_inputs = 1
    available = True

    #: Toehold lengths to explore per trigger. Widening this multiplies the search space.
    toehold_lengths: ClassVar[tuple[int, ...]] = (12, 15, 18)

    #: Unstructured 5' leader ahead of the toehold. Matches the source generator's default
    #: (``leader_sequence="GGG"``) — a fixed, unengineered spacer, not swept.
    LEADER_SEQUENCE: ClassVar[str] = "GGG"

    #: Ascending-stem length either side of the 3-nt bulge, matching the source
    #: generator's defaults (``a_domain_size``'s neighbours ``b_domain_size_pre_bulge`` /
    #: ``_post_bulge``). Fixed rather than swept: only ``toehold_lengths`` varies per the
    #: stub's own note that "two designs from the same trigger differ only in toehold
    #: length" — see the port's open questions for what this means when a trigger is
    #: longer than one sweep step needs.
    STEM_PRE_BULGE_LEN: ClassVar[int] = 9
    STEM_POST_BULGE_LEN: ClassVar[int] = 6

    #: Loop length; must be at least as long as the RBS/Kozak element it carries. Matches
    #: the source generator's default (``loop_size=11``, exactly the RBS length below, so
    #: the default leaves no undesigned filler at all).
    LOOP_LEN: ClassVar[int] = 11

    #: Prokaryotic ribosome binding site placed in the loop. Matches the source
    #: generator's ``RBS_SEQUENCE``.
    RBS_PROKARYOTIC: ClassVar[str] = "AACAGAGGAGA"

    #: Eukaryotic Kozak context placed in the loop instead of an RBS (``host.track``
    #: dispatches between the two, per this class's own docstring). The source generator
    #: is prokaryotic-only (it has no eukaryotic branch); this reuses
    #: ``AntisenseNotGate.KOZAK_EUKARYOTIC``'s value for the same conserved element rather
    #: than inventing a new one, but it is unvalidated for a *toehold* specifically — see
    #: the port's open questions.
    KOZAK_EUKARYOTIC: ClassVar[str] = "GCCACC"

    #: In-frame linker between the start codon and the payload (attached later, at
    #: plasmid assembly — see the port's open questions on why the payload itself is not
    #: part of ``GateDesign.sequence`` here). Matches the source generator's
    #: ``linker_pattern`` default.
    LINKER_SEQUENCE: ClassVar[str] = "AACCUGGCGGCAGCGCAAAAG"

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

        Note:
            ``constraints.min_separation`` is a minimum log2 fold change — a property of
            the *gene* (``SelectedGene.log2_fold_change``), not of a ``TriggerCandidate``,
            which carries no expression field at all. This check cannot be implemented
            against the type this method actually receives; see the port's open
            questions rather than a silent, made-up substitute.
        """
        if trigger_set.repressors or len(trigger_set.activators) != self.max_inputs:
            return Compatibility.no(
                f"This gate takes exactly {self.max_inputs} activating input(s) and no "
                f"repressors, but got {len(trigger_set.activators)} activator(s) and "
                f"{len(trigger_set.repressors)} repressor(s)."
            )
        if self.host not in self.supported_hosts:
            return Compatibility.no(f"{self.label} is not offered for {self.host.value}.")

        footprint = (
            min(self.toehold_lengths) + self.STEM_PRE_BULGE_LEN + 3 + self.STEM_POST_BULGE_LEN
        )
        too_short = [t.trigger_id for t in trigger_set.activators if t.length < footprint]
        if too_short:
            return Compatibility.no(
                f"Trigger(s) {', '.join(too_short)} are shorter than {footprint} nt — too "
                "short to supply a toehold and stem even at the shortest swept toehold "
                "length."
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

        Deviations from the source generator (see the port's open questions):
            * ``STEM_PRE_BULGE_LEN``/``STEM_POST_BULGE_LEN`` stay fixed at the source
              generator's defaults for every swept ``toehold_length``; only the toehold
              itself grows or shrinks. Any reverse-complemented trigger nucleotides beyond
              ``toehold_length + STEM_PRE_BULGE_LEN + 3 + STEM_POST_BULGE_LEN`` are simply
              unused for that variant, rather than the stem scaling to consume the whole
              binding region the way the source generator's single fixed-length trigger did.
            * The loop's undesigned filler (when ``LOOP_LEN`` exceeds the RBS/Kozak
              length — zero nucleotides at the class defaults) is a fixed, non-repeating
              placeholder, not solved by a sequence-design optimizer the way the source
              generator's NUPACK ``tube_design`` call would.
            * The construct stops at the linker. The source generator fused a specific
              downstream gene onto the same output string; ``ToeholdGate.__init__`` is
              given no payload (unlike ``AntisenseNotGate``, which takes one), and
              ``SegmentKind`` treats ``SWITCH`` and ``PAYLOAD`` as separate plasmid
              segments — so the payload is attached later, at plasmid assembly, not here.
        """
        trigger = trigger_set.activators[0]
        binding_region = sq.reverse_complement(trigger.sequence)
        loop = self._loop_element()

        for toehold_length in self.toehold_lengths:
            footprint = toehold_length + self.STEM_PRE_BULGE_LEN + 3 + self.STEM_POST_BULGE_LEN
            if footprint > len(binding_region):
                continue

            a_domain = binding_region[:toehold_length]
            pre_start = toehold_length
            b_pre = binding_region[pre_start : pre_start + self.STEM_PRE_BULGE_LEN]
            bulge_start = pre_start + self.STEM_PRE_BULGE_LEN
            b_bulge = binding_region[bulge_start : bulge_start + 3]
            post_start = bulge_start + 3
            b_post = binding_region[post_start : post_start + self.STEM_POST_BULGE_LEN]

            switch = (
                self.LEADER_SEQUENCE
                + a_domain
                + b_pre
                + b_bulge
                + b_post
                + loop
                + sq.reverse_complement(b_post)
                + sq.START_CODON
                + sq.reverse_complement(b_pre)
                + self.LINKER_SEQUENCE
            )
            if len(switch) > constraints.max_switch_length:
                continue

            aug_index = (
                len(self.LEADER_SEQUENCE)
                + toehold_length
                + self.STEM_PRE_BULGE_LEN
                + 3
                + self.STEM_POST_BULGE_LEN
                + len(loop)
                + self.STEM_POST_BULGE_LEN
            )
            dot_bracket = (
                "." * len(self.LEADER_SEQUENCE)
                + "." * toehold_length
                + "(" * self.STEM_PRE_BULGE_LEN
                + "." * 3
                + "(" * self.STEM_POST_BULGE_LEN
                + "." * len(loop)
                + ")" * self.STEM_POST_BULGE_LEN
                + "." * 3
                + ")" * self.STEM_PRE_BULGE_LEN
                + "." * len(self.LINKER_SEQUENCE)
            )

            yield GateDesign(
                design_id=f"toehold-{trigger.trigger_id}-{toehold_length}",
                gate_kind=self.kind,
                host=self.host,
                trigger_set=trigger_set,
                sequence=switch,
                dot_bracket=dot_bracket,
                architecture={
                    "toehold_length": toehold_length,
                    "stem_pre_bulge_len": self.STEM_PRE_BULGE_LEN,
                    "stem_post_bulge_len": self.STEM_POST_BULGE_LEN,
                    "loop_len": len(loop),
                    "leader_len": len(self.LEADER_SEQUENCE),
                    "linker_len": len(self.LINKER_SEQUENCE),
                    "aug_index": aug_index,
                    "track": self.host.track.value,
                },
            )

    def _loop_element(self) -> str:
        """The loop's translation-initiation element: RBS (prokaryotic) or Kozak
        (eukaryotic), padded with a fixed filler to ``LOOP_LEN`` if it is longer than the
        element itself.

        Not a scientific computation — the RBS/Kozak choice is dispatched on
        ``self.host.track`` per this class's own docstring, and the filler (when needed)
        is a placeholder, not a sequence-design result. See the port's open questions.
        """
        element = (
            self.RBS_PROKARYOTIC if self.host.track is Track.PROKARYOTIC else self.KOZAK_EUKARYOTIC
        )
        filler_len = max(0, self.LOOP_LEN - len(element))
        return _filler(filler_len) + element

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

        Emits (see the port's metrics audit for why not the others the docstring above
        names): ``gate_folding_energy``, ``predicted_leakage``, ``dynamic_range``,
        ``trigger_accessibility``, ``gc_content``. ``translation_score`` and
        ``binding_site_off_target`` are not legal ``evaluate_design`` keys (they are
        ``GateDesign`` fields filled elsewhere, not profile metrics) and are not computed
        here; ``self.translation`` (``TranslationScorer.score``) is not called because it
        still raises ``NotImplementedError`` — see the port's open questions for
        ``predicted_success_rate``, which is left unemitted for the same reason.
        """
        switch = design.sequence
        trigger = design.trigger_set.activators[0]
        aug_index = design.architecture["aug_index"]

        off_matrix = self.folder.base_pair_probabilities(switch)
        off_accessibility = _mean_unpaired(off_matrix, aug_index, aug_index + 3)

        on_matrix = self.folder.base_pair_probabilities(f"{switch}&{trigger.sequence}")
        on_accessibility = _mean_unpaired(on_matrix, aug_index, aug_index + 3)

        return {
            "gate_folding_energy": self.folder.mfe(switch).energy,
            "predicted_leakage": off_accessibility,
            "dynamic_range": on_accessibility / max(off_accessibility, 1e-3),
            "trigger_accessibility": trigger.accessibility,
            "gc_content": sq.gc_content(switch),
        }

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

    **Not ported.** ``generate_designs`` below is unchanged (still ``NotImplementedError``)
    — the source generator this file ports (see the module docstring) only builds
    single-input switches; it has no serial/two-hairpin construction to port. ``ToeholdGate``'s
    ``is_compatible`` is inherited unchanged and generalises correctly (it already reads
    ``self.max_inputs``), but ``evaluate_design`` is also inherited unchanged and only
    folds against a single activator (``trigger_set.activators[0]``) — a real two-input
    evaluation needs both triggers, and per this method's own docstring below, the two
    single-trigger intermediate states as well. Whoever implements this class's
    ``generate_designs`` should override ``evaluate_design`` too rather than rely on the
    inherited one. See the port's open questions.
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


#: A short, non-repeating unit — no base repeats, so no length of filler ever introduces
#: a homopolymer run regardless of ``ToeholdGate.LOOP_LEN``.
_FILLER_UNIT = "ACAG"


def _filler(length: int) -> str:
    """A fixed placeholder for the loop's undesigned nucleotides.

    The source generator (see this module's docstring) solves these positions with
    NUPACK's ``tube_design`` sequence optimizer; this port has no such step, so this is a
    deterministic, non-scientific stand-in — not a designed sequence. At the class
    defaults ``length`` is 0 (``LOOP_LEN`` exactly matches the RBS), so this only matters
    if ``LOOP_LEN`` is widened. See the port's open questions.
    """
    if length <= 0:
        return ""
    return (_FILLER_UNIT * (length // len(_FILLER_UNIT) + 1))[:length]


def _mean_unpaired(matrix: list[list[float]], start: int, end: int) -> float:
    """Mean P(unpaired) over ``[start, end)`` from a ``base_pair_probabilities`` matrix.

    P(unpaired) at position i is ``1 - sum(matrix[i])`` — the matrix is already symmetric
    and 0-indexed (``FoldEngine.base_pair_probabilities``'s contract), so this sums a
    position's pairing probability to *every* other position regardless of which strand
    it is on. For a dimer matrix that is exactly what "is the AUG still accessible with
    the trigger bound" needs. (Duplicated from the same helper in ``gates/antisense.py``
    rather than imported — see the port's open questions on promoting it to a shared
    tool.)
    """
    n = len(matrix)
    end = min(end, n)
    if end <= start:
        return 0.0
    unpaired = [max(0.0, 1.0 - sum(matrix[i])) for i in range(start, end)]
    return sum(unpaired) / len(unpaired)
