"""The engine's scientific vocabulary.

Every type the pipeline passes between stages. **Fully implemented** — these are data
and arithmetic, not science, so there is nothing here to fill in later.

Frozen throughout, because the pipeline parallelises by pickling and must be
deterministic (docs/engine-design.md §2). Nothing here imports Django, and nothing
here imports anything else from the engine: `domain` is the bottom of the import
graph (docs/engine-map.md §3b).
"""

from dataclasses import dataclass, field
from enum import StrEnum

# --- Vocabularies -----------------------------------------------------------------


class Host(StrEnum):
    """The organism a circuit is designed for."""

    ECOLI = "ecoli"
    YEAST = "yeast"
    HUMAN = "human"

    @property
    def track(self) -> "Track":
        """Design rules follow the track, not the individual organism."""
        return Track.PROKARYOTIC if self is Host.ECOLI else Track.EUKARYOTIC


class Track(StrEnum):
    """Translation machinery. Decides RBS-in-loop versus Kozak, among other rules."""

    PROKARYOTIC = "prokaryotic"
    EUKARYOTIC = "eukaryotic"


class GateKind(StrEnum):
    TOEHOLD = "toehold"
    TOEHOLD_AND = "toehold_and"
    ANTISENSE_NOT = "antisense_not"
    CRISPR = "crispr"


class Regulation(StrEnum):
    UP = "up"
    DOWN = "down"


class GeneState(StrEnum):
    """Whether a transcript must be present or absent for the circuit to fire."""

    ON = "ON"
    OFF = "OFF"


class LogicOperator(StrEnum):
    AND = "AND"
    OR = "OR"
    NOT = "NOT"
    IDENTITY = "IDENTITY"


class SegmentKind(StrEnum):
    PROMOTER = "promoter"
    SWITCH = "switch"
    PAYLOAD = "payload"
    TERMINATOR = "terminator"
    BACKBONE = "backbone"


class AssemblyStandard(StrEnum):
    RFC10 = "RFC10"
    RFC1000 = "RFC1000"


class DesiredOutcome(StrEnum):
    GFP = "gfp"
    MCHERRY = "mcherry"
    LUCIFERASE = "luciferase"
    ANTIBIOTIC = "ampr"
    APOPTOSIS = "apoptosis"
    CUSTOM = "other"


# --- Inputs -----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SampleMetadata:
    """Which columns of the count matrix are control and which are condition."""

    control_samples: tuple[str, ...]
    condition_samples: tuple[str, ...]

    def __post_init__(self) -> None:
        overlap = set(self.control_samples) & set(self.condition_samples)
        if overlap:
            raise ValueError(f"Samples cannot be both control and condition: {sorted(overlap)}")


@dataclass(frozen=True, slots=True)
class DgeRow:
    """One gene's differential-expression result, as DESeq2 and friends report it."""

    gene_id: str
    symbol: str
    base_mean: float
    log2_fold_change: float
    p_adj: float
    lfc_se: float | None = None
    stat: float | None = None
    p_value: float | None = None

    @property
    def regulation(self) -> Regulation:
        return Regulation.UP if self.log2_fold_change >= 0 else Regulation.DOWN


@dataclass(frozen=True, slots=True)
class DgeTable:
    """The parsed differential-expression input."""

    rows: tuple[DgeRow, ...]

    def __len__(self) -> int:
        return len(self.rows)

    def by_gene_id(self) -> dict[str, DgeRow]:
        return {row.gene_id: row for row in self.rows}


@dataclass(frozen=True, slots=True)
class CountMatrix:
    """Normalised or raw counts, genes by samples.

    ``counts`` is a plain nested tuple rather than a numpy array so that `domain` stays
    dependency-free; stages convert to numpy when they need arithmetic.
    """

    gene_ids: tuple[str, ...]
    samples: tuple[str, ...]
    counts: tuple[tuple[float, ...], ...]
    metadata: SampleMetadata

    @property
    def shape(self) -> tuple[int, int]:
        return len(self.gene_ids), len(self.samples)


# --- Stage records ----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SelectedGene:
    """Stage 1 output — a gene that separates the two cell states."""

    gene_id: str
    symbol: str
    regulation: Regulation
    log2_fold_change: float
    p_adj: float
    control_percentile: float
    condition_percentile: float
    condition_specificity: float
    score: float


@dataclass(frozen=True, slots=True)
class TriggerCandidate:
    """Stage 2 output — a sub-segment of a transcript, ranked as a possible input."""

    trigger_id: str
    gene_id: str
    symbol: str
    sequence: str
    start_index: int
    openness: float
    accessibility: float
    mfe: float
    off_target_penalty: float
    segment_specificity: float
    gc_content: float
    aug_indexes: tuple[int, ...] = ()
    stop_indexes: tuple[int, ...] = ()
    ribosome_occupancy: float | None = None
    score: float = 0.0

    @property
    def length(self) -> int:
        return len(self.sequence)


