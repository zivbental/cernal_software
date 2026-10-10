"""Research implementation of the endogenous iSBH-sgRNA construction.

Exhaustive binary blocker search over explicit architecture templates.
Platform availability stays False until its input contract can
carry target DNA, reference scaffold, genomic scores and calibrated parameters.
"""

from collections.abc import Iterator
from dataclasses import asdict
from itertools import product
from typing import ClassVar

from engine import sequences as sq
from engine.domain import (
    CRISPR_LOOP_LENGTHS,
    CRISPR_TRIGGER_TAIL_LENGTHS,
    Compatibility,
    Constraints,
    CrisprObservables,
    CrisprTemplate,
    GateDesign,
    GateKind,
    Host,
    ToolRequirement,
    TriggerSet,
)
from engine.gates.base import GateFamily
from engine.gates.tools.folding import FoldEngine


def scan_spacers(dna: str, window: tuple[int, int]) -> list[dict]:
    """SpCas9 NGG on both strands. Window bounds the whole protospacer, not PAM.

    Coordinates always refer to the input plus strand, zero based and half open.
    The minus-strand spacer is reverse-complemented into its own 5'-3' direction.
    The activation window is user supplied; no TSS or species-specific guess.
    """
    dna = sq.to_dna(dna)
    if not dna or set(dna) - set("ACGT"):
        raise ValueError("Target must be unambiguous DNA")
    start, end = window
    if not 0 <= start < end <= len(dna):
        raise ValueError("Invalid activation window")
    result = []
    for strand, oriented in (("+", dna), ("-", sq.reverse_complement(dna, dna=True))):
        for i in range(len(oriented) - 22):
            if oriented[i + 21 : i + 23] != "GG":
                continue
            a, b = (i, i + 20) if strand == "+" else (len(dna) - i - 20, len(dna) - i)
            if start <= a and b <= end:
                result.append(
                    {
                        "id": f"{a}:{b}:{strand}",
                        "start": a,
                        "end": b,
                        "strand": strand,
                        "sequence": sq.to_rna(oriented[i : i + 20]),
                        "pam": oriented[i + 20 : i + 23],
                    }
                )
    return sorted(result, key=lambda s: (s["start"], s["strand"]))


