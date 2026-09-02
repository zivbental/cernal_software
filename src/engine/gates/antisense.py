"""Antisense NOT gate.

An antisense RNA silences the payload while its trigger is present, so the circuit fires
when the trigger is *absent* — the inverting element the map's NOT logic needs.

**Provenance.** The architecture and metrics below are a port of a validated
equilibrium-thermodynamics pipeline built and run outside this repo (``choose_trigger.py``
/ ``build_switch.py`` against real trigger candidates, scored against mCherry as a
stand-in payload). The port keeps the science — the switch architecture, which regions
must be open versus bound, and the Boltzmann/partition-function approach to accessibility
— and re-expresses it against this repo's ``FoldEngine`` (ViennaRNA) instead of the
original NUPACK calls, and against this file's ``GateFamily`` contract instead of a
standalone script. Where the two genuinely diverge, the divergence is called out inline
rather than silently guessed.
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


class AntisenseNotGate(GateFamily):
    """Post-transcriptional silencing. The pipeline's inverting element.

    **The mechanism:** the switch is built as ``[UTR][loop][spacer][AUG][payload]``. The
    ``UTR`` and ``spacer`` are not independent sequences — together they are one
    continuous engineered block, built as the reverse complement of a single window of the
    trigger and then split so the block's last ``spacer_length`` nucleotides become the
    spacer. ``loop`` is the host's conserved translation-initiation element (the ribosome
    binding site in *E. coli*; the Kozak context in a eukaryotic host) and is never
    engineered.

    With no trigger, the switch is designed to carry little structure of its own, so the
    loop and the start codon stay open and translation proceeds (**ON by default**). When
    the trigger appears, it hybridises with the UTR and spacer arms; the loop and AUG sit
    in the small bulge trapped between the two duplex arms, and initiation is blocked
    (**OFF**). That inversion is what makes ``NOT`` buildable, and therefore what lets a
    circuit use a **down-regulated** gene as an input — without it, only UP genes are
    usable and half the differential-expression signal is wasted.

    This ports the "trigger transcript **is** the antisense, acting directly on the
    payload" wiring the base stub's docstring names as one of two options — the simpler
    one, needing no extra transcriptional unit. The alternative (trigger drives expression
    of a *separate* antisense RNA, for amplification) is not built here.

    **The gate is generic over the payload gene.** ``payload`` is a constructor argument,
    not a hardcoded sequence, so the exact same code builds designs for GFP, mCherry, or
    any other CDS — a caller (a notebook, a future stage) picks the gene by constructing
    the gate with it, the same way ``host`` picks the organism.

    Simplifications versus the source pipeline, because rewriting the payload is a
    separate tool (``codons.variants``, still ``NotImplementedError`` — see module-level
    notes):

    * The source pipeline additionally makes the region just after ``AUG`` (a linker, or
      the payload's own first codons) trigger-complementary, and searches codon-synonymous
      rewrites of it. That needs ``CodonOptimizer.variants``, which this gate does not
      call; the real payload's first ``PAYLOAD_HEAD_LENGTH`` nucleotides are folded as-is,
      unmodified, rather than being optimised for antisense binding the way the source
      pipeline's linker search did.
    * The source pipeline also explores independent ("open"/"random") spacer sequences
      that do not bind the trigger at all, trading OFF-state strength for ON-state safety.
      Only the trigger-complementary spacer is generated here.
    * ``binding_energy_factor``'s reference ΔG was calibrated per run, from the strongest-
      binding quartile of that run's own candidate pool. ``evaluate_design`` scores one
      design in isolation and has no pool to calibrate against, so it uses the source
      pipeline's literature-reasonable fixed default instead (see ``_DG_REFERENCE_KCAL``).

    Args:
        host: Prokaryotic and eukaryotic silencing differ in efficiency and in what
            counts as sufficient complementarity — concretely, which conserved element
            (``_loop_element``) sits between the UTR and the start codon.
        folder: Shared ``FoldEngine``. Both the antisense and its target must be
            accessible for the duplex to form.
        codons: Shared ``CodonOptimizer``. Held for the payload-rewriting step named
            above; not called by this implementation (see the simplifications note).
        payload: The gene this switch controls — a full coding sequence, DNA or RNA,
            starting with a start codon (e.g. a GFP or mCherry CDS). Required: a NOT gate
            silences a specific protein's translation, and there is no meaningful design
            without knowing which one. Only the first ``PAYLOAD_HEAD_LENGTH`` nucleotides
            *after* the payload's own start codon are actually folded into each switch —
            see ``PAYLOAD_HEAD_LENGTH`` for why.

    Raises:
        ValueError: if ``payload`` is not valid RNA/DNA, or does not start with a start
            codon — always a caller error (the wrong sequence, or a fragment rather than
            a full CDS), not something a design decision can route around.
    """

    name = "antisense"
    version = "0.1.0"
    kind = GateKind.ANTISENSE_NOT
    label = "Antisense Repression"
    description = "Post-transcriptional silencing"
    supported_hosts: ClassVar[frozenset[Host]] = frozenset({Host.ECOLI, Host.YEAST, Host.HUMAN})
    max_inputs = 1
    available = True

    #: UTR-arm lengths to sweep, nucleotides. Matches the source pipeline's
    #: ``UTR_MIN_LENGTH``/``UTR_MAX_LENGTH``/``UTR_LENGTH_STEP`` (8-14 nt, step 2).
    UTR_LENGTHS: ClassVar[tuple[int, ...]] = (8, 10, 12, 14)

    #: Spacer lengths to sweep. Translation only constrains the *length* of the RBS-AUG
    #: gap (5-9 nt, 7 optimal); the source pipeline's ``SPACER_LENGTH`` fixed it at 7, but
    #: since the spacer here is one continuous block with the UTR (`trigger_complement`
    #: mode) its length is a free design parameter like the UTR's, so it is swept too.
    SPACER_LENGTHS: ClassVar[tuple[int, ...]] = (5, 7, 9)

    #: E. coli Shine-Dalgarno consensus. Matches the source pipeline's ``RBS`` constant.
    RBS_PROKARYOTIC: ClassVar[str] = "AGGAGGA"

    #: Kozak context immediately upstream of the start codon. The source pipeline never
    #: validated a eukaryotic run — this extends the same architecture using the standard
    #: consensus (``gccRccAUGG``; see ``TranslationScorer.kozak_match``) rather than
    #: leaving YEAST/HUMAN unbuildable, and is flagged here rather than guessed silently.
    KOZAK_EUKARYOTIC: ClassVar[str] = "GCCACC"

    #: Nucleotides of the payload's own CDS, immediately after its start codon, that get
    #: folded into every switch. Kudla et al. 2009 (*Science*, "Coding-sequence
    #: determinants of gene expression in E. coli") found mRNA folding strength in
    #: roughly this window around the start codon to be the strongest predictor of
    #: expression level in their assay — bigger than codon usage — and it is close to
    #: the ribosome's own ~30 nt initiation footprint. The source pipeline used the same
    #: figure (``ON_PROXY_CDS_NT = 30``).
    PAYLOAD_HEAD_LENGTH: ClassVar[int] = 30

    #: Stride between successive window offsets along the trigger. The full sweep is
    #: ``len(UTR_LENGTHS) * len(SPACER_LENGTHS) * offsets`` designs; a stride of 1 explores
    #: every offset but multiplies the search space for very little extra diversity between
    #: adjacent, near-identical windows.
    WINDOW_STEP: ClassVar[int] = 3

    #: Below this fraction accessible, ``is_compatible`` calls the trigger too structured
    #: for the antisense arm to reliably pair with — cheap gate, no folding.
    MIN_TRIGGER_ACCESSIBILITY: ClassVar[float] = 0.3

    #: Binding-energy sigmoid, ported unchanged from the source pipeline's
    #: ``DG_REFERENCE_KCAL`` / ``DG_STEEPNESS`` (see the simplification note above for why
    #: the reference is fixed here rather than pool-calibrated).
    _DG_REFERENCE_KCAL: ClassVar[float] = -15.0
    _DG_STEEPNESS: ClassVar[float] = 2.0

    def __init__(
        self, host: Host, folder: FoldEngine, codons: CodonOptimizer, payload: str
    ) -> None:
        self.host = host
        self.folder = folder
        self.codons = codons

        payload_rna = sq.to_rna(payload)
        if not sq.is_valid_rna(payload_rna):
            raise ValueError("payload must be a non-empty RNA or DNA sequence.")
        if payload_rna[:3] != sq.START_CODON:
            raise ValueError(
                f"payload must be a full CDS starting with a start codon, got {payload_rna[:3]!r}."
            )
        self.payload = payload_rna
        # Computed once, not per design: it never varies across generate_designs' sweep.
        self.payload_head = payload_rna[3 : 3 + self.PAYLOAD_HEAD_LENGTH]

    def _loop_element(self) -> str:
        """The conserved translation-initiation element between spacer and AUG.

        Never engineered — it is not derived from the trigger and does not vary across
        ``generate_designs``' sweep, unlike the UTR and spacer arms either side of it.
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
        """Can this family invert this trigger set?

        **Cheap checks only** — nothing here folds. One input, and it must be a
        *repressor*: this gate silences the payload while its trigger is present, so the
        trigger is the transcript that must be **absent** for expression, which is exactly
        what ``TriggerSet.repressors`` means. The trigger must also be long enough to
        supply a UTR arm, the loop element and a spacer, and accessible enough for that
        arm to plausibly pair — both read from fields Stage 2 already computed, not
        recomputed here.
        """
        if trigger_set.arity != self.max_inputs:
            return Compatibility.no(
                f"This gate takes exactly one input, but {trigger_set.arity} were given."
            )
        if trigger_set.activators or len(trigger_set.repressors) != 1:
            return Compatibility.no(
                "This gate silences the payload while its trigger is present, so its one "
                "input must be a transcript that has to be ABSENT for the payload to "
                "express — a repressor, not an activator."
            )
        if self.host not in self.supported_hosts:
            return Compatibility.no(f"Antisense repression is not offered for {self.host.value}.")

        trigger = trigger_set.repressors[0]
        footprint = min(self.UTR_LENGTHS) + len(self._loop_element()) + min(self.SPACER_LENGTHS)
        if trigger.length < footprint:
            return Compatibility.no(
                f"The trigger is {trigger.length} nt, too short to build an antisense "
                f"switch — this gate needs at least {footprint} nt to fit a "
                "5' UTR arm, the ribosome binding site (or Kozak context) and a spacer."
            )
        if trigger.accessibility < self.MIN_TRIGGER_ACCESSIBILITY:
            return Compatibility.no(
                f"The trigger is only {trigger.accessibility:.0%} accessible in its own "
                "context — too structured for an antisense arm to reliably pair with it."
            )
        return Compatibility.yes()

    def generate_designs(
        self, trigger_set: TriggerSet, constraints: Constraints
    ) -> Iterator[GateDesign]:
        """Build an antisense element that silences the payload when the trigger is present.

        Sweeps ``UTR_LENGTHS x SPACER_LENGTHS x window offset`` along the trigger. For
        each combination, the UTR and spacer arms are cut from one continuous window of
        the trigger — the source pipeline's "single antisense block split between UTR and
        spacer" — and reverse-complemented, so together they are exactly what the trigger
        will hybridise against. The loop element and AUG sit between them, unengineered.
        Downstream of AUG comes ``self.payload_head`` — the real payload's own first
        ``PAYLOAD_HEAD_LENGTH`` nucleotides, set once in ``__init__`` — so every yielded
        design is specific to the gene this gate was constructed for.

        No folding happens here — cheap, structural construction only, matching
        ``is_compatible``'s no-fold rule and consistent with ``ToeholdGate.generate_designs``
        alongside it. ``evaluate_design`` is where ``folder`` gets used.

        Args:
            trigger_set: One repressor trigger, already validated by ``is_compatible``.
            constraints: ``max_switch_length`` caps the construct.

        Yields:
            ``GateDesign`` per (UTR length, spacer length, window offset) combination, with
            the swept lengths and the window's position on the trigger recorded in
            ``architecture`` — enough for ``evaluate_design`` to relocate the loop, spacer
            and AUG boundaries without re-deriving them, and enough to trace a design back
            to exactly how it was built.

        Gotcha:
            An antisense NOT is ON by default. That inverts the safety argument: a
            **failed** antisense gate expresses the payload rather than staying dark. For
            a reporter that is harmless; for an apoptosis inducer it is not, and the
            report must say so.
        """
        trigger = trigger_set.repressors[0]
        trigger_rna = trigger.sequence
        loop = self._loop_element()
        design_index = 0

        for utr_length in self.UTR_LENGTHS:
            for spacer_length in self.SPACER_LENGTHS:
                total_span = utr_length + len(loop) + spacer_length
                if total_span > trigger.length:
                    continue
                max_start = trigger.length - total_span

                for window_start in range(0, max_start + 1, self.WINDOW_STEP):
                    utr_footprint = trigger_rna[window_start : window_start + utr_length]
                    spacer_footprint_start = window_start + utr_length + len(loop)
                    spacer_footprint = trigger_rna[
                        spacer_footprint_start : spacer_footprint_start + spacer_length
                    ]

                    utr_arm = sq.reverse_complement(utr_footprint)
                    spacer_arm = sq.reverse_complement(spacer_footprint)
                    switch = utr_arm + loop + spacer_arm + sq.START_CODON + self.payload_head

                    if len(switch) > constraints.max_switch_length:
                        continue

                    design_index += 1
                    yield GateDesign(
                        design_id=f"antisense-{trigger.trigger_id}-{design_index:04d}",
                        gate_kind=self.kind,
                        host=self.host,
                        trigger_set=trigger_set,
                        sequence=switch,
                        architecture={
                            "utr_length": utr_length,
                            "loop_length": len(loop),
                            "spacer_length": spacer_length,
                            "payload_head_length": len(self.payload_head),
                            "window_start": window_start,
                            "loop_element": loop,
                            "track": self.host.track.value,
                        },
                    )

    def evaluate_design(self, design: GateDesign) -> dict[str, float | None]:
        """Measure a silencing design.

        Returns raw values on the same metric names as every other family, so the two can
        be ranked together (docs/engine.md §3.4). Every accessibility figure comes from
        ``folder.base_pair_probabilities`` — the full partition-function ensemble, never a
        single MFE structure or a per-nucleotide independence approximation, per the
        project's own scoring notes.

        Returns:
            * ``gate_folding_energy`` — ``folder.mfe`` of the whole switch, alone. A
              self-structured switch is already fighting the ON state before any trigger
              shows up.
            * ``predicted_leakage`` — here it means **residual expression when the trigger
              IS present**, the inverse of a toehold's leakage: mean P(unpaired) over the
              loop+spacer+AUG initiation region in the switch **with the trigger bound**
              (one partition function over ``"switch&trigger"``). Same metric name, same
              direction (lower is better), opposite biological event.
            * ``dynamic_range`` — the initiation region's openness with no trigger, over
              its residual openness with the trigger bound (``predicted_leakage``). Ratio
              of accessibilities, not of energies — energy is not linear in expression.
            * ``trigger_accessibility`` — carried from stage 2, not recomputed.
            * ``predicted_success_rate`` — ``hybridization_energy`` between the switch and
              trigger, passed through the source pipeline's ΔG sigmoid
              (``_binding_energy_factor``): a duplex that is not thermodynamically
              favourable will not reliably form regardless of how open either side looks
              in isolation.
            * ``gc_content`` — free, from ``sequences.gc_content``.
            * ``initiation_open_run_nt`` — longest *contiguous* run of positions with
              P(unpaired) at or above 0.5 within the initiation region, switch alone. Mean
              openness can look fine while every open position is a single free base
              between paired ones; a ribosome footprint needs a contiguous stretch, not a
              scattering of open nucleotides, so this is reported alongside the mean rather
              than instead of it. Not one of the profile's declared metrics — an
              unrecognised metric name is exactly what ``ScoringProfile.spec`` is built to
              ignore, so it is safe to report without changing anything downstream.
        """
        architecture = design.architecture
        utr_length = architecture["utr_length"]
        loop_length = architecture["loop_length"]
        spacer_length = architecture["spacer_length"]

        loop_start = utr_length
        spacer_start = loop_start + loop_length
        aug_start = spacer_start + spacer_length
        initiation_start, initiation_end = loop_start, aug_start + 3

        trigger = design.trigger_set.repressors[0]
        switch = design.sequence

        alone_matrix = self.folder.base_pair_probabilities(switch)
        on_accessibility = _mean_unpaired(alone_matrix, initiation_start, initiation_end)
        open_run = _longest_open_run(alone_matrix, initiation_start, initiation_end)

        complex_matrix = self.folder.base_pair_probabilities(f"{switch}&{trigger.sequence}")
        predicted_leakage = _mean_unpaired(complex_matrix, initiation_start, initiation_end)

        gate_folding_energy = self.folder.mfe(switch).energy

        binding_dg = hybridization_energy(switch, trigger.sequence, self.folder)
        predicted_success_rate = self._binding_energy_factor(binding_dg)

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

        Ported unchanged from the source pipeline's ``binding_energy_factor`` — see
        ``_DG_REFERENCE_KCAL`` for why the reference point is fixed rather than
        pool-calibrated here.
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


def _mean_unpaired(matrix: list[list[float]], start: int, end: int) -> float:
    """Mean P(unpaired) over ``[start, end)`` from a ``base_pair_probabilities`` matrix.

    P(unpaired) at position i is ``1 - sum(matrix[i])`` — matrix is already symmetric and
    0-indexed (``FoldEngine.base_pair_probabilities``'s contract), so this sums a position's
    pairing probability to *every* other position regardless of which strand it is on. For
    a dimer matrix that is exactly what "residual leakage" needs: a loop position paired to
    itself and one paired to the trigger both count as blocked.
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

    Mean openness treats one open base between two paired ones the same as a long open
    stretch; a ribosome footprint needs the latter. Boltzmann-weighted (from the ensemble
    matrix), not a single MFE structure's pairing pattern.
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
