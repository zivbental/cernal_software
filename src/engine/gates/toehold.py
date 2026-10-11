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
from itertools import combinations, product
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
    TriggerCandidate,
    TriggerSet,
)
from engine.gates.base import GateFamily
from engine.gates.tools.binding import (
    alignment_pairs,
    can_pair,
    fixed_alignment_energy,
    longest_complementary_run,
    weakest_binding_confidence,
)
from engine.gates.tools.codons import CodonOptimizer
from engine.gates.tools.folding import FoldEngine, mean_unpaired, unpaired_defect
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
        payload: Optional — the effector gene's own CDS (DNA or RNA, a full ORF
            starting with a start codon). When given, the real payload's own first
            ``PAYLOAD_HEAD_LENGTH`` nucleotides are folded into every generated switch
            (same idea as ``AntisenseNotGate.payload``, which requires one), so
            ``evaluate_design`` measures the molecule a ribosome would actually see
            once this gene is fused on — not a fixed placeholder standing in for any
            gene. Unlike ``AntisenseNotGate``, optional: a toehold switch is useful to
            design and rank before an effector gene is chosen.

    Reference: Green et al., "Toehold switches: de-novo-designed regulators of gene
    expression" (2014), and the pipeline map's Switches Design stage.
    """

    name = "toehold"
    design_prefix = "toehold"
    version = "0.10.0-payload-context"
    kind = GateKind.TOEHOLD
    label = "Toehold Riboswitch"
    description = "Translational control · pre-mRNA"
    supported_hosts: ClassVar[frozenset[Host]] = frozenset(
        {Host.ECOLI, Host.YEAST, Host.HUMAN, Host.C_ACNES}
    )
    max_inputs = 1
    available = True

    #: Toehold lengths to explore per trigger. Widening this multiplies the search space.
    toehold_lengths: ClassVar[tuple[int, ...]] = (12, 15, 18)

    #: Unstructured 5' leader ahead of the toehold, dispatched on ``self.host.track`` by
    #: ``_leader_sequence`` the same way ``_loop_element`` dispatches the RBS/Kozak
    #: choice — these are not interchangeable defaults, they are two different upstream
    #: contexts. ``LEADER_SEQUENCE_PROKARYOTIC`` ("GGG") is the source generator's own
    #: default (``leader_sequence="GGG"``) — a T7-in-vitro-transcription convention (T7
    #: initiates most efficiently on a leading G run), not a eukaryotic construct
    #: concern. ``LEADER_SEQUENCE_EUKARYOTIC`` is the actual plasmid sequence the team
    #: supplied that attaches immediately before the toehold in the human construct
    #: (``plasmid_prefix`` in the team's own scripts) — not a placeholder, so it is not
    #: swept the way ``TRAILING_LOOP_LENGTHS``/``KOZAK_LINKER_LENGTHS`` are.
    LEADER_SEQUENCE_PROKARYOTIC: ClassVar[str] = "GGG"
    LEADER_SEQUENCE_EUKARYOTIC: ClassVar[str] = "GUCAGAUC"

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

    #: Which Kozak placement(s) ``generate_designs`` builds, for a eukaryotic host.
    #: ``"loop"`` is the layout above — RBS-in-loop, borrowed unmodified from the
    #: prokaryotic mechanism (steric occlusion of the start codon). ``"trailing"`` is a
    #: second, biologically distinct layout: Kozak and AUG sit *after* the closed
    #: hairpin rather than inside its loop, so the hairpin blocks a scanning ribosome
    #: (docs/modalities.md's "scanning ribosome model") rather than caging the start
    #: codon directly. A prokaryotic host always builds ``"loop"`` only — Shine-Dalgarno
    #: initiation has no scanning phase for a downstream hairpin to block — regardless
    #: of this setting; see ``generate_designs``.
    #:
    #: Not a subclass split (docs/engine.md §2.4's "host: a parameter, not a subclass" —
    #: the same reasoning applies here): both layouts share every method except the
    #: switch construction and the leakage proxy in ``evaluate_design``. Pass a narrower
    #: tuple to ``__init__`` to restrict generation to one layout; the default sweeps
    #: both and leaves ``engine.scoring`` to rank across them, per ``CLAUDE.md`` §3 — a
    #: gate never picks its own winner.
    KOZAK_LAYOUTS: ClassVar[tuple[str, ...]] = ("loop", "trailing")

    #: Loop lengths swept for the ``"trailing"`` layout. Once Kozak leaves the loop, the
    #: loop is no longer sized or filled by a fixed conserved element — it is free, and
    #: needs its own length sweep the way ``toehold_lengths`` sweeps the toehold. The
    #: actual nucleotides are still ``_filler``'s deterministic placeholder; no sequence-
    #: design optimizer exists in this port (see ``_filler``).
    TRAILING_LOOP_LENGTHS: ClassVar[tuple[int, ...]] = (10, 12)

    #: Optional spacer between the closed hairpin and the Kozak element, for the
    #: ``"trailing"`` layout only. ``0`` (no spacer, Kozak immediately follows the
    #: stem) and a short non-zero option, swept the same way — whether *some* distance
    #: from the hairpin's base helps the scanning ribosome re-initiate, or whether it
    #: just adds unstructured length for no benefit, is exactly the kind of question
    #: ``engine.scoring`` settles across designs, not a constant to guess once here.
    KOZAK_LINKER_LENGTHS: ClassVar[tuple[int, ...]] = (0, 3)

    #: Nucleotides of the payload's own CDS, immediately after its start codon, that get
    #: folded into every switch when ``payload`` is supplied. Same figure and rationale
    #: as ``AntisenseNotGate.PAYLOAD_HEAD_LENGTH``: Kudla et al. 2009 (*Science*,
    #: "Coding-sequence determinants of gene expression in E. coli") found mRNA folding
    #: strength in roughly this window around the start codon to be the strongest
    #: predictor of expression level in their assay — bigger than codon usage. Without a
    #: payload, ``evaluate_design`` folds the switch alone (or with ``LINKER_SEQUENCE``
    #: for ``"loop"``) — a different molecule from what a real ribosome would see once a
    #: specific gene is fused on, and the two can rank designs differently: a candidate
    #: whose stem looks clean in isolation can pick up new base-pairing partners once the
    #: real downstream sequence is folded in, or vice versa.
    PAYLOAD_HEAD_LENGTH: ClassVar[int] = 30

    def __init__(
        self,
        host: Host,
        folder: FoldEngine,
        translation: TranslationScorer,
        codons: CodonOptimizer,
        *,
        kozak_layouts: tuple[str, ...] | None = None,
        payload: str | None = None,
    ) -> None:
        # Tools are handed in, never constructed here: FoldEngine's cache only helps if
        # every caller shares one instance (docs/engine.md §2.4).
        self.host = host
        self.folder = folder
        self.translation = translation
        self.codons = codons
        # None means "use the class default sweep" rather than "sweep nothing" — a
        # caller narrowing to one layout passes an explicit one-element tuple instead.
        self.kozak_layouts = kozak_layouts if kozak_layouts is not None else self.KOZAK_LAYOUTS

        # Optional, unlike AntisenseNotGate's required `payload` — a toehold switch is
        # useful to design and rank before an effector gene is chosen, so `None` falls
        # back to today's placeholder behaviour (LINKER_SEQUENCE for "loop", nothing for
        # "trailing") rather than forcing every caller to supply one.
        self.payload: str | None = None
        self.payload_head: str | None = None
        if payload is not None:
            payload_rna = sq.to_rna(payload)
            if not sq.is_valid_rna(payload_rna):
                raise ValueError("payload must be a non-empty RNA or DNA sequence.")
            if payload_rna[:3] != sq.START_CODON:
                raise ValueError(
                    "payload must be a full CDS starting with a start codon, got "
                    f"{payload_rna[:3]!r}."
                )
            self.payload = payload_rna
            # Computed once, not per design: it never varies across generate_designs'
            # sweep, same reasoning as AntisenseNotGate's own payload_head.
            self.payload_head = payload_rna[3 : 3 + self.PAYLOAD_HEAD_LENGTH]

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
        if any(
            t.log2_fold_change is not None and t.log2_fold_change < 0
            for t in trigger_set.activators
        ):
            return Compatibility.no(
                "Down-regulated inputs require a physical inverter for target-state activation."
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

            **Yields rather than returns.** A prokaryotic exact scanned candidate carries
            its mapped gate footprint and yields one matching variant. A manual direct
            candidate, and every eukaryotic candidate regardless of scan status, retain
            the sweep across every fitting toehold length — each variant's
            ``architecture["gate_toehold_length_match"]`` flags whether it is the one the
            RNAplfold scan actually verified, for downstream ranking to weigh. Across
            thousands of trigger sets, the validator will discard most designs.

        Construction (Step 5):
            1. **Binding region** — ``sequences.reverse_complement(trigger.sequence)``.
               This is what the trigger pairs with, and it becomes the toehold plus part
               of the stem.
            2. **Split it.** The first ``toehold_len`` nucleotides stay single-stranded
               as the toehold; the rest forms the ascending side of the stem.
            3. **Loop and Kozak/RBS placement — two layouts, swept via
               ``self.kozak_layouts``:**

               * ``"loop"`` — insert the RBS (prokaryotic) or Kozak context
                 (eukaryotic) in the loop itself, where it is accessible in the OFF
                 state. Borrowed unmodified from the prokaryotic steric-occlusion
                 mechanism; see ``KOZAK_LAYOUTS``'s own docstring for why it is marked
                 unvalidated for a eukaryotic toehold specifically.
               * ``"trailing"`` (eukaryotic only) — the loop carries no conserved
                 element and is free-length (``TRAILING_LOOP_LENGTHS``); Kozak and the
                 start codon are appended *after* the fully closed hairpin instead,
                 optionally behind a short spacer (``KOZAK_LINKER_LENGTHS``). The
                 mechanism this models is scanning-ribosome blockage
                 (docs/modalities.md): the hairpin, not the AUG's own accessibility,
                 is what a trigger has to open.

               A prokaryotic host always builds ``"loop"`` only, regardless of
               ``self.kozak_layouts`` — Shine-Dalgarno initiation has no scanning
               phase for a downstream hairpin to block.
            4. **Descending stem.** Complementary to the ascending side. For
               ``"loop"``, it contains the start codon so it is sequestered until the
               stem opens; for ``"trailing"``, the equivalent bulge position carries
               the trigger-derived complement instead, since the start codon has moved
               downstream of the whole hairpin.
            5. **Linker.** In frame, joining the switch to the payload. Keep it low in
               structure and free of stop codons; ``codons`` can rewrite it if it
               interferes.
            6. **Target structure.** Emit the dot-bracket the design is *meant* to fold
               into. The validator compares against it, so a design without one cannot be
               checked.

            For a manual direct candidate, or any eukaryotic candidate, vary
            ``toehold_lengths`` (and, for ``"trailing"``, ``TRAILING_LOOP_LENGTHS`` x
            ``KOZAK_LINKER_LENGTHS`` too) and yield one design per combination — a
            RNAplfold-verified footprint narrows *which* trigger window was scanned, not
            which built toehold length will initiate best once Kozak/the leader and the
            payload are attached, so eukaryotic hosts keep exploring the whole tuple. Only
            a prokaryotic exact scanned candidate uses its one mapped length; widening
            ``toehold_lengths`` does not multiply that candidate's designs. Ranking the
            results, across layouts included, is ``engine.scoring``'s job (``CLAUDE.md``
            §3): this method emits every combination it can build, not the ones it judges
            best.

        Note:
            Legacy/manual variants from the same trigger differ only in these swept
            parameters, so they share most of their sequence. That is precisely why
            ``FoldEngine`` caches:
            the validator will fold overlapping sequences repeatedly.

        Deviations from the source generator (see the port's open questions):
            * ``STEM_PRE_BULGE_LEN``/``STEM_POST_BULGE_LEN`` stay fixed at the source
              generator's defaults for every swept ``toehold_length``; only the toehold
              itself grows or shrinks. Any reverse-complemented trigger nucleotides beyond
              ``toehold_length + STEM_PRE_BULGE_LEN + 3 + STEM_POST_BULGE_LEN`` are simply
              unused for that variant, rather than the stem scaling to consume the whole
              binding region the way the source generator's single fixed-length trigger did.
            * The loop's undesigned nucleotides (the ``"loop"`` layout's filler beyond
              the RBS/Kozak length, and the whole loop for ``"trailing"``) are a fixed,
              non-repeating placeholder, not solved by a sequence-design optimizer the
              way the source generator's NUPACK ``tube_design`` call would.
            * The ``"trailing"`` layout itself is not part of the source generator at
              all — it was not in scope for this port until the discrepancy against the
              team's own eukaryotic scripts (``plasmid_prefix + trg_bind_region + loop +
              stem_down + kozak``, Kozak last) surfaced it. It is new, unreviewed
              science — see this method's own construction notes above and
              ``evaluate_design``'s note on the leakage proxy it needs.
            * The construct stops at the linker. The source generator fused a specific
              downstream gene onto the same output string; ``ToeholdGate.__init__`` is
              given no payload (unlike ``AntisenseNotGate``, which takes one), and
              ``SegmentKind`` treats ``SWITCH`` and ``PAYLOAD`` as separate plasmid
              segments — so the payload is attached later, at plasmid assembly, not here.
        """
        trigger = trigger_set.activators[0]
        binding_region = sq.reverse_complement(trigger.sequence)

        layouts = self.kozak_layouts if self.host.track is Track.EUKARYOTIC else ("loop",)

        # A prokaryotic scanned stage-2 candidate names one exact gate footprint, so it
        # yields one matching toehold variant. Legacy/manual direct candidates, and every
        # eukaryotic candidate regardless of scan status, keep the full sweep: the
        # scanned footprint identifies the trigger window RNAplfold verified as open, not
        # which toehold length will fold and initiate best against Kozak/the leader once
        # built — that is still an open question the eukaryotic layouts are meant to
        # explore, not one this evidence has settled.
        toehold_lengths = (
            (trigger.gate_toehold_length,)
            if trigger.gate_toehold_length is not None and self.host.track is not Track.EUKARYOTIC
            else self.toehold_lengths
        )
        for toehold_length in toehold_lengths:
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

            for layout in layouts:
                if layout == "loop":
                    variants = [self._build_loop_kozak_design(a_domain, b_pre, b_bulge, b_post)]
                elif layout == "trailing":
                    variants = list(
                        self._build_trailing_kozak_designs(a_domain, b_pre, b_bulge, b_post)
                    )
                else:
                    raise ValueError(f"Unknown kozak_layouts entry: {layout!r}")

                for switch, dot_bracket, architecture in variants:
                    if len(switch) > constraints.max_switch_length:
                        continue
                    architecture["toehold_length"] = toehold_length
                    architecture["trigger_footprint_length"] = footprint
                    architecture["trigger_orientation"] = "transcript_forward"
                    architecture["gate_toehold_length_match"] = (
                        toehold_length == trigger.gate_toehold_length
                        if trigger.gate_toehold_length is not None
                        else None
                    )
                    design_id = (
                        f"{self.design_prefix}-{trigger.trigger_id}-{toehold_length}-{layout}"
                    )
                    if layout == "trailing":
                        design_id += (
                            f"-{architecture['loop_len']}-{architecture['kozak_linker_len']}"
                        )
                    yield GateDesign(
                        design_id=design_id,
                        gate_kind=self.kind,
                        host=self.host,
                        trigger_set=trigger_set,
                        sequence=switch,
                        dot_bracket=dot_bracket,
                        architecture=architecture,
                    )

    def _build_loop_kozak_design(
        self, a_domain: str, b_pre: str, b_bulge: str, b_post: str
    ) -> tuple[str, str, dict]:
        """The ``"loop"`` layout: RBS/Kozak in the loop, start codon in the stem.

        Construction unchanged from before ``"trailing"`` existed, except the tail
        after the start codon: the real payload's own first ``PAYLOAD_HEAD_LENGTH``
        nucleotides when ``self.payload`` is set, else the unengineered
        ``LINKER_SEQUENCE`` placeholder as before — see ``PAYLOAD_HEAD_LENGTH``'s
        docstring and ``generate_designs``'s construction notes.
        """
        leader = self._leader_sequence()
        loop = self._loop_element()
        tail = self.payload_head if self.payload_head is not None else self.LINKER_SEQUENCE

        switch = (
            leader
            + a_domain
            + b_pre
            + b_bulge
            + b_post
            + loop
            + sq.reverse_complement(b_post)
            + sq.START_CODON
            + sq.reverse_complement(b_pre)
            + tail
        )

        aug_index = (
            len(leader)
            + len(a_domain)
            + self.STEM_PRE_BULGE_LEN
            + 3
            + self.STEM_POST_BULGE_LEN
            + len(loop)
            + self.STEM_POST_BULGE_LEN
        )
        dot_bracket = (
            "." * len(leader)
            + "." * len(a_domain)
            + "(" * self.STEM_PRE_BULGE_LEN
            + "." * 3
            + "(" * self.STEM_POST_BULGE_LEN
            + "." * len(loop)
            + ")" * self.STEM_POST_BULGE_LEN
            + "." * 3
            + ")" * self.STEM_PRE_BULGE_LEN
            + "." * len(tail)
        )
        architecture = {
            "stem_pre_bulge_len": self.STEM_PRE_BULGE_LEN,
            "stem_post_bulge_len": self.STEM_POST_BULGE_LEN,
            "loop_len": len(loop),
            "leader_len": len(leader),
            "linker_len": len(tail),
            "payload_head_length": len(self.payload_head) if self.payload_head else 0,
            "aug_index": aug_index,
            "track": self.host.track.value,
            "kozak_layout": "loop",
            "kozak_rc_in_toehold": self._kozak_rc_in_toehold(a_domain),
        }
        return switch, dot_bracket, architecture

    def _build_trailing_kozak_designs(
        self, a_domain: str, b_pre: str, b_bulge: str, b_post: str
    ) -> Iterator[tuple[str, str, dict]]:
        """The ``"trailing"`` layout: Kozak and the start codon after the closed hairpin.

        Yields one variant per ``TRAILING_LOOP_LENGTHS`` x ``KOZAK_LINKER_LENGTHS``
        combination — see ``generate_designs``'s construction notes and
        ``KOZAK_LAYOUTS``'s docstring for the mechanism this models and why these two
        are swept rather than fixed.

        Deliberately **no `LINKER_SEQUENCE`** after the start codon, unlike ``"loop"``.
        ``LINKER_SEQUENCE`` is an unengineered spacer inherited unchanged from the
        prokaryotic source generator (its own docstring: "matches the source
        generator's ``linker_pattern`` default") — not something either mechanism
        requires biologically, but harmless to leave in for a layout ported unmodified.
        For eukaryotic cap-dependent scanning specifically, the 40S subunit initiates
        the moment it meets Kozak+AUG; nothing after the AUG plays a role in *finding*
        it, so there is no reason to hold this layout to a leftover prokaryotic
        default. **When ``self.payload`` is set**, the real payload's own first
        ``PAYLOAD_HEAD_LENGTH`` nucleotides are folded in after the start codon instead
        — see ``PAYLOAD_HEAD_LENGTH``'s docstring for why this can change which design
        ranks best. Without one, the switch still stops exactly at the start codon
        (``GateDesign.sequence[aug_index:]`` is just ``"AUG"``); the full payload
        attaches later regardless (``PlasmidBuilder._frame_violations``, which fuses
        from ``aug_index`` onward using the *complete* payload either way — folding in
        only the head here is for realistic evaluation, not a change to what actually
        gets assembled).

        Open question this leaves, not resolved here: ``validate_payload_cds``
        (``stages/plasmids.py``) requires every payload to itself start with a start
        codon, so the fused ORF reads switch-AUG, then the payload's *own* leading AUG
        as an ordinary internal codon — an N-terminal Met before the payload's
        intended sequence. Whether that is acceptable (translation start codons are
        near-universally Met regardless, and N-terminal Met is often cleaved
        post-translationally anyway) or whether the switch's own placeholder AUG
        should instead be dropped in favour of the payload's is a scientific call for
        the team, not decided here.
        """
        leader = self._leader_sequence()
        tail = self.payload_head if self.payload_head is not None else ""
        kozak_rc_in_toehold = self._kozak_rc_in_toehold(a_domain)
        for loop_len in self.TRAILING_LOOP_LENGTHS:
            loop = _filler(loop_len)
            hairpin = (
                a_domain
                + b_pre
                + b_bulge
                + b_post
                + loop
                + sq.reverse_complement(b_post)
                + sq.reverse_complement(b_bulge)
                + sq.reverse_complement(b_pre)
            )
            for kozak_linker_len in self.KOZAK_LINKER_LENGTHS:
                kozak_linker = _filler(kozak_linker_len)
                switch = (
                    leader + hairpin + kozak_linker + self.KOZAK_EUKARYOTIC + sq.START_CODON + tail
                )
                aug_index = (
                    len(leader) + len(hairpin) + kozak_linker_len + len(self.KOZAK_EUKARYOTIC)
                )
                dot_bracket = (
                    "." * len(leader)
                    + "." * len(a_domain)
                    + "(" * self.STEM_PRE_BULGE_LEN
                    + "." * 3
                    + "(" * self.STEM_POST_BULGE_LEN
                    + "." * loop_len
                    + ")" * self.STEM_POST_BULGE_LEN
                    + "." * 3
                    + ")" * self.STEM_PRE_BULGE_LEN
                    + "." * kozak_linker_len
                    + "." * len(self.KOZAK_EUKARYOTIC)
                    + "." * len(sq.START_CODON)
                    + "." * len(tail)
                )
                architecture = {
                    "stem_pre_bulge_len": self.STEM_PRE_BULGE_LEN,
                    "stem_post_bulge_len": self.STEM_POST_BULGE_LEN,
                    "loop_len": loop_len,
                    "kozak_linker_len": kozak_linker_len,
                    "leader_len": len(leader),
                    "linker_len": len(tail),
                    "payload_head_length": len(self.payload_head) if self.payload_head else 0,
                    "aug_index": aug_index,
                    "track": self.host.track.value,
                    "kozak_layout": "trailing",
                    "kozak_rc_in_toehold": kozak_rc_in_toehold,
                }
                yield switch, dot_bracket, architecture

    def _leader_sequence(self) -> str:
        """The unstructured 5' leader ahead of the toehold, dispatched on
        ``self.host.track`` — same pattern as ``_loop_element``'s RBS/Kozak dispatch.

        Not a scientific computation. ``LEADER_SEQUENCE_EUKARYOTIC`` is the actual
        plasmid sequence the human construct attaches before the toehold, so unlike
        ``_loop_element``'s filler it must not be treated as swappable placeholder
        text — see ``LEADER_SEQUENCE_PROKARYOTIC``/``LEADER_SEQUENCE_EUKARYOTIC``'s own
        docstring for why the two are not interchangeable defaults.
        """
        return (
            self.LEADER_SEQUENCE_PROKARYOTIC
            if self.host.track is Track.PROKARYOTIC
            else self.LEADER_SEQUENCE_EUKARYOTIC
        )

    def _kozak_rc_in_toehold(self, a_domain: str) -> bool:
        """Whether the toehold (``a_domain``) contains the reverse complement of
        ``KOZAK_EUKARYOTIC`` — a self-complementarity risk specific to this gate's own
        construction, not a general folding-energy question ``predicted_leakage`` (a
        summary accessibility average) is built to catch reliably at arbitrary position.

        Both layouts place a real Kozak copy somewhere in the switch (loop or trailing
        tail); if the trigger-derived toehold happens to carry Kozak's reverse
        complement, that stretch of toehold is a direct Watson-Crick match for the
        switch's own Kozak and can hybridize to it intramolecularly — competing with (or
        replacing) the designed stem/toehold structure regardless of what the OFF-state
        MFE or accessibility numbers report for the folded ensemble as a whole. Flagged
        here as a structural fact on ``architecture`` (checked wherever the switch's own
        Kozak copy actually is: the loop, or the trailing tail), not folded into
        ``evaluate_design``'s canonical metrics — none of the nine ``DEFAULT_V1`` names
        (``engine/scoring/profiles.py``) represent a self-complementarity flag, and
        that vocabulary is shared by every gate family, not this one's to extend
        unilaterally. Surfaced as data for ``engine.scoring`` (or a human) to act on,
        same as this class's other open questions.
        """
        return sq.reverse_complement(self.KOZAK_EUKARYOTIC) in a_domain

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
            * ``predicted_leakage`` — a proxy for OFF-state translation, **and the proxy
              itself depends on ``design.architecture["kozak_layout"]``** (same metric
              name, two different biological events, per ``CLAUDE.md`` §6's own warning
              about this metric specifically):

              * ``"loop"`` — the accessible fraction of the **start codon** in the OFF
                ensemble: base-pair probabilities from ``folder``, read at the AUG. A
                start codon never quite sequestered is a leaky switch.
              * ``"trailing"`` — the AUG sits *outside* the hairpin here (see
                ``generate_designs``), so AUG-region accessibility does not discriminate
                ON from OFF — it stays roughly accessible either way, which is a stops-
                discriminating failure of exactly the kind ``CLAUDE.md`` §2 warns about
                if reused unmodified. Read instead at the **toehold+stem region**: how
                often the blocking hairpin itself fails to stay formed. Unreviewed
                science — flagged, not silently chosen; see the port's open questions.
              * **Eukaryotic track only** (either layout), when
                ``architecture["kozak_rc_in_toehold"]`` is ``True``: reported as the
                worst-case ``1.0`` instead of the measured value. ``_mean_unpaired``
                sums each footprint position's pairing probability against *every*
                other position in the switch, Kozak included — so a toehold that
                closed against the switch's own downstream Kozak copy instead of its
                intended stem partner reads as *low* (good-looking) accessibility, not
                high. The proxy cannot tell a properly-closed hairpin from a
                Kozak-hijacked one; since the flag can, prefer distrust over a number
                that may only look good because it measured the wrong closure.
                Prokaryotic designs are exempt: the flag itself is still computed for
                them (``_build_loop_kozak_design`` doesn't branch on track), but it
                checks for ``KOZAK_EUKARYOTIC``'s reverse complement — meaningless
                against an RBS-carrying loop, since there is no Kozak copy anywhere in
                a prokaryotic switch to hijack. See ``_kozak_rc_in_toehold``.
            * ``dynamic_range`` — ON over OFF, using whichever region ``predicted_leakage``
              above measured for this design's layout. Derived from the difference
              between the two accessibilities, not the two energies; energy difference is
              not linear in expression.
            * ``trigger_accessibility`` — already measured in stage 2 and carried on the
              trigger. Read it, do not recompute it, or the two disagree.
            * ``translation_score`` — ``self.translation.score(...)`` at the start codon.

        Gotcha:
            Fold the ON state as a **dimer** (``cofold`` with the ``&`` separator), not as
            a concatenated single strand. Concatenation gives a plausible-looking number
            that means nothing.

        Emits ``gate_folding_energy``, ``predicted_leakage``, ``dynamic_range``,
        ``trigger_accessibility``, ``gc_content``, ``predicted_success_rate``,
        ``state_separation`` and ``circuit_complexity``.

        ``translation_score`` is not a legal ``evaluate_design`` key (it is a
        ``GateDesign`` field filled elsewhere, not a profile metric) and is not computed
        here; ``self.translation`` (``TranslationScorer.score``) is not called because it
        still raises ``NotImplementedError``. ``predicted_success_rate`` no longer waits
        on it — it is the shared binding sigmoid
        (``engine.gates.tools.binding.binding_energy_factor``) over
        ``hybridization_energy``, the same scale ``AntisenseNotGate`` reports on, so the
        two chemistries stay comparable.

        ``orthogonality`` is **not** emitted, and not because it is unfinished. It is
        declared as independence *from other gates*; every design this family can build
        is single-input, so there is no other gate in the circuit to be independent of,
        and the quantity does not exist to be measured. A number here — 1.0 for "nothing
        to clash with", or a self-dimerisation figure wearing the name — would be a
        different quantity under a metric name the profile already defines, which is the
        failure CLAUDE.md §2 is about. It stays absent, and its spec carries
        ``missing_behavior=SKIP`` so an inapplicable metric costs a design nothing.
        """
        switch = design.architecture.get("evaluation_sequence", design.sequence)
        trigger = design.trigger_set.activators[0]
        layout = design.architecture.get("kozak_layout", "loop")

        off_matrix = self.folder.base_pair_probabilities(switch)
        on_matrix = self.folder.base_pair_probabilities(f"{switch}&{trigger.sequence}")

        if layout == "trailing":
            # The blocked-scanning mechanism: what matters is whether the *hairpin*
            # stays closed, not the (always-accessible) AUG downstream of it. Measured
            # over the toehold+stem span — the region generate_designs actually folds
            # into a hairpin for this layout.
            region_start = design.architecture["leader_len"]
            region_end = region_start + (
                design.architecture["toehold_length"]
                + design.architecture["stem_pre_bulge_len"]
                + 3
                + design.architecture["stem_post_bulge_len"]
            )
        else:
            aug_index = design.architecture["aug_index"]
            region_start, region_end = aug_index, aug_index + 3

        off_accessibility = _mean_unpaired(off_matrix, region_start, region_end)
        on_accessibility = _mean_unpaired(on_matrix, region_start, region_end)

        # Extra step, eukaryotic only: _kozak_rc_in_toehold checks for
        # KOZAK_EUKARYOTIC's reverse complement specifically, which is meaningless for
        # a prokaryotic switch — its loop carries an RBS, not a Kozak, so there is no
        # Kozak copy anywhere downstream for the toehold to hijack. Gating on host
        # track (not just the flag) keeps this general evaluate_design — shared by
        # every track and by ProkaryoticToeholdGate/ProkaryoticToeholdAndGate — from
        # scoring prokaryotic designs against a motif their construction never places.
        if design.architecture.get("kozak_rc_in_toehold") and self.host.track is Track.EUKARYOTIC:
            # See this method's own docstring: a Kozak-hijacked closure reads as low
            # (good) accessibility here, indistinguishable from a properly-closed
            # hairpin. Report the worst case instead of a number that may only look
            # good because it measured the wrong partner.
            off_accessibility = 1.0

        activators = design.trigger_set.activators
        return {
            "gate_folding_energy": self.folder.mfe(switch).energy,
            "predicted_leakage": off_accessibility,
            "dynamic_range": on_accessibility / max(off_accessibility, 1e-3),
            "trigger_accessibility": trigger.accessibility,
            "gc_content": sq.gc_content(design.sequence),
            "predicted_success_rate": weakest_binding_confidence(
                switch, [t.sequence for t in activators], self.folder
            ),
            "state_separation": self.state_separation(activators),
            "circuit_complexity": self.component_count(len(activators)),
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
    #: 0.3.0: `generate_designs`, `measure_design` and `evaluate_design` have bodies, the
    #: initiation rules match the architecture spec, the RNase E pattern left the hard screen
    #: and trigger B's window is screened. Every one of those moves the numbers, so the label
    #: moves with them -- a stored result from 0.2.0-stub is not comparable with one from here.
    #:
    #: 0.4.0: 45 columns ADDED and none moved. The x* partner breakdown became a closed
    #: seven-term accounting in all four states (free, own arm, trigger A, trigger B, linker,
    #: secondary_z, residual -- verified to sum to 1.0 within 1e-6 on real designs of both
    #: geometries), hairpin fidelity is measured in states 01, 10 and 11 as well as 00, and
    #: `lock_minus_a_site` is carried unranked. Each is a read off a pair-probability matrix
    #: the pass already built, so nothing refolds and no existing number changes -- the engine's
    #: state-00 fidelity agrees with `objective_energy`'s independent derivation to three
    #: decimals on all five terms. The label still moves, because a 0.3.0 row has no
    #: `hairpin_*_10` column at all and absent must not read as unmeasured.
    #: 0.5.0: the stem selection rule and four new columns. `stem_order="front_tops"` takes one
    #: stem per non-empty 3x3 square plus the strongest stem on each of the THREE Pareto axes,
    #: gives up an empty square's slot instead of filling it from the lock edge, and has no
    #: quota -- the count follows the data (measured: 7 of 9 squares occupied, median, so about
    #: 10 stems). That changes WHICH designs exist for a pair, so results are not comparable
    #: across the label. `mainpre_engA_{state}` is additive and free.
    version = "0.6.0"
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
    #: Sequence patterns that disqualify a trigger window outright. **Every one of them has
    #: to discriminate**, and the hit rate per window is what decides that. Measured over
    #: 4,308 bundled *E. coli* transcripts (51.9% GC), on 36-nt and 50-nt windows -- the two
    #: trigger footprints:
    #:
    #: ===============  =============  =============
    #: pattern          36-nt windows  50-nt windows
    #: ===============  =============  =============
    #: ``internal_SD``           0.6%           0.8%
    #: ``poly_U``                2.8%           3.9%
    #: ``G_quadruplex``          0.0%           0.0%
    #: ===============  =============  =============
    #:
    #: ``G_quadruplex`` has never fired on any window measured. It stays because it is free
    #: and the failure it guards against is real, but nothing in this repo has tested it.
    #:
    #: **``RNase_E`` was removed, and that is a correction rather than a relaxation.** The
    #: pattern here was ``[AG]AUGA``, which is not the RNase E consensus -- see
    #: ``RNASE_E_CONSENSUS`` for the measured reason the real one cannot be a filter.
    FORBIDDEN_MOTIFS: ClassVar[dict[str, str]] = {
        "G_quadruplex": r"G{3,}[ACGU]{1,7}G{3,}[ACGU]{1,7}G{3,}[ACGU]{1,7}G{3,}",
        "poly_U": r"U{5,}",
        "internal_SD": r"AGGAGG|AAGGAG|GGAGGA",
    }

    #: The RNase E cleavage consensus, ``RN|WUU``: purine, any base, the cut, then A-or-U and
    #: two uridines. From Chao et al. 2017, which mapped ~22,000 sites in vivo by TIER-seq and
    #: describes it as a 2-nt uridine ruler -- the U at +2 from the cut is the determinant.
    #:
    #: **Counted and reported, never filtering**, and the numbers are why. On the same 4,308
    #: transcripts it fires on **39.7% of 36-nt windows and 51.0% of 50-nt windows**: as a
    #: hard screen it would reject half of every trigger B pool, which discriminates nothing.
    #:
    #: Weighting it by accessibility is biologically right -- RNase E cleaves single-stranded
    #: RNA, so a consensus site inside a paired region is not a site -- and it helps without
    #: rescuing it. Measured on the four PFAS targets (83 sites in ggt, fadB, astC, aldA),
    #: requiring P(unpaired) at the cut above 0.3 / 0.5 / 0.7 / 0.9 leaves 70 / 60 / 40 / 16
    #: of those sites, and the per-window rejection rate only falls from 37.6% / 49.0% to
    #: 8.1% / 11.5% at the strictest floor. One window in nine is still too many to discard
    #: for a motif whose effect depends on context this screen cannot see.
    #:
    #: ``stages/motifs.py`` left RNase E out of the shared screener for the same reason,
    #: stated there before this was measured: the real determinant "needs structure and does
    #: not belong in a sequence screener".
    RNASE_E_CONSENSUS: ClassVar[str] = r"[AG][ACGU][AU]UU"

    #: Offset of the cut within ``RNASE_E_CONSENSUS``: between positions 2 and 3, so index 2
    #: is the first base 3' of the cut and index 3 is the U at +2 that the ruler reads.
    RNASE_E_CUT_OFFSET: ClassVar[int] = 2

    #: *E. coli* rare codons. A negative control may not introduce one: it has to differ
    #: from the real construct in whether the trigger works, not in how well it translates.
    #: Codons rare enough in *E. coli* to stall a ribosome, **arbitrated by the bundled
    #: usage table rather than by preference** (``notebooks/toehold_and/data/
    #: ecoli_codon_usage_table.csv``). Two sets existed -- these five, and the notebook
    #: objective's eight -- so the table was asked which codons actually qualify. The five
    #: span fraction 0.04-0.11 of their own amino acid and 2.1-6.8 occurrences per 1000.
    #: Applying that same threshold (fraction <= 0.11 AND <= 6.8 per 1000) to all 64 codons
    #: returns exactly these five plus **CGG** (0.11, 5.9) and nothing else. Of the other
    #: two contested codons, CCC (0.13, 5.4) is outside on fraction and UCG (0.14, 8.5) is
    #: outside on both -- and UCG fired on 0 of 4,352 designs. Four of the six are arginine,
    #: which is the classically troublesome amino acid in *E. coli*.
    #:
    #: **Flagged and counted, never filtered.** They are enriched among the designs the
    #: folding score likes, because AGG and CGG are G-rich and so strengthen pairing: the
    #: model rewards what the cell punishes. That is a reason to see the number beside a
    #: design, not to drop it.
    RARE_CODONS: ClassVar[frozenset[str]] = frozenset({"AGG", "AGA", "CGA", "AUA", "CUA", "CGG"})

    #: The Shine-Dalgarno core screened for OUTSIDE the main loop. A second ribosome
    #: binding site anywhere else would recruit initiation away from the designed one.
    #: Six nucleotides by decision: measured over 2,176 designs, the full
    #: ``AACAGAGGAGA`` and this 6-mer each occur outside the loop in **0**, while the
    #: 5-mer ``GGAGG`` occurs in **704 (32.4%)** -- a 5-mer appears by chance in a GC-rich
    #: switch, so screening on it rejects a third of the population and measures nothing.
    RBS_CORE: ClassVar[str] = "AGGAGA"

    def find_cross_gene_pairs(
        self,
        gene_a: str,
        transcript_a: str,
        gene_b: str,
        transcript_b: str,
    ) -> Iterator["_CrossGenePair"]:
        """Every maximal reverse-complementary run shared by two transcripts, both roles.

        The cross-gene counterpart of ``find_trigger_pairs``. Same seeding and extension --
        index every ``MIN_OVERLAP``-mer of one sequence, walk the other, grow each seed while
        the bases keep pairing -- with two differences that follow from there being two
        molecules:

        * **No within-gene matches.** They are not wanted: two windows on one mRNA are one
          transcript's presence reported twice, not a two-input measurement.
        * **No gap rule.** ``MIN_WINDOW_GAP`` exists because two windows on one transcript
          can overlap each other. On separate transcripts they cannot, so there is nothing
          to space apart.

        Args:
            gene_a, transcript_a: The gene whose run is read as ``x``. RNA uppercase.
            gene_b, transcript_b: The gene whose run is read as ``x*``.

        Yields:
            Two records per run -- one per role assignment, the second from ``swapped()``.
            A run is symmetric; the construct built on it is not, since trigger A's footprint
            reaches ``ARM_LEN`` upstream of the overlap and trigger B's reaches
            ``TOEHOLD_B_LEN`` downstream. Only pairs whose **both** footprints fit inside
            their own transcript are yielded.

            Each run is reported at its **maximal** length only, for the reason
            ``find_trigger_pairs`` gives: a truncated overlap is strictly dominated, because
            both footprints are the same size regardless and a shorter ``x`` only moves
            positions out of the conflict-free core.

        Note:
            **Motif screening is not applied here**, exactly as in ``find_trigger_pairs``:
            this is geometry, and a screen needs ``screen_trigger_pair``. One scan is
            ``O(n_a + n_b)``, so a caller enumerating genes needs only ``j > i`` -- scanning
            the other order finds the same runs and both assignments already come out of
            this one.
        """
        rna_a, rna_b = sq.to_rna(transcript_a), sq.to_rna(transcript_b)
        n_a, n_b = len(rna_a), len(rna_b)
        k = self.MIN_OVERLAP

        index: dict[str, list[int]] = {}
        for j in range(n_b - k + 1):
            index.setdefault(rna_b[j : j + k], []).append(j)

        seen: set[tuple[int, int, int]] = set()
        for i in range(n_a - k + 1):
            for j in index.get(sq.reverse_complement(rna_a[i : i + k]), ()):
                start_x, start_xs, length = i, j, k
                # Extending x 3'-ward in A walks its partner 5'-ward in B: antiparallel.
                while (
                    length < self.SECONDARY_INVASION_LEN
                    and start_x + length < n_a
                    and start_xs > 0
                    and rna_b[start_xs - 1] == sq.reverse_complement(rna_a[start_x + length])
                ):
                    start_xs -= 1
                    length += 1
                while (
                    length < self.SECONDARY_INVASION_LEN
                    and start_x > 0
                    and start_xs + length < n_b
                    and rna_b[start_xs + length] == sq.reverse_complement(rna_a[start_x - 1])
                ):
                    start_x -= 1
                    length += 1
                seen.add((start_x, start_xs, length))

        for start_x, start_xs, length in sorted(seen):
            pair = _CrossGenePair(
                gene_a=gene_a,
                gene_b=gene_b,
                x_start=start_x,
                xstar_start=start_xs,
                len_x=length,
                arm_len=self.ARM_LEN,
                invasion_len=self.SECONDARY_INVASION_LEN,
                toehold_b_len=self.TOEHOLD_B_LEN,
            )
            if pair.fits(n_a, n_b):
                yield pair
            flipped = pair.swapped()
            if flipped.fits(n_b, n_a):
                yield flipped

    def screen_trigger_window(self, window_a: str, main_pre: str | None = None) -> tuple[str, ...]:
        """Sequence restrictions on ONE trigger window. Empty means clean.

        Args:
            window_a: The window's full footprint on the transcript.
            main_pre: The 9 nt immediately 5' of the overlap, for trigger A only. Omitted
                for trigger B, whose bases never enter a reading frame -- see
                ``screen_trigger_pair``.

        Returns:
            The name of every violated restriction, in declaration order.

        Note:
            ``main_pre`` is checked for a stop codon **in its own frame**, read from its
            own 5' end. In the finished switch it lands at +4…+12, codons 2 to 4 of the
            output protein, so its frame there is set by the switch's start codon and not
            by the frame it happens to occupy in the transcript it was taken from.

            These bases belong to the gene being sensed. **Nothing downstream can edit
            them** -- not a wobble substitution, not a synonymous rewrite -- because we do
            not synthesise the transcript. That is what makes this a screen and not a
            repair: measured on 1,200 mCherry pairs, 24.1% carry a motif hit on one window
            or the other and none of them is fixable. A motif in the SWITCH is a different
            matter, and there 43.3% of the offending positions are A or C and so have a
            G·U alternative.
        """
        rna = sq.to_rna(window_a)
        hits = [name for name, pattern in self.FORBIDDEN_MOTIFS.items() if re.search(pattern, rna)]
        if main_pre is not None:
            pre = sq.to_rna(main_pre)
            if any(pre[i : i + 3] in sq.STOP_CODONS for i in (0, 3, 6)):
                hits.append("in_frame_stop")
        return tuple(hits)

    def stop_rescue_cost(self, main_pre: str) -> int | None:
        """Wobble substitutions needed to clear every in-frame stop in ``main_pre``.

        ``main_pre`` is the 9 nt immediately 5' of the overlap in trigger A, and it becomes
        codons 2 to 4 of the output protein, so a stop among them truncates the reporter.
        **That is a reason to price the repair, not to drop the pair** -- it was the largest
        single rejection at step 1 (2,012 of 3,967 on ggt+fadB) and every one of those
        rejections was avoidable.

        ``main_pre`` pairs with ``main_pre_star`` in the main stem, so a base can be changed
        while the pair survives as a G·U wobble. Exactly two moves exist: a base opposite U
        may go ``A->G``, and a base opposite G may go ``C->U``. G and U have no alternative.
        Applied to the three stop codons:

        ======  ==========================================  ==============
        codon   repair                                      substitutions
        ======  ==========================================  ==============
        ``UAG``  ``A->G`` at position 2 gives ``UGG`` (Trp)   1
        ``UGA``  ``A->G`` at position 3 gives ``UGG`` (Trp)   1
        ``UAA``  either ``A->G`` alone gives another stop;
                 both together give ``UGG``                   2
        ======  ==========================================  ==============

        Measured over the three PFAS gene pairs, 58.8% / 62.0% / 67.2% of the stops cost one
        substitution and the remainder cost two; 3-5% of affected pairs carry more than one
        stop. **Every stop is rescuable** -- this returns what it costs.

        Returns:
            ``0`` when there is no stop, else the total number of substitutions. A UAA
            costing two matters because two wobbles in a 9-nt stem region is a real
            weakening, and the design stage may still decline it. ``None`` when
            ``main_pre`` is not 9 nt, which is not a measurement.

            **Nothing enforces a ceiling on that cost today.** This prices the repair; no
            caller refuses a price. An earlier draft of ``LOWER3`` named a
            ``GRIP_BREAK_MAX`` for it, and that constant was never written -- see
            ``LOWER3``, where the levels it was meant to govern are also gone.
        """
        pre = sq.to_rna(main_pre)
        if len(pre) != 9:
            return None
        cost = 0
        for i in (0, 3, 6):
            codon = pre[i : i + 3]
            if codon in ("UAG", "UGA"):
                cost += 1
            elif codon == "UAA":
                cost += 2
        return cost

    def screen_trigger_pair(self, window_a: str, window_b: str, main_pre: str) -> tuple[str, ...]:
        """What is wrong with a trigger pair that can be known from the windows alone.

        **This no longer screens for motifs, and that is a correction.** It used to run
        ``FORBIDDEN_MOTIFS`` over the two windows as they sit in the *E. coli* gene. Most of
        what reaches the switch is the REVERSE COMPLEMENT of those bases -- ``r2_star`` is
        revcomp of trigger B's ``r2``, ``k1_star`` and ``main_pre_star`` are revcomp of
        trigger A's -- so the gene window is the wrong molecule to read. Trigger B is the
        clearest case: none of B appears forward anywhere in the switch, so every rejection
        on B's window was for a pattern the construct does not contain.

        The screen cannot be completed here in any case. ``k2_star`` and ``secondary_z`` come
        from the stem solver, which has not run, and a motif can straddle a domain junction
        that exists only once assembled. So motifs are screened on the finished switch by
        ``assembly_violations``, and this returns what the windows really do determine.

        Returns:
            ``()`` when nothing is wrong. A stop codon in trigger A's ``main_pre`` is
            reported as ``A:stop_in_main_pre:<n>``, where ``n`` is the number of wobble
            substitutions that clears it -- see ``stop_rescue_cost``. **It is a flag and the
            caller decides**; the pair is not unusable.
        """
        cost = self.stop_rescue_cost(main_pre)
        if cost:
            return (f"A:stop_in_main_pre:{cost}",)
        return ()

    def rnase_e_sites(
        self, window: str, openness: list[float] | None = None, floor: float = 0.0
    ) -> tuple[int, ...]:
        """Positions in ``window`` matching the RNase E consensus. Reported, never filtering.

        Args:
            window: A trigger window, RNA uppercase.
            openness: Per-base unpaired probability for ``window``, aligned to it, when the
                caller wants only sites the enzyme could actually reach. RNase E cleaves
                single-stranded RNA, so a consensus site inside a paired region is not a
                site. One RNAplfold pass per transcript covers every window on it --
                measured at 1.56 s for the pass and 1.5 microseconds per window after it --
                so asking for this costs nothing per pair.
            floor: Minimum P(unpaired) at the cut. Ignored without ``openness``.

        Returns:
            The start index of each match, so a caller can report both the count and where.
            See ``RNASE_E_CONSENSUS`` for why this is a count and not a rejection.
        """
        rna = sq.to_rna(window)
        found: list[int] = []
        for match in re.finditer(self.RNASE_E_CONSENSUS, rna):
            at = match.start()
            if openness is not None:
                cut = at + self.RNASE_E_CUT_OFFSET
                if cut >= len(openness) or openness[cut] <= floor:
                    continue
            found.append(at)
        return tuple(found)

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
        # `arm` slices the MAIN hairpin out of trigger A; `len_k2` is trigger B's
        # invasion domain on the SECONDARY arm, which is where r2 begins. One constant
        # served both while the two hairpins were the same length.
        arm, len_k2 = self.ARM_LEN, self.SECONDARY_INVASION_LEN - len_x
        pre_bulge, post_bulge = self.STEM_PRE_BULGE_LEN, self.STEM_POST_BULGE_LEN
        rna_a, rna_b = sq.to_rna(trigger_a), sq.to_rna(trigger_b)

        k1 = rna_a[:post_bulge]
        bulge = rna_a[post_bulge : post_bulge + self.BULGE_LEN]
        main_pre = rna_a[post_bulge + self.BULGE_LEN : arm]
        x = rna_a[arm : arm + len_x]
        # Bounded to `TOEHOLD_B_LEN`, not "whatever is left of trigger B". The open slice
        # made the switch's length a function of the trigger WINDOW's length: a 50-nt
        # window in Kim geometry (which wants 49) produced a 33-nt r2 and a 166-nt switch
        # against the 165 the assertion below expects, so a scanner offering one window
        # size for both geometries crashed on one of them. `len_k2 + len_x` is
        # `SECONDARY_INVASION_LEN`, so for an exactly-sized trigger B this slice is a
        # no-op and no existing design changes; it only discards bases a longer window
        # supplied and this architecture has no domain for.
        r2 = rna_b[len_k2 + len_x :][: self.TOEHOLD_B_LEN]

        rbs_loop = self.RBS_FLANK + self.RBS_PROKARYOTIC
        main_z = self._repair_main_z(k1, rbs_loop)
        pieces = [
            # Main's host-dispatched leader, and this branch's trim, because the two sides of
            # this conflict were each right about a different line. `_leader_sequence()` picks the
            # prokaryotic or eukaryotic leader off `host.track`, which the class constant could
            # not; and the `TOEHOLD_TRIM` slice is what `TrimmedToeholdAndGate` (TOEHOLD_TRIM = 8)
            # relies on -- the length assertion below already subtracts it, so dropping the slice
            # would make the assembled length disagree with the expected one for that subclass.
            ("cap", self._leader_sequence()),
            ("r2_star", sq.reverse_complement(r2)[self.TOEHOLD_TRIM :]),
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
            len(self._leader_sequence())
            + self.TOEHOLD_B_LEN
            - self.TOEHOLD_TRIM
            # The SECONDARY hairpin's two arms: sw_x + k2_star and secondary_z + sw_xs, each
            # summing to SECONDARY_ARM_LEN because len_x + len_k2 + len(cap) = invasion + cap
            # = arm. The MAIN hairpin's arms are the pre_bulge/bulge/post_bulge terms below,
            # spelled out separately -- which is why this one must not read ARM_LEN.
            + 2 * self.SECONDARY_ARM_LEN
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
        # **The motif screen belongs here, on the molecule we actually synthesise.** It used
        # to run over the trigger windows as they sit in the gene, which is the wrong
        # sequence: most of what reaches the switch is the reverse complement of those bases,
        # and a motif can straddle a domain junction that exists only after assembly. Both
        # directions of that error were real -- measured on 2,176 built switches,
        # `internal_SD` occurs 384 times here while the window screen was rejecting pairs
        # for patterns the construct never contained.
        faults.extend(
            name
            for name, pattern in self.FORBIDDEN_MOTIFS.items()
            if re.search(pattern, switch.sequence)
        )
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
        # τ3 REPLACED. `A_S_10 < 0.2` was partner-blind: it asked whether x* is unpaired,
        # which cannot distinguish "the lock holds" from "trigger A has taken it". Measured on
        # 712 designs past the ON ceiling, `A_S_10` has a median of **0.0006** and sails
        # through, while `xstar_engA_10` on the same designs has a median of **0.9988** --
        # trigger A alone holding x* almost completely. The leak this gate exists to catch.
        #
        # 0.5 is where the distribution puts it, not a round number: strongly bimodal, with
        # only 7.0% of values between 0.2 and 0.8, so the cut falls in the empty middle. And it
        # is measured for EVERY design now, not only the ones past the ceiling.
        ("xstar_engA_10", "<", 0.5),  # τ3a — trigger A alone must not take x*
        ("mainpre_engA_10", "<", 0.5),  # τ3b — nor reach the main stem's ascending arm
        ("A_M_10", "<", 0.2),  # τ4a — nor the main one. The dangerous leak.
        ("A_M_01", "<", 0.2),  # τ4b — and neither may trigger B, which is the harder test
        ("A_S_01", ">", 0.5),  # τ5  — but trigger B must open the inhibitory hairpin
        # τ6 IS WRONG AS WRITTEN, and the partner-aware terms show it. On a real design
        # (ggt x fadB, len_x 13, open_3x3): A_S_11 = 0.003 so this gate REJECTS it, while
        # xstar_engA_11 = 0.997 -- x* is 99.7% bound to trigger A, which is exactly what the
        # design is for. "x* paired" and "x* paired to A" are indistinguishable to a mean-unpaired
        # measure, so the correct outcome registers as the failure mode.
        #
        # τ3 is blind in the dangerous direction for the same reason: on that design A_S_10 = 0.008
        # passes it easily while xstar_engA_10 = 0.392, so trigger A alone is already taking 39% of
        # the site. A leak this gate exists to catch, and cannot see.
        #
        # The replacement is `xstar_engA_11 > ...` and `xstar_engA_10 < ...`, which is a SCORING
        # change: it needs thresholds set from a measured distribution and a version bump, so it is
        # recorded here rather than made silently. The observables now exist either way.
        # τ6 REMOVED. `A_S_11 > 0.5` asked "is x* open with both triggers present" with a
        # partner-blind measure, which cannot tell "x* is free" from "x* is held by trigger A"
        # -- so the designed outcome registered as the failure mode. Quantified on 712 designs
        # that pass the ON ceiling: `A_S_11` median **0.0003**, so the gate rejected almost
        # everything, while `xstar_engA_11` on the same designs has median **0.9997**.
        #
        # `xstar_engA_11` and `mainpre_engA_11` replace it as OBSERVABLES and deliberately not
        # as a threshold. The sample says they are a mechanism flag rather than a quality
        # filter: the four best-separating designs in it (7.265, 7.149, 7.117, 6.964) all have
        # `xstar_engA_10` at 0.0000 -- the OFF side passing perfectly -- and `xstar_engA_11`
        # between 0.18 and 0.47. They separate the states by a route that is not the designed
        # one, and a floor on `engA_11` would have discarded the best designs in the run.
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
        ext, k2 = _secondary_domains(
            trigger_a, trigger_b, len_x, self.ARM_LEN, self.SECONDARY_INVASION_LEN
        )
        k2_star, secondary_z = _build_arms(ext, k2, {})
        if self.SECONDARY_CAP:
            k2_star += self.SECONDARY_CAP
            secondary_z = sq.reverse_complement(self.SECONDARY_CAP) + secondary_z
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
        # Trigger A's own positions in the concatenation, for the partner-aware terms below.
        # Tubes are built `switch&A&B` and `pooled_pair_probabilities` maps every ordering
        # back onto these positions, so the index does not depend on which one dominates.
        a_block = (len(switch.sequence), len(switch.sequence) + len(trigger_a))
        # Trigger B's block is per STATE, not one offset reused. The tubes are `switch&B` for
        # 01 and `switch&A&B` for 11, so B starts after the switch in one and after trigger A
        # in the other; a single offset would read A's positions as B's in state 11. An absent
        # trigger gets an empty block, and `_mean_paired_to` returns 0.0 for it -- which here
        # is a true measurement, not a sentinel: x* cannot be bound to a strand in another tube.
        base = len(switch.sequence)
        b_blocks = {
            "00": (base, base),
            "01": (base, base + len(trigger_b)),
            "10": (base, base),
            "11": (base + len(trigger_a), base + len(trigger_a) + len(trigger_b)),
        }
        xstar = switch.domains["sw_xs"]
        own_arm = switch.domains["sw_x"]
        main_pre_star = switch.domains["main_pre_star"]
        aug_span = switch.domains["aug"]
        linker = switch.domains["linker"]
        secondary_z = switch.domains["secondary_z"]
        # The RBS-loop-to-linker span, 57 nt. Nothing else covers it: `A_M` is
        # main_z+aug+main_pre and deliberately excludes the ribosome binding site, and the
        # Shine-Dalgarno core alone is 11 nt. The ribosome needs the binding site and the start
        # codon reachable TOGETHER, and that question had no column on this path.
        rbs_linker = (switch.domains["rbs_loop"][0], linker[1])
        # The Shine-Dalgarno core inside the loop, without the designed 5' flank.
        rbs_core = (
            switch.domains["rbs_loop"][0] + len(self.RBS_FLANK),
            switch.domains["rbs_loop"][1],
        )
        duplexes = _intended_duplexes(switch.domains)
        for state, strands in tubes.items():
            # Pooled, not the bare matrix: state 11 has three strands and therefore two
            # orderings, and in "switch&B&A" trigger A's arcs cross trigger B's, so
            # ViennaRNA forbids the both-bound structure and reports an ensemble in which
            # trigger A is not there. Measured, the two orderings disagree by up to 0.997
            # in per-base unpaired probability inside this very window. Writing the
            # strands in the lucky order is not a reason to trust the answer.
            matrix = self.folder.pooled_pair_probabilities(strands)
            for name, (start, end) in spans.items():
                observables[f"{name}_{state}"] = _mean_unpaired(matrix, start, end)
            # Partner-aware, because "x* is open" does not say what it is open FOR.
            # `A_S_{state}` above answers whether; these answer to whom, and this
            # architecture's mechanism is a sequence of answers to the second question:
            # locked with no trigger, still locked with A alone, freed by B, taken by A.
            observables[f"xstar_locked_{state}"] = _mean_paired_to(matrix, xstar, own_arm)
            observables[f"xstar_engA_{state}"] = (
                0.0 if trigger_a not in strands else _mean_paired_to(matrix, xstar, a_block)
            )
            # The SECOND half of the designed ON path, and the one `xstar_engA` cannot see.
            # B frees x*, A nucleates there, and then A invades the main stem's ascending arm:
            # `xstar_engA_11` says A arrived, this says A opened something. Measured per domain
            # on a real design in state 11, trigger A puts 2.98 of 3 expected pairs on the freed
            # x* and 7.97 of 9 on `main_pre_star`. In state 10 the same term is the leak's own
            # measure -- A reaching the main arm with no B present.
            observables[f"mainpre_engA_{state}"] = (
                0.0 if trigger_a not in strands else _mean_paired_to(matrix, main_pre_star, a_block)
            )
            # The AUG's own openness: the base the ribosome has to reach. Not a restatement
            # of `A_M`, which spans main_z through aug to main_pre and averages the bulge in
            # with the arms, so a design with a paired AUG and open arms looks fine there.
            observables[f"aug_{state}"] = _mean_unpaired(matrix, *aug_span)

            # **The strongest single metric anyone has on Green's measured switches**, and it was
            # free: +0.356 on his 168 and +0.390 on his 13, against the Barrier's +0.179/+0.280.
            # Green's own S13 agrees from the other side -- "the RBS/mRNA secondary structure
            # terms constitute the category of parameters with the strongest overall
            # correlation". It is VISTA's Ideal Ensemble Defect over a region whose specified
            # structure is "completely unpaired", which collapses to the mean base-pairing
            # probability there, so it is `1 - mean_unpaired` off a matrix already in hand.
            # LOWER is better, unlike every other mean here -- which is why the reduction
            # is a named tool function rather than an inversion written out here. Written
            # inline it was one measurement with two definitions, and the second copy
            # (`notebooks/.../candidates.py`) was free to disagree about the None case.
            observables[f"ied_rbs_linker_{state}"] = unpaired_defect(matrix, *rbs_linker)
            # The same 31-nt ribosome footprint `dG_open_{state}` prices in energy, as a
            # probability instead. Two statistics over one window, which is the only way to tell
            # whether a window's edge comes from the window or from the statistic.
            observables[f"meanW_{state}"] = _mean_unpaired(matrix, *rank)
            # The Shine-Dalgarno core on its own.
            observables[f"rbs11_mean_{state}"] = _mean_unpaired(matrix, *rbs_core)

            # Where x* goes, as a CLOSED accounting rather than a list of whichever partners
            # happened to clear a display threshold:
            #
            #     free + own_arm + trigger_a + trigger_b + linker + secondary_z + other = 1
            #
            # `free` is `A_S_{state}` and the first two partners are the terms just above, so
            # these four complete the sum. The reason it is worth four columns: "x* freed by B
            # alone" is the weakest term in the lock, and the obvious reading -- that B fails to
            # open it -- is wrong. B releases the secondary stem completely (x*-to-sw_x and
            # x*-to-B both measured at 0.000), and the missing 0.5 to 0.7 goes to the LINKER
            # (0.27 to 0.61) with some of `secondary_z` (0.09 to 0.42). x* is freed and then
            # immediately re-paired, so it is not available for trigger A -- and the linker is a
            # constant we choose, which makes this actionable rather than merely descriptive.
            #
            # `other` is the residual, not a drop: every remaining partner is still counted, so
            # the sum closes and a partner nobody named cannot go missing.
            observables[f"xstar_linker_{state}"] = _mean_paired_to(matrix, xstar, linker)
            observables[f"xstar_sec_z_{state}"] = _mean_paired_to(matrix, xstar, secondary_z)
            observables[f"xstar_engB_{state}"] = _mean_paired_to(matrix, xstar, b_blocks[state])
            free = observables[f"A_S_{state}"]
            if free is None:
                observables[f"xstar_other_{state}"] = None
            else:
                named = (
                    observables[f"xstar_locked_{state}"]
                    + observables[f"xstar_engA_{state}"]
                    + observables[f"xstar_linker_{state}"]
                    + observables[f"xstar_sec_z_{state}"]
                    + observables[f"xstar_engB_{state}"]
                )
                observables[f"xstar_other_{state}"] = (1.0 - free) - named

            # Hairpin fidelity in EVERY state, not only the OFF one. The matrix for this tube is
            # already built, so the other three states cost nothing beyond reading it -- and the
            # question they answer is the mechanism itself: which intended duplex gives way, and
            # to which trigger. `worst` is the minimum rather than the mean, because a hairpin
            # with one arm fully formed and the other absent is not half a hairpin, it is a
            # different structure.
            for name, (left, right) in duplexes.items():
                observables[f"hairpin_{name}_{state}"] = _duplex_formed(matrix, left, right)
            formed = [
                observables[f"hairpin_{name}_{state}"]
                for name in duplexes
                if observables[f"hairpin_{name}_{state}"] is not None
            ]
            observables[f"hairpin_worst_{state}"] = min(formed) if formed else None

            if state == "00":
                toehold = switch.domains["r2_star"]
                observables["A_r2_star_00"] = _mean_unpaired(matrix, *toehold)
                # The same region weighted by closeness to the secondary hairpin, carried
                # BESIDE the flat mean and not instead of it: 346,528 stored rows already
                # hold `A_r2_star_00` under the flat definition, and redefining a name
                # leaves nothing in the data to say which definition produced which row.
                observables["A_r2_star_w_00"] = _mean_unpaired_3prime_weighted(matrix, *toehold)

        # The worst-OFF forms the panel ranks on. Pure arithmetic over values just measured, so
        # there is no second definition of "the OFF state" anywhere and no extra fold. `max` for
        # an accessibility because the worst OFF state is the most open one; `max` for `ied` too,
        # since higher ied means more paired and the worst OFF state is the one that LEAKS, i.e.
        # the least paired -- so that one takes `min`.
        def worst_max(prefix: str) -> float | None:
            values = [observables.get(f"{prefix}_{s}") for s in ("00", "01", "10")]
            present = [v for v in values if v is not None]
            return max(present) if len(present) == len(values) else None

        def gain(prefix: str) -> float | None:
            on, off = observables.get(f"{prefix}_11"), worst_max(prefix)
            return None if on is None or off is None else on - off

        observables["A_M_off"] = worst_max("A_M")
        observables["aug_off"] = worst_max("aug")
        observables["aug_gain"] = gain("aug")
        observables["meanW_off"] = worst_max("meanW")
        observables["meanW_gain"] = gain("meanW")
        # `ied` is lower-better, so its gain is the OFF state MINUS the ON state, and its worst
        # OFF state is the least-paired one.
        ied_off_values = [observables.get(f"ied_rbs_linker_{s}") for s in ("01", "10")]
        ied_present = [v for v in ied_off_values if v is not None]
        observables["ied_off_worst"] = min(ied_present) if len(ied_present) == 2 else None
        observables["ied_gain"] = (
            None
            if observables.get("ied_rbs_linker_00") is None
            or observables.get("ied_rbs_linker_11") is None
            else observables["ied_rbs_linker_00"] - observables["ied_rbs_linker_11"]
        )
        observables["ied_gain_worst"] = (
            None
            if observables["ied_off_worst"] is None or observables.get("ied_rbs_linker_11") is None
            else observables["ied_off_worst"] - observables["ied_rbs_linker_11"]
        )
        # One extra fold, and a tiny one: the MFE of the isolated 57-nt subsequence. +0.334 on
        # G168 by rank and +0.693 by Pearson on G13. A 57-nt fold is milliseconds against about
        # a second for a whole design, so it is affordable where `dG_arm_{state}` and
        # `rbs_aug_open_{state}` -- four constrained folds each -- are not and are left out.
        observables["dG_rbs_linker"] = self.folder.mfe(
            switch.sequence[rbs_linker[0] : rbs_linker[1]]
        ).energy

        observables["d_off"] = self.folder.ensemble_defect(
            switch.sequence, switch.dot_bracket
        ) / len(switch.sequence)

        # Binding energies, as ensemble free-energy differences. Never a bare dG_bind for
        # trigger A: measured against the *bare* switch it rewards A opening the main
        # hairpin on its own, which is exactly the state-10 leak the gates exist to catch,
        # so the score and the gate would pull against each other. A is conditioned on B.
        # `pooled_partition`, not `partition`: state 11 has three strands and therefore two
        # orderings, and ViennaRNA only counts structures non-crossing in the order written.
        # Measured on a real pair, the two orderings of this tube are **12.66 kcal/mol**
        # apart, and on a second pair the same switch came out 5.03 apart with the opposite
        # ordering favoured -- so there is no order a caller can just prefer. Unpooled,
        # `dG_bind_A_given_B` subtracts a two-strand term from a three-strand term folded
        # under a constraint the two-strand term never had, and inherits the whole spread.
        g = {state: self.folder.pooled_partition(strands) for state, strands in tubes.items()}
        observables["dG_bind_B"] = g["01"] - g["00"] - self.folder.pooled_partition(rna_b)
        observables["dG_bind_A_given_B"] = g["11"] - g["01"] - self.folder.pooled_partition(rna_a)
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

    def knockout(
        self, transcript: str, start: int, length: int, partner: str
    ) -> "_Knockout | None":
        """The **fewest** synonymous substitutions that stop this region nucleating.

        A trigger needs at least ``MIN_OVERLAP`` contiguous complementary nucleotides to
        nucleate, so that is the criterion: a knockout is any synonymous variant of the
        region leaving no run that long against its site on the switch. Nothing else about
        the transcript changes, which is what makes the four bench constructs comparable —
        they differ from state 11 only at the trigger being disabled.

        **Minimal substitutions, by instruction** (*"החלפות מינימליות לקודונים דומים"*,
        supervisor, relayed 2026-09-15; the same rule as the .docx's "smallest set of
        synonymous substitutions"). The original sequence is the one with bench data behind
        it, and every edit is a perturbation to local folding and expression, so the control
        spends as few as the criterion allows. Ties — variants with equally few edits — go
        to the one retaining least pairing, which is a refinement rather than a competing
        objective.

        There is deliberately **no cap** on the count. The ported script carried
        ``max_edits=4`` as an undeclared default, which does not make a knockout more
        minimal — it silently refuses regions needing more, a 15-nt perfect duplex among
        them, and reports them as impossible. Minimality is expressed by the search order,
        not by a ceiling.

        A variant is rejected if it changes the protein, introduces a rare codon, or
        introduces a forbidden motif that was not already present: a control that translates
        differently or is cleaved differently tests more than the one variable it isolates.

        Args:
            transcript: The coding sequence, RNA uppercase, in frame from its first base.
            start: 0-based start of the region to disable.
            length: Its length in nucleotides.
            partner: The switch domain this region pairs with, built against the
                **original** sequence, since that is the gate the control is a control for.

        Returns:
            The minimal knockout, or ``None`` when no synonymous variant disables the
            region at all. ``None`` is a real answer: on mCherry 169 of 1,036
            otherwise-valid pairs cannot have either trigger disabled, which is why
            ``controls_constructible`` runs inside the scan.
        """
        rna = sq.to_rna(transcript)
        original_protein = sq.translate(rna, stop_at_stop=False)
        context = slice(max(0, start - 20), start + length + 20)
        candidates = self._recodings(rna, start, length, partner)

        best: _Knockout | None = None
        best_key: tuple[int, int, float] | None = None
        for edits in candidates:
            if not edits:
                continue
            variant = list(rna)
            for position, _, replacement in edits:
                variant[position] = replacement
            candidate = "".join(variant)
            region = candidate[start : start + length]

            residual = longest_complementary_run(region, partner)
            if residual >= self.MIN_OVERLAP:
                continue
            if sq.translate(candidate, stop_at_stop=False) != original_protein:
                continue
            if any(
                re.search(pattern, candidate[context]) and not re.search(pattern, rna[context])
                for pattern in self.FORBIDDEN_MOTIFS.values()
            ):
                continue

            aligned = partner[: len(region)]
            pairable = sum(alignment_pairs(region, aligned))
            energy = fixed_alignment_energy(region, aligned, self.folder)
            # Fewest substitutions first, as instructed; ties go to the variant retaining
            # least pairing, then to the weakest residual duplex (energies are negative, so
            # a larger value is the weaker one).
            key = (len(edits), pairable, -(energy if energy is not None else 0.0))
            if best_key is None or key < best_key:
                best_key = key
                best = _Knockout(
                    edits=edits,
                    sequence=candidate,
                    residual_run=residual,
                    pairable_positions=pairable,
                    residual_energy=energy,
                )
        return best

    def _recodings(
        self, rna: str, start: int, length: int, partner: str, *, beam: int = 24
    ) -> list[tuple[tuple[int, str, str], ...]]:
        """Cheapest synonymous recodings of ``[start, start+length)`` that break every run.

        Brute force is not available here: disabling a whole 36-nt trigger window means
        twelve codons with up to six spellings each, and 6^12 is not a search. But the
        criterion is **local** — no four consecutive positions may all pair — so the cost
        decomposes, and a codon-by-codon dynamic program over "how long is the pairable run
        I am carrying" finds the true minimum in linear time.

        Only positions inside the region may move. A codon straddling the boundary is
        allowed to change only where it overlaps, since R13 confines every edit to a trigger
        window and a substitution outside one alters sequence that has bench data behind it.

        Returns up to ``beam`` edit sets per run-state, cheapest first, so the caller can
        reject any that introduce a forbidden motif and still have alternatives left. Rare
        codons are excluded here rather than filtered later: a control that translates at a
        different rate is testing more than the trigger.
        """
        end = start + length
        first, last = start // 3, (end - 1) // 3
        # state -> list of (cost, edits); state is the trailing pairable-run length.
        paths: dict[int, list[tuple[int, tuple[tuple[int, str, str], ...]]]] = {0: [(0, ())]}

        for codon_index in range(first, last + 1):
            base = codon_index * 3
            original = rna[base : base + 3]
            options = [original, *self._synonymous(original)]
            nxt: dict[int, list[tuple[int, tuple[tuple[int, str, str], ...]]]] = {}
            for option in options:
                if option in self.RARE_CODONS:
                    continue
                # A straddling codon may differ only where it lies inside the region.
                if any(
                    original[offset] != option[offset] and not (start <= base + offset < end)
                    for offset in range(3)
                ):
                    continue
                edits = tuple(
                    (base + offset, original[offset], option[offset])
                    for offset in range(3)
                    if original[offset] != option[offset]
                )
                for state, entries in paths.items():
                    run = state
                    ok = True
                    for offset in range(3):
                        position = base + offset
                        if not (start <= position < end):
                            continue
                        index = position - start
                        if can_pair(option[offset], partner[length - 1 - index]):
                            run += 1
                            if run >= self.MIN_OVERLAP:
                                ok = False
                                break
                        else:
                            run = 0
                    if not ok:
                        continue
                    for cost, taken in entries:
                        nxt.setdefault(run, []).append((cost + len(edits), taken + edits))
            paths = {
                state: sorted(entries, key=lambda item: item[0])[:beam]
                for state, entries in nxt.items()
            }
            if not paths:
                return []

        merged = sorted(
            (entry for entries in paths.values() for entry in entries), key=lambda item: item[0]
        )
        return [edits for _, edits in merged[:beam]]

    def bench_constructs(self, transcript: str, pair: "_TriggerPair") -> dict[str, str | None]:
        """The four logic states as four transcripts on **one background**.

        By instruction — *"לייצר ווראנטים שבהם מוחקים את שני הטריגרים או אחד מהם"*
        (supervisor, relayed 2026-09-15) — the panel is variants of the same transcript with
        **both** triggers deleted or one of them, all by minimal synonymous substitution:

        * ``11`` the unmodified transcript, both triggers intact
        * ``10`` trigger B disabled, so only trigger A is present
        * ``01`` trigger A disabled
        * ``00`` **both disabled** — not the transcript withheld

        That last point differs from ``PIPELINE_CONTEXT.md`` §5.6, which describes state 00
        as "no transcript". Disabling both on one background is the stronger control:
        withholding the transcript also removes its transcriptional and translational load,
        so a difference between 00 and 11 would confound the triggers with the burden of
        expressing the molecule at all. Here every construct has the same length, the same
        abundance and the same protein, and differs only in whether each trigger can
        nucleate.

        Each trigger is attacked at the overlap first, the cheapest and most specific
        target — for trigger A it is the *only* nucleation site, which is what ``a = 0``
        means. Where the codons there do not permit enough change, and with wobbles counted
        they often do not, the invasion arm is the fallback: ``k1`` for trigger A, ``k2``
        for trigger B.

        Returns:
            ``{"11": …, "10": …, "01": …, "00": …}``, with a state mapped to ``None`` when
            no synonymous knockout exists for it. ``00`` is ``None`` whenever either single
            knockout is, since it is the two applied together.
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
        constructs: dict[str, str | None] = {"11": rna}
        # Each knockout is remembered with the region it actually hit. A trigger can be
        # disabled at its overlap *or* at its invasion arm, and re-checking only the overlap
        # would read a perfectly good arm knockout as ineffective.
        applied: dict[str, tuple[tuple[tuple[int, str, str], ...], int, int, str]] = {}
        for state, targets in routes.items():
            constructs[state] = None
            for start, length, partner in targets:
                if start < 0 or length <= 0 or start + length > len(rna):
                    continue
                result = self.knockout(rna, start, length, partner)
                if result is not None:
                    constructs[state] = result.sequence
                    applied[state] = (result.edits, start, length, partner)
                    break

        constructs["00"] = None
        if len(applied) == 2:
            # The windows are disjoint and at least MIN_WINDOW_GAP apart, so the two edit
            # sets cannot collide and both knockouts apply to one sequence unchanged.
            doubled = list(rna)
            for state_edits, _, _, _ in applied.values():
                for position, _, replacement in state_edits:
                    doubled[position] = replacement
            both = "".join(doubled)
            still_dead = all(
                longest_complementary_run(both[start : start + length], partner) < self.MIN_OVERLAP
                for _, start, length, partner in applied.values()
            )
            protein_held = sq.translate(both, stop_at_stop=False) == sq.translate(
                rna, stop_at_stop=False
            )
            if still_dead and protein_held:
                constructs["00"] = both
        return constructs

    def main_stem_energies(
        self, trigger_a: str, len_x: int, main_z: str
    ) -> tuple[float | None, float | None, float | None]:
        """The three energies that decide whether the AND is thermodynamic or only kinetic.

        Trigger A's footprint on the switch runs ``sw_xs · main_pre* · bulge* · k1*``,
        contiguous because ``a = 0``. In state 10 the ``sw_xs`` end is locked inside the
        inhibitory hairpin, so trigger A has only the 18-nt arm to work with; in state 11
        trigger B has freed ``sw_xs`` and trigger A gets ``len_x`` more base pairs, in the
        same helix. So there are exactly three numbers to compare:

        * ``stem`` — the switch's own arm against its own descending copy. What trigger A
          has to beat.
        * ``grip_alone`` — trigger A against the 18-nt arm, which is all it can reach
          without trigger B.
        * ``grip_with_x`` — trigger A against ``sw_xs`` plus the arm, what it reaches once
          trigger B has acted.

        **The window.** Free energies are negative, so a true equilibrium AND needs

            ``grip_with_x  <  stem  <  grip_alone``

        — trigger A loses to the stem by itself and wins with the extra ``len_x`` pairs.
        As designed today ``k1* = revcomp(k1)``, so trigger A is complementary to all 18
        and ``grip_alone`` beats ``stem`` outright: measured -30.5 against -23.9, a 6.6
        kcal/mol surplus, which is the state-10 leak. ``mainZ`` is the only free sequence
        in that arm, and ``k1* = revcomp(mainZ)``, so choosing ``mainZ`` moves
        ``grip_alone`` and ``stem`` together and is the one lever available.

        No folding: three fixed-alignment duplex energies, so a 4096-way sweep over
        ``mainZ`` costs seconds and only survivors need the four tubes.

        Warning:
            **Necessary, not sufficient, and measured to be insufficient.** Satisfying the
            window does not buy ``separation``: 40 variants over 10 trigger pairs, spread
            from 0.1 to 10.7 kcal/mol inside it, all returned ``separation`` 0.00 with
            ``dG_open(10) == dG_open(11)`` (``strength_window.py``). Trigger A never has to
            beat the *whole* stem — only the sub-helix over ``main_pre*``, where trigger
            A's ``main_pre`` is the switch's own sequence plus the 3-nt ``bulge`` that the
            descending ``AUG`` cannot pair. R7 grants trigger A those three pairs by
            design, and ``mainZ`` lies on the far side of the bulge, so no choice of it can
            take them back. Use these three numbers to *screen*, never to rank, and never
            as evidence that a design gates.

        Args:
            trigger_a: Trigger A, RNA uppercase, ``k1 · bulge · main_pre · xA · extA``.
            len_x: Overlap length, so ``sw_xs`` is known.
            main_z: The candidate 6-nt spacer. ``k1*`` is its reverse complement.

        Returns:
            ``(stem, grip_alone, grip_with_x)`` in kcal/mol; any element is ``None`` if
            the model could not evaluate that alignment.
        """
        arm, post = self.ARM_LEN, self.STEM_POST_BULGE_LEN
        rna = sq.to_rna(trigger_a)
        bulge = rna[post : post + self.BULGE_LEN]
        main_pre = rna[post + self.BULGE_LEN : arm]
        x = rna[arm : arm + len_x]

        ascending = (
            sq.reverse_complement(main_pre)
            + sq.reverse_complement(bulge)
            + (sq.reverse_complement(main_z))
        )
        descending = main_z + "AUG" + main_pre
        return (
            fixed_alignment_energy(ascending, descending, self.folder),
            fixed_alignment_energy(rna[:arm], ascending, self.folder),
            fixed_alignment_energy(
                rna[: arm + len_x], sq.reverse_complement(x) + ascending, self.folder
            ),
        )

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
                    length < self.SECONDARY_INVASION_LEN
                    and start_x + length < n
                    and start_xs > 0
                    and rna[start_xs - 1] == sq.reverse_complement(rna[start_x + length])
                ):
                    start_xs -= 1
                    length += 1
                while (
                    length < self.SECONDARY_INVASION_LEN
                    and start_x > 0
                    and start_xs + length < n
                    and rna[start_xs + length] == sq.reverse_complement(rna[start_x - 1])
                ):
                    start_x -= 1
                    length += 1
                seen.add((start_x, start_xs, length))

        for start_x, start_xs, length in sorted(seen):
            pair = _TriggerPair(
                start_x,
                start_xs,
                length,
                self.ARM_LEN,
                self.TOEHOLD_B_LEN,
                self.SECONDARY_INVASION_LEN,
            )
            if pair.fits(n) and pair.disjoint() and pair.gap() >= gap:
                yield pair

    #: Both stem arms span 18 nt (R1), so ``len_k2 = ARM_LEN - len_x``: every nucleotide
    #: the overlap takes is one fewer for trigger B to invade with. That is the trade the
    #: overlap length is chosen against.
    #:
    #: ``ARM_LEN`` is the **main** hairpin's arm and also the default for the secondary one.
    #: The three constants below let the secondary hairpin differ, which is Kim 2019's
    #: verified inhibitory geometry: a 20-nt arm that trigger B invades only 17 of, capped
    #: with the weak ``AUA`` ladder. Their defaults reproduce this architecture exactly --
    #: arm 18, full 18-nt invasion, no cap -- so nothing moves until a caller changes them.
    ARM_LEN: ClassVar[int] = 18

    #: Nucleotides trimmed from the **5' end** of ``r2_star``, the switch's toehold. Trigger
    #: B keeps its full ``r2``; the switch simply complements less of it, so the trigger-pair
    #: set is unchanged and only the assembled switch shortens. Trimmed from the 5' end
    #: because the 3' end is the part adjacent to the inhibitory hairpin, where structure
    #: blocks binding from becoming invasion -- that end is what we want to keep and report.
    #: 0 is this architecture's current behaviour.
    TOEHOLD_TRIM: ClassVar[int] = 0

    #: The secondary (inhibitory) hairpin's arm, ``sw_x`` plus ``k2_star``. Kim: 20.
    SECONDARY_ARM_LEN: ClassVar[int] = 18

    #: How much of that arm trigger B invades. The remainder is the cap. Kim: 17 of 20, so
    #: B stops 3 short of the loop. **Must not exceed** ``SECONDARY_ARM_LEN``.
    SECONDARY_INVASION_LEN: ClassVar[int] = 18

    #: The uninvaded top of the ascending arm, written 5'->3' and sitting against the loop.
    #: Kim and Green's forward-engineered generation both use ``AUA`` -- deliberately weak,
    #: so the three pairs trigger B cannot reach are also the three easiest to melt. Empty
    #: means no cap, which is this architecture's current behaviour.
    SECONDARY_CAP: ClassVar[str] = ""

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
        cap = self.SECONDARY_CAP
        if self.SECONDARY_INVASION_LEN + len(cap) != self.SECONDARY_ARM_LEN:
            raise ValueError(
                f"secondary geometry does not close: invasion {self.SECONDARY_INVASION_LEN} "
                f"+ cap {len(cap)} != arm {self.SECONDARY_ARM_LEN}. The uninvaded top of the "
                f"arm is exactly what the cap fills, so these must sum."
            )
        ext, k2 = _secondary_domains(
            trigger_a, trigger_b, len_x, self.ARM_LEN, self.SECONDARY_INVASION_LEN
        )
        x = trigger_a[self.ARM_LEN : self.ARM_LEN + len_x]
        conflicts = _arm_conflicts(ext, k2)

        stems: list[_SecondaryStem] = []
        objectives: list[tuple[float, float, float]] = []
        for combination in product(_ARM_STATES, repeat=len(conflicts)):
            states = dict(zip(conflicts, combination, strict=True))
            k2_star, secondary_z = _build_arms(ext, k2, states)
            if not _invasion_runs_ok(ext, k2, k2_star, self.MAX_INVASION_STALL):
                continue
            # The triggers reach only the INVADED arm, so their two site energies are
            # measured on it. `fixed_alignment_energy` forces first[i] against
            # second[n-1-i] and takes n from `first` alone, so handing it arms of unequal
            # length would build a structure string the wrong size for the compound and
            # return ViennaRNA's 1e5 sentinel -- the exact failure that guard exists for.
            b_site = fixed_alignment_energy(k2, k2_star, self.folder)
            a_site = fixed_alignment_energy(
                x + ext, secondary_z + sq.reverse_complement(x), self.folder
            )
            # The LOCK is the whole stem that has to be torn open, so the cap belongs in it.
            # Kim's three uninvaded pairs still hold the hairpin shut; they are simply pairs
            # trigger B never gets to break.
            if cap:
                k2_star = k2_star + cap
                secondary_z = sq.reverse_complement(cap) + secondary_z
            lock = fixed_alignment_energy(k2_star, secondary_z, self.folder)
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

    #: Gas constant times 310.15 K, in kcal/mol: the factor converting an opening cost in
    #: kcal/mol to the probability that the window is open, and back. ``_opening_cost`` is
    #: ``-RT ln P_open``, so ``P_open = exp(-dG / RT)``.
    RT_KCAL: ClassVar[float] = 0.0019872042586408 * 310.15

    def _switch_from_design(self, design: GateDesign) -> "_AssembledSwitch":
        """Rebuild the assembled switch from a finished design, without re-running assemble.

        Everything ``_AssembledSwitch`` holds is already on the design: the sequence and
        structure are fields, and ``architecture["domain_map"]`` is the map ``assemble``
        itself returned, stored at generation time precisely so that no later stage has to
        re-derive it from the string. Rebuilding beats re-assembling because the axis
        patches (closure, upper3, lower3) are applied AFTER assembly -- re-running assemble
        would hand back the unpatched switch and measure a design nobody asked for.
        """
        return _AssembledSwitch(
            sequence=design.sequence,
            dot_bracket=design.dot_bracket,
            domains={name: tuple(span) for name, span in design.architecture["domain_map"].items()},
            len_x=design.architecture["len_x"],
        )

    #: Every key ``generate_designs`` puts on ``GateDesign.architecture``, declared once.
    #:
    #: Same reason as ``MEASURED_KEYS`` below: a reader keeping its own list is how a computed
    #: value gets dropped. On the generation side it already had -- nine of these were produced
    #: by the levers and thrown away before any CSV, including ``wobble_applied``, the single
    #: field that makes a lever's effect estimable at all.
    #:
    #: **The conditional comparison is what these are for.** Comparing an override against the
    #: control across all designs mixes the designs the lever never changed, where the natural
    #: sequence already was the override, with the ones it did -- and the first group is
    #: identical to the control by construction. Measured consequence: ``wobble_GU`` against
    #: ``trigger_derived`` came out 17.7% against 16.4%, a diluted number read as a null result.
    #: With ``lower3_strong_before``, ``upper3_natural`` and ``closure_natural`` the comparison
    #: splits on whether the lever had anything to do.
    #:
    #: Geometry has no such field and cannot: Kim and naive differ in invasion length, so
    #: ``find_trigger_pairs`` returns a different candidate set and ``secondary_stems`` a
    #: different front. A cross-geometry comparison is paired by trigger pair but not by stem.
    GENERATION_KEYS: ClassVar[tuple[str, ...]] = (
        # identity and coordinates
        "geometry",
        "scheme",
        "len_x",
        "stem_index",
        "closure",
        "upper3",
        "lower3",
        "trigger_a_id",
        "trigger_b_id",
        "gene_a",
        "gene_b",
        "aug_index",
        "rbs_span",
        "rbs_core_motif",
        "augs_outside_window",
        "augs_upstream_of_rbs",
        "domain_map",
        "main_stem_arms",
        "w_rank",
        "w_flank",
        # the stem's three Pareto objectives and the two differences
        "lock_energy",
        "ddg_pref",
        "a_site_energy",
        "b_site_energy",
        "lock_minus_a_site",
        # what each lever FOUND, and whether it changed anything
        "closure_natural",
        "closure_changed",
        "upper3_natural",
        "upper3_changed",
        "lower3_strong_before",
        "lower3_forced",
        "wobble_applied",
        # the lever's side effects on the reading frame
        "main_z_repaired",
        "rare_codons_after_aug",
        "codons_after_aug",
    )

    #: Every key ``measure_design`` returns, declared once so a reader never keeps its own list.
    #:
    #: **This exists because a parallel list is how a measured column disappears.** The run that
    #: produced 346,528 rows hand-listed 24 of these and wrote those; the other 66 were folded and
    #: discarded on every row, so any question needing one of them meant re-running the sweep for
    #: numbers that had already been computed. The same hand-list carried ``free_xstar_01``, which
    #: names no observable this class has ever returned -- 0 values out of 346,528, and nothing
    #: anywhere said so.
    #:
    #: ``tests/engine/gates/test_toehold_and_inventory.py`` asserts EQUALITY against what
    #: ``measure_design`` actually returns, in both directions: a new measurement that is not
    #: declared fails, and a declared one that stops being returned fails. Adding a measurement is
    #: therefore an edit here in the same change.
    #:
    #: ``skipped`` is deliberately absent: it is a reason, not a measurement, and it is present
    #: only when the ON ceiling stopped the pass. A ``None`` beside it means **not attempted**,
    #: which is a different fact from a measurement that was attempted and failed.
    MEASURED_KEYS: ClassVar[tuple[str, ...]] = (
        # Free: no folding at all.
        "gc_content",
        "switch_length",
        "longest_homopolymer",
        "component_count",
        # The main stem's two arms, per state. `open_11` is taken first and alone, because its
        # ceiling rejects most designs before the other three tubes are folded.
        *(f"open_{state}" for state in ("00", "01", "10", "11")),
        "andness",
        # The 30-nt ribosome footprint -- a different window from `open_*`, similar name, both
        # load-bearing.
        *(f"dG_open_{state}" for state in ("00", "01", "10", "11")),
        "dG_open_flank_00",
        "separation",
        "ddG_AND",
        "flank_penalty",
        *(f"P_open_{state}" for state in ("00", "01", "10", "11")),
        # Accessibility of the stem and toehold, as means of per-base unpaired probability.
        *(f"A_S_{state}" for state in ("00", "01", "10", "11")),
        *(f"A_M_{state}" for state in ("00", "01", "10", "11")),
        *(f"A_S_full_{state}" for state in ("00", "01", "10", "11")),
        "A_r2_star_00",
        "A_r2_star_w_00",
        "A_M_ratio",
        "A_M_gain",
        *(f"aug_{state}" for state in ("00", "01", "10", "11")),
        # Partner-aware: what x* is open FOR. These seven partition x* exactly and sum to 1.
        *(f"xstar_locked_{state}" for state in ("00", "01", "10", "11")),
        *(f"xstar_engA_{state}" for state in ("00", "01", "10", "11")),
        *(f"mainpre_engA_{state}" for state in ("00", "01", "10", "11")),
        # Green's RBS/mRNA structure terms -- the strongest category on his measured switches,
        # and free here because the matrix for each state is already built.
        *(f"ied_rbs_linker_{state}" for state in ("00", "01", "10", "11")),
        *(f"meanW_{state}" for state in ("00", "01", "10", "11")),
        *(f"rbs11_mean_{state}" for state in ("00", "01", "10", "11")),
        "ied_off_worst",
        "ied_gain",
        "ied_gain_worst",
        "meanW_off",
        "meanW_gain",
        "A_M_off",
        "aug_off",
        "aug_gain",
        "dG_rbs_linker",
        *(f"xstar_engB_{state}" for state in ("00", "01", "10", "11")),
        *(f"xstar_linker_{state}" for state in ("00", "01", "10", "11")),
        *(f"xstar_sec_z_{state}" for state in ("00", "01", "10", "11")),
        *(f"xstar_other_{state}" for state in ("00", "01", "10", "11")),
        # How much of each intended duplex forms, per state.
        *(
            f"hairpin_{name}_{state}"
            for name in ("main_pre", "k1", "lock", "sec", "worst")
            for state in ("00", "01", "10", "11")
        ),
        "d_off",
        "dG_bind_B",
        "dG_bind_A_given_B",
        # The refolding barrier: measured at 52% of the cost of a fully measured design, so it
        # is taken last.
        "barrier",
        # Pair-level, and ``None`` unless ``measure_design`` is given the transcript and both
        # sites. Measured on the real PFAS transcripts: 10 to 34 s per window, against 0.25 to
        # 0.54 s for a whole enumerated design -- these fold the 1.4 to 2.2 kb transcript, not
        # the switch. They are a property of the trigger PAIR, identical for every design on it,
        # so they can be filled afterwards over the few hundred distinct windows without
        # re-folding one design. A caller that leaves them out must say so rather than let two
        # empty columns read as an unmeasurable quantity.
        "access_a",
        "access_b",
    )

    def measure_design(
        self,
        design: GateDesign,
        *,
        on_ceiling: float | None = None,
        transcript: str | None = None,
        site_a: tuple[int, int] | None = None,
        site_b: tuple[int, int] | None = None,
    ) -> dict[str, float | None]:
        """Every raw measurement this family can make on one design, in one pass.

        **This is the single measurement pass.** The numbers used to be computed across
        four layers -- `four_tube_observables` here, `score_design` in the notebook's
        objective, a 40-column pass in its panel builder, and a further set that existed
        only once a report card was built -- and every one of those boundaries dropped a
        column at some point. Six times in this work a measured column stopped at a layer
        boundary and read as absent downstream while sitting at full coverage two layers
        down. One pass, one dict, and the panel and report become readers of it.

        Args:
            design: A design from ``generate_designs``, carrying the coordinate sets it
                stored at generation time.
            on_ceiling: Stop after the ON tube when its opening cost exceeds this, and say
                so in ``skipped``. A ``None`` beside a ``skipped`` reason means **not
                attempted**, which is a different thing from a measurement that failed --
                the two must not be confused, which is why the key exists.
            transcript, site_a, site_b: The endogenous context. Given all three, the two
                accessibility terms are priced from the transcript; otherwise they are
                ``None``, and nothing downstream may read them as zero.

        Returns:
            Raw measurements, each in the unit its own analysis quotes it in. A measurement
            that could not be made is ``None`` and never ``0.0`` -- on every
            lower-is-better quantity here zero reads as perfect and clears every threshold.
            **Nothing normalised, nothing weighted, no total.** The notebook's objective
            sums four of these into a `score`; that sum is a ranking choice and belongs to
            whoever is ranking, not to the measurement.

        Order:
            Cheapest first, which is worth a measured 5.2-5.7x and is not cosmetic. Free
            string measures, then the ON tube (whose ceiling rejects 88% of designs), then
            the three OFF tubes, then the four-tube ensemble set, and the refolding barrier
            last because it alone is 52% of the cost of a fully measured design.
        """
        switch = self._switch_from_design(design)
        arms = tuple(tuple(span) for span in design.architecture["main_stem_arms"])
        role_a, role_b = design.trigger_set.activators
        trigger_a, trigger_b = sq.to_rna(role_a.sequence), sq.to_rna(role_b.sequence)

        out: dict[str, float | None] = {}

        # ---- free: no folding at all --------------------------------------------------
        out["gc_content"] = sq.gc_content(switch.sequence)
        out["switch_length"] = float(len(switch.sequence))
        # `longest_homopolymer` returns (base, length); only the length is a measurement.
        out["longest_homopolymer"] = float(sq.longest_homopolymer(switch.sequence)[1])
        # The count behind the `circuit_complexity` axis, stored and NOT scored -- see
        # `evaluate_design`'s note on why emitting the scored name here would re-rank the
        # one-input family rather than describe this one. Two trigger inputs plus the two
        # hairpins they open: a property of the architecture, identical for every design of
        # this family, which is exactly what a component-count penalty is for (it
        # discriminates between CHEMISTRIES, not between designs within one).
        out["component_count"] = float(len(design.trigger_set.activators) + 2)

                # ---- the ON tube, first, because its ceiling is what makes the sweep affordable
        on_strands = f"{switch.sequence}&{trigger_a}&{trigger_b}"
        # Two spans of the same complex, so the second costs one more constrained
        # partition function rather than a second fold.
        #
        # `dG_open_11` is the RIBOSOME'S WINDOW and is what the ceiling reads, because that
        # is the span the ceiling's value is calibrated on: Green's 168 have a median ON
        # cost of 3.64 kcal/mol there, and the 77 of them above 20-fold ON/OFF have 3.07.
        #
        # `open_11` is the MAIN STEM'S ARMS. It is kept as an observable -- every design
        # built before this change carries it, and it is the quantity the stem levers act
        # on most directly -- but it decides nothing.
        out["open_11"] = self.folder.open_penalty(on_strands, arms)
        out["dG_open_11"] = self.folder.open_penalty(
            on_strands, (tuple(design.architecture["w_rank"]),)
        )
        # ---- the state-10 leak, BEFORE the ceiling decides ----------------------------
        # These two were produced only for designs that pass, so no stored row carried them for
        # a rejected one -- 0 of 2,408 in the sample -- and asking what the rejected designs
        # look like took a separate run. That run measured Spearman **-0.500** between
        # `open_11` and `xstar_engA_10`: the ceiling is not independent of the leak it does not
        # look at, so a threshold calibrated only on survivors is calibrated on a population the
        # ceiling already shaped.
        #
        # One dimer, about 0.86 s, and nothing is wasted on a passer: the matrix is cached on the
        # instance, so `four_tube_observables` finds this tube already folded.
        leak_matrix = self.folder.pooled_pair_probabilities(f"{switch.sequence}&{trigger_a}")
        a_block = (len(switch.sequence), len(switch.sequence) + len(trigger_a))
        out["xstar_engA_10"] = _mean_paired_to(leak_matrix, switch.domains["sw_xs"], a_block)
        out["mainpre_engA_10"] = _mean_paired_to(
            leak_matrix, switch.domains["main_pre_star"], a_block
        )

        if on_ceiling is not None and (
            out["dG_open_11"] is None or out["dG_open_11"] > on_ceiling
        ):
            # A reason, with the leak terms measured beside it. A design that fails is a
            # measurement, not an absence -- which is the contract the characterisation run
            # is built on.
            #
            # The threshold is read against `dG_open_11`, the cost of opening the ribosome's
            # window, which is the span Green's figures are measured over. Before version
            # 0.6.0 it was read against `open_11`, the stem's arms, which is a different and
            # smaller span; results from before that change are not comparable with results
            # after it at the same numeric setting.
            out["skipped"] = "on_ceiling"
            return out

        # ---- the three OFF tubes ------------------------------------------------------
        for state, strands in (
            ("00", switch.sequence),
            ("01", f"{switch.sequence}&{trigger_b}"),
            ("10", f"{switch.sequence}&{trigger_a}"),
        ):
            out[f"open_{state}"] = self.folder.open_penalty(strands, arms)

        off = [out["open_00"], out["open_01"], out["open_10"]]
        out["andness"] = (
            None
            if out["open_11"] is None or any(v is None for v in off)
            else out["open_11"] - min(v for v in off if v is not None)
        )

        # ---- the four-tube ensemble set, over the ribosome footprint ------------------
        # A different window from `open_*` above and therefore a different measurement;
        # see this method's own note. Folds hit `FoldEngine`'s instance cache for the
        # tubes already folded, so the overlap is not paid twice.
        out.update(self.four_tube_observables(switch, trigger_a, trigger_b))

        # ---- derived ratios, no further folding ---------------------------------------
        # A_M_ratio: the ON state's main-stem accessibility against the worst OFF state's.
        # Its denominator collapses for the closed-bulge geometries -- 4.7% of designs hold
        # 89 of the top 100 by this ratio, with worst-OFF denominators down to 0.0011 -- so
        # it is carried, and it must not be allowed to rank on its own.
        a_m_off = [out.get(f"A_M_{s}") for s in ("00", "01", "10")]
        a_m_on = out.get("A_M_11")
        if a_m_on is None or any(v is None for v in a_m_off):
            out["A_M_ratio"] = None
            out["A_M_gain"] = None
        else:
            worst = max(v for v in a_m_off if v is not None)
            out["A_M_ratio"] = a_m_on / worst if worst > 0.0 else None
            out["A_M_gain"] = a_m_on - worst

        # P_open for each state: the same information as `dG_open_*` on a 0-1 scale, which
        # is the scale `predicted_leakage` and `dynamic_range` are declared on. Carried
        # explicitly rather than recomputed by each reader from the energy.
        for state in ("00", "01", "10", "11"):
            cost = out.get(f"dG_open_{state}")
            out[f"P_open_{state}"] = None if cost is None else math.exp(-cost / self.RT_KCAL)

        # ---- the refolding barrier, LAST: 52% of the cost of a measured design --------
        # OFF structure -> the same structure with the main stem's arms released. `saddle`
        # takes one strand, so this is the switch's own refolding cost rather than the
        # trigger-bound path: the wall the molecule clears once the trigger has committed,
        # and an upper bound on it.
        folded = self.folder.mfe(switch.sequence)
        target = list(folded.structure)
        partner: dict[int, int] = {}
        stack: list[int] = []
        for index, char in enumerate(folded.structure):
            if char == "(":
                stack.append(index)
            elif char == ")":
                opened = stack.pop()
                partner[index] = opened
                partner[opened] = index
        for lo, hi in arms:
            for index in range(lo, min(hi, len(target))):
                if index in partner:
                    target[partner[index]] = "."
                target[index] = "."
        out["barrier"] = self.folder.saddle(switch.sequence, folded.structure, "".join(target))

        # ---- the endogenous context, when it was supplied -----------------------------
        if transcript is not None and site_a is not None and site_b is not None:
            out["access_a"] = self.folder.open_penalty(transcript, (site_a,))
            out["access_b"] = self.folder.open_penalty(transcript, (site_b,))
        else:
            # Not measurable without the transcript the triggers came from. `None`, and
            # every reader has to treat it as absent -- a 0.0 here is a free perfect score.
            out["access_a"] = out["access_b"] = None
        return out

    def evaluate_design(self, design: GateDesign) -> dict[str, float | None]:
        """The nine declared metrics, projected from the one measurement pass.

        ``ToeholdGate``'s version folds against ``trigger_set.activators[0]`` only, which
        is a one-input evaluation of a two-input gate: it would score this family on a
        single trigger and never look at the second, so the AND behaviour -- the whole
        point of the chemistry -- would not appear in any number it returned. The class
        docstring says whoever fills ``generate_designs`` must override this too.

        Returns:
            Only the names in ``DEFAULT_V1``, raw. ``None`` for anything unmeasurable; a
            ``0.0`` stand-in would score ``predicted_leakage`` as a perfect 1.0 and clear
            its own 0.85 hard filter. Everything else this family measures is in
            ``measure_design``, which this calls -- so the two can never disagree about a
            design, and the folds are shared through ``FoldEngine``'s instance cache.

        What each name means for THIS chemistry:
            * ``predicted_leakage`` -- CLAUDE.md §6 requires a family to state which
              biological event it means by this name. Here it is **the probability that the
              ribosome footprint is open in the WORST of the three OFF states**: any OFF
              state that opens is a leak for an AND gate, so the worst one is the honest
              summary rather than a mean over the three. Measured, that worst state is
              state 10 -- trigger A alone -- in 400 of 400 designs.
            * ``state_separation`` -- log2 of the ON/worst-OFF opening ratio, which is
              ``separation`` (kcal/mol) divided by ``RT ln 2``. The profile declares this
              axis as log2, and the four tubes measure an energy; the conversion is here
              rather than left to a reader who might hand the energy over directly.
            * ``dynamic_range`` -- the **linear** ON/OFF fold change, as the profile
              declares (1.0-500.0). ``state_separation`` immediately above it is log2 of
              the same comparison, and handing the log to this one costs a hundredfold.
            * ``trigger_accessibility`` -- the bottleneck of the two triggers, **read off
              the candidates** and never recomputed (CLAUDE.md §5): a second measurement
              with a slightly different window produces two numbers for one quantity and
              both get persisted.
            * ``orthogonality`` -- ``None``. It is independence from the OTHER gates in a
              circuit, which is not a property of one design; computing it from whatever
              designs happen to share a batch is the batch-relative scoring CLAUDE.md §3
              bans outright.
            * ``predicted_success_rate`` -- ``None``. ``TranslationScorer.score`` still
              raises ``NotImplementedError``, so there is nothing to report and a guess
              would be indistinguishable from a measurement.
            * ``circuit_complexity`` -- ``None``, deliberately, and this one is a trap.
              A two-input gate genuinely is more complex than a one-input one, and the
              count is in ``measure_design`` as ``component_count``. But ``ToeholdGate``
              emits no ``circuit_complexity`` either, and a missing metric scores as the
              WORST value at full weight. Emitting it here while the sibling family does
              not would therefore not record that this gate is more complex -- it would
              quietly re-rank the one-input family as maximally complex against it.
              Both families should emit it, in one change that bumps both versions; until
              then symmetry is the honest state. See the handover note.
        """
        raw = self.measure_design(design)
        role_a, role_b = design.trigger_set.activators

        separation = raw.get("separation")
        p_on = raw.get("P_open_11")
        worst_off = [raw.get(f"P_open_{state}") for state in ("00", "01", "10")]
        leakage = None if any(v is None for v in worst_off) else max(worst_off)

        return {
            # The OFF hairpin's MFE. Cached, so this is the same fold `measure_design`
            # already took for the barrier rather than a second one.
            "gate_folding_energy": self.folder.mfe(design.sequence).energy,
            "predicted_leakage": leakage,
            "state_separation": (
                None if separation is None else separation / (self.RT_KCAL * math.log(2.0))
            ),
            "dynamic_range": (
                None if p_on is None or leakage is None or leakage <= 0.0 else p_on / leakage
            ),
            "trigger_accessibility": min(role_a.accessibility, role_b.accessibility),
            "gc_content": raw.get("gc_content"),
            "orthogonality": None,
            "predicted_success_rate": None,
            "circuit_complexity": None,
        }

    def role_footprints(self) -> tuple[int, int]:
        """The minimum length of trigger A and of trigger B, in that order.

        Straight off ``_TriggerPair.window_a``/``window_b``, which document the same two
        numbers as the footprints the pair finder cuts:

            A: ``arm_len + len_x + len_k2``       == ``ARM_LEN + SECONDARY_INVASION_LEN``
            B: ``len_k2 + len_x + toehold_b_len`` == ``SECONDARY_INVASION_LEN + TOEHOLD_B_LEN``

        Both are independent of ``len_x`` because ``len_k2 = invasion_len - len_x`` cancels
        it, which is why a pair's windows are a constant size whatever overlap it shares.
        Naive geometry: 36 and 50. Kim's 17-nt invasion: 35 and 49.

        Derived from the class constants rather than written down, so a subclass that
        changes the geometry (``TrimmedToeholdAndGate``, ``KimSecondaryArmToeholdAndGate``)
        gets the right pair of numbers without editing this method.
        """
        return (
            self.ARM_LEN + self.SECONDARY_INVASION_LEN,
            self.SECONDARY_INVASION_LEN + self.TOEHOLD_B_LEN,
        )

    def is_compatible(self, trigger_set: TriggerSet, constraints: Constraints) -> Compatibility:
        """Arity, host and the **two-input** footprints.

        ``ToeholdGate``'s version is a one-input check, and inheriting it unchanged is a
        crash rather than a rejection: its footprint is
        ``min(toehold_lengths) + STEM_PRE_BULGE_LEN + 3 + STEM_POST_BULGE_LEN``, well under
        the 36 and 50 nt two inputs need, so a pair of 30-nt windows passed it and then
        raised ``ValueError: fixed alignment needs equal lengths, got 10 and 4`` from inside
        ``secondary_stems``. That is the failure this override exists to turn back into a
        reported reason -- CLAUDE.md §3: a family rejects a trigger set with
        ``Compatibility.no(reason)``, and a silent drop or a traceback is not that.

        **Either role assignment is enough.** ``generate_designs`` tries both orders, so a
        pair is usable when one of the two assignments has a long enough A *and* a long
        enough B. Requiring it of both orders would reject pairs that build.
        """
        inherited = super().is_compatible(trigger_set, constraints)
        if not inherited.ok:
            return inherited

        min_a, min_b = self.role_footprints()
        first, second = trigger_set.activators
        if not any(
            len(sq.to_rna(role_a.sequence)) >= min_a and len(sq.to_rna(role_b.sequence)) >= min_b
            for role_a, role_b in ((first, second), (second, first))
        ):
            lengths = ", ".join(f"{t.trigger_id} {t.length} nt" for t in trigger_set.activators)
            return Compatibility.no(
                f"No role assignment fits {self.label}'s footprints: trigger A needs "
                f"{min_a} nt (arm {self.ARM_LEN} + invasion {self.SECONDARY_INVASION_LEN}) "
                f"and trigger B needs {min_b} nt (invasion "
                f"{self.SECONDARY_INVASION_LEN} + toehold {self.TOEHOLD_B_LEN}), but the "
                # No "add 50 to trigger_lengths" here: `build_tools` adds a requested
                # family's own footprints already, so that advice was printed in runs
                # where it had been followed. What is left is the fact, which is that
                # these two windows cannot fill the two roles -- on a short transcript
                # that is simply true and no setting fixes it.
                f"set is {lengths}."
            )

        # **The shared overlap, asked here so that its absence is a REPORTED reason.**
        # A pair can clear the footprints and still share no complementary run at the
        # offsets this architecture binds at, and then `generate_designs` yields nothing:
        # a silent drop, which CLAUDE.md §3 bans. For two windows picked independently it
        # is also the common outcome rather than a rare one -- the two triggers have to be
        # reverse-complementary over at least `MIN_OVERLAP` positions at fixed offsets, and
        # ranking single windows by accessibility does nothing to arrange that. Pure string
        # work, no folding, so it is free to ask.
        if not any(
            self._overlap_lengths(sq.to_rna(role_a.sequence), sq.to_rna(role_b.sequence))
            for role_a, role_b in ((first, second), (second, first))
        ):
            return Compatibility.no(
                f"{first.trigger_id} and {second.trigger_id} share no reverse-complementary "
                f"run of at least {self.MIN_OVERLAP} nt at the offsets {self.label} binds "
                f"at (trigger A's x begins at {self.ARM_LEN}, trigger B's x* at "
                f"{self.SECONDARY_INVASION_LEN} - len_x), so there is no secondary stem to "
                f"build. Use `find_trigger_pairs` on the transcript to enumerate the "
                f"windows that do share one, rather than pairing windows ranked singly."
            )

        # **The eukaryotic track cannot build this architecture yet.** `assemble` sets
        # `rbs_loop = RBS_FLANK + RBS_PROKARYOTIC` with no branch on host track, although
        # the cap directly below it is host-dispatched. Verified by building one: a
        # eukaryotic AND design comes out with a eukaryotic leader and a PROKARYOTIC
        # Shine-Dalgarno in its loop, and no Kozak anywhere -- a switch that cannot
        # initiate translation in yeast or a human cell. Caught here as well as on the
        # pipeline's blocklist because the blocklist keys on family NAME, and the base
        # `toehold_and` name carries no track: requested with a eukaryotic host it would
        # otherwise reach `assemble` and build the same chimera.
        if self.host.track is Track.EUKARYOTIC:
            return Compatibility.no(
                f"{self.label} is not buildable for {self.host.value}: the loop's ribosome "
                "binding site is hardcoded to the prokaryotic Shine-Dalgarno sequence, so "
                "a eukaryotic design would carry no Kozak and could not initiate. Making "
                "the loop host-dispatched is a deliberate declaration, not a default."
            )
        return Compatibility.yes()

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
        if len(trigger_set.activators) != 2 or trigger_set.repressors:
            # `is_compatible` checks arity first and the designer calls it first, so this is
            # a guard against a direct caller rather than a path the pipeline takes.
            return
        first, second = trigger_set.activators

        # Both role assignments. Trigger A opens the main stem and trigger B frees the
        # secondary lock, so A-with-B is a different construct from B-with-A and the two do
        # not perform the same -- the docstring above says to generate both and let scoring
        # decide, and that is what the loop does.
        for role_a, role_b in ((first, second), (second, first)):
            trigger_a, trigger_b = sq.to_rna(role_a.sequence), sq.to_rna(role_b.sequence)
            for len_x in self._overlap_lengths(trigger_a, trigger_b, constraints):
                yield from self._designs_for_overlap(
                    trigger_set, role_a, role_b, trigger_a, trigger_b, len_x, constraints
                )

    #: Cycle 2's chosen closure set: **one representative per d**, plus the control. The
    #: energetic centre of the class is the declared TIE-BREAK inside a d, not the reason for
    #: the choice -- see "why d and not energy" below, which is measured.
    #:
    #: ``d`` counts how many of the three bulge positions pair with the start codon facing them
    #: across the helix, in the real antiparallel register -- bulge position ``i`` faces ``AUG``
    #: position ``2 - i``, so the bulge sees ``GUA``. Within a class the representative is the
    #: option whose ``fixed_alignment_energy`` against the AUG is nearest the class mean::
    #:
    #:     d = 3   CGU  +1.80   class mean 2.07   {CAU 1.40, CGU 1.80, UAU 3.00}
    #:     d = 2   AGU  +3.20   class mean 3.63   {CGC 2.60, AAU 2.90, AGU 3.20, CCU 5.80}
    #:     d = 1   AAC  +3.40   class mean 3.48   {AAA 3.20, CCC 3.30, AAC 3.40, AGC 4.00}
    #:     d = 0   ---   none: every option is exactly 0.00, because with no pair there is no
    #:                   energy to be in the middle of
    #:
    #: **``AUG`` fills d = 0 on external evidence instead.** It is the most common bulge in
    #: Green's measured library -- 62.5% of the 176 located structurally in his Table S1, median
    #: ON/OFF 86.5 on n = 102 -- and it was never one of our sixteen. Its rivals there are not
    #: distinguishable from it (``AUA`` p = 0.91, ``GUG`` p = 0.33) or have single-digit n, so it
    #: is the only d = 0 choice that is not a sample of one.
    #:
    #: **Why d and not energy, measured.** The set's three real rungs are 1.80, 3.20 and 3.40 --
    #: ``AUG``'s 0.00 is a sentinel, since ``fixed_alignment_energy`` returns 0.0 by contract
    #: when no pair is possible -- so two of them sit 0.20 kcal/mol apart, well inside
    #: ViennaRNA's own error. That looks like a redundant pair until the energies are tested
    #: against performance, and then it is the energy axis that fails. Paired inside a cell on
    #: 25,607 measured designs, ``AGU`` against ``AAC`` (0.20 apart) is the MORE consistent
    #: comparison: ``A_M_ratio`` 74.5% to 2.7%, ``ied_gain`` 80.4% to 19.6% (p = 0.0009). The
    #: far pair ``CAU`` against ``CCU`` (4.40 apart) splits 47.8% to 52.2% on ``ied_gain``
    #: (p = 0.82) -- a coin flip. The classes themselves overlap in energy (``UAU`` is d = 3 at
    #: 3.00, above ``CGC`` at d = 2 and 2.60; ``CCU`` is d = 2 at 5.80, the extreme of the set),
    #: Spearman d against energy -0.705. And the two near-identical energies are not redundant
    #: designs: ``AGU`` wins every OFF-state measure and LOSES the ON state, ``A_M_11`` worse in
    #: 74.9% of matched designs, median -0.0508 -- they sit on opposite sides of one trade.
    #: Effect size stated honestly: the median paired difference is exactly 0.0000 on
    #: ``separation`` and ``A_M_ratio``, so most designs are unaffected and the whole difference
    #: is in the tail (4 of 255 at +6.4 separation), on n = 255 across 28 cells.
    #:
    #: **Why not our own gating rates.** ``closed_CAU`` looked like the best closure anywhere:
    #: 34.1% gating against ``trigger_derived``'s 12.6%. Head to head inside its own class,
    #: PAIRED within a cell so the trigger pair, the stem and every other axis are held fixed, it
    #: is **2 cells to 2 against CGU (p = 1.0)** and 3 to 3 against UAU. The 34.1% was an
    #: unconditional rate across different trigger pairs. Under the paired test the d = 3 and
    #: d = 2 classes are flat, and in d = 1 and d = 0 what is distinguishable is which option is
    #: WORSE -- ``AGC`` loses 14-43 and ``GCC`` loses 4-28 -- not which is best.
    CLOSURES_CHOSEN: ClassVar[tuple[tuple[str, str | None], ...]] = (
        ("trigger_derived", None),
        ("green_AUG", "AUG"),
        ("centre_d1_AAC", "AAC"),
        ("centre_d2_AGU", "AGU"),
        ("centre_d3_CGU", "CGU"),
    )

    #: Levels for the AUG bulge's closure, patched into ``bulge_star``. All sixteen, because
    #: the (depth, G+C) grid is the axis and leaving cells out makes the sweep uneven.
    #:
    #: **They must all stay, and the scoring must not be fooled by them.** Measured over the
    #: gating population, ``closed_*`` is 4.7% of designs and holds **89 of the top 100** by
    #: A_M ratio, with worst-OFF denominators down to 0.0011 -- the extreme ratios are a
    #: collapsed denominator, not a better ON state, and on the bounded measures those same
    #: designs are the weakest. Green's own S6.2 calls extra pairs in the AUG bulge a defect
    #: that "occurred often in the forward-engineered toehold switches", and no measured
    #: library can arbitrate it. So: keep the levers, and never let the ratio rank alone.
    CLOSURES: ClassVar[tuple[tuple[str, str | None], ...]] = (
        ("open_3x3", None),
        ("closed_UAU", "UAU"),
        ("closed_CAU", "CAU"),
        ("closed_CGU", "CGU"),
        ("pair2_CCU", "CCU"),
        ("pair1_CCC", "CCC"),
        ("d2_gc3_CGC", "CGC"),
        ("d2_gc1_AGU", "AGU"),
        ("d2_gc0_AAU", "AAU"),
        ("d1_gc2_AGC", "AGC"),
        ("d1_gc1_AAC", "AAC"),
        ("d1_gc0_AAA", "AAA"),
        ("d0_gc3_GCC", "GCC"),
        ("d0_gc2_ACC", "ACC"),
        ("d0_gc1_ACA", "ACA"),
        ("d0_gc0_AUA", "AUA"),
    )

    #: Top three base pairs of the main stem. ``None`` leaves them trigger-derived.
    #:
    #: Only the two all-weak overrides, because those are the ones asked for. The sweep also
    #: carried ``WWS_AUG`` and ``WSW_AGA``; they are left out rather than silently retained,
    #: and whether any override earns its place is an open measurement -- count how often each
    #: level reaches a cell's argmin before widening this.
    UPPER3: ClassVar[tuple[tuple[str, str | None], ...]] = (
        ("trigger_derived", None),
        ("WWW_UAU", "UAU"),
        ("WWW_AUA", "AUA"),
    )

    #: Bottom three base pairs. ``WOBBLE`` is a target, not a sequence -- see ``_apply_lower3``.
    #:
    #: Measured: only ``trigger_derived`` and ``wobble_GU`` leave trigger A's grip on the stem
    #: base intact -- 0 mismatches across 368 designs -- while the fixed levels break it, and
    #: ``WSS``/``AGG`` was dropped 100% of the time by the rare-codon screen.
    #:
    #: **So the broken-pair allowance is moot and is not implemented.** Earlier drafts
    #: described a ``grip_broken`` count with a ``GRIP_BREAK_MAX`` of 1, to let a FORCED
    #: level still reach a 2S1W arrangement without losing trigger A's grip. Both levels
    #: that survive leave the grip intact, so there is nothing for it to permit; neither
    #: name exists in the code, and a reader looking for them should stop here.
    LOWER3_WOBBLE: ClassVar[str] = "<wobble>"
    LOWER3: ClassVar[tuple[tuple[str, str | None], ...]] = (
        ("trigger_derived", None),
        ("wobble_GU", LOWER3_WOBBLE),
    )

    #: Stop codons, so the lower3 rescue can refuse to create one.
    STOP_CODONS: ClassVar[frozenset[str]] = frozenset({"UAA", "UAG", "UGA"})

    @property
    def geometry_name(self) -> str:
        """A label for this family's secondary geometry, recorded on every design.

        Two subclasses differ only in three class constants, so the label is derived from
        them rather than declared -- a geometry cannot then be mislabelled by forgetting to
        update a string.
        """
        cap = self.SECONDARY_CAP or "none"
        return f"arm{self.SECONDARY_ARM_LEN}/inv{self.SECONDARY_INVASION_LEN}/cap{cap}"

    def _axis_grid(self, closure_set: str = "full"):
        """Every (closure, upper3, lower3) point. A generator, so nothing is held at once.

        ``closure_set`` selects which closure axis to walk: ``"full"`` is all sixteen and is
        what cycle 1's 431,916 designs were built on, ``"chosen"`` is the five of
        ``CLOSURES_CHOSEN``. Both are kept because the argument for the chosen set is a
        comparison against the full one, and replacing the axis outright would make cycle 1
        unreproducible.
        """
        closures = self.CLOSURES_CHOSEN if closure_set == "chosen" else self.CLOSURES
        for closure in closures:
            for upper3 in self.UPPER3:
                for lower3 in self.LOWER3:
                    yield closure, upper3, lower3

    def _apply_axes(self, base, closure, upper3, lower3):
        """Patch one assembled switch by domain NAME, never changing a length.

        Returns the patched switch and a dict of notes, or ``None`` when an axis cannot be
        applied without creating a fault that cannot be repaired.

        **Patching by name and never by length is what keeps the domain map valid.** Every
        write below replaces exactly as many bases as it removes, so ``base.domains`` still
        describes the result and every downstream measurement reads the right span.

        **Order matters, and this is the subtle part.** ``assemble`` already ran
        ``_repair_main_z``, which removes an out-of-frame AUG that trigger A's first six
        nucleotides would otherwise put in the 5' UTR -- 93 of 867 candidates on mCherry. But
        the ``upper3`` lever OVERWRITES ``main_z``, so applying it undoes that repair and
        brings the second start codon straight back. So the repair is re-run here, after the
        patches, and a design that still carries one is dropped with a reason rather than
        emitted. Two levers each correct alone, wrong in combination.
        """
        sequence = list(base.sequence)
        notes: dict[str, object] = {}

        def put(name: str, text: str, at_end: bool = False) -> None:
            lo, hi = base.domains[name]
            if at_end:
                sequence[hi - len(text) : hi] = list(text)
            else:
                sequence[lo : lo + len(text)] = list(text)

        # What was there BEFORE any lever ran. These are the conditioning variables that make
        # a lever's effect estimable: comparing an override against the control across all
        # designs mixes the designs it never changed -- where the natural sequence already was
        # the override -- with the ones it did, and the first group is identical to the control
        # by construction, so it dilutes the effect toward zero. Measured consequence: wobble_GU
        # against trigger_derived came out 17.7% against 16.4%, which is a diluted number and
        # not a null result.
        cl_lo, cl_hi = base.domains["bulge_star"]
        mz_lo, _mz_hi = base.domains["main_z"]
        notes["closure_natural"] = "".join(sequence[cl_lo:cl_hi])
        notes["upper3_natural"] = "".join(sequence[mz_lo : mz_lo + 3])
        # The bottom three pairs' natural strength, read off `main_pre_star` exactly as
        # `_apply_lower3` reads it. `== 2` means Green's two-strong-one-weak is already met and
        # the wobble lever is a no-op, which is the condition the comparison has to split on.
        mps_lo, _ = base.domains["main_pre_star"]
        notes["lower3_strong_before"] = sum(1 for i in range(3) if sequence[mps_lo + i] in "GC")

        if closure[1] is not None:
            put("bulge_star", closure[1])
            notes["closure_changed"] = notes["closure_natural"] != closure[1]

        if upper3[1] is not None:
            put("k1_star", upper3[1], at_end=True)
            put("main_z", sq.reverse_complement(upper3[1]))
            notes["upper3_changed"] = notes["upper3_natural"] != sq.reverse_complement(upper3[1])

        if lower3[1] is not None:
            applied = self._apply_lower3(sequence, base, lower3[1])
            if applied is None:
                return None
            notes.update(applied)

        repaired = self._repair_patched_main_z(sequence, base)
        if repaired is None:
            notes["aug_utr_unrepairable"] = True
            return None
        notes["main_z_repaired"] = repaired

        switch = _AssembledSwitch(
            sequence="".join(sequence),
            dot_bracket=base.dot_bracket,
            domains=base.domains,
            len_x=base.len_x,
        )
        notes["rare_codons_after_aug"] = self._rare_codons_after_aug(switch)
        notes["codons_after_aug"] = self._codons_after_aug(switch)
        # Present on EVERY design, including the ones whose lever was `trigger_derived` and so
        # never ran. A key that appears only when a lever fired is a column that reads as
        # missing for the control arm, which is the comparison's own denominator.
        notes.setdefault("closure_changed", False)
        notes.setdefault("upper3_changed", False)
        notes.setdefault("wobble_applied", 0)
        notes.setdefault("lower3_forced", False)
        return switch, notes

    def _apply_lower3(self, sequence: list[str], base, level: str):
        """The bottom three pairs. ``WOBBLE`` is a strength target reached through G-U pairs.

        A G-U wobble moves the stem's strength WITHOUT trigger A losing the position:

            trigger U -> star is normally A, pair A-U (weak). Put G: the trigger keeps a G-U
                         wobble and the stem pair becomes G-C. STRONGER.
            trigger G -> star is normally C, pair C-G (strong). Put U: the trigger keeps a
                         G-U wobble and the pair becomes U-A. WEAKER.

        The target is Green's two-strong-one-weak, and the ARRANGEMENT is left to the data:
        over 12 pair-stems WSS opened 59 times against SSW's 28 at the same leak, so forcing
        a position would convert away from the arrangement that opens most.

        **And this is where a stem lever can cost a design its reading frame.** The writes
        land in ``main_pre_star`` and, pairing with them, in ``main_pre`` -- nine coding
        nucleotides immediately after the AUG, exactly three codons in frame. All three
        writes fall in the LAST of those, so the lever rewrites one whole codon: the third
        after the start, which is inside the three the rare-codon screen reads. Unguarded it
        can create an in-frame stop, and ``SwitchValidator`` then rejects the design for a
        side effect of a stem-strength choice rather than for anything about its gate.

        There is choice available to rescue it. Reaching two-of-three needs one or two
        conversions out of three available positions, so several SUBSETS reach the same
        strength with different resulting codons. They are ranked: no stop codon first (a
        hard requirement), then no rare codon, then the original left-to-right order so a
        design whose first-fit choice was already clean is unchanged. A design with no clean
        subset keeps the first fit and is FLAGGED, never dropped -- rare codons are counted,
        not filtered.
        """
        if level != self.LOWER3_WOBBLE:
            put_star = sq.reverse_complement(level)
            lo, hi = base.domains["main_pre_star"]
            sequence[lo : lo + 3] = list(put_star)
            lo, hi = base.domains["main_pre"]
            sequence[hi - 3 : hi] = list(level)
            return {"lower3_forced": True}

        star_start = base.domains["main_pre_star"][0]
        pre_end = base.domains["main_pre"][1]
        strong = sum(1 for i in range(3) if sequence[star_start + i] in "GC")
        # Which positions CAN move, and to what. Only star A (trigger U) and star C
        # (trigger G) have a G-U to reach for; star G and star U are left alone rather than
        # forced into a mismatch.
        movable = []
        for offset in range(3):
            here = sequence[star_start + offset]
            if strong < 2 and here == "A":
                movable.append((offset, "G", "C", +1))
            elif strong > 2 and here == "C":
                movable.append((offset, "U", "A", -1))
        if not movable or strong == 2:
            return {"wobble_applied": 0}

        need = 2 - strong
        want = abs(need)
        choices = [
            subset
            for size in range(1, len(movable) + 1)
            for subset in combinations(movable, size)
            if size == want
        ] or [tuple(movable[:1])]

        def codon_after(subset) -> str:
            trial = list(sequence)
            for offset, star_base, pre_base, _ in subset:
                trial[star_start + offset] = star_base
                trial[pre_end - 1 - offset] = pre_base
            return "".join(trial[pre_end - 3 : pre_end])

        ranked = sorted(
            choices,
            key=lambda subset: (
                codon_after(subset) in self.STOP_CODONS,
                codon_after(subset) in self.RARE_CODONS,
                tuple(offset for offset, *_ in subset),
            ),
        )
        best = ranked[0]
        codon = codon_after(best)
        for offset, star_base, pre_base, _ in best:
            sequence[star_start + offset] = star_base
            sequence[pre_end - 1 - offset] = pre_base
        return {
            "wobble_applied": len(best),
            "wobble_codon": codon,
            "wobble_made_stop": codon in self.STOP_CODONS,
            "wobble_made_rare": codon in self.RARE_CODONS,
            "wobble_rescued": len(ranked) > 1
            and codon not in self.STOP_CODONS
            and codon_after(choices[0]) in self.STOP_CODONS,
        }

    def _repair_patched_main_z(self, sequence: list[str], base) -> int | None:
        """Remove an out-of-frame AUG from the 5' UTR after the axes have been patched.

        Same policy as ``_repair_main_z``, which ``assemble`` already applied and which the
        ``upper3`` lever can undo: a position may move to any base that still PAIRS with its
        partner in ``k1*``, wobbles included, so the stem stays closed and one pair merely
        becomes a wobble. Fewest substitutions win.

        Returns how many bases it changed, or ``None`` when no repair removes the AUG -- the
        caller then drops the design with a reason rather than emitting one whose ribosome
        starts in the wrong frame.
        """
        rl_lo, rl_hi = base.domains["rbs_loop"]
        mz_lo, mz_hi = base.domains["main_z"]
        ks_lo, ks_hi = base.domains["k1_star"]

        def utr() -> str:
            return "".join(sequence[rl_lo:rl_hi]) + "".join(sequence[mz_lo:mz_hi])

        if "AUG" not in utr():
            return 0

        width = mz_hi - mz_lo
        # k1* runs antiparallel to main_z, so main_z position i pairs with k1* position
        # (width - 1 - i) counted from k1*'s 3' end.
        partners = ["".join(sequence[ks_lo:ks_hi])[width - 1 - i] for i in range(width)]
        options = [[b for b in "ACGU" if can_pair(b, partners[i])] for i in range(width)]
        current = [sequence[mz_lo + i] for i in range(width)]

        best: tuple[int, list[str]] | None = None
        for combination in product(*options):
            trial = list(combination)
            if "AUG" in "".join(sequence[rl_lo:rl_hi]) + "".join(trial):
                continue
            edits = sum(1 for a, b in zip(trial, current, strict=True) if a != b)
            if best is None or edits < best[0]:
                best = (edits, trial)
        if best is None:
            return None
        for i, letter in enumerate(best[1]):
            sequence[mz_lo + i] = letter
        return best[0]

    def _codons_after_aug(self, switch) -> tuple[str, ...]:
        """The three codons after the start codon, verbatim.

        **Carried as sequence, not as a verdict, because the rare-codon SET is contested.**
        Two definitions exist -- this class's five (AGG AGA CGA AUA CUA, the classic rare
        E. coli codons) and the notebook objective's eight (those plus CGG, CCC, UCG) --
        and the difference is not cosmetic. Measured over 2,176 designs per geometry: the
        five flag 32.4%, the eight flag 50.0%, and **17.6% are flagged only by the extras**
        (CCC 192, CGG 192, UCG never). When that screen was a filter, those 384 designs per
        geometry were being dropped by the choice of set.

        Which set is correct is a question about E. coli codon usage, so it is not settled
        in passing here. With the codons themselves on the design, the count under any set
        is one comprehension away and neither existing set has to change.
        """
        start = switch.domains["aug"][1]
        codons = tuple(switch.sequence[start + 3 * i : start + 3 * i + 3] for i in range(3))
        return tuple(codon for codon in codons if len(codon) == 3)

    def _rare_codons_after_aug(self, switch) -> int:
        """How many of the three codons after the start are rare in this host.

        **Counted and reported, never filtered.** They are enriched among the designs the
        folding score likes -- AGG and CGG are G-rich, so they strengthen pairing and the
        model rewards what the cell punishes -- which is a reason to see the number beside a
        design, not to drop it silently.

        Under THIS class's ``RARE_CODONS``. ``_codons_after_aug`` carries the codons
        themselves for a reader who means the other set; see its note for the 17.6%.
        """
        return sum(1 for codon in self._codons_after_aug(switch) if codon in self.RARE_CODONS)

    def _overlap_lengths(
        self, trigger_a: str, trigger_b: str, constraints: Constraints | None = None
    ) -> tuple[int, ...]:
        """Overlap lengths at which these two triggers actually share a duplex, longest first.

        **The overlap has to be re-derived here, and this is the only place it can be.**
        ``find_trigger_pairs`` discovers it while scanning ONE transcript and reports it as
        ``_TriggerPair``, but a ``TriggerSet`` arrives as two independent
        ``TriggerCandidate`` records and that record has no field for ``len_x`` or for the
        overlap coordinates. It cannot have a sensible one either: the overlap is a property
        of the PAIR, not of either trigger.

        So it is recomputed from the sequences, and the architecture fixes where to look
        rather than leaving it to a search. Trigger A reads ``k1 · bulge · main_pre · xA ·
        extA``, so ``x`` begins at ``ARM_LEN``; trigger B reads ``k2 · xB · r2``, so ``x*``
        begins at ``len_k2 = invasion_len - len_x``. Both offsets are exactly the ones
        ``secondary_stems`` and ``_secondary_domains`` slice at, so a length returned here
        is one those two will agree with.

        **This works across two transcripts, which the mCherry path never needed.** Nothing
        below reads a transcript or a coordinate -- only the two sequences -- so a trigger
        from one gene pairs with a trigger from another exactly as two windows of one
        transcript do. That is what the PFAS targets require.

        Longest first, because a shorter overlap is strictly dominated: both triggers'
        footprints on the stem arm are the same regardless, so trimming ``x`` only moves
        positions out of the conflict-free core into the contested region and degrades
        trigger A's site, trigger B's site and the lock at once.
        """
        constraints = Constraints() if constraints is None else constraints
        min_a, min_b = self.role_footprints()
        if len(trigger_a) < min_a or len(trigger_b) < min_b:
            # `is_compatible` reports this with a reason and the designer calls it first,
            # so reaching here means a direct caller. Returning no overlap rather than
            # trusting the gate: a short trigger does NOT fail the overlap test -- the
            # offsets it slices at are all near the 5' end -- it passes, and then
            # `secondary_stems` raises `fixed alignment needs equal lengths` because
            # trigger A was too short to supply an `ext` as long as trigger B's `k2`.
            return ()
        # The declared range, intersected with what this geometry can actually build.
        # `overlap_range` was a field on `Constraints` that nothing read: this walked
        # `range(invasion, MIN_OVERLAP - 1, -1)` and ignored it, so a caller setting it got no
        # error and no change. The ceiling is the family's own `SECONDARY_INVASION_LEN` -- 18
        # for this geometry and 17 for Kim's, whose arm is 20 but which trigger B invades only
        # 17 of -- so a declared ceiling can only narrow it, never widen it past what the
        # architecture has arm for.
        low, high = constraints.overlap_range
        floor = max(self.MIN_OVERLAP, int(low))
        ceiling = min(self.SECONDARY_INVASION_LEN, int(high))
        for len_x in range(ceiling, floor - 1, -1):
            # From the GEOMETRY, never from `ceiling`. This is where trigger B's `x*` begins --
            # the offset `secondary_stems` and `_secondary_domains` slice at -- so a narrowed
            # `overlap_range` must shrink the SEARCH and never move trigger B's site.
            len_k2 = self.SECONDARY_INVASION_LEN - len_x
            x = trigger_a[self.ARM_LEN : self.ARM_LEN + len_x]
            x_star = trigger_b[len_k2 : len_k2 + len_x]
            if len(x) != len_x or len(x_star) != len_x:
                # The window is too short to carry the overlap at that offset. Not an error:
                # `trigger_lengths` is a constraint and a 30-nt window cannot hold a 36-nt
                # footprint, which `is_compatible` is the one to report.
                continue
            if x == sq.reverse_complement(x_star):
                # The MAXIMAL run only, and then stop. `find_trigger_pairs` gives the
                # reasoning: truncating an overlap is strictly dominated, because both
                # triggers' footprints on the stem arm are the same length regardless, so a
                # shorter x only moves positions out of the conflict-free core into the
                # contested region and degrades trigger A's site, trigger B's site and the
                # lock at once. Returning the sub-overlaps as well multiplied the design
                # space fivefold with nothing but dominated designs in it.
                return (len_x,)
        return ()

    def _designs_for_overlap(
        self,
        trigger_set: TriggerSet,
        role_a: TriggerCandidate,
        role_b: TriggerCandidate,
        trigger_a: str,
        trigger_b: str,
        len_x: int,
        constraints: Constraints,
    ) -> Iterator[GateDesign]:
        """Every architecture variant for one role assignment at one overlap length."""
        stems = [
            stem
            for stem in self.secondary_stems(trigger_a, trigger_b, len_x)
            # A positive lock is not a lock. Dropping these is not a hidden filter: an
            # unlocked secondary stem means trigger B has nothing to free, so the construct
            # is not the architecture being built.
            if stem.lock_energy <= 0.0
        ]
        if not stems:
            return
        # **This sort collapses a Pareto front onto one of its three axes.**
        # `secondary_stems` returns the NON-DOMINATED set over (lock_energy, a_site_energy,
        # b_site_energy), so every stem it offers is already a distinct trade among locking the
        # hairpin, letting trigger A grip the secondary arm, and letting trigger B invade it.
        # Measured on 404 real PFAS pairs, that front holds a median of 82 usable stems (mean
        # 89.4, max 268), and the best DROPPED stem is a median of only 0.40 kcal/mol behind the
        # last one kept. Taking the first `stems_per_pair` by lock_energy therefore does not take
        # the two best stems; it takes two points from one edge of the front and discards the
        # a_site_energy trade entirely -- the axis the architecture's own claim rests on.
        # Widening this is a budget decision: every usable stem on every PFAS pair is 612M
        # designs. Carried as a declared cap rather than silently, and this is what it costs.
        selected = _select_stems(stems, constraints.stems_per_pair, constraints.stem_order)
        for stem_index, stem in enumerate(selected):
            # Only the schemes that gate. A-anchored is measured dead -- 0 of 4,330 ever
            # gated, with opening SEP identically 0.000 and an A_M ratio of exactly 1.000
            # across all 392 that pass every other test, which is a trigger pair that does
            # not change the switch at all. `unlocked` cannot gate by construction.
            if stem.scheme not in ("B-anchored", "mixed"):
                continue
            base = self.assemble(trigger_a, trigger_b, len_x, stem)
            for closure, upper3, lower3 in self._axis_grid(constraints.closure_set):
                built = self._apply_axes(base, closure, upper3, lower3)
                if built is None:
                    continue
                switch, notes = built
                # `assembly_violations` had no caller anywhere in the engine until now, so
                # three switch-level checks it implements -- an upstream AUG, an in-frame
                # stop, a frame shift -- were written, tested and never run. It is also
                # where the motif screen moved to, so this is the one place the finished
                # molecule is read.
                faults = self.assembly_violations(switch)
                if faults:
                    notes = {**notes, "assembly_violations": faults}
                rbs_start = switch.domains["rbs_loop"][0]
                aug_end = switch.domains["aug"][1]
                outside = [i for i in sq.find_augs(switch.sequence) if not rbs_start <= i < aug_end]
                augs_outside = len(outside)
                augs_upstream = sum(1 for i in outside if i < rbs_start)
                architecture = {
                    "geometry": self.geometry_name,
                    "scheme": stem.scheme,
                    "len_x": len_x,
                    "stem_index": stem_index,
                    "closure": closure[0],
                    "upper3": upper3[0],
                    "lower3": lower3[0],
                    "trigger_a_id": role_a.trigger_id,
                    "trigger_b_id": role_b.trigger_id,
                    "gene_a": role_a.gene_id,
                    "gene_b": role_b.gene_id,
                    # `SwitchValidator.validate` reads this and SILENTLY SKIPS the
                    # exactly-one-AUG and in-frame-stop checks when it is absent, so it is
                    # not optional -- a design without it loses two checks with no sign.
                    "aug_index": switch.domains["aug"][0],
                    # **Where the ribosome loads.** Everything downstream of this is
                    # scanned for a competing start codon; everything upstream of it is
                    # 5' of the Shine-Dalgarno sequence, where prokaryotic initiation does
                    # not occur. The three domains up there (`main_pre_star`, `k1_star`,
                    # `bulge_star`) are a reverse complement of the sensed gene and are not
                    # ours to edit, so an AUG landing in one of them is a property of the
                    # target rather than a design choice -- measured, 3,716 of them across
                    # 2,176 designs, none of them reachable.
                    "rbs_span": switch.domains["rbs_loop"],
                    # The motif that must appear ONLY inside that loop. Named here because
                    # which sequence counts as a ribosome binding site is the family's
                    # knowledge, not the shared validator's -- the eukaryotic track would
                    # name a Kozak instead.
                    "rbs_core_motif": self.RBS_CORE,
                    # Counted, not dropped: see `rbs_span` above.
                    "augs_outside_window": augs_outside,
                    "augs_upstream_of_rbs": augs_upstream,
                    # The real domain map, as `assemble` built it. See this patch's note:
                    # the notebook re-derives it from the string, 3'-anchored, which is a
                    # second definition of the same thing.
                    "domain_map": {name: tuple(span) for name, span in switch.domains.items()},
                    # The two opening windows, named apart because they measure different
                    # things: the stem's arms, and the ribosome's footprint.
                    "main_stem_arms": (switch.domains["main_z"], switch.domains["main_pre"]),
                    "w_rank": switch.span(-17, 13),
                    "w_flank": switch.span(-24, 13),
                    "lock_energy": stem.lock_energy,
                    "ddg_pref": stem.ddg_pref,
                    "a_site_energy": stem.a_site_energy,
                    "b_site_energy": stem.b_site_energy,
                    # The symmetric partner of `ddg_pref`, which already IS
                    # `lock_energy - b_site_energy` and is therefore not repeated under a second
                    # name. That difference asks whether trigger B can displace the switch's own
                    # copy, and `>= 0` is required (R6). This one asks the same question for
                    # trigger A on the secondary arm -- and no threshold is applied, because
                    # there is no measured distribution to set one from yet. Carried, nothing
                    # reads it. Measured on this branch's own designs the margin runs to a median
                    # of -4.36 with a maximum of +2.66, against Kim's working +3.86, so the
                    # direction the data points in is that we are too stingy to A, not too
                    # generous -- which is exactly why the threshold waits for the distribution.
                    "lock_minus_a_site": stem.lock_energy - stem.a_site_energy,
                    **notes,
                }
                yield GateDesign(
                    design_id=(
                        f"{self.design_prefix}-{role_a.trigger_id}-{role_b.trigger_id}"
                        f"-x{len_x}-s{stem_index}"
                        f"-{closure[0]}-{upper3[0]}-{lower3[0]}"
                    ),
                    gate_kind=self.kind,
                    host=self.host,
                    trigger_set=trigger_set,
                    sequence=switch.sequence,
                    dot_bracket=switch.dot_bracket,
                    architecture=architecture,
                )


class ProkaryoticToeholdGate(ToeholdGate):
    """Single-input toehold family for prokaryotic translation."""

    name = "prokaryotic_toehold"
    design_prefix = "prokaryotic_toehold"
    label = "Prokaryotic Toehold"
    description = "Prokaryotic single-input translational control"
    supported_hosts: ClassVar[frozenset[Host]] = frozenset({Host.ECOLI, Host.C_ACNES})


class ProkaryoticToeholdAndGate(ToeholdAndGate):
    """Two-input AND toehold family for prokaryotic translation."""

    name = "prokaryotic_toehold_and"
    design_prefix = "prokaryotic_toehold_and"
    label = "Prokaryotic AND Toehold"
    description = "Prokaryotic two-input translational AND"
    supported_hosts: ClassVar[frozenset[Host]] = frozenset({Host.ECOLI, Host.C_ACNES})


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


def _intended_duplexes(
    domains: dict[str, tuple[int, int]],
) -> dict[str, tuple[range, range]]:
    r"""The four duplexes the two hairpins are meant to form, as ranges to be zipped.

    Each entry is ``(ascending, descending)`` so that ``a[k]`` is the base meant to pair with
    ``b[k]``; a caller zips them. Pairing is antiparallel, which is why the 3' side counts down::

        main stem     main_pre_star <-> main_pre        9 bp
                      k1_star       <-> main_z          6 bp
        secondary     sw_x          <-> sw_xs       len_x bp
                      k2_star       <-> secondary_z    k2 bp

    Read entirely off the domain map ``assemble`` returns, so both geometries are measured
    against their own intended shape without assuming any length. ``objective_energy`` derives
    the same four from ``len(switch) - 75`` plus arithmetic for the secondary spans because from
    a CSV row a bare string is all it has; here the spans are named, so there is nothing to
    re-derive and no 3'-anchored assumption to break when a 3'-side length changes.

    **What is deliberately absent.** The linker and the cap/r2* stretch carry internal structure
    by design, so counting their folding as deviation is what makes a whole-molecule ensemble
    defect the wrong instrument. The loops (``rbs_loop``, ``secondary_loop``) are unpaired by
    intent. And the **AUG bulge** (``bulge_star`` against ``aug``) is not a stem on purpose -- the
    AUG sits open in the OFF state and the ``closure`` axis varies it deliberately -- so scoring
    it as deviation would penalise the very thing being explored. Its openness is reported
    separately, as ``aug_{state}``.
    """

    def pair(five: str, three: str) -> tuple[range, range]:
        lo_a, hi_a = domains[five]
        lo_b, hi_b = domains[three]
        return range(lo_a, hi_a), range(hi_b - 1, lo_b - 1, -1)

    return {
        "main_pre": pair("main_pre_star", "main_pre"),
        "k1": pair("k1_star", "main_z"),
        "lock": pair("sw_x", "sw_xs"),
        "sec": pair("k2_star", "secondary_z"),
    }


def _duplex_formed(matrix: list[list[float]], left: range, right: range) -> float | None:
    """How much of one intended duplex actually forms in this tube, 0 to 1.

    One term per pair. The matrix is symmetric with a zero diagonal, so summing both triangles
    reads a probability above 1 -- a real bug in this repo's history, which is why the index
    order is forced here rather than trusted.

    Returns ``None`` when no pair of the duplex lies inside the matrix, never ``0.0``: higher is
    better, so zero is the worst score rather than a missing one, and a duplex entirely outside
    the matrix means the domain map and the folded strands are out of step.
    """
    pairs = [
        (i, j) for i, j in zip(left, right, strict=False) if i != j and max(i, j) < len(matrix)
    ]
    if not pairs:
        return None
    return sum(matrix[min(i, j)][max(i, j)] for i, j in pairs) / len(pairs)


def _mean_paired_to(
    matrix: list[list[float]], span: tuple[int, int], partner: tuple[int, int]
) -> float:
    """Mean probability that each base of ``span`` is paired to **something in** ``partner``.

    The partner-aware sibling of ``_mean_unpaired``, and the distinction is the point: "x* is
    open" and "x* is bound to trigger A" are different facts, and a design can satisfy the first
    while failing the second by refolding onto a third thing. One term per pair, because the
    matrix is symmetric and summing both triangles would push a probability above 1.

    Returns 0.0 for an empty span rather than raising: that is a caller error which should surface
    as a visibly impossible measurement, not as an exception inside a tube loop.
    """
    lo, hi = span
    if hi <= lo:
        return 0.0
    total = 0.0
    for i in range(lo, hi):
        for j in range(*partner):
            total += matrix[i][j] if i < j else matrix[j][i]
    return total / (hi - lo)


def _mean_unpaired_3prime_weighted(matrix: list[list[float]], start: int, end: int) -> float | None:
    """``_mean_unpaired`` with TRIANGULAR weights rising toward the 3' end of the span.

    For ``r2_star``, whose 3' end abuts the secondary hairpin's first base, this is "openness
    weighted by closeness to the hairpin": the base next to ``sw_x`` weighs ``L`` and the base
    ``L - 1`` nucleotides away weighs 1. Measured span on a real design -- ``r2_star`` 3-35,
    ``sw_x`` starting at 35 -- so distance from the hairpin grows toward the 5' end and the
    weight grows the other way.

    **Why a trigger's toehold should not be averaged flat.** Nucleation happens at one end, not
    across a whole window, so a 32-nt region open at its far end and closed where the trigger
    actually arrives scores the same as the reverse under a flat mean. On a 32-nt span these
    weights sum to 528, of which the 3'-most 9 bases hold 252 and the 5'-most 9 hold 45 -- 47.7%
    against 8.5%, where a flat mean gives each group 28.1%. The two cannot be confused for one
    another.

    Triangular rather than harmonic or exponential **by declaration, not by evidence**: it is the
    gentlest form consistent with "weighted by distance", and the flat mean is carried beside it
    so which form discriminates stays a measurement rather than an assertion.

    Returns ``None`` on the same contract as ``_mean_unpaired`` -- an empty span, or one that
    does not lie inside the matrix, is a missing measurement and never a zero.
    """
    n = len(matrix)
    if not 0 <= start < end <= n:
        return None
    total = weight_sum = 0.0
    for offset, index in enumerate(range(start, end), start=1):
        unpaired = max(0.0, 1.0 - sum(matrix[index]))
        total += offset * unpaired
        weight_sum += offset
    return total / weight_sum


#: The shared span reduction, re-exported under its historic private name.
#:
#: The definition now lives in ``gates/tools/folding.py`` beside the adapter that produces
#: the matrix it reads, which is where this module's own docstring asked for it to be
#: promoted. Sixteen modules import ``_mean_unpaired`` from here, so the name is kept as
#: an alias rather than broken; new code should import ``mean_unpaired`` from the tool.
#: ``unpaired_defect`` replaced the ``1.0 - _mean_unpaired(...)`` that used to be written
#: out at each call site.
_mean_unpaired = mean_unpaired


# --- The AND gate's secondary (inhibitory) stem -------------------------------------
#
# The top half of that stem carries three claims that cannot all be met. Trigger B must
# invade the ascending arm, trigger A must nucleate on the descending arm, and the two
# arms must hold each other shut when either trigger arrives alone. Across the overlap
# `x` the three coincide and nothing is decided. Above it they do not, and at each
# disagreeing position exactly two of the three can be served. These helpers enumerate
# that choice rather than resolving it with a global rule, because which pair to serve is
# a different answer at different positions.


class TrimmedToeholdAndGate(ProkaryoticToeholdAndGate):
    """A0 with a shortened toehold, for testing whether a shorter ``r2*`` binds better.

    A long toehold gives trigger B more to grip, and also more to fold against itself.
    ``toehold.csv`` measures how unpaired the 3' end is; this changes it. Trigger B is
    untouched -- it keeps its full ``r2`` and the trigger-pair set is identical -- so the
    only difference is that the switch complements less of it.

    The switch shortens by ``TOEHOLD_TRIM``, which moves every domain downstream of the
    toehold. Anything holding a hard-coded offset will be wrong, which is why
    ``vista_metrics`` derives its spans from a real assembly rather than listing them.
    """

    version = "trimmed-toehold-2"
    TOEHOLD_TRIM: ClassVar[int] = 8


class KimSecondaryArmToeholdAndGate(ProkaryoticToeholdAndGate):
    """A0 with Kim 2019's verified inhibitory geometry on the secondary hairpin.

    Three constants, nothing else. The parent stays at this project's own geometry -- an
    18-nt secondary arm that trigger B invades completely -- so both are runnable and a
    result at one can be diffed against the other on the same trigger pairs, which is the
    only way to tell whether Kim's rule helps *here*.

    **What changes.** The arm grows to 20 nt while trigger B's invasion domain shrinks to
    17, so B stops 3 nt short of the loop and those 3 pairs are supplied by the design
    rather than by the transcript. They are ``AUA``: deliberately the weakest ladder
    available, so the pairs B cannot reach are also the easiest to melt.
    ``architecture_comparison.md`` records that Kim applies this rule to **both** hairpins
    and that we applied it to neither; this closes half that gap.

    **What it costs.** Trigger B's window is 3 nt shorter, and the overlap is now bounded
    by the invasion length rather than the arm, so ``find_trigger_pairs`` returns a
    slightly different candidate set and stage 1 must be re-run before anything folds.
    The assembled switch is 167 nt rather than 161, which moves every domain downstream of
    the secondary hairpin -- any hard-coded offset will be wrong, which is why
    ``vista_metrics`` verifies its own against a real assembly instead of trusting them.
    """

    version = "kim-secondary-2"

    SECONDARY_ARM_LEN: ClassVar[int] = 20
    SECONDARY_INVASION_LEN: ClassVar[int] = 17
    SECONDARY_CAP: ClassVar[str] = "AUA"


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
    #: Positions still able to pair anywhere in the alignment, contiguous or not. The
    #: quantity actually minimised: a run of three is worse when the rest still pairs.
    pairable_positions: int = 0
    #: Residual duplex energy against the site, kcal/mol. Less negative is more disabled;
    #: ``None`` when the model could not evaluate it.
    residual_energy: float | None = None


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
    invasion_len: int | None = None
    """How much of the secondary arm trigger B invades. ``None`` means ``arm_len``, which
    is this architecture's default and what made the two indistinguishable."""

    @property
    def len_k2(self) -> int:
        """Trigger B's invasion domain. Every nucleotide the overlap takes is one fewer.

        Sized by the **invasion** length, not the arm: with Kim's 20-nt arm invaded to 17,
        trigger B's window shrinks by the 3 nt it never reaches, and those 3 come from the
        cap instead of from the transcript.
        """
        return (self.arm_len if self.invasion_len is None else self.invasion_len) - self.len_x

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
class _CrossGenePair:
    """One reverse-complementary run shared by **two different transcripts**.

    ``_TriggerPair``'s sibling for the cross-gene case, and deliberately not the same record.
    ``_TriggerPair`` carries two coordinates into one sequence and offers ``gap()`` and
    ``disjoint()`` because two windows on one transcript can collide. Windows on different
    transcripts cannot, so those methods would have no meaning here and are absent rather
    than returning a polite constant.

    ``gene_a``/``gene_b`` are the ids the caller indexed the transcripts by, carried so a
    candidate can say which gene each half came from without a second lookup. Coordinates are
    0-based, inclusive start and exclusive end, as everywhere else.
    """

    gene_a: str
    gene_b: str
    #: Start of the shared run in gene_a, which supplies trigger A.
    x_start: int
    #: Start of its reverse complement in gene_b, which supplies trigger B.
    xstar_start: int
    len_x: int
    arm_len: int
    invasion_len: int
    toehold_b_len: int

    @property
    def len_k2(self) -> int:
        """Trigger B's invasion domain 5' of the overlap. Cancels ``len_x``, as in one gene."""
        return self.invasion_len - self.len_x

    def window_a(self) -> tuple[int, int]:
        """Trigger A's footprint in ``gene_a``: the stem arm, the overlap, the extension."""
        return self.x_start - self.arm_len, self.x_start + self.len_x + self.len_k2

    def window_b(self) -> tuple[int, int]:
        """Trigger B's footprint in ``gene_b``: invasion, overlap, then the free toehold."""
        return (
            self.xstar_start - self.len_k2,
            self.xstar_start + self.len_x + self.toehold_b_len,
        )

    def fits(self, length_a: int, length_b: int) -> bool:
        """Both footprints lie inside their own transcript."""
        a_start, a_end = self.window_a()
        b_start, b_end = self.window_b()
        return a_start >= 0 and b_start >= 0 and a_end <= length_a and b_end <= length_b

    def swapped(self) -> "_CrossGenePair":
        """The same run with the roles exchanged: gene_b supplies A, gene_a supplies B.

        The run is symmetric but the construct is not, so both assignments are real
        candidates and `generate_designs` would have to try both anyway. Note the overlap
        coordinates swap with the roles -- the run in gene_b read as ``x`` begins at
        ``xstar_start``, and its partner in gene_a at ``x_start``.
        """
        return _CrossGenePair(
            gene_a=self.gene_b,
            gene_b=self.gene_a,
            x_start=self.xstar_start,
            xstar_start=self.x_start,
            len_x=self.len_x,
            arm_len=self.arm_len,
            invasion_len=self.invasion_len,
            toehold_b_len=self.toehold_b_len,
        )


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

    #: ``fixed_alignment_energy(k2_star, secondary_z)`` **including the cap** -- the free energy
    #: of the secondary hairpin's own stem, in kcal/mol. Negative is a duplex that forms, so
    #: ``generate_designs`` keeps ``<= 0``: a positive value is not a weak lock, it is no lock.
    #: Do not read it as the ``>= 0`` test above, which is ``ddg_pref`` and a different quantity.
    lock_energy: float

    #: ``fixed_alignment_energy(x + ext, secondary_z + revcomp(x))`` -- **trigger A's binding to
    #: the secondary arm**, in kcal/mol. This is the quantity the architecture's central claim
    #: rests on: shortening trigger A's toehold and removing the gap between the hairpins is
    #: affordable only if A's grip on the secondary stem makes up for it.
    #:
    #: It is carried onto every design's ``architecture`` and **nothing ranks on it.** The three
    #: selection arms are IED gain, the A_M ratio and opening SEP; none reads this, and
    #: ``generate_designs`` sorts the stems by ``lock_energy`` alone. The notebook carries
    #: ``lock_minus_a_site`` -- the trade between locking the hairpin and letting A grip it --
    #: and that is not ranked on either.
    a_site_energy: float

    #: ``fixed_alignment_energy(k2, k2_star)`` -- trigger B's binding to the invaded arm, in
    #: kcal/mol. With ``lock_energy`` it forms ``ddg_pref``, the displacement test.
    b_site_energy: float

    @property
    def scheme(self) -> str:
        """Which design family this build belongs to, for stratifying a bench panel.

        Scheme A anchors every contested position to trigger A and scheme B anchors every
        one to trigger B, so each reaches ``2^n`` builds; scheme C lets positions choose
        independently, reaching ``3^n`` and containing both as strict subsets. A build using
        *both* lock states is therefore reachable by neither — that is what "mixed" means,
        and it is the only label that is evidence scheme C earns its cost.
        """
        states = set(self.states)
        locks_a, locks_b = "lockA" in states, "lockB" in states
        if locks_a and locks_b:
            return "mixed"
        if locks_a:
            return "A-anchored"
        if locks_b:
            return "B-anchored"
        return "unlocked"


def _secondary_domains(
    trigger_a: str, trigger_b: str, len_x: int, main_arm_len: int, invasion_len: int | None = None
) -> tuple[str, str]:
    """Trigger A's extension past the overlap, and trigger B's invasion domain.

    Trigger A reads ``k1 · bulge · main_pre · xA · extA`` and trigger B reads
    ``k2 · xB · r2``, so both wanted domains are slices of sequences already in hand.
    This is the adapter between a chosen trigger pair and the stem builder; the builder's
    own two-transcript entry point is for a case this architecture does not use.

    The two lengths are separate because they describe different hairpins. ``main_arm_len``
    places trigger A's extension -- it begins past the main arm and the overlap -- while
    ``invasion_len`` sizes trigger B's invasion domain on the *secondary* arm. They were one
    parameter while both hairpins were 18 nt, which is why a 20-nt secondary arm could not
    be expressed. ``invasion_len`` defaults to ``main_arm_len``, reproducing that.
    """
    if invasion_len is None:
        invasion_len = main_arm_len
    len_k2 = invasion_len - len_x
    ext_start = main_arm_len + len_x
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


def _select_stems(stems: list["_SecondaryStem"], budget: int, order: str) -> list["_SecondaryStem"]:
    """Which stems of a pair's Pareto front to build on, under ``Constraints.stem_order``.

    ``secondary_stems`` returns the non-dominated set over ``(lock_energy, a_site_energy,
    b_site_energy)``, so the question is not which stems are best -- none dominates another --
    but which part of the front to spend the budget on.

    ``"lock"`` is the historic rule and is kept exactly: sort by ``lock_energy``, take the first
    ``budget``. It samples one edge of the front, and the ``a_site_energy`` axis -- trigger A's
    grip on the secondary arm, the architecture's own claim -- is not represented at all.

    ``"front"`` bins the front into tertiles on each of those two axes independently and takes
    one stem per occupied bin, the one nearest its bin's centre so the pick represents the bin
    rather than its corner. Bins are visited in a fixed order and any budget left over goes to
    the lock-sorted remainder, so the result is deterministic and a resumed run rebuilds it.

    ``"front_tops"`` is ``"front"`` without the quota, plus the third axis:

    * one stem per **non-empty** square of the 3x3 board, nearest that square's centre. An empty
      square contributes nothing -- the slot is given up rather than filled from the lock edge.
    * the single strongest stem on **each of the three Pareto axes** -- ``lock_energy``,
      ``a_site_energy`` and ``b_site_energy`` -- deduplicated against the representatives.

    The third axis matters because the board cannot see it. ``secondary_stems`` returns the
    non-dominated set over all three, but the squares are cut on two, so stems differing only in
    trigger B's grip land in one square and the centre rule picks among them blind to it:
    measured, ``b_site_energy`` still spreads a median 3.05 kcal/mol inside a square and up to
    15.00 in the worst one. Its own extreme puts it back in the set at the cost of one stem.

    **``budget`` is ignored for this order.** The data decides the count, so there is no quota and
    no leftover slot to fill. Measured occupancy on 60 real cells is 7 of 9 squares (median;
    6:3, 7:34, 8:19, 9:4), so the natural output is about 10 stems and runs roughly 9 to 12.
    Callers record the actual count -- it varies between pairs, which is only safe if the row says
    what it was.

    An unknown ``order`` falls back to ``"lock"`` and is **not** silently different: the caller
    declared a value this function does not implement, and the historic rule is the safe reading.
    """
    if budget <= 0 or not stems:
        return []
    by_lock = sorted(stems, key=lambda stem: stem.lock_energy)
    if order not in ("front", "front_tops"):
        return by_lock[:budget]
    if order == "front" and len(stems) <= budget:
        return by_lock[:budget]

    #: Slices per axis. Three, and left at three deliberately: the depth question that would
    #: have justified a finer board is answered by `front_tops` adding the axis extremes
    #: instead, so this stays a constant rather than becoming a knob nobody turns. It is named
    #: here so a reader can find it, and the selection rule itself is recorded per row.
    bins = 3
    locks = sorted(stem.lock_energy for stem in stems)
    sites = sorted(stem.a_site_energy for stem in stems)

    def edges(values: list[float]) -> list[float]:
        return [values[int(len(values) * (i + 1) / bins) - 1] for i in range(bins - 1)]

    def which(value: float, cuts: list[float]) -> int:
        for i, cut in enumerate(cuts):
            if value <= cut:
                return i
        return len(cuts)

    lock_cuts, site_cuts = edges(locks), edges(sites)
    buckets: dict[tuple[int, int], list[_SecondaryStem]] = {}
    for stem in stems:
        key = (which(stem.lock_energy, lock_cuts), which(stem.a_site_energy, site_cuts))
        buckets.setdefault(key, []).append(stem)

    chosen: list[_SecondaryStem] = []
    for key in sorted(buckets):
        group = buckets[key]
        mid_lock = sum(stem.lock_energy for stem in group) / len(group)
        mid_site = sum(stem.a_site_energy for stem in group) / len(group)
        chosen.append(
            min(
                group,
                key=lambda stem: (
                    (stem.lock_energy - mid_lock) ** 2 + (stem.a_site_energy - mid_site) ** 2,
                    stem.lock_energy,
                ),
            )
        )
        if order == "front" and len(chosen) >= budget:
            return chosen[:budget]

    taken = {id(stem) for stem in chosen}
    if order == "front_tops":
        # The strongest stem on each Pareto axis. These are free energies, so "strongest" is
        # most negative; the extra sort keys make the choice total, because two stems with the
        # same energy on one axis must still order deterministically for a resumed run to
        # rebuild the same set.
        for axis in ("lock_energy", "a_site_energy", "b_site_energy"):
            top = min(
                stems,
                key=lambda stem: (
                    getattr(stem, axis),
                    stem.lock_energy,
                    stem.a_site_energy,
                    stem.b_site_energy,
                ),
            )
            if id(top) not in taken:
                taken.add(id(top))
                chosen.append(top)
        # No budget truncation: see the docstring. An empty square gave up its slot and the
        # count is whatever the data supports.
        return chosen

    # `order == "front"`: fewer occupied bins than the budget, so fill from the lock-sorted
    # remainder, which keeps the historic rule's designs in the set rather than inventing a
    # third ordering.
    for stem in by_lock:
        if len(chosen) >= budget:
            break
        if id(stem) not in taken:
            chosen.append(stem)
    return chosen[:budget]


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