@dataclass(frozen=True, slots=True)
class Constraints:
    """The researcher's limits, carried into every stage that has to respect them."""

    max_triggers: int = 2
    min_separation: float = 0.5
    max_p_adj: float = 0.05
    trigger_lengths: tuple[int, ...] = (30, 36)
    max_switch_length: int = 200
    forbidden_motifs: tuple[str, ...] = ()
    standard: AssemblyStandard = AssemblyStandard.RFC10


@dataclass(frozen=True, slots=True)
class Compatibility:
    """Whether a gate family can realise a trigger set, and why not if it cannot."""

    ok: bool
    reason: str = ""

    @classmethod
    def yes(cls) -> "Compatibility":
        return cls(ok=True)

    @classmethod
    def no(cls, reason: str) -> "Compatibility":
        return cls(ok=False, reason=reason)


@dataclass(frozen=True, slots=True)
class TriggerSet:
    """The inputs to one circuit.

    ``activators`` must be present and ``repressors`` absent. Two triggers may come from
    the same gene — the pipeline map is explicit about that — so nothing here
    deduplicates by ``gene_id``.
    """

    activators: tuple[TriggerCandidate, ...]
    repressors: tuple[TriggerCandidate, ...] = ()

    @property
    def arity(self) -> int:
        return len(self.activators) + len(self.repressors)

    @property
    def logic_type(self) -> str:
        if self.repressors and not self.activators:
            return "NOT"
        if len(self.activators) == 1:
            return "AND-NOT" if self.repressors else "single-input"
        return "AND-NOT" if self.repressors else "AND"

    @property
    def trigger_ids(self) -> tuple[str, ...]:
        return tuple(t.trigger_id for t in self.activators + self.repressors)


@dataclass(frozen=True, slots=True)
class GateDesign:
    """Stage 3 output — one concrete switch built for one trigger set."""

    design_id: str
    gate_kind: GateKind
    host: Host
    trigger_set: TriggerSet
    sequence: str
    dot_bracket: str = ""
    structure_deviation: float = 0.0
    mfe_on: float = 0.0
    mfe_off: float = 0.0
    mfe_trigger: float = 0.0
    binding_site_accessibility: float = 0.0
    binding_site_off_target: float = 0.0
    translation_score: float = 0.0
    architecture: dict = field(default_factory=dict)
    score: float = 0.0

    @property
    def length(self) -> int:
        return len(self.sequence)


@dataclass(frozen=True, slots=True)
class Rejection:
    """Why a candidate was excluded. Never discarded silently (rule 8)."""

    reason: str
    filter_name: str = ""


# --- Logic ------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BooleanExpression:
    """A circuit's logic as a tree, not a string.

    A parsed form is needed anyway: to evaluate the circuit against samples, to count
    complexity, and to enumerate equivalent expressions. Rendering to text is the easy
    direction.
    """

    operator: LogicOperator
    operands: tuple["BooleanExpression | str", ...]

    @classmethod
    def gene(cls, gene_id: str) -> "BooleanExpression":
        return cls(LogicOperator.IDENTITY, (gene_id,))

    def evaluate(self, active: frozenset[str]) -> bool:
        """True when this expression fires, given the set of present transcripts."""
        values = [
            operand.evaluate(active)
            if isinstance(operand, BooleanExpression)
            else operand in active
            for operand in self.operands
        ]
        match self.operator:
            case LogicOperator.IDENTITY:
                return values[0]
            case LogicOperator.NOT:
                return not values[0]
            case LogicOperator.AND:
                return all(values)
            case LogicOperator.OR:
                return any(values)
        raise ValueError(f"Unknown operator {self.operator}")

    def gene_ids(self) -> tuple[str, ...]:
        found: list[str] = []
        for operand in self.operands:
            if isinstance(operand, BooleanExpression):
                found.extend(operand.gene_ids())
            else:
                found.append(operand)
        return tuple(dict.fromkeys(found))

    def complexity(self) -> int:
        """Component count — the axis a circuit's score is traded off against."""
        total = 0 if self.operator is LogicOperator.IDENTITY else 1
        for operand in self.operands:
            total += operand.complexity() if isinstance(operand, BooleanExpression) else 1
        return total

    def render(self) -> str:
        """``A AND (B OR C) AND NOT D``."""
        parts = [
            operand.render() if isinstance(operand, BooleanExpression) else operand
            for operand in self.operands
        ]
        match self.operator:
            case LogicOperator.IDENTITY:
                return parts[0]
            case LogicOperator.NOT:
                return f"NOT {parts[0]}"
            case _:
                joined = f" {self.operator.value} ".join(parts)
                return joined if len(parts) == 1 else f"({joined})"


