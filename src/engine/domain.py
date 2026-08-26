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
    """The switch chemistries. One value per registered ``GateFamily``."""

    TOEHOLD = "toehold"
    TOEHOLD_AND = "toehold_and"
    ANTISENSE_NOT = "antisense_not"
    CRISPR = "crispr"


class Regulation(StrEnum):
    """Which direction a gene moved between the two states.

    Distinct from ``GeneState``: this describes the *data*, that describes what the
    *circuit requires*. An UP gene is a natural activator input, a DOWN gene reaches a
    circuit through a NOT gate.
    """

    UP = "up"
    DOWN = "down"


class GeneState(StrEnum):
    """Whether a transcript must be present or absent for the circuit to fire."""

    ON = "ON"
    OFF = "OFF"


class LogicOperator(StrEnum):
    """Boolean operators a circuit can be built from.

    ``IDENTITY`` is a leaf — a single gene with no gate — so that every expression is a
    tree and callers never special-case the one-input form.
    """

    AND = "AND"
    OR = "OR"
    NOT = "NOT"
    IDENTITY = "IDENTITY"


class SegmentKind(StrEnum):
    """Parts of an assembled construct.

    A stable vocabulary: the frontend colours the plasmid map by these, so adding a value
    means the map needs a colour for it. Deliberately has no ``marker`` — a selective
    marker *is* the payload, not an add-on beside it.
    """

    PROMOTER = "promoter"
    SWITCH = "switch"
    PAYLOAD = "payload"
    TERMINATOR = "terminator"
    BACKBONE = "backbone"


class AssemblyStandard(StrEnum):
    """iGEM assembly standards, which decide the prohibited restriction sites.

    RFC10 forbids EcoRI, XbaI, SpeI, PstI and NotI inside a part; RFC1000 (Type IIS)
    forbids BsaI and SapI.
    """

    RFC10 = "RFC10"
    RFC1000 = "RFC1000"


class DesiredOutcome(StrEnum):
    """What a circuit expresses when it fires.

    All equivalent: a reporter and a selective marker are the same kind of construct with
    a different payload. Each selected outcome gets its own set of plasmid candidates.
    """

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
        """Which way this gene moved. Sign of the fold change, nothing more."""
        return Regulation.UP if self.log2_fold_change >= 0 else Regulation.DOWN


@dataclass(frozen=True, slots=True)
class DgeTable:
    """The parsed differential-expression input."""

    rows: tuple[DgeRow, ...]

    def __len__(self) -> int:
        return len(self.rows)

    def by_gene_id(self) -> dict[str, DgeRow]:
        """Index the rows for lookup. Build once; the table is scanned repeatedly."""
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
        """``(genes, samples)``, matching numpy's convention."""
        return len(self.gene_ids), len(self.samples)


