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
    version = "0.8.1"
    kind = GateKind.TOEHOLD
    label = "Toehold Riboswitch"
    description = "Translational control · pre-mRNA"
    supported_hosts: ClassVar[frozenset[Host]] = frozenset({Host.ECOLI, Host.YEAST, Host.HUMAN})
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
