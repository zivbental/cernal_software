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

from bisect import bisect_right
from collections.abc import Iterator
from dataclasses import dataclass
from itertools import product
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
from engine.gates.tools.binding import can_pair, fixed_alignment_energy
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
    design_prefix = "toehold"
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
                design_id=f"{self.design_prefix}-{trigger.trigger_id}-{toehold_length}",
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
    # NOTE: `available` is still inherited as True from ToeholdGate while
    # `generate_designs` below raises, so a submission naming this family validates and
    # then fails part-way through a run. Re-declaring it False here is the documented fix,
    # but it unregisters the family and three tests in tests/engine/gates/test_toehold.py
    # assert it is registered, so the flip belongs with the commit that gives
    # `generate_designs` a body rather than to this one.

    #: Both stem arms span 18 nt (R1), so ``len_k2 = ARM_LEN - len_x``: every nucleotide
    #: the overlap takes is one fewer for trigger B to invade with. That is the trade the
    #: overlap length is chosen against.
    ARM_LEN: ClassVar[int] = 18

    #: Consecutive positions trigger B may be left unable to pair at before the stem is
    #: rejected. Three in a row is enough to stall branch migration.
    MAX_INVASION_STALL: ClassVar[int] = 2

    def secondary_stems(self, trigger_a: str, trigger_b: str, len_x: int) -> list["_SecondaryStem"]:
        """Every secondary stem worth folding, for one trigger pair and overlap length.

        Enumerates the per-position assignment of §5.2's three states, keeps what satisfies
        R6 and the invasion-stall cap, and returns the Pareto front over (lock, A-site,
        B-site). Letting each position choose independently explores ``3^n`` builds and
        strictly contains the two global strategies — anchoring every position to trigger A
        or every position to trigger B — as special cases; measured on real candidates,
        roughly half of the frontier is mixed, meaning neither global strategy can express
        it.

        The Pareto step is what makes the downstream folding affordable. The front grows
        roughly linearly in the number of conflicts while ``3^n`` grows exponentially —
        11, 29, 88 and 99 builds at n = 4, 6, 8 and 9 — so it reduces the work by three
        orders of magnitude without discarding anything a later stage might have preferred.
        Nothing is ranked here: a build is dropped only when another is at least as good on
        all three claims and better on one.

        Args:
            trigger_a: Trigger A, RNA uppercase, reading ``k1 · bulge · main_pre · xA · extA``.
            trigger_b: Trigger B, RNA uppercase, reading ``k2 · xB · r2``.
            len_x: Length of the perfect reverse-complementary overlap the pair shares.

        Returns:
            The non-dominated stems, in enumeration order. Empty if no assignment satisfies
            R6 — a real outcome for a pair whose extension fights its partner everywhere,
            and the caller's signal to move on rather than to relax the rule.
        """
        ext, k2 = _secondary_domains(trigger_a, trigger_b, len_x, self.ARM_LEN)
        x = trigger_a[self.ARM_LEN : self.ARM_LEN + len_x]
        conflicts = _arm_conflicts(ext, k2)

        stems: list[_SecondaryStem] = []
        objectives: list[tuple[float, float, float]] = []
        for combination in product(_ARM_STATES, repeat=len(conflicts)):
            states = dict(zip(conflicts, combination, strict=True))
            k2_star, secondary_z = _build_arms(ext, k2, states)
            if not _invasion_runs_ok(ext, k2, k2_star, self.MAX_INVASION_STALL):
                continue
            lock = fixed_alignment_energy(k2_star, secondary_z, self.folder)
            b_site = fixed_alignment_energy(k2, k2_star, self.folder)
            a_site = fixed_alignment_energy(
                x + ext, secondary_z + sq.reverse_complement(x), self.folder
            )
            if lock is None or b_site is None or a_site is None:
                continue  # unevaluable, not zero — see fixed_alignment_energy
            ddg_pref = lock - b_site
            if ddg_pref < 0.0:
                continue  # R6: the switch's own copy must be the weaker binder
            stems.append(
                _SecondaryStem(
                    k2_star=k2_star,
                    secondary_z=secondary_z,
                    states=combination,
                    ddg_pref=ddg_pref,
                    lock_energy=lock,
                    a_site_energy=a_site,
                    b_site_energy=b_site,
                )
            )
            objectives.append((lock, a_site, b_site))
        return [stems[i] for i in _pareto_front(objectives)]

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