class CrisprGate(GateFamily):
    name = "crispr"
    version = "0.12.2-research"
    ensemble_model = "off-g-on-connected-gT-v1"
    kind = GateKind.CRISPR
    label = "CRISPR-Cas sgRNA Gate"
    description = "Endogenous iSBH research model; explicit target and scaffold required"
    supported_hosts: ClassVar[frozenset[Host]] = frozenset({Host.YEAST, Host.HUMAN})
    max_inputs = 1
    available = False

    def __init__(
        self,
        host: Host,
        folder: FoldEngine,
        *,
        spacer: str = "",
        scaffold: str = "",
        scaffold_reference: str = "",
        templates: tuple[CrisprTemplate, ...] = (),
    ) -> None:
        self.host, self.folder = host, folder
        self.spacer, self.scaffold = sq.to_rna(spacer), sq.to_rna(scaffold)
        self.scaffold_reference, self.templates = scaffold_reference, templates
        if self.spacer and (len(self.spacer) != 20 or not sq.is_valid_rna(self.spacer)):
            raise ValueError("spacer must contain exactly 20 RNA bases")
        if self.scaffold and not sq.is_valid_rna(self.scaffold):
            raise ValueError("Invalid scaffold sequence")
        if self.scaffold_reference:
            if len(self.scaffold_reference) != len(self.scaffold):
                raise ValueError("Scaffold and reference structure lengths differ")
            balance = 0
            for char in self.scaffold_reference:
                if char not in ".()":
                    raise ValueError("Reference must use dot-bracket .()")
                balance += (char == "(") - (char == ")")
                if balance < 0:
                    raise ValueError("Unbalanced scaffold reference")
            if balance:
                raise ValueError("Unbalanced scaffold reference")
        if templates and {t.loop_length for t in templates} != set(CRISPR_LOOP_LENGTHS):
            raise ValueError("Supply all ten loop lengths: 14 through 32 in steps of 2")
        if len(set(templates)) != len(templates):
            raise ValueError("Duplicate CRISPR architecture template")
        for loop_length in sorted({t.loop_length for t in templates}):
            lengths = {t.trigger_tail_length for t in templates if t.loop_length == loop_length}
            if lengths != set(CRISPR_TRIGGER_TAIL_LENGTHS):
                raise ValueError("Each loop must include all three BT lengths: 10, 15, 20")

    def required_tools(self) -> list[ToolRequirement]:
        return [ToolRequirement(name="ViennaRNA", version="2.7")]

    def is_compatible(self, trigger_set: TriggerSet, constraints: Constraints) -> Compatibility:
        if self.host not in self.supported_hosts:
            return Compatibility.no(f"CRISPR gates are not supported for {self.host.value}")
        if not (self.spacer and self.scaffold and self.scaffold_reference and self.templates):
            return Compatibility.no("Supply spacer, scaffold reference and architecture templates")
        if len(trigger_set.activators) != 1 or trigger_set.repressors:
            return Compatibility.no("One activating trigger is required")
        trigger = trigger_set.activators[0].sequence
        if not sq.is_valid_rna(trigger):
            return Compatibility.no("Trigger must be unambiguous uppercase RNA")
        if not any(t.trigger_length == len(trigger) for t in self.templates):
            return Compatibility.no("No template matches this trigger window length")
        lengths = [
            len(self.scaffold) + 40 + 2 * t.extension_length + t.loop_length + t.trigger_tail_length
            for t in self.templates
            if t.trigger_length == len(trigger)
        ]
        if min(lengths) > constraints.max_switch_length:
            return Compatibility.no("All guide templates exceed max_switch_length")
        return Compatibility.yes()

    def generate_designs(
        self, trigger_set: TriggerSet, constraints: Constraints
    ) -> Iterator[GateDesign]:
        compatibility = self.is_compatible(trigger_set, constraints)
        if not compatibility.ok:
            raise ValueError(compatibility.reason)
        trigger = trigger_set.activators[0]
        complementary = sq.reverse_complement(trigger.sequence)
        blocker_lock = sq.reverse_complement(self.spacer)
        for template in self.templates:
            if template.trigger_length != trigger.length:
                continue
            tail_end = template.trigger_tail_length
            tail = complementary[:tail_end]
            # Confirmed design constraint: B is always 20 nt; its sequence may vary.
            blocker_trigger = complementary[tail_end : tail_end + 20]
            extension_end = tail_end + 20 + template.extension_length
            anti_extension = complementary[tail_end + 20 : extension_end]
            # In antiparallel binding, the 5-prime part of T binds the guide loop.
            loop = complementary[extension_end:]
            if len(loop) != template.loop_length:
                raise ValueError("Trigger window does not match architecture lengths")
            # Confirmed: E and E-prime are exact reverse complements of equal length.
            extension = sq.reverse_complement(anti_extension)
            # One choice where the two complements agree, otherwise two.
            # product is lazy; no sequence set or 2**m-sized list is retained.
            # Trigger complement first keeps enumeration stable and auditable.
            choices = tuple(
                (trigger_base,) if trigger_base == lock_base else (trigger_base, lock_base)
                for trigger_base, lock_base in zip(blocker_trigger, blocker_lock, strict=True)
            )
            variable_positions = tuple(i for i, bases in enumerate(choices) if len(bases) == 2)
            candidate_count = 1 << len(variable_positions)
            for candidate_index, bases in enumerate(product(*choices)):
                blocker = "".join(bases)
                # User-confirmed page-3 order; every domain is written 5' to 3'.
                components = (
                    ("trigger_tail", tail),
                    ("blocker", blocker),
                    ("anti_extension", anti_extension),
                    ("loop", loop),
                    ("extension", extension),
                    ("spacer", self.spacer),
                    ("scaffold", self.scaffold),
                )
                guide = "".join(sequence for _, sequence in components)
                regions, offset = {}, 0
                for name, sequence in components:
                    regions[name] = (offset, offset + len(sequence))
                    offset += len(sequence)
                # Different architecture templates retain separate identities.
                if len(guide) > constraints.max_switch_length:
                    continue
                intended_trigger_regions = {
                    name: (trigger.length - end, trigger.length - start)
                    for name, (start, end) in regions.items()
                    if name in ("trigger_tail", "blocker", "anti_extension", "loop")
                }
                yield GateDesign(
                    design_id=f"{trigger.trigger_id}-L{template.loop_length}-BT{tail_end}-b{candidate_index}",
                    gate_kind=self.kind,
                    host=self.host,
                    trigger_set=trigger_set,
                    sequence=guide,
                    architecture={
                        "scaffold": self.scaffold,
                        "spacer": self.spacer,
                        "extension": extension,
                        "loop": loop,
                        "anti_extension": anti_extension,
                        "blocker": blocker,
                        "trigger_tail": tail,
                        "blocker_candidate_index": candidate_index,
                        "blocker_candidate_count": candidate_count,
                        "blocker_variable_positions": variable_positions,
                        "blocker_search": "exhaustive-binary-complements-v1",
                        "regions": regions,
                        "intended_trigger_regions": intended_trigger_regions,
                        "order_5_to_3": [name for name, _ in components],
                        "gate_version": self.version,
                        "model": self.ensemble_model,
                    },
                )

    def observables(self, design: GateDesign) -> CrisprObservables:
        """Collect every measurement without applying feasibility thresholds."""
        measured = {}
        for batch in self.measurement_stages(design):
            measured.update(batch)
        return CrisprObservables(**measured)

    def measurement_stages(self, design: GateDesign) -> Iterator[dict[str, float]]:
        """Yield OFF accessibility, OFF defect, ON accessibility, then ON defect.

        OFF is the free-guide ensemble. ON is conditioned on a connected gT
        complex, without prescribing its pairing pattern or spacer exposure.
        Both accessibility values are joint constrained/total partition ratios;
        ON does not estimate the fraction of guides bound in solution.

        Advancing the iterator performs only the next group of measurements.
        The caller can stop before requesting subsequent folding calculations.
        """
        if not design.sequence.endswith(self.spacer + self.scaffold):
            raise ValueError("Design does not belong to this configured guide")
        scaffold_start = len(design.sequence) - len(self.scaffold)
        spacer_start = scaffold_start - len(self.spacer)
        trigger = design.trigger_set.activators[0].sequence
        a_off = self.folder.region_accessibility(design.sequence, spacer_start, scaffold_start)
        yield {"a_off": a_off}
        d_off = self.folder.region_defect(
            design.sequence, self.scaffold_reference, start=scaffold_start
        )
        yield {"d_off": d_off}
        dg = self.folder.binding_free_energy(design.sequence, trigger)
        yield {"dg_bind": dg}
        complex_rna = design.sequence + "&" + trigger
        a_on = self.folder.region_accessibility(complex_rna, spacer_start, scaffold_start)
        yield {"a_on": a_on}
        d_on = self.folder.region_defect(complex_rna, self.scaffold_reference, start=scaffold_start)
        yield {"d_on": d_on}

    def evaluate_design(self, design: GateDesign) -> dict[str, float | None]:
        """Only shared raw metrics. J and Phi are handled by engine.scoring.crispr."""
        measured = asdict(self.observables(design))
        return {
            "predicted_leakage": measured["a_off"],
            "dynamic_range": (
                measured["a_on"] / measured["a_off"] if measured["a_off"] > 0 else None
            ),
            "gate_folding_energy": self.folder.mfe(design.sequence).energy,
            "trigger_accessibility": design.trigger_set.activators[0].accessibility,
            "gc_content": sq.gc_content(design.sequence),
        }

    def emit_sequence(self, design: GateDesign) -> str:
        return design.sequence