# --- Stage records ----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SelectedGene:
    """Stage 1 output — a gene that separates the two cell states.

    Attributes:
        gene_id: The database identifier, e.g. ``b0002``. Joins to the DGE table and to
            the sequence library.
        symbol: The human-readable name, e.g. ``thrA``. For display only — never join on
            it, since symbols are not unique across annotation builds.
        regulation: Which way it moved. **Not the same as the gate's ``GeneState``**: an
            UP gene is a natural activator input, a DOWN gene reaches the circuit through
            a NOT gate. Stage 4 makes that mapping.
        log2_fold_change: Effect size, from the researcher's DGE results.
        p_adj: Adjusted p-value. Genes DESeq2 filtered out carry no value at all, and
            "not tested" must not be treated as "not significant".
        control_percentile: Where this gene sits in the control group's own expression
            distribution, 0 to 100.
        condition_percentile: The same for the condition group. Two genes with identical
            fold changes can differ sharply here, and the pair is a better separation
            signal than the fold change alone.
        condition_specificity: How much of this gene's expression is confined to the
            target state rather than being everywhere. Needs a reference atlas; a gene
            expressed strongly in the target *and* throughout the body is a poor trigger
            for anything therapeutic.
        score: Stage 1's combined ranking. The weighting decides what the whole run
            explores, so it should be a recorded scientific choice.
    """

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
    """Stage 2 output — a sub-segment of a transcript, ranked as a possible input.

    A trigger is **not a gene**. It is a specific window at a specific offset in a
    specific transcript, and most windows are unusable: buried in structure, shared with
    other transcripts, or GC-extreme.

    Attributes:
        trigger_id: Minted by ``CandidateStore``, e.g. ``trig-000123``.
        gene_id: The transcript this window came from.
        symbol: Display name of that gene.
        sequence: The window itself, RNA, uppercase.
        start_index: 0-indexed offset within the transcript. With ``length`` this locates
            the window exactly, which is what makes a result reproducible.
        openness: Mean unpaired probability across the window, 0 to 1. The map's
            ``Trigger Openness``. Higher is more reachable.
        accessibility: The same idea, but summarised so that a window open at its ends
            and paired in the middle does not score as well as one open throughout.
        mfe: The window's own folding energy, kcal/mol. A trigger that folds tightly on
            itself competes with binding the switch.
        off_target_penalty: From ``OffTargetScanner.scan_trigger`` — direction (b),
            sponging by other transcripts. 0 is clean.
        segment_specificity: How well this window distinguishes its gene from its
            paralogues.
        gc_content: Percent G+C. Extremes hurt synthesis and duplex behaviour alike.
        aug_indexes: Start codons inside the window. Recorded because a trigger carrying
            one can interfere once incorporated into a switch's stem.
        stop_indexes: In-frame stop codons, for the same reason.
        ribosome_occupancy: Optional, from ribosome profiling if the lab has it. A window
            a ribosome is constantly traversing is not reliably accessible.
        score: Stage 2's ranking. Pruning on this is what sets the whole pipeline's
            compute budget.
    """

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
        """Window length in nucleotides. With ``start_index``, locates it exactly."""
        return len(self.sequence)


@dataclass(frozen=True, slots=True)
class Constraints:
    """The researcher's limits, carried into every stage that has to respect them.

    Built from ``params["constraints"]`` at the start of a run and never modified after,
    so what a run was asked to do is recoverable from its snapshot.

    Attributes:
        max_triggers: Circuit arity ceiling. 2 is the practical limit — pairs grow as the
            square of the trigger count, and triples make the search space intractable
            without a cluster (docs/step-5-engine-plan.md §3).
        min_separation: Minimum absolute log2 fold change for a gene to be usable. A gene
            that barely moves cannot drive a switch however well it folds.
        max_p_adj: Significance threshold, conventionally 0.05.
        trigger_lengths: Window sizes to scan, in nucleotides. A tuple because different
            chemistries need different footprints, and each length scanned multiplies the
            candidate count.
        max_switch_length: Ceiling on a switch construct. Bounded by what synthesis
            vendors accept and by folding cost, which grows steeply with length.
        forbidden_motifs: Extra sequences to reject, beyond the assembly standard's.
            The scientific team's to populate.
        standard: Which assembly standard to enforce. Decides which restriction sites are
            prohibited.
    """

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
        """This family can realise the trigger set."""
        return cls(ok=True)

    @classmethod
    def no(cls, reason: str) -> "Compatibility":
        """It cannot. ``reason`` is shown to the researcher, so write it for them."""
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
        """Total inputs. Checked against a family's ``max_inputs``."""
        return len(self.activators) + len(self.repressors)

    @property
    def logic_type(self) -> str:
        """Human-readable shape of this input set, for display and for the summary line."""
        if self.repressors and not self.activators:
            return "NOT"
        if len(self.activators) == 1:
            return "AND-NOT" if self.repressors else "single-input"
        return "AND-NOT" if self.repressors else "AND"

    @property
    def trigger_ids(self) -> tuple[str, ...]:
        """Every trigger id, activators first. Recorded on the design for traceability."""
        return tuple(t.trigger_id for t in self.activators + self.repressors)