class ProkaryoticToeholdGate(ToeholdGate):
    """Single-input toehold family for prokaryotic translation."""

    name = "prokaryotic_toehold"
    design_prefix = "prokaryotic_toehold"
    label = "Prokaryotic Toehold"
    description = "Prokaryotic single-input translational control"
    supported_hosts: ClassVar[frozenset[Host]] = frozenset({Host.ECOLI})


class ProkaryoticToeholdAndGate(ToeholdAndGate):
    """Two-input AND toehold family for prokaryotic translation."""

    name = "prokaryotic_toehold_and"
    design_prefix = "prokaryotic_toehold_and"
    label = "Prokaryotic AND Toehold"
    description = "Prokaryotic two-input translational AND"
    supported_hosts: ClassVar[frozenset[Host]] = frozenset({Host.ECOLI})


class EukaryoticToeholdGate(ToeholdGate):
    """Single-input toehold family for eukaryotic translation."""

    name = "eukaryotic_toehold"
    design_prefix = "eukaryotic_toehold"
    label = "Eukaryotic Toehold"
    description = "Eukaryotic single-input translational control"
    supported_hosts: ClassVar[frozenset[Host]] = frozenset({Host.YEAST, Host.HUMAN})


class EukaryoticToeholdAndGate(ToeholdAndGate):
    """Two-input AND toehold family for eukaryotic translation."""

    name = "eukaryotic_toehold_and"
    design_prefix = "eukaryotic_toehold_and"
    label = "Eukaryotic AND Toehold"
    description = "Eukaryotic two-input translational AND"
    supported_hosts: ClassVar[frozenset[Host]] = frozenset({Host.YEAST, Host.HUMAN})


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


# --- The AND gate's secondary (inhibitory) stem -------------------------------------
#
# The top half of that stem carries three claims that cannot all be met. Trigger B must
# invade the ascending arm, trigger A must nucleate on the descending arm, and the two
# arms must hold each other shut when either trigger arrives alone. Across the overlap
# `x` the three coincide and nothing is decided. Above it they do not, and at each
# disagreeing position exactly two of the three can be served. These helpers enumerate
# that choice rather than resolving it with a global rule, because which pair to serve is
# a different answer at different positions.

#: Per-position assignments worth making at a conflict. A fourth (serve neither trigger,
#: close the lock against A's base while B needs another) satisfies nothing and is
#: dominated, so it is never generated.
_ARM_STATES: tuple[str, ...] = ("both", "lockA", "lockB")


@dataclass(frozen=True, slots=True)
class _SecondaryStem:
    """One built secondary stem, with what the build costs on each of the three claims.

    Intra-module only: this never crosses a stage boundary, which is why it is not a
    record in ``engine.domain``.
    """

    k2_star: str
    secondary_z: str
    #: Assignment per conflict position, parallel to ``conflicts``.
    states: tuple[str, ...]
    #: ``dG(secondaryZ : k2*) - dG(k2 : k2*)``. R6 wants this ``>= 0``: free energies are
    #: negative, so positive means the switch's own copy is the *weaker* binder and
    #: trigger B can displace it. Computing it the other way round inverts the gate.
    ddg_pref: float
    lock_energy: float
    a_site_energy: float
    b_site_energy: float


