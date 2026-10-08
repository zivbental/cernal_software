"""Eukaryotic antisense NOT gate.

The prokaryotic family (``antisense.py``) builds ``[UTR][RBS][spacer][AUG][payload]``
and leaves the coding sequence after AUG unengineered. A scanning ribosome has no
Shine-Dalgarno and no spacer: the conserved element is one Kozak cassette that
already contains the AUG, and the trigger complementarity is split around that
cassette.

    switch   5'-[UTR arm][GCCACC][AUG][linker][payload head]-3'
    trigger  3'-[........][  gap  ][......]

The UTR arm is the reverse complement of the 3' end of a trigger window. The
linker is the reverse complement of the 5' end, forced to start with G so the
Kozak +4 position stays canonical without inserting a base (an insertion would
break the reading frame). The linker is a multiple of 3 and at most 8 amino
acids. The UTR arm is strictly longer than the linker, so most of the
complementarity sits upstream of the start.

Folding, the open-run helper and the binding sigmoid are the prokaryotic
gate's. This file does not call ViennaRNA itself.
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
    TriggerSet,
)
from engine.gates.antisense import (
    AntisenseNotGate,
    _longest_open_run,
    _mean_unpaired,
)
from engine.gates.base import GateFamily
from engine.gates.tools.binding import hybridization_energy
from engine.gates.tools.codons import CodonOptimizer
from engine.gates.tools.folding import FoldEngine


class EukaryoticAntisenseNotGate(GateFamily):
    """Translational NOT gate for a scanning ribosome.

    ON when the trigger is absent: the Kozak cassette is unpaired and initiation
    proceeds. OFF when the trigger binds both the 5' UTR arm and the short coding
    linker, trapping ``GCCACCAUG`` in the gap between them.

    Args:
        host: ``YEAST`` or ``HUMAN``. *E. coli* is rejected: that track uses
            ``AntisenseNotGate``.
        folder: Shared ``FoldEngine``.
        codons: Shared ``CodonOptimizer``. Not called. The linker is the trigger
            complement with +4 forced to G, not a codon-optimised rewrite.
        payload: Full CDS, DNA or RNA, starting with AUG. The sequence stored on
            each design is the UTR, the Kozak cassette, and the first
            ``CDS_FOLD_NT`` nucleotides of (linker + payload after its own AUG).
            The rest of the payload is attached later, at plasmid assembly, the
            same way ``AntisenseNotGate`` keeps only a payload head.

    Raises:
        ValueError: ``payload`` is not RNA/DNA, or does not start with AUG.
    """

    name = "euk_antisense"
    version = "0.1.0"
    kind = GateKind.EUK_ANTISENSE_NOT
    label = "Eukaryotic Antisense Repression"
    description = "Kozak NOT gate: trigger binds the 5' UTR and a short in-frame linker"
    supported_hosts: ClassVar[frozenset[Host]] = frozenset({Host.YEAST, Host.HUMAN})
    max_inputs = 1
    available = True

    #: Trigger windows. 30 nt is the shortest that still leaves a 15 nt UTR after
    #: a 6 nt linker and the 9 nt GCCACC+AUG gap. 100 nt is omitted: with the
    #: linker capped at 24 nt it forces a very long UTR.
    WINDOW_LENGTHS: ClassVar[tuple[int, ...]] = (30, 40, 50, 70)

    #: Same slide as ``AntisenseNotGate``. Adjacent windows are nearly identical.
    WINDOW_STEP: ClassVar[int] = AntisenseNotGate.WINDOW_STEP

    #: Canonical vertebrate Kozak context, shared with the prokaryotic family's
    #: eukaryotic loop so the two files cannot drift to two consensus strings.
    KOZAK: ClassVar[str] = AntisenseNotGate.KOZAK_EUKARYOTIC

    #: Coding sequence folded after the AUG, linker included. Matches the
    #: eukaryotic source pipeline's ``CDS_FOLD_NT``.
    CDS_FOLD_NT: ClassVar[int] = 60

    MIN_UTR_NT: ClassVar[int] = 15
    MIN_LINKER_NT: ClassVar[int] = 6
    MAX_LINKER_NT: ClassVar[int] = 24
    LINKER_STEP: ClassVar[int] = 3

    #: ``AAAAA`` on the trigger becomes poly-U on the switch.
    MAX_HOMOPOLYMER_A: ClassVar[int] = 5

    MIN_TRIGGER_ACCESSIBILITY: ClassVar[float] = AntisenseNotGate.MIN_TRIGGER_ACCESSIBILITY

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

    def _cassette(self) -> str:
        """``GCCACCAUG``. Fixed. Not reverse-complemented from the trigger."""
        return self.KOZAK + sq.START_CODON

    def required_tools(self) -> list[ToolRequirement]:
        return [ToolRequirement(name="ViennaRNA", version="2.7")]

    def is_compatible(self, trigger_set: TriggerSet, constraints: Constraints) -> Compatibility:
        """One repressor, long enough for the shortest window, on a eukaryotic host.

        No folding. Accessibility is the value stage 2 already stored.
        """
        if self.host not in self.supported_hosts:
            return Compatibility.no(
                "The eukaryotic antisense NOT gate is for yeast or human. "
                f"{self.host.value} uses the prokaryotic antisense family."
            )
        if trigger_set.arity != self.max_inputs:
            return Compatibility.no(
                f"This gate takes exactly one input, but {trigger_set.arity} were given."
            )
        if trigger_set.activators or len(trigger_set.repressors) != 1:
            return Compatibility.no(
                "This gate silences the payload while its trigger is present, so its one "
                "input must be a repressor, not an activator."
            )
        trigger = trigger_set.repressors[0]
        needed = min(self.WINDOW_LENGTHS)
        if trigger.length < needed:
            return Compatibility.no(
                f"The trigger is {trigger.length} nt, too short for a eukaryotic "
                f"antisense window (minimum {needed} nt)."
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
        """Yield one design per window and in-frame linker length.

        A window is dropped when it contains ``AAAAA`` or longer, when the UTR
        arm would not be strictly longer than the linker, when the linker has an
        in-frame stop, or when the UTR arm contains an AUG in any frame.
        """
        trigger = trigger_set.repressors[0]
        trigger_rna = sq.to_rna(trigger.sequence)
        cassette = self._cassette()
        gap = len(cassette)
        design_index = 0

        for window_length in self.WINDOW_LENGTHS:
            for window_start, window in sq.windows(trigger_rna, window_length, self.WINDOW_STEP):
                base, run = sq.longest_homopolymer(window)
                if base == "A" and run >= self.MAX_HOMOPOLYMER_A:
                    continue
                for linker_length in range(
                    self.MIN_LINKER_NT, self.MAX_LINKER_NT + 1, self.LINKER_STEP
                ):
                    utr_length = window_length - gap - linker_length
                    if utr_length < self.MIN_UTR_NT or utr_length <= linker_length:
                        continue
                    utr_arm = sq.reverse_complement(window[-utr_length:])
                    if sq.START_CODON in utr_arm:
                        continue
                    linker = _force_plus4_g(sq.reverse_complement(window[:linker_length]))
                    if sq.find_stops(linker):
                        continue

                    coding = (linker + self.payload[3:])[: self.CDS_FOLD_NT]
                    switch = utr_arm + cassette + coding
                    if len(switch) > constraints.max_switch_length:
                        continue

                    design_index += 1
                    yield GateDesign(
                        design_id=f"euk-antisense-{trigger.trigger_id}-{design_index:04d}",
                        gate_kind=self.kind,
                        host=self.host,
                        trigger_set=trigger_set,
                        sequence=switch,
                        architecture={
                            "window_length": window_length,
                            "window_start": window_start,
                            "utr_length": utr_length,
                            "linker_length": linker_length,
                            "extra_aa": linker_length // 3,
                            "loop_length": gap,
                            "cds_fold_nt": len(coding),
                            "kozak": self.KOZAK,
                            "track": self.host.track.value,
                        },
                    )

    def evaluate_design(self, design: GateDesign) -> dict[str, float | None]:
        """Score Kozak openness and trigger binding with the shared ``FoldEngine``.

        ``predicted_leakage`` is the mean P(unpaired) of ``GCCACCAUG`` while the
        trigger is bound: residual initiation, lower is better, same direction as
        ``AntisenseNotGate``. ``predicted_success_rate`` is that family's binding
        sigmoid, so the two chemistries stay on one axis. How much of the UTR and
        the linker is actually paired to the trigger is reported separately as
        ``flank_binding_probability`` and is not part of the scoring profile.
        """
        architecture = design.architecture
        utr_length = int(architecture["utr_length"])
        linker_length = int(architecture["linker_length"])
        loop_length = int(architecture["loop_length"])
        loop_start = utr_length
        loop_end = loop_start + loop_length
        linker_start = loop_end
        linker_end = linker_start + linker_length

        trigger = design.trigger_set.repressors[0]
        switch = design.sequence

        alone = self.folder.base_pair_probabilities(switch)
        on_accessibility = _mean_unpaired(alone, loop_start, loop_end)
        open_run = _longest_open_run(alone, loop_start, loop_end)

        complex_matrix = self.folder.base_pair_probabilities(f"{switch}&{trigger.sequence}")
        predicted_leakage = _mean_unpaired(complex_matrix, loop_start, loop_end)
        flank_binding = _mean_paired_to_partner(
            complex_matrix,
            ((0, utr_length), (linker_start, linker_end)),
            partner_start=len(switch),
        )

        gate_folding_energy = self.folder.mfe(switch).energy
        binding_dg = hybridization_energy(switch, trigger.sequence, self.folder)
        predicted_success_rate = _binding_energy_factor(binding_dg)
        dynamic_range = on_accessibility / max(predicted_leakage, 1e-3)

        return {
            "gate_folding_energy": gate_folding_energy,
            "predicted_leakage": predicted_leakage,
            "dynamic_range": dynamic_range,
            "trigger_accessibility": trigger.accessibility,
            "predicted_success_rate": predicted_success_rate,
            "gc_content": sq.gc_content(switch),
            "initiation_open_run_nt": float(open_run),
            "flank_binding_probability": flank_binding,
        }

    def emit_sequence(self, design: GateDesign) -> str:
        return design.sequence


def _force_plus4_g(linker: str) -> str:
    """Replace the first base with G. Length is unchanged, so the frame holds."""
    if not linker:
        return linker
    return "G" + linker[1:]


def _binding_energy_factor(binding_dg: float) -> float:
    """The prokaryotic family's sigmoid, so both NOT gates share one success scale."""
    reference = AntisenseNotGate._DG_REFERENCE_KCAL
    steepness = AntisenseNotGate._DG_STEEPNESS
    x = (binding_dg - reference) / steepness
    x = max(-50.0, min(50.0, x))
    return 1.0 / (1.0 + math.exp(x))


def _mean_paired_to_partner(
    matrix: list[list[float]],
    intervals: tuple[tuple[int, int], ...],
    partner_start: int,
) -> float:
    """Mean probability that bases in ``intervals`` pair with the other strand.

    ``FoldEngine.base_pair_probabilities`` indexes a dimer as switch positions
    first and trigger positions from ``partner_start``. Pairing inside the
    switch does not count: the eukaryotic OFF state is trigger binding, not
    self-structure.
    """
    width = len(matrix)
    paired: list[float] = []
    for start, end in intervals:
        for index in range(start, min(end, width)):
            paired.append(sum(matrix[index][partner_start:width]))
    if not paired:
        return 0.0
    return sum(paired) / len(paired)
