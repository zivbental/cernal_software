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

import math
import re
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
from engine.gates.tools.binding import (
    alignment_pairs,
    can_pair,
    fixed_alignment_energy,
    longest_complementary_run,
)
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

    #: Trigger B's toehold: the one domain the architecture leaves permanently free, so
    #: it can be matched to B at no cost to the lock. Fixes trigger B's window at
    #: ``ARM_LEN + TOEHOLD_B_LEN`` = 50 nt whatever the overlap length.
    TOEHOLD_B_LEN: ClassVar[int] = 32

    #: Shortest overlap worth calling one. Below four contiguous nucleotides there is no
    #: nucleation site, which is also why it is the knockout criterion: a trigger left
    #: with no run this long can no longer start.
    MIN_OVERLAP: ClassVar[int] = 4

    #: Nucleotides required between the two trigger windows. Both triggers come off one
    #: transcript here, so that molecule carries the overlap and its complement together
    #: and can fold back to sequester both before either reaches the switch — worst in
    #: state 11, the one state that has to work. A 4-8 bp stem closed by a loop of a few
    #: hundred nucleotides is marginal rather than certain, which is why this is a
    #: selection criterion and not a disqualification.
    #:
    #: This belongs in ``Constraints`` and there is no field for it yet; it is a class
    #: constant rather than a literal buried in a method so that it is at least declared.
    #: It is **a nucleotide count**, unrelated to ``separation``, which is kcal/mol.
    MIN_WINDOW_GAP: ClassVar[int] = 50

    #: The 7 designed nucleotides ahead of the fixed RBS. Together they are the 18-nt RBS
    #: loop, with the RBS flush at its 3' end — which is what makes ``k1*`` the
    #: Shine-Dalgarno-to-start spacing (R2, R8).
    RBS_FLANK: ClassVar[str] = "AGACAAG"

    #: The inhibitory hairpin's loop: Kim's Sw-G5-G3n* sequence, carrying no SD-like motif
    #: so it creates no second ribosome entry point (R9, Appendix B).
    SECONDARY_LOOP: ClassVar[str] = "CAAGAACUUAGACAA"

    #: The 3-nt bulge facing the start codon across the main stem, making a 3x3 internal
    #: loop (R7). It earns its place twice: trigger A pairs straight *through* it in the ON
    #: state, giving 18 contiguous base pairs where the hairpin managed 15 plus a loop, and
    #: it splits the stem into two shorter helices, reducing RNase III exposure.
    BULGE_LEN: ClassVar[int] = 3

    #: Patterns forbidden anywhere in trigger A's window, as regular expressions over RNA.
    #: RNase E cleavage would shorten the transcript carrying the trigger; a G-quadruplex
    #: or a poly-U run would sequester or terminate it; an internal Shine-Dalgarno would
    #: give the ribosome a second place to start.
    #:
    #: Not routed through ``MotifScreener``, and not from preference: that screener
    #: ``re.escape``s its ``extra_motifs``, so it can only match literals and cannot
    #: express any of these. It also answers a different question — restriction sites and
    #: homopolymers, i.e. whether a sequence can be *assembled* — where these are about
    #: whether the transcript survives and is translated once. Teaching it regexes is a
    #: change to a stage every family is screened by, so it needs coordinating; until then
    #: these live here, where the pipeline can reach them.
    FORBIDDEN_MOTIFS: ClassVar[dict[str, str]] = {
        "RNase_E": r"[AG]AUGA",
        "G_quadruplex": r"G{3,}[ACGU]{1,7}G{3,}[ACGU]{1,7}G{3,}[ACGU]{1,7}G{3,}",
        "poly_U": r"U{5,}",
        "internal_SD": r"AGGAGG|AAGGAG|GGAGGA",
    }

    #: *E. coli* rare codons. A negative control may not introduce one: it has to differ
    #: from the real construct in whether the trigger works, not in how well it translates.
    RARE_CODONS: ClassVar[frozenset[str]] = frozenset({"AGG", "AGA", "CGA", "AUA", "CUA"})

    def screen_trigger_window(self, window_a: str, main_pre: str) -> tuple[str, ...]:
        """Sequence restrictions on trigger A's window. Empty means clean.

        Args:
            window_a: Trigger A's full 36-nt footprint on the transcript.
            main_pre: The 9 nt immediately 5' of the overlap.

        Returns:
            The name of every violated restriction, in declaration order.

        Note:
            ``main_pre`` is checked for a stop codon **in its own frame**, read from its
            own 5' end. In the finished switch it lands at +4…+12, codons 2 to 4 of the
            output protein, so its frame there is set by the switch's start codon and not
            by the frame it happens to occupy in the transcript it was taken from.
        """
        rna = sq.to_rna(window_a)
        hits = [name for name, pattern in self.FORBIDDEN_MOTIFS.items() if re.search(pattern, rna)]
        pre = sq.to_rna(main_pre)
        if any(pre[i : i + 3] in sq.STOP_CODONS for i in (0, 3, 6)):
            hits.append("in_frame_stop")
        return tuple(hits)

    def _synonymous(self, codon: str) -> list[str]:
        """Other codons for the same residue, excluding rare ones and the codon itself."""
        residue = sq.CODON_TABLE.get(codon)
        if residue is None:
            return []
        return [
            c
            for c, r in sq.CODON_TABLE.items()
            if r == residue and c != codon and c not in self.RARE_CODONS
        ]

    def knockout_possible(self, transcript: str, start: int, length: int, partner: str) -> bool:
        """Could synonymous substitution alone leave this trigger unable to nucleate?

        The negative controls are the whole point of a four-state panel: state 10 is the
        transcript with trigger B disabled, state 01 with trigger A disabled, both on the
        same background so the comparison means something. A pair whose codons do not
        permit that cannot be validated, however good the gate is.

        Computed exactly rather than by search: break *every* position any synonymous
        codon can break, then ask whether a pairable run of ``MIN_OVERLAP`` still
        survives. If one does, no combination of synonymous edits can disable this
        trigger.

        **Wobbles count**, through ``longest_complementary_run``, and that is why this is
        not a rare outcome — a position can only be broken by a base pairing with
        *neither* partner option, and codons like ``AUG`` and ``UGG`` offer nothing at all.

        Args:
            transcript: The coding sequence, RNA uppercase, in frame from its first base.
            start: 0-based start of the region to disable.
            length: Its length in nucleotides.
            partner: The switch domain this region pairs with, built against the original
                sequence, since that is what the gate was designed for.
        """
        rna = sq.to_rna(transcript)
        broken = list(rna[start : start + length])
        for position in self._breakable_positions(rna, start, length):
            codon_index, offset = divmod(position, 3)
            codon = rna[codon_index * 3 : codon_index * 3 + 3]
            partner_base = partner[length - 1 - (position - start)]
            for alternative in self._synonymous(codon):
                if not can_pair(alternative[offset], partner_base):
                    broken[position - start] = alternative[offset]
                    break
        return longest_complementary_run("".join(broken), partner) < self.MIN_OVERLAP

    def _breakable_positions(self, transcript: str, start: int, length: int) -> set[int]:
        """Positions inside a region that some synonymous codon can actually change."""
        movable: set[int] = set()
        for codon_index in range(start // 3, (start + length - 1) // 3 + 1):
            codon = transcript[codon_index * 3 : codon_index * 3 + 3]
            for alternative in self._synonymous(codon):
                for offset in range(3):
                    position = codon_index * 3 + offset
                    if codon[offset] != alternative[offset] and start <= position < start + length:
                        movable.add(position)
        return movable

    def controls_constructible(self, transcript: str, pair: "_TriggerPair") -> tuple[bool, bool]:
        """Whether states 01 and 10 can both be built for this pair, as ``(ko_A, ko_B)``.

        Each trigger has two places it can be hit. The overlap is the cheapest and most
        specific — for trigger A it is the *only* nucleation site, which is what ``a = 0``
        means. When the codons there do not permit enough change, and with wobbles counted
        they often do not, the invasion arm is the fallback: ``k1`` for trigger A, ``k2``
        for trigger B.
        """
        rna = sq.to_rna(transcript)
        a_start, _ = pair.window_a()
        x = rna[pair.x_start : pair.x_start + pair.len_x]
        x_star = rna[pair.xstar_start : pair.xstar_start + pair.len_x]

        ko_a = self.knockout_possible(rna, pair.x_start, pair.len_x, x_star) or (
            self.knockout_possible(
                rna, a_start, 6, sq.reverse_complement(rna[a_start : a_start + 6])
            )
        )
        k2_start = pair.xstar_start - pair.len_k2
        ko_b = self.knockout_possible(rna, pair.xstar_start, pair.len_x, x) or (
            pair.len_k2 > 0
            and k2_start >= 0
            and self.knockout_possible(
                rna,
                k2_start,
                pair.len_k2,
                sq.reverse_complement(rna[k2_start : pair.xstar_start]),
            )
        )
        return ko_a, ko_b

    def assemble(
        self, trigger_a: str, trigger_b: str, len_x: int, stem: "_SecondaryStem"
    ) -> "_AssembledSwitch":
        """Build the switch for one trigger pair and one secondary stem.

        Of the fifteen domains, twelve are already fixed by this point — five constants,
        and seven reverse complements of trigger domains. ``k2_star`` and ``secondary_z``
        come from ``secondary_stems``; ``mainZ`` is trigger A's own ``k1``, which makes the
        main stem's ``ddG_pref`` exactly zero. That is accepted rather than tuned: the
        exchange is a wash and the drive comes from elsewhere — the toehold, and the three
        extra pairs trigger A makes straight through the 3x3 internal loop that the hairpin
        itself cannot.

        The two hairpins sit directly adjacent, with **nothing between them**. That is
        ``a = 0``, the defining parameter of this architecture: until trigger B has opened
        the inhibitory hairpin, trigger A has no exposed nucleotide anywhere to bind.

        Args:
            trigger_a: 36 nt, reading ``k1 · bulge · main_pre · xA · extA``.
            trigger_b: 50 nt, reading ``k2 · xB · r2``.
            len_x: The overlap length the stem was built for.
            stem: One entry from ``secondary_stems``.

        Returns:
            The switch from the 5' cap through the LINKER — the region stage 4 folds —
            with its intended OFF structure and the coordinates of every domain. The
            reporter CDS is appended later, at plasmid assembly.
        """
        arm, len_k2 = self.ARM_LEN, self.ARM_LEN - len_x
        pre_bulge, post_bulge = self.STEM_PRE_BULGE_LEN, self.STEM_POST_BULGE_LEN
        rna_a, rna_b = sq.to_rna(trigger_a), sq.to_rna(trigger_b)

        k1 = rna_a[:post_bulge]
        bulge = rna_a[post_bulge : post_bulge + self.BULGE_LEN]
        main_pre = rna_a[post_bulge + self.BULGE_LEN : arm]
        x = rna_a[arm : arm + len_x]
        r2 = rna_b[len_k2 + len_x :]

        rbs_loop = self.RBS_FLANK + self.RBS_PROKARYOTIC
        main_z = self._repair_main_z(k1, rbs_loop)
        pieces = [
            ("cap", self.LEADER_SEQUENCE),
            ("r2_star", sq.reverse_complement(r2)),
            ("sw_x", x),
            ("k2_star", stem.k2_star),
            ("secondary_loop", self.SECONDARY_LOOP),
            ("secondary_z", stem.secondary_z),
            ("sw_xs", sq.reverse_complement(x)),
            # a = 0: nothing between the two hairpins.
            ("main_pre_star", sq.reverse_complement(main_pre)),
            ("bulge_star", sq.reverse_complement(bulge)),
            ("k1_star", sq.reverse_complement(k1)),
            ("rbs_loop", rbs_loop),
            ("main_z", main_z),
            ("aug", "AUG"),
            ("main_pre", main_pre),
            ("linker", self.LINKER_SEQUENCE),
        ]

        sequence = ""
        domains: dict[str, tuple[int, int]] = {}
        for name, piece in pieces:
            domains[name] = (len(sequence), len(sequence) + len(piece))
            sequence += piece

        expected = (
            len(self.LEADER_SEQUENCE)
            + self.TOEHOLD_B_LEN
            + 2 * arm
            + len(self.SECONDARY_LOOP)
            + pre_bulge
            + self.BULGE_LEN
            + post_bulge
            + len(rbs_loop)
            + post_bulge
            + 3
            + pre_bulge
            + len(self.LINKER_SEQUENCE)
        )
        if len(sequence) != expected:
            raise ValueError(f"assembled {len(sequence)} nt, expected {expected}")

        return _AssembledSwitch(
            sequence=sequence,
            dot_bracket=self._off_structure(sequence, domains),
            domains=domains,
            len_x=len_x,
        )

    def _repair_main_z(self, k1: str, rbs_loop: str) -> str:
        """Choose ``mainZ``, trying to keep it identical to trigger A's ``k1``.

        ``mainZ`` is the switch's own copy of ``k1`` and doubles as the spacer, so setting
        it to ``k1`` makes the main stem's ``ddG_pref`` exactly zero and every pair
        Watson-Crick. It has one failure mode: a trigger whose first six nucleotides
        contain ``AUG`` puts a second start codon in the 5' UTR, out of frame with the real
        one, so what the ribosome translates from there is not the reporter. On mCherry
        that hits 93 of 867 otherwise-clean candidates.

        Rather than discard them, repair the smallest amount of sequence. A position may
        move to any base that still pairs with its partner in ``k1*``, **wobbles
        included** — and that is what makes a repair cheap rather than destructive:
        ``k1[i]`` of A or C has exactly one alternative, reachable through a G:U wobble,
        while G and U have none, since only G pairs with C and only U pairs with A. So the
        stem stays closed at every position; one pair merely becomes a wobble.

        Among the repairs that remove the start codon, the fewest substitutions win, and
        ties go to the strongest remaining duplex — the change that weakens the main
        hairpin least. Returns ``k1`` unchanged when no repair is needed, and also when
        none is possible, leaving ``assembly_violations`` to report the fault rather than
        hiding it behind a silently different design.
        """
        if "AUG" not in rbs_loop + k1:
            return k1

        options: list[list[str]] = []
        for base in k1:
            partner = sq.reverse_complement(base)
            options.append([b for b in "ACGU" if can_pair(b, partner)])

        k1_star = sq.reverse_complement(k1)
        repairs: list[tuple[int, float, str]] = []
        for combination in product(*options):
            candidate = "".join(combination)
            if "AUG" in rbs_loop + candidate:
                continue
            energy = fixed_alignment_energy(candidate, k1_star, self.folder)
            if energy is None:
                continue
            changed = sum(1 for a, b in zip(candidate, k1, strict=True) if a != b)
            repairs.append((changed, energy, candidate))
        if not repairs:
            return k1
        return min(repairs)[2]

    def _off_structure(self, sequence: str, domains: dict[str, tuple[int, int]]) -> str:
        """The structure the OFF state is drawn as, for ``ensemble_defect`` to score against.

        Built from what the arms can *actually* pair rather than from the drawing: scheme C
        leaves mismatches in the upper stem by design, and a reference structure asserting
        pairs the bases cannot form would measure the design against something impossible.

        The start codon is left unpaired. It sits in the 3x3 internal loop opposite
        ``bulge_star`` and is already open in the OFF state — the gate works by burying the
        *ribosome binding site* and the stem around the AUG, not the AUG itself.
        """
        structure = ["."] * len(sequence)

        for ascending, descending in (
            (("sw_x", "k2_star"), ("secondary_z", "sw_xs")),
            (("main_pre_star",), ("main_pre",)),
            (("k1_star",), ("main_z",)),
        ):
            up_start = domains[ascending[0]][0]
            up_end = domains[ascending[-1]][1]
            down_start = domains[descending[0]][0]
            down_end = domains[descending[-1]][1]
            up, down = sequence[up_start:up_end], sequence[down_start:down_end]
            for offset, paired in enumerate(alignment_pairs(up, down)):
                if paired:
                    structure[up_start + offset] = "("
                    structure[down_end - 1 - offset] = ")"
        return "".join(structure)

    def assembly_violations(self, switch: "_AssembledSwitch") -> tuple[str, ...]:
        """Sequence-level faults in a finished switch. Empty means clean.

        Two ways to lose the reporter, both in the same region and both checked on the
        finished molecule rather than assumed from the parts (R5). An in-frame stop
        truncates the product before it begins. An earlier AUG gives the ribosome a second
        place to start, and out of frame with the real one what it translates is not the
        reporter.
        """
        faults: list[str] = []
        aug_start = switch.domains["aug"][0]
        coding = switch.sequence[aug_start:]
        if sq.find_stops(coding):
            faults.append("in_frame_stop")
        loop_start = switch.domains["rbs_loop"][0]
        if "AUG" in switch.sequence[loop_start:aug_start]:
            faults.append("upstream_aug")
        if len(coding) % 3:
            faults.append("frame_shift")
        return tuple(faults)

    #: The feasible set: pass/fail on the four-tube observables, applied before any
    #: ranking. Each entry is ``(observable, comparison, threshold)``.
    #:
    #: The values come from §4.6 of the objective-function document, set from physics at
    #: values that exclude only the indefensible rather than values chosen to select
    #: winners. A stem meant to be shut should be mostly paired and one meant to be open
    #: more open than closed, which is all 0.2 and 0.5 assert. The two energy bounds sit at
    #: roughly the folding model's own error: below about 1.5 kcal/mol two designs are not
    #: distinguishable, so a gate there excludes what cannot be told apart rather than
    #: making a claim.
    #:
    #: ``A_S`` is taken over ``sw_xs`` alone — the site trigger A must nucleate on — with
    #: the whole descending arm reported beside it as ``A_S_full`` (D22).
    #:
    #: ``τ12``, the designed-flank gate, is deliberately absent: it is a kcal/mol
    #: difference with no symmetry argument to reach it, and the decision is to measure
    #: ``flank_penalty`` across a real run first and set the threshold from where the
    #: distribution actually sits. Adding a guessed value here would be the one thing
    #: worse than leaving it out.
    THRESHOLDS: ClassVar[tuple[tuple[str, str, float], ...]] = (
        ("A_S_00", "<", 0.2),  # τ1  — the inhibitory hairpin is shut with no trigger
        ("A_M_00", "<", 0.2),  # τ2  — so is the main one
        ("A_S_10", "<", 0.2),  # τ3  — trigger A alone must not open the inhibitory hairpin
        ("A_M_10", "<", 0.2),  # τ4a — nor the main one. The dangerous leak.
        ("A_M_01", "<", 0.2),  # τ4b — and neither may trigger B, which is the harder test
        ("A_S_01", ">", 0.5),  # τ5  — but trigger B must open the inhibitory hairpin
        ("A_S_11", ">", 0.5),  # τ6  — and keep it open with both present
        ("A_M_11", ">", 0.5),  # τ7  — trigger A opens the main hairpin, but only with B
        ("A_r2_star_00", ">", 0.5),  # τ8  — the toehold is available to begin with
        ("d_off", "<", 0.1),  # τ9  — the OFF state is the structure we drew
        ("separation", ">", 1.5),  # τ10 — state 11 is the most open, by more than noise
        ("ddG_AND", "<", -1.0),  # τ11 — and the two triggers act cooperatively
    )

    def gate_violations(
        self,
        observables: dict[str, float | None],
        thresholds: tuple[tuple[str, str, float], ...] | None = None,
    ) -> tuple[str, ...]:
        """Every threshold this design fails. Empty means it enters the ranking.

        **Every** violation, not the first: a design failing one gate and a design failing
        six are different objects, and which gates a candidate set fails is the most
        informative thing a run produces when nothing passes.

        A missing measurement counts as a failure rather than a pass. ``None`` means the
        ensemble could not be computed, and admitting an unmeasured design would let it
        outrank measured ones on a number nobody has.
        """
        failed: list[str] = []
        for name, comparison, threshold in thresholds or self.THRESHOLDS:
            value = observables.get(name)
            if value is None:
                failed.append(f"{name}=None")
            elif (value < threshold) if comparison == "<" else (value > threshold):
                continue
            else:
                failed.append(f"{name}{comparison}{threshold}")
        return tuple(failed)

    #: Observables that depend on the trigger pair alone, not on which secondary stem was
    #: chosen for it. Scheme C designs ``k2_star`` and ``secondary_z``, which live in the
    #: *secondary* hairpin, so the main hairpin and the free toehold are effectively the
    #: same molecule whichever build it picks. Measured across four stems spanning the
    #: frontier, every entry below moves by less than 0.006 — against a folding model whose
    #: own error is ~1.5 kcal/mol — while ``A_S`` and ``d_off`` move visibly.
    #:
    #: **Deliberately excluded, and the reason is not subtle:** trigger B binds the
    #: secondary stem, so everything that involves it is stem-dependent. Measured on the
    #: same four stems, ``dG_bind_B`` spans **20.1 kcal/mol**, ``dG_bind_A_given_B`` 15.4
    #: (it is conditioned on B), and ``dG_open_01`` and ``ddG_AND`` 1.7 each. ``separation``
    #: is excluded too: it is a minimum over the three OFF states, so it is only invariant
    #: while state 10 is the leakiest, and a pair whose state 01 leaks worst would make it
    #: move with the stem.
    #:
    #: What survives is exactly the set of gates no stem can rescue — the main hairpin's
    #: four accessibilities and the toehold's — which is what makes a pair screenable
    #: before any stem is enumerated, one fold instead of roughly a hundred and twenty.
    STEM_INDEPENDENT: ClassVar[frozenset[str]] = frozenset(
        {
            "dG_open_00",
            "dG_open_10",
            "dG_open_11",
            "dG_open_flank_00",
            "flank_penalty",
            "A_M_00",
            "A_M_01",
            "A_M_10",
            "A_M_11",
            "A_r2_star_00",
        }
    )

    def probe_switch(self, trigger_a: str, trigger_b: str, len_x: int) -> "_AssembledSwitch":
        """A switch on the un-traded secondary stem, for screening the pair itself.

        Built at the corner where every contested position serves both triggers, which
        needs no energies and so no folding. It is not a design worth ordering — its upper
        stem is mismatched wherever the triggers disagree — but the main hairpin, the
        toehold and the reporter region are identical to every real build's, and those are
        what a pair is screened on.
        """
        ext, k2 = _secondary_domains(trigger_a, trigger_b, len_x, self.ARM_LEN)
        k2_star, secondary_z = _build_arms(ext, k2, {})
        untraded = _SecondaryStem(k2_star, secondary_z, (), 0.0, 0.0, 0.0, 0.0)
        return self.assemble(trigger_a, trigger_b, len_x, untraded)

    def screen_pair(self, trigger_a: str, trigger_b: str, len_x: int) -> dict[str, float | None]:
        """The stem-independent observables for one trigger pair: one fold, not a hundred.

        A pair that leaks in state 10 cannot be rescued by any secondary stem — trigger A
        opening the main hairpin unaided is a property of trigger A and the main hairpin,
        and scheme C designs neither. Screening here and enumerating stems only for the
        survivors is the difference between folding every build and folding a pair once.
        """
        probe = self.probe_switch(trigger_a, trigger_b, len_x)
        observables = self.four_tube_observables(probe, trigger_a, trigger_b)
        return {k: v for k, v in observables.items() if k in self.STEM_INDEPENDENT}

    def pair_gate_violations(self, screened: dict[str, float | None]) -> tuple[str, ...]:
        """The thresholds a pair fails on its own, before any stem is designed.

        Restricted to the gates whose observable is stem-independent, which is what makes
        a rejection here **final**: no build could have changed the answer, so there is no
        point enumerating its stems. The rest of the feasible set is applied per build,
        once a stem exists to apply it to.
        """
        applicable = tuple(t for t in self.THRESHOLDS if t[0] in self.STEM_INDEPENDENT)
        return self.gate_violations(screened, thresholds=applicable)

    def four_tube_observables(
        self, switch: "_AssembledSwitch", trigger_a: str, trigger_b: str
    ) -> dict[str, float | None]:
        """Fold the four logic states at equilibrium and read the gate's behaviour off them.

        The tubes are the switch alone and the switch with each combination of triggers
        present in excess, named by state with **trigger A as the left digit**::

            00 = [S]        neither         10 = [S, A]     A alone, which must stay shut
            01 = [S, B]     B alone          11 = [S, A, B]  both, the only ON state

        Every quantity here is an ensemble property — a ratio of partition functions, or a
        mean over the pair-probability matrix. None of them needs a single representative
        structure, so none is chosen: where the minimum free energy structure carries
        little of the ensemble, substituting it would answer a different and worse
        question.

        Returns:
            Raw measurements, in the units the framework quotes them in. A measurement
            that could not be made is ``None``, never ``0.0`` — on a lower-is-better
            quantity zero reads as perfect and passes every threshold.

        Note:
            ``separation`` and ``ddG_AND`` are taken on ``W_rank`` only. ``W_flank`` adds
            the seven designed nucleotides of the RBS loop's 5' flank and is a pass/fail
            check on those alone: in state 11 the region upstream of -24 is duplexed to
            trigger A, so ranking there would penalise a gate for working.
        """
        rna_a, rna_b = sq.to_rna(trigger_a), sq.to_rna(trigger_b)
        tubes = {
            "00": switch.sequence,
            "01": f"{switch.sequence}&{rna_b}",
            "10": f"{switch.sequence}&{rna_a}",
            "11": f"{switch.sequence}&{rna_a}&{rna_b}",
        }
        rank, flank = switch.span(-17, 13), switch.span(-24, 13)

        opening: dict[str, float | None] = {}
        for state, strands in tubes.items():
            opening[state] = self._opening_cost(strands, rank)
        flank_00 = self._opening_cost(tubes["00"], flank)

        observables: dict[str, float | None] = {
            f"dG_open_{state}": value for state, value in opening.items()
        }
        observables["dG_open_flank_00"] = flank_00

        # separation: the ON state against whichever OFF state comes closest to leaking.
        # A minimum, not a mean, because an AND gate is only as good as its worst leak --
        # and it is what makes a state-10 leak collapse the score rather than average out.
        off = [opening[s] for s in ("00", "01", "10")]
        if opening["11"] is None or any(value is None for value in off):
            observables["separation"] = None
        else:
            observables["separation"] = min(value - opening["11"] for value in off)

        if all(opening[s] is not None for s in ("00", "01", "10", "11")):
            observables["ddG_AND"] = (opening["11"] - opening["01"]) - (
                opening["10"] - opening["00"]
            )
        else:
            observables["ddG_AND"] = None

        if flank_00 is None or opening["00"] is None:
            observables["flank_penalty"] = None
        else:
            observables["flank_penalty"] = flank_00 - opening["00"]

        # Stem and toehold accessibility: a mean of per-base unpaired probabilities, each
        # read from the partition function's pair-probability matrix rather than from any
        # one structure. Deliberately not the joint probability that a whole arm is open at
        # once -- over eighteen nucleotides that is ~1e-22 even for an arm with nothing to
        # pair against, which would put every design below every threshold.
        spans = {
            "A_S": switch.domains["sw_xs"],
            "A_M": (switch.domains["main_z"][0], switch.domains["main_pre"][1]),
            "A_S_full": (switch.domains["secondary_z"][0], switch.domains["sw_xs"][1]),
        }
        for state, strands in tubes.items():
            matrix = self.folder.base_pair_probabilities(strands)
            for name, (start, end) in spans.items():
                observables[f"{name}_{state}"] = _mean_unpaired(matrix, start, end)
            if state == "00":
                toehold = switch.domains["r2_star"]
                observables["A_r2_star_00"] = _mean_unpaired(matrix, *toehold)

        observables["d_off"] = self.folder.ensemble_defect(
            switch.sequence, switch.dot_bracket
        ) / len(switch.sequence)

        # Binding energies, as ensemble free-energy differences. Never a bare dG_bind for
        # trigger A: measured against the *bare* switch it rewards A opening the main
        # hairpin on its own, which is exactly the state-10 leak the gates exist to catch,
        # so the score and the gate would pull against each other. A is conditioned on B.
        g = {state: self.folder.partition(strands) for state, strands in tubes.items()}
        observables["dG_bind_B"] = g["01"] - g["00"] - self.folder.partition(rna_b)
        observables["dG_bind_A_given_B"] = g["11"] - g["01"] - self.folder.partition(rna_a)
        return observables

    def _opening_cost(self, strands: str, window: tuple[int, int]) -> float | None:
        """``-RT ln P_open`` over a window: the work of opening it unaided.

        The right barrier for the 30S subunit, which has a narrow entry channel, no
        helicase at initiation, and captures transiently open states rather than forcing
        them apart. It is the **wrong** barrier for a trigger, which nucleates on a few
        bases and then trades pairs through branch migration without ever paying the full
        opening cost — which is why stem accessibility above stays a bounded probability
        instead.
        """
        probability = self.folder.p_open(strands, window)
        if probability is None or probability <= 0.0:
            return None
        return -self.folder.rt * math.log(probability)

    #: Most synonymous substitutions a negative control may spend. A control differing from
    #: the real construct at many positions stops being a control for one variable.
    MAX_KNOCKOUT_EDITS: ClassVar[int] = 4

    def knockout(
        self, transcript: str, start: int, length: int, partner: str
    ) -> "_Knockout | None":
        """The fewest synonymous substitutions that stop this region nucleating.

        A trigger needs at least ``MIN_OVERLAP`` contiguous complementary nucleotides to
        nucleate at all, so a knockout is any synonymous variant of the region leaving no
        run that long against its site on the switch. Nothing else about the transcript
        changes, which is what makes the four bench constructs comparable: states 10 and 01
        differ from state 11 only here.

        Codon combinations are examined in order of increasing edit count, so the first hit
        is minimal. A variant is rejected if it changes the protein, introduces a rare codon
        or introduces a forbidden motif that was not already present — a control that
        translates differently, or is cleaved differently, is testing more than one thing.

        Args:
            transcript: The coding sequence, RNA uppercase, in frame from its first base.
            start: 0-based start of the region to disable.
            length: Its length in nucleotides.
            partner: The switch domain this region pairs with, built against the
                **original** sequence, since that is the gate the control is a control for.

        Returns:
            The minimal knockout, or ``None`` when no synonymous variant within
            ``MAX_KNOCKOUT_EDITS`` disables the region. ``None`` is a real answer: on
            mCherry 169 of 1,036 otherwise-valid pairs cannot have either trigger disabled,
            which is why ``controls_constructible`` runs inside the scan.
        """
        rna = sq.to_rna(transcript)
        first, last = start // 3, (start + length - 1) // 3
        indices = list(range(first, last + 1))
        choices = [
            [rna[i * 3 : i * 3 + 3], *self._synonymous(rna[i * 3 : i * 3 + 3])] for i in indices
        ]
        original_protein = sq.translate(rna, stop_at_stop=False)
        context = slice(max(0, start - 20), start + length + 20)

        best: _Knockout | None = None
        for combination in product(*choices):
            edits = tuple(
                (i * 3 + offset, rna[i * 3 + offset], codon[offset])
                for i, codon in zip(indices, combination, strict=True)
                for offset in range(3)
                if rna[i * 3 + offset] != codon[offset]
            )
            if not edits or len(edits) > self.MAX_KNOCKOUT_EDITS:
                continue
            if best is not None and len(edits) >= len(best.edits):
                continue
            variant = list(rna)
            for position, _, replacement in edits:
                variant[position] = replacement
            candidate = "".join(variant)

            residual = longest_complementary_run(candidate[start : start + length], partner)
            if residual >= self.MIN_OVERLAP:
                continue
            if sq.translate(candidate, stop_at_stop=False) != original_protein:
                continue
            if any(codon in self.RARE_CODONS for codon in combination):
                continue
            introduced = [
                name
                for name, pattern in self.FORBIDDEN_MOTIFS.items()
                if re.search(pattern, candidate[context]) and not re.search(pattern, rna[context])
            ]
            if introduced:
                continue
            best = _Knockout(edits=edits, sequence=candidate, residual_run=residual)
        return best

    def bench_constructs(self, transcript: str, pair: "_TriggerPair") -> dict[str, str | None]:
        """The four logic states as four transcripts on one background.

        What makes the comparison interpretable: state 11 is the unmodified transcript,
        states 10 and 01 each carry one trigger disabled by one or two synonymous
        substitutions, and state 00 is the transcript withheld altogether — so it is
        ``None`` here rather than a sequence. The protein is identical across all three
        that exist.

        Each trigger is attacked at the overlap first, which is the cheapest and most
        specific target — for trigger A it is the *only* nucleation site, which is what
        ``a = 0`` means. Where the codons there do not permit enough change, and with
        wobbles counted they often do not, the invasion arm is the fallback: ``k1`` for
        trigger A, ``k2`` for trigger B.

        Returns:
            ``{"11": …, "10": …, "01": …, "00": None}``, with a state mapped to ``None``
            when no synonymous knockout exists for it.
        """
        rna = sq.to_rna(transcript)
        a_start, _ = pair.window_a()
        x = rna[pair.x_start : pair.x_start + pair.len_x]
        x_star = rna[pair.xstar_start : pair.xstar_start + pair.len_x]
        k2_start = pair.xstar_start - pair.len_k2

        # Disabling trigger A gives state 01 (A absent, B intact), and vice versa.
        routes = {
            "01": (
                (pair.x_start, pair.len_x, x_star),
                (a_start, 6, sq.reverse_complement(rna[a_start : a_start + 6])),
            ),
            "10": (
                (pair.xstar_start, pair.len_x, x),
                (k2_start, pair.len_k2, sq.reverse_complement(rna[k2_start : pair.xstar_start])),
            ),
        }
        constructs: dict[str, str | None] = {"11": rna, "00": None}
        for state, targets in routes.items():
            constructs[state] = None
            for start, length, partner in targets:
                if start < 0 or length <= 0 or start + length > len(rna):
                    continue
                result = self.knockout(rna, start, length, partner)
                if result is not None:
                    constructs[state] = result.sequence
                    break
        return constructs

    def find_trigger_pairs(
        self, transcript: str, *, min_window_gap: int | None = None
    ) -> Iterator["_TriggerPair"]:
        """Every pair of windows in one transcript that can serve as triggers A and B.

        The two triggers must share a reverse-complementary overlap, because that overlap
        is what couples the halves of the gate: trigger A carries ``x`` and trigger B
        carries ``x*``, and ``x*`` is the only site trigger A can nucleate on once B has
        acted. In a validation design both inputs come from one gene, so the pair is two
        windows of the same transcript.

        Every overlap is found, not sampled. Two strands pair antiparallel, so if an
        overlap starts at ``p`` on one window its partner runs backwards from ``j`` on the
        other and ``p + j`` never changes — every possible overlap lies on one
        anti-diagonal of the position-by-position matrix. Seeding on every 4-mer and
        extending both ways walks all of them.

        Each pair is reported at its **maximal** perfect run only. Truncating it into
        sub-overlaps is strictly dominated: both triggers' footprints on the stem arm are
        18 nt regardless, so a shorter ``x`` only moves positions out of the conflict-free
        core and into the contested region, degrading trigger A's site, trigger B's site
        and the lock at once, with no compensating gain anywhere.

        Args:
            transcript: The coding sequence both triggers are drawn from, RNA uppercase.
            min_window_gap: Nucleotides required between the two windows; defaults to
                ``MIN_WINDOW_GAP``. Passed explicitly so the cutoff is visible at the call
                site rather than applied invisibly.

        Yields:
            Pairs whose full footprints fit inside the transcript, do not collide, and are
            at least ``min_window_gap`` apart. **Motif screening and knockout feasibility
            are not applied here** — they need a motif screener and a codon table, neither
            of which a gate family may reach for, and both are filters rather than
            geometry. See the notebook workbench for the full stage-1 selection.
        """
        gap = self.MIN_WINDOW_GAP if min_window_gap is None else min_window_gap
        rna = sq.to_rna(transcript)
        n = len(rna)

        index: dict[str, list[int]] = {}
        for j in range(n - self.MIN_OVERLAP + 1):
            index.setdefault(rna[j : j + self.MIN_OVERLAP], []).append(j)

        seen: set[tuple[int, int, int]] = set()
        for i in range(n - self.MIN_OVERLAP + 1):
            for j in index.get(sq.reverse_complement(rna[i : i + self.MIN_OVERLAP]), ()):
                start_x, start_xs, length = i, j, self.MIN_OVERLAP
                # Extending x 3'-ward walks its partner 5'-ward: they pair antiparallel.
                while (
                    length < self.ARM_LEN
                    and start_x + length < n
                    and start_xs > 0
                    and rna[start_xs - 1] == sq.reverse_complement(rna[start_x + length])
                ):
                    start_xs -= 1
                    length += 1
                while (
                    length < self.ARM_LEN
                    and start_x > 0
                    and start_xs + length < n
                    and rna[start_xs + length] == sq.reverse_complement(rna[start_x - 1])
                ):
                    start_x -= 1
                    length += 1
                seen.add((start_x, start_xs, length))

        for start_x, start_xs, length in sorted(seen):
            pair = _TriggerPair(start_x, start_xs, length, self.ARM_LEN, self.TOEHOLD_B_LEN)
            if pair.fits(n) and pair.disjoint() and pair.gap() >= gap:
                yield pair

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
class _Knockout:
    """One trigger disabled by synonymous substitution — a negative-control transcript."""

    #: ``(position, from_base, to_base)`` per change, 0-based into the transcript.
    edits: tuple[tuple[int, str, str], ...]
    sequence: str
    #: Longest pairable run left against the switch site, **wobbles counted**. Below
    #: ``MIN_OVERLAP``, or this is not a knockout.
    residual_run: int


@dataclass(frozen=True, slots=True)
class _AssembledSwitch:
    """A finished switch, from the 5' cap through the LINKER — the region stage 4 folds.

    Intra-module only; it becomes a ``GateDesign`` at the stage boundary.
    """

    sequence: str
    dot_bracket: str
    #: Domain name to ``(start, end)``, 0-based and half-open, in 5'->3' order.
    domains: dict[str, tuple[int, int]]
    len_x: int

    def position(self, index: int) -> int:
        """The index re-expressed in the framework's coordinates, where the A of the start
        codon is ``+1``, the base 5' of it is ``-1``, and **there is no zero**.

        Every window in the specification is quoted this way, so converting here once is
        what stops each caller rediscovering that the numbering skips a value.
        """
        aug = self.domains["aug"][0]
        return index - aug + 1 if index >= aug else index - aug

    def span(self, first: int, last: int) -> tuple[int, int]:
        """A window quoted in framework coordinates, back as a half-open index range.

        ``span(-17, 13)`` is ``W_rank``, the 30-nt ribosome footprint stage 4 ranks on;
        ``span(-24, 13)`` is ``W_flank``, which is pass/fail only and must never be ranked
        — in state 11 the region upstream of -24 is duplexed to trigger A, so ranking there
        penalises a working gate.
        """
        aug = self.domains["aug"][0]
        start = aug + first - 1 if first > 0 else aug + first
        end = aug + last - 1 if last > 0 else aug + last
        return start, end + 1


@dataclass(frozen=True, slots=True)
class _TriggerPair:
    """Two windows of one transcript, sharing a perfect reverse-complementary overlap.

    Coordinates are 0-based, inclusive start and exclusive end, like everywhere else in
    the engine. Intra-module only — it becomes a ``TriggerSet`` at the stage boundary.
    """

    x_start: int
    """Start of ``x``, trigger A's overlap domain."""
    xstar_start: int
    """Start of ``x*``, trigger B's ``Secondary_pre`` domain."""
    len_x: int
    arm_len: int
    toehold_b_len: int

    @property
    def len_k2(self) -> int:
        """Trigger B's invasion domain. Every nucleotide the overlap takes is one fewer."""
        return self.arm_len - self.len_x

    def window_a(self) -> tuple[int, int]:
        """Trigger A: the 18-nt stem arm, the overlap, then the extension facing
        ``secondaryZ``. Constant at 36 nt, since ``len_k2`` cancels ``len_x``.

        **This is the widest footprint, the one schemes A and C need.** A scheme anchoring
        every position to trigger B would need up to 14 nt less. Screening on the wide one
        is the conservative direction, but it does drop pairs a narrower scheme could have
        used, and it changes the candidate count — so it must not be narrowed quietly.
        """
        return self.x_start - self.arm_len, self.x_start + self.len_x + self.len_k2

    def window_b(self) -> tuple[int, int]:
        """Trigger B: the invasion domain, the overlap, then the free toehold. Constant at
        ``arm_len + toehold_b_len`` = 50 nt."""
        return self.xstar_start - self.len_k2, self.xstar_start + self.len_x + self.toehold_b_len

    def fits(self, transcript_length: int) -> bool:
        """Both full footprints lie inside the transcript."""
        a_start, a_end = self.window_a()
        b_start, b_end = self.window_b()
        return (
            a_start >= 0
            and b_start >= 0
            and a_end <= transcript_length
            and b_end <= transcript_length
        )

    def disjoint(self) -> bool:
        """The two windows do not overlap each other. One nucleotide cannot serve both."""
        a_start, a_end = self.window_a()
        b_start, b_end = self.window_b()
        return a_end <= b_start or b_end <= a_start

    def gap(self) -> int:
        """Nucleotides between the windows — the loop a cis interaction would have to close."""
        a_start, a_end = self.window_a()
        b_start, b_end = self.window_b()
        return b_start - a_end if a_end <= b_start else a_start - b_end


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