def _secondary_domains(trigger_a: str, trigger_b: str, len_x: int, arm_len: int) -> tuple[str, str]:
    """Trigger A's extension past the overlap, and trigger B's invasion domain.

    Trigger A reads ``k1 · bulge · main_pre · xA · extA`` and trigger B reads
    ``k2 · xB · r2``, so both wanted domains are slices of sequences already in hand.
    This is the adapter between a chosen trigger pair and the stem builder; the builder's
    own two-transcript entry point is for a case this architecture does not use.
    """
    len_k2 = arm_len - len_x
    ext_start = arm_len + len_x
    return trigger_a[ext_start : ext_start + len_k2], trigger_b[:len_k2]


def _arm_conflicts(ext: str, k2: str) -> tuple[int, ...]:
    """Positions in ``k2*`` where trigger A's extension is not what trigger B needs."""
    wanted = sq.reverse_complement(k2)
    return tuple(p for p in range(len(ext)) if ext[p] != wanted[p])


def _build_arms(ext: str, k2: str, states: dict[int, str]) -> tuple[str, str]:
    """The two designed domains for one per-position assignment.

    ``k2_star[p]`` pairs with ``secondary_z[len_k2 - 1 - p]``, so the descending arm is
    written 3'→5' relative to the ascending one and both are returned 5'→3' as they sit
    on the switch.
    """
    wanted = sq.reverse_complement(k2)
    n = len(ext)
    k2_star = "".join(ext[p] if states.get(p) == "lockA" else wanted[p] for p in range(n))
    secondary_z = "".join(
        sq.reverse_complement(
            wanted[n - 1 - q] if states.get(n - 1 - q) == "lockB" else ext[n - 1 - q]
        )
        for q in range(n)
    )
    return k2_star, secondary_z


def _invasion_runs_ok(ext: str, k2: str, k2_star: str, max_run: int) -> bool:
    """Reject stems that hand trigger B a stretch it cannot migrate through.

    **The cap is on positions where B cannot pair at all**, not on positions the design
    flipped toward B. Where B gains a pair the incumbent lacks, its step is downhill; where
    it must break a lock pair and form nothing, the step is uphill, and a run of those is
    the barrier this rule exists to prevent. Capping the *flips* instead would be actively
    harmful: it forces the lock's mismatches to scatter, and scattered mismatches cost
    considerably more lock stability than clustered ones, because loop initiation is
    sub-linear in size.
    """
    n = len(ext)
    stalled = [p for p in _arm_conflicts(ext, k2) if not can_pair(k2_star[p], k2[n - 1 - p])]
    run = 1
    for i in range(1, len(stalled)):
        run = run + 1 if stalled[i] == stalled[i - 1] + 1 else 1
        if run > max_run:
            return False
    return True


def _pareto_front(points: list[tuple[float, float, float]]) -> list[int]:
    """Indices of the non-dominated points, all three objectives minimised.

    A staircase sweep rather than the obvious all-pairs scan. Sorting by the first
    objective means every point already seen is no worse on it, so domination collapses to
    a two-dimensional query, answered against a list kept sorted on the second objective
    with a strictly decreasing third. That is ``O(m log m)`` where all-pairs is ``O(m²)``
    — at the largest real stems (~1.9M builds) the difference is minutes against weeks.

    Exact ties are kept, all of them: identical objectives do not dominate each other, and
    two builds scoring alike here are still different sequences that fold differently.
    """
    groups: dict[tuple[float, float, float], list[int]] = {}
    for index, point in enumerate(points):
        groups.setdefault(point, []).append(index)

    staircase: list[tuple[float, float]] = []  # sorted by o1 ascending, o2 descending
    survivors: list[int] = []
    for o0, o1, o2 in sorted(groups):
        cut = bisect_right(staircase, (o1, float("inf")))
        if cut and staircase[cut - 1][1] <= o2:
            continue  # something already seen is at least as good on all three
        survivors.extend(groups[(o0, o1, o2)])
        drop = cut
        while drop < len(staircase) and staircase[drop][1] >= o2:
            drop += 1
        staircase[cut:drop] = [(o1, o2)]
    return sorted(survivors)
