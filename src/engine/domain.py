"""The engine's scientific vocabulary.

Every type the pipeline passes between stages. **Fully implemented** — these are data
and arithmetic, not science, so there is nothing here to fill in later.

Frozen throughout, because the pipeline parallelises by pickling and must be
deterministic (docs/engine.md §2.2). Nothing here imports Django, and nothing
here imports anything else from the engine: `domain` is the bottom of the import
graph (docs/engine.md §4).
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType

# --- Vocabularies -----------------------------------------------------------------


class Track(StrEnum):
    """Translation machinery. Decides RBS-in-loop versus Kozak, among other rules."""

    PROKARYOTIC = "prokaryotic"
    EUKARYOTIC = "eukaryotic"


class Host(StrEnum):
    """The organism a circuit is designed for."""

    ECOLI = "ecoli"
    YEAST = "yeast"
    HUMAN = "human"
    #: *Cutibacterium acnes* ATCC 6919, the strain the iGEM AIS-China 2026 team built a
    #: genome-derived codon model for (docs/collaborations.md). Gram-positive, anaerobic,
    #: ~60% GC — and prokaryotic, which is the whole reason ``HOST_TRACKS`` below is
    #: explicit rather than defaulting to EUKARYOTIC.
    C_ACNES = "c_acnes"

    @property
    def track(self) -> Track:
        """Design rules follow the track, not the individual organism.

        Looked up in ``HOST_TRACKS``, where every member must name its track
        explicitly. This used to be ``PROKARYOTIC if self is ECOLI else EUKARYOTIC``,
        which made EUKARYOTIC the silent default: a bacterium added as a new ``Host``
        would have been given a Kozak context and the eukaryotic ``TranslationScorer``
        branch instead of a Shine-Dalgarno RBS, and nothing would have raised. There is
        deliberately no default here. A member without an entry fails at import time
        (see ``require_track_for_every_host``), never at design time.
        """
        return HOST_TRACKS[self]


#: The translation track of every ``Host``. The single place a host declares it. Adding a
#: ``Host`` member without an entry here raises when this module is imported.
HOST_TRACKS: Mapping[Host, Track] = MappingProxyType(
    {
        Host.ECOLI: Track.PROKARYOTIC,
        Host.YEAST: Track.EUKARYOTIC,
        Host.HUMAN: Track.EUKARYOTIC,
        # A Shine-Dalgarno RBS in the toehold loop, not a Kozak context. Getting this
        # wrong for an actinobacterium is the exact failure the explicit mapping exists
        # to prevent, and it would not have raised.
        Host.C_ACNES: Track.PROKARYOTIC,
    }
)


def require_track_for_every_host(hosts: Iterable[Host], tracks: Mapping[Host, Track]) -> None:
    """Raise unless ``tracks`` names a ``Track`` for every one of ``hosts``, and nothing else.

    Explicit ``raise``, not ``assert``: an assert disappears under ``python -O``, and this is
    the guard against a silently wrong translation track.
    """
    hosts = tuple(hosts)
    missing = [host.name for host in hosts if host not in tracks]
    if missing:
        raise TypeError(
            f"Host member(s) {missing} have no entry in HOST_TRACKS. Declare PROKARYOTIC or "
            "EUKARYOTIC explicitly; there is deliberately no default track."
        )
    unknown = [str(host) for host in tracks if host not in hosts]
    if unknown:
        raise TypeError(f"HOST_TRACKS names {unknown}, which are not Host members.")
    bad = [host.name for host in hosts if not isinstance(tracks[host], Track)]
    if bad:
        raise TypeError(f"HOST_TRACKS entries for {bad} are not Track members.")


require_track_for_every_host(Host, HOST_TRACKS)


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
    NONE = "none"  # No restriction-based assembly protocol selected.


class DesiredOutcome(StrEnum):
    """What a circuit expresses when it fires.

    All equivalent: a reporter and a selective marker are the same kind of construct with
    a different payload. Each selected outcome gets its own set of plasmid candidates.
    """

    GFP = "gfp"
    MCHERRY = "mcherry"
    LUCIFERASE = "luciferase"
    ANTIBIOTIC = "ampr"
    KANAMYCIN = "kanr"
    APOPTOSIS = "apoptosis"
    CUSTOM = "other"

    @property
    def display_name(self) -> str:
        """The name a researcher sees, e.g. in ``logic_graph.output`` — distinct from
        the enum's own lowercase wire value."""
        return {
            DesiredOutcome.GFP: "GFP",
            DesiredOutcome.MCHERRY: "mCherry",
            DesiredOutcome.LUCIFERASE: "Luciferase",
            DesiredOutcome.ANTIBIOTIC: "AmpR",
            DesiredOutcome.KANAMYCIN: "KanR",
            DesiredOutcome.APOPTOSIS: "Apoptosis inducer",
            DesiredOutcome.CUSTOM: "Custom",
        }[self]


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
    """One gene's differential-expression result, as DESeq2 and friends report it.

    Only ``gene_id`` and ``log2_fold_change`` are guaranteed present — everything else
    is ``None`` when the source table does not carry it, never a fabricated number
    (docs/genes.md §2). The public dataset catalog carries no adjusted p-value at all in
    any of its 15 curated comparisons and no p-value in five of them; a bundled example
    upload carries neither ``symbol`` nor per-group means. ``p_adj``/``p_value`` of
    ``None`` mean "not tested", not "not significant" — a DESeq2 run drops rows it
    filtered internally, and those rows must never be treated as passing a significance
    threshold.

    Attributes:
        base_mean: DESeq2's ``baseMean`` — average expression across *all* samples,
            not split by group. Cannot distinguish the ON state from the OFF state on
            its own; see ``control_mean``/``target_mean``.
        control_mean: Mean expression in the control group, when the source table
            provides per-group means (the platform's ``base_expression`` column,
            uncommon in a raw DESeq2 export — most researchers export ``baseMean``
            only).
        target_mean: Mean expression in the condition group (the platform's
            ``target_expression`` column).
    """

    gene_id: str
    log2_fold_change: float
    symbol: str = ""
    p_adj: float | None = None
    p_value: float | None = None
    base_mean: float | None = None
    control_mean: float | None = None
    target_mean: float | None = None
    lfc_se: float | None = None
    stat: float | None = None

    @property
    def regulation(self) -> Regulation:
        """Which way this gene moved. Sign of the fold change, nothing more."""
        return Regulation.UP if self.log2_fold_change >= 0 else Regulation.DOWN