@dataclass(frozen=True, slots=True)
class LogicGene:
    """One gene as the circuit diagram draws it."""

    name: str
    role: str
    state: GeneState
    direction: Regulation


@dataclass(frozen=True, slots=True)
class LogicGraph:
    """The Boolean structure, in the shape the results view renders."""

    genes: tuple[LogicGene, ...]
    mid_gate: LogicOperator
    outer_gate: LogicOperator
    invert: bool
    output: str
    caption: str


# --- Construct --------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Segment:
    """One stretch of the assembled construct."""

    kind: SegmentKind
    name: str
    sequence: str

    @property
    def length_bp(self) -> int:
        return len(self.sequence)


@dataclass(frozen=True, slots=True)
class Plasmid:
    """The assembled construct. Data plus arithmetic — no behaviour."""

    segments: tuple[Segment, ...]

    @property
    def length_bp(self) -> int:
        return sum(segment.length_bp for segment in self.segments)

    @property
    def sequence(self) -> str:
        return "".join(segment.sequence for segment in self.segments)

    @property
    def gc_content(self) -> float:
        sequence = self.sequence.upper()
        if not sequence:
            return 0.0
        return 100.0 * sum(base in "GC" for base in sequence) / len(sequence)


@dataclass(frozen=True, slots=True)
class ConfusionMatrix:
    """Circuit ON/OFF against condition/control samples.

    The pipeline map draws this as a table; it is a type here because circuit scoring
    is arithmetic over it.
    """

    true_positive: int
    false_positive: int
    false_negative: int
    true_negative: int

    @property
    def sensitivity(self) -> float:
        denominator = self.true_positive + self.false_negative
        return self.true_positive / denominator if denominator else 0.0

    @property
    def specificity(self) -> float:
        denominator = self.true_negative + self.false_positive
        return self.true_negative / denominator if denominator else 0.0

    @property
    def separation_margin(self) -> float:
        """Youden's J — how cleanly the circuit tells the two states apart. 0 is chance."""
        return self.sensitivity + self.specificity - 1.0


@dataclass(frozen=True, slots=True)
class CircuitCandidate:
    """Stage 4 output — a complete, scored circuit."""

    circuit_id: str
    expression: BooleanExpression
    logic_graph: LogicGraph
    designs: tuple[GateDesign, ...]
    confusion: ConfusionMatrix
    output: str
    score: float = 0.0
    rejection: Rejection | None = None

    @property
    def complexity(self) -> int:
        return self.expression.complexity()

    @property
    def is_rejected(self) -> bool:
        return self.rejection is not None


@dataclass(frozen=True, slots=True)
class PlasmidDesign:
    """Stage 5 output — an orderable construct."""

    plasmid_id: str
    circuit_id: str
    plasmid: Plasmid
    standard: AssemblyStandard
    violations: tuple[str, ...] = ()

    @property
    def is_compliant(self) -> bool:
        return not self.violations


# --- Supporting -------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ToolRequirement:
    """An external tool a gate family needs, and the version it was validated against."""

    name: str
    version: str
    optional: bool = False


@dataclass(frozen=True, slots=True)
class Hit:
    """One near-match found in the transcriptome."""

    gene_id: str
    start: int
    mismatches: int
    identity: float


@dataclass(frozen=True, slots=True)
class OffTargetReport:
    """What an off-target scan found, and what it costs the candidate."""

    hits: tuple[Hit, ...]
    penalty: float

    @property
    def worst_identity(self) -> float:
        return max((hit.identity for hit in self.hits), default=0.0)


@dataclass(frozen=True, slots=True)
class FoldResult:
    """Structure and free energy from one fold. Cached by the tool that produced it."""

    structure: str
    energy: float


@dataclass(frozen=True, slots=True)
class StructureMatch:
    """How closely a predicted fold matches the intended one."""

    deviation: float
    p_target_fold: float


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Whether a design passes the hard rules, and every reason it does not."""

    ok: bool
    violations: tuple[str, ...] = ()

    @classmethod
    def passed(cls) -> "ValidationResult":
        return cls(ok=True)

    @classmethod
    def failed(cls, *violations: str) -> "ValidationResult":
        return cls(ok=False, violations=violations)


@dataclass(frozen=True, slots=True)
class QcReport:
    """What the quality check found before anything expensive runs."""

    ok: bool
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    stats: dict = field(default_factory=dict)