@dataclass(frozen=True, slots=True)
class GateDesign:
    """Stage 3 output — one concrete switch built for one trigger set.

    Attributes:
        design_id: Minted by ``CandidateStore``.
        gate_kind: Which chemistry built it.
        host: The organism it was designed for. Decides RBS versus Kozak, among other
            rules, so a design is not portable between hosts.
        trigger_set: The inputs it responds to. Carried rather than referenced by id, so
            a design is self-contained when it reaches scoring.
        sequence: The switch, RNA, uppercase.
        dot_bracket: Predicted structure, same length as ``sequence``.
        structure_deviation: How far the prediction sits from what the generator
            intended, **normalised by length** so designs of different sizes compare.
        mfe_on: Folding energy with the trigger present, kcal/mol. The open state.
        mfe_off: Folding energy alone. The closed state, and it should be strongly
            negative — an unstable OFF hairpin is a leaky switch.
        mfe_trigger: The trigger's own folding energy, needed to compute binding.
        binding_site_accessibility: How reachable the toehold is in the OFF state. A
            switch whose toehold is itself buried can never be opened.
        binding_site_off_target: From ``scan_switch`` — direction (a), cross-activation
            by non-cognate RNA. Feeds the leakage estimate.
        translation_score: Codon adaptation of the fused payload, from ``CodonOptimizer``.
        architecture: Family-specific parameters — stem and loop lengths, toehold length.
            A dict because it is opaque to everything outside the family that produced it,
            and because fixing its shape would fix the set of chemistries.
        score: The final switch score, from ``engine.scoring``.
    """

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
        """Switch length in nucleotides, against ``Constraints.max_switch_length``."""
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
        """A leaf: this gene, unmodified. The base case every expression builds from."""
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
        """Every gene this expression references, in order, without duplicates.

        Used to check the circuit is buildable — an expression naming a gene with no
        designed switch is not a circuit.
        """
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
        """Segment length. Drives the proportional arcs on the plasmid map."""
        return len(self.sequence)


@dataclass(frozen=True, slots=True)
class Plasmid:
    """The assembled construct. Data plus arithmetic — no behaviour."""

    segments: tuple[Segment, ...]

    @property
    def length_bp(self) -> int:
        """Total construct length. Synthesis vendors price and cap on this."""
        return sum(segment.length_bp for segment in self.segments)

    @property
    def sequence(self) -> str:
        """The whole construct, segments concatenated in order.

        This is what gets screened for restriction sites — screening segments
        individually misses sites formed across a junction.
        """
        return "".join(segment.sequence for segment in self.segments)

    @property
    def gc_content(self) -> float:
        """Percent G+C over the whole construct. Extremes hurt synthesis."""
        sequence = self.sequence.upper()
        if not sequence:
            return 0.0
        return 100.0 * sum(base in "GC" for base in sequence) / len(sequence)


@dataclass(frozen=True, slots=True)
class ConfusionMatrix:
    """Circuit ON/OFF against condition/control samples.

    The most honest number the pipeline produces. Everything upstream is prediction —
    predicted folding, predicted binding, predicted off-target load. This is measurement,
    against samples the researcher actually collected.

    Attributes:
        true_positive: Condition samples where the circuit fires. Correct.
        false_positive: Control samples where it fires. **The dangerous one** — a
            kill-switch firing in healthy cells is a safety failure, not an inconvenience.
        false_negative: Condition samples where it stays dark. A missed detection.
        true_negative: Control samples where it stays dark. Correct.

    Note:
        Accuracy is the wrong headline here and ``separation_margin`` is the right one:
        a circuit that fires on everything catches every true positive and separates
        nothing, and only the margin says so.
    """

    true_positive: int
    false_positive: int
    false_negative: int
    true_negative: int

    @property
    def sensitivity(self) -> float:
        """Fraction of condition samples the circuit correctly fires on. Recall."""
        denominator = self.true_positive + self.false_negative
        return self.true_positive / denominator if denominator else 0.0

    @property
    def specificity(self) -> float:
        """Fraction of control samples the circuit correctly stays dark on."""
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
        """Component count — the axis score is traded against in the Pareto filter."""
        return self.expression.complexity()

    @property
    def is_rejected(self) -> bool:
        """True when this circuit was excluded. Its ``rejection`` says why (rule 8)."""
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
        """True when the construct breaks no assembly-standard rule and can be ordered."""
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
        """Closest off-target match found. 1.0 means an exact duplicate exists."""
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
        """The design obeys every hard rule."""
        return cls(ok=True)

    @classmethod
    def failed(cls, *violations: str) -> "ValidationResult":
        """It does not. Pass **every** violation, not just the first — a generator being
        tuned is far easier to fix when it reports all its problems at once."""
        return cls(ok=False, violations=violations)


@dataclass(frozen=True, slots=True)
class QcReport:
    """What the quality check found before anything expensive runs."""

    ok: bool
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    stats: dict = field(default_factory=dict)