@dataclass(frozen=True, slots=True)
class DgeTable:
    """The parsed differential-expression input."""

    rows: tuple[DgeRow, ...]
    # True is a caller declaration that all tested hypotheses are retained, not an
    # inference from high p-value coverage. None is unknown; False is a subset.
    hypothesis_universe_complete: bool | None = None
    source_row_count: int | None = None
    columns: tuple[str, ...] = ()
    detected_columns: tuple[tuple[str, str], ...] = ()

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

    Every field below ``log2_fold_change`` is ``None`` rather than a placeholder number
    when it was not measured (docs/genes.md §3, §4.5) — a run given only a bare DE table
    (no count matrix, no transcript sequences, no reference atlas) still produces a
    ranked shortlist, but most of these fields, and ``score``'s underlying axes, will be
    ``None`` on every row. That degradation is reported, not hidden.

    Attributes:
        gene_id: The database identifier, e.g. ``b0002``. Joins to the DGE table and to
            the sequence library.
        symbol: The human-readable name, e.g. ``thrA``. For display only — never join on
            it, since symbols are not unique across annotation builds.
        regulation: Which way it moved. **Not the same as the gate's ``GeneState``**: an
            UP gene is a natural activator input, a DOWN gene reaches the circuit through
            a NOT gate. Stage 4 makes that mapping.
        log2_fold_change: Effect size, from the researcher's DGE results.
        score: Stage 1's combined ranking. The weighting decides what the whole run
            explores, so it should be a recorded scientific choice
            (``GeneSelector``'s own ``WEIGHT_*`` constants, docs/genes.md §4.5).
        p_adj: Adjusted p-value, when the table carries one. Genes DESeq2 filtered out
            carry no value at all, and "not tested" must not be treated as "not
            significant" — ``None`` here may mean either "not tested" or "the table has
            no adjusted p-value column at all"; see ``GeneSelector``'s significance tier
            for which.
        control_percentile: Where this gene sits in the control group's own expression
            distribution, 0 to 100. Needs a count matrix.
        condition_percentile: The same for the condition group. Two genes with identical
            fold changes can differ sharply here, and the pair is a better separation
            signal than the fold change alone.
        condition_specificity: How much of this gene's expression is confined to the
            target state rather than being everywhere. Needs a reference atlas; a gene
            expressed strongly in the target *and* throughout the body is a poor trigger
            for anything therapeutic.
        trigger_yield: Fraction of this transcript's scanned windows that survive a
            no-folding screen (motif violations, an accidental start codon in either
            orientation, GC extremes) — docs/genes.md §4.2. A gene with a yield of 0.0 is
            never selected: however clean its statistics, stage 2 could build nothing
            from it. Needs the transcript sequence (Q1); ``None`` when it was not
            supplied, never 0.0 for "not tested".
        usable_windows: The raw count behind ``trigger_yield`` — how many windows
            survived, not just what fraction. Useful on its own when the transcript is
            short enough that the fraction alone hides a very small absolute number.
    """

    gene_id: str
    symbol: str
    regulation: Regulation
    log2_fold_change: float | None
    score: float
    p_adj: float | None = None
    control_percentile: float | None = None
    condition_percentile: float | None = None
    condition_specificity: float | None = None
    trigger_yield: float | None = None
    usable_windows: int | None = None


@dataclass(frozen=True, slots=True)
class SeedOpeningTrial:
    """One physically contactable 8-nt toehold seed evaluated by RNAplfold.

    Coordinates are transcript-forward, 0-based, start-inclusive/end-exclusive.
    ``relative_start`` is measured from the exposed toehold's transcript-forward start.
    """

    start: int
    end: int
    relative_start: int
    sequence: str
    probability: float


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
        log2_fold_change: The *gene's* effect size, carried down from
            ``SelectedGene`` — not a property of this window. It is here because
            everything below stage 1 (``is_compatible``'s ``min_separation`` check,
            ``state_separation``) needs it and a ``TriggerCandidate`` is the only
            record those layers receive. ``None`` for a `direct` submission, which
            made no differential-expression comparison at all.
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
    gc_content: float
    log2_fold_change: float | None = None
    aug_indexes: tuple[int, ...] = ()
    stop_indexes: tuple[int, ...] = ()
    ribosome_occupancy: float | None = None
    score: float = 0.0
    transcript_id: str = ""
    reference_accession: str = ""
    reference_selection_method: str = ""
    transcript_sequence_sha256: str = ""
    # Gate-aware RNAplfold evidence. ``gate_toehold_length`` is populated only for
    # exact-footprint scanned candidates; ``None`` preserves legacy/manual direct
    # candidates, for which gate generation may still sweep every fitting variant.
    gate_toehold_length: int | None = None
    hypothesis_start: int | None = None
    hypothesis_end: int | None = None
    joint_open_probability_20: float | None = None
    mean_marginal_openness_20: float | None = None
    delta_g_open_kcal_per_mol_per_nt: float | None = None
    selected_seed_start: int | None = None
    selected_seed_end: int | None = None
    selected_seed_probability: float | None = None
    seed_trials: tuple[SeedOpeningTrial, ...] = ()
    rnaplfold_version: str | None = None
    rnaplfold_window: int | None = None
    rnaplfold_max_span: int | None = None
    rnaplfold_unpaired: int | None = None
    rnaplfold_temperature_celsius: float | None = None

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
        max_circuit_gates: How many gates one circuit may combine — the length of the
            logic, not the arity of a single gate. 1 means every selected gene becomes
            its own one-gene circuit, which is all this engine built before stage 4
            existed. Raising it lets ``CircuitDesigner`` combine genes into
            ``A AND NOT B``-style circuits; each extra gate is another switch to
            synthesise, so ``circuit_complexity`` (weight 1.0, lower better) prices it
            in rather than the cap alone deciding. Distinct from ``max_triggers``,
            which is how many *inputs one gate* takes.
        max_triggers: Circuit arity ceiling. 2 is the practical limit — pairs grow as the
            square of the trigger count, and triples make the search space intractable
            without a cluster (docs/ROADMAP.md §3).
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
        max_genes: Stage 1's shortlist ceiling (docs/genes.md §5 D4). A compute-budget
            knob, not a scientific threshold — everything downstream scales with it, so
            it belongs here rather than as a class constant nobody can configure.
        max_separation: Optional ceiling on ``abs(log2FoldChange)``. ``min_separation`` is
            a floor; an implausibly *large* fold change is usually evidence of a
            near-zero denominator, not strong regulation (docs/genes.md §1). ``None``
            means no ceiling is applied.
        min_base_expression: Floor on a gene's expression in whichever group is the "ON"
            state for its direction — too low and a switch never sees enough trigger.
            ``None`` means the check is skipped (most public datasets carry no
            abundance column at all, docs/genes.md §2).
        max_base_expression: Ceiling on a gene's expression in whichever group is the
            "OFF" state for its direction — too high and the switch leaks.
        trigger_gc_range: GC% band a trigger window must fall inside to count as usable
            in stage 1's trigger-yield screen (docs/genes.md §4.2). Separate from
            ``engine.scoring``'s ``gc_content`` metric range: this is a coarse,
            no-folding-required pre-filter at gene-selection time, not the scored
            per-design metric — the default mirrors that range because nobody has
            reviewed a different one yet.
        direction_balance: When true, stage 1 reserves shortlist slots for both
            ``Regulation.UP`` and ``Regulation.DOWN`` genes rather than letting
            whichever direction happens to have larger effect sizes in this dataset
            crowd out the other (docs/genes.md §4.4 — measured as 19-to-1 on a real
            public comparison). Circuit logic needing ``AND NOT`` has nothing to build
            from if stage 1 never kept a repressor candidate.
    """

    max_triggers: int = 1
    max_circuit_gates: int = 1
    min_separation: float = 0.5
    max_p_adj: float = 0.05
    trigger_lengths: tuple[int, ...] = (30, 33, 36)
    max_switch_length: int = 200
    forbidden_motifs: tuple[str, ...] = ()
    standard: AssemblyStandard = AssemblyStandard.RFC10
    max_genes: int = 20
    max_separation: float | None = None
    min_base_expression: float | None = None
    max_base_expression: float | None = None
    trigger_gc_range: tuple[float, float] = (30.0, 70.0)
    direction_balance: bool = True


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
    # Immutable JSON records of original exact GenBank feature locations/qualifiers.
    annotations: tuple[str, ...] = ()

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
    coding_regions: tuple[tuple[int, int, str, str], ...] = ()
    backbone_annotations: tuple[str, ...] = ()
    insertion_index: int | None = None
    assembly_method: str = "expression_cassette"
    assembly_notes: tuple[str, ...] = ()
    payload_optimization: str = ""
    eligibility_violations: tuple[str, ...] = ()

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
class FoldResult:
    """Structure and free energy from one fold. Cached by the tool that produced it."""

    structure: str
    energy: float


@dataclass(frozen=True, slots=True)
class StructureMatch:
    """How closely a predicted fold matches the intended one."""

    deviation: float
    p_target_fold: float | None


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Whether a design passes the hard rules, and every reason it does not."""

    ok: bool
    violations: tuple[str, ...] = ()
    structure_deviation: float | None = None

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
