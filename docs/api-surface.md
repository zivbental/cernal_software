# API surface — everything the engine already has

<!-- GENERATED FILE — DO NOT EDIT BY HAND. -->

> **This file is generated from the source.** Do not edit it; edit the code and
> regenerate with `uv run python tools/gen_api_surface.py`.
> `tests/test_api_surface_is_fresh.py` fails if the two have drifted, so it cannot
> quietly go stale.

## How to use this file

**Search here before you write any function.** Ctrl-F the thing you were about to
write — `gc_content`, `reverse_complement`, `hybridization_energy`, `mint_id`,
`write_artifact` — and if it is listed as `BUILT`, call it instead. The failure this
prevents is not a merge conflict; it is two members computing the same quantity on
two different scales, after which `engine.scoring` normalises both onto one axis as
though they were comparable, and no error is ever raised.

Four statuses, and they mean different things:

| Status | Meaning | What you do with it |
| --- | --- | --- |
| `BUILT` | Implemented and callable today. | **Call it. Never reimplement it.** |
| `STUB` | Body raises `NotImplementedError("Step 5 — …")`. | Unclaimed work — this is where a ported module lands. |
| `ABSTRACT` | `@abstractmethod`; a contract for subclasses. | Implement it in your subclass; `ABCMeta` refuses to instantiate you until you do. |
| `PROTOCOL` | Body is `...`; a structural shape. | Match the shape. Nothing calls the `...` itself. |

`__init__` is listed even though it is a dunder, because it **is** the dependency-
injection contract: it tells you which tools an object must be handed. Tools are
constructed once in `engine.pipeline.build_tools` and passed down — never built
inside a stage or a gate.

Public means the name does not start with `_`. No engine module declares `__all__`,
so that convention is the only rule there is.

## Totals

| | Count |
| --- | ---: |
| Modules | 35 |
| Public classes | 80 |
| Public callables (excluding `__init__`) | 156 |
| — `BUILT` | 107 |
| — `STUB` | 42 |
| — `ABSTRACT` | 5 |
| — `PROTOCOL` | 2 |
| `__init__` constructors | 20 |

## Index

Modules in dependency order. Imports point downward only: a layer may call the
layers above it, never the ones below.

| Layer | Module | S | Not `STUB` | `STUB` | Purpose |
| --- | --- | --- | ---: | ---: | --- |
| domain | `engine.domain` |  | 29 | 0 | The engine's scientific vocabulary. |
| sequences | `engine.sequences` | S6 | 12 | 0 | S6 — sequence facts. Pure functions, no state, no dependencies. |
| scoring | `engine.scoring` |  | 0 | 0 |  |
| scoring | `engine.scoring.normalize` |  | 5 | 0 | Turning heterogeneous raw metrics into comparable normalized values. |
| scoring | `engine.scoring.profiles` |  | 5 | 0 | Versioned scoring profiles. |
| gate_tools | `engine.gates.tools` |  | 0 | 0 | Scientific primitives shared across the gate families. |
| gate_tools | `engine.gates.tools.binding` | S3 | 1 | 0 | S3 — trigger/switch hybridisation energy. |
| gate_tools | `engine.gates.tools.codons` | S8 | 0 | 2 | S8 — codon usage and synonymous rewriting. |
| gate_tools | `engine.gates.tools.folding` | S2, S4 | 4 | 3 | S2, S4 — RNA secondary structure prediction for gate designs. |
| gate_tools | `engine.gates.tools.translation` | S9 | 0 | 4 | S9 — translation initiation strength. |
| gates | `engine.gates` |  | 0 | 0 |  |
| gates | `engine.gates.antisense` |  | 5 | 0 | Antisense NOT gate. |
| gates | `engine.gates.base` |  | 8 | 0 | The GateFamily interface. |
| gates | `engine.gates.crispr` |  | 3 | 2 | CRISPR-derived sgRNA gate. |
| gates | `engine.gates.registry` |  | 4 | 0 | Gate family lookup. |
| gates | `engine.gates.toehold` |  | 2 | 4 | Toehold switches — single input, and two-input AND. |
| gates | `engine.gates.notebooks._fixtures` |  | 18 | 0 | Shared setup for the per-gate notebooks under this folder. |
| stages | `engine.stages` |  | 0 | 0 | The pipeline stages. |
| stages | `engine.stages.circuits` |  | 0 | 4 | Stage 4 — circuit design and scoring. |
| stages | `engine.stages.folding` | S1 | 0 | 2 | S1 — local accessibility profiling, the primitive behind trigger selection. |
| stages | `engine.stages.genes` |  | 0 | 1 | Stage 1 — gene selection. |
| stages | `engine.stages.motifs` | S7 | 2 | 0 | S7 — prohibited motif screening. |
| stages | `engine.stages.off_target` | S5 | 0 | 4 | S5 — off-target scanning, in both directions. |
| stages | `engine.stages.plasmids` |  | 0 | 2 | Stage 5 — plasmid construction. |
| stages | `engine.stages.quality` | S15 | 0 | 1 | S15 — input quality control. |
| stages | `engine.stages.reporting` |  | 0 | 3 | Stage 6 — the compiler's output. |
| stages | `engine.stages.switches` |  | 0 | 3 | Stage 3 — switch design and validation. |
| stages | `engine.stages.triggers` |  | 0 | 1 | Stage 2 — trigger scoring. |
| top | `engine` |  | 0 | 0 |  |
| top | `engine.artifacts` |  | 3 | 0 | Writing engine output files. |
| top | `engine.client` |  | 7 | 0 | The Platform-facing engine interface. |
| top | `engine.contract` |  | 5 | 0 | The Platform ⇄ Engine contract. |
| top | `engine.errors` |  | 0 | 0 | Engine error hierarchy. |
| top | `engine.pipeline` |  | 0 | 2 | The real scientific pipeline. |
| top | `engine.store` | S11, S13 | 1 | 4 | S11, S13 — provenance and pruning. |

## Layer 1 · Domain — the vocabulary

Data and arithmetic only, no science. Every value that crosses a module boundary must already be one of these types. Collections are **tuples**, not lists, because the dataclasses are `frozen=True, slots=True`.

### `engine.domain`

`src/engine/domain.py`

The engine's scientific vocabulary.

#### `class Host(StrEnum)`

The organism a circuit is designed for.

| Attribute | Type | Default |
| --- | --- | --- |
| `ECOLI` |  | `'ecoli'` |
| `YEAST` |  | `'yeast'` |
| `HUMAN` |  | `'human'` |

| Status | Method | Purpose |
| --- | --- | --- |
| `BUILT` | `@property def track(self) -> 'Track'` | Design rules follow the track, not the individual organism. |

#### `class Track(StrEnum)`

Translation machinery. Decides RBS-in-loop versus Kozak, among other rules.

| Attribute | Type | Default |
| --- | --- | --- |
| `PROKARYOTIC` |  | `'prokaryotic'` |
| `EUKARYOTIC` |  | `'eukaryotic'` |

#### `class GateKind(StrEnum)`

The switch chemistries. One value per registered ``GateFamily``.

| Attribute | Type | Default |
| --- | --- | --- |
| `TOEHOLD` |  | `'toehold'` |
| `TOEHOLD_AND` |  | `'toehold_and'` |
| `ANTISENSE_NOT` |  | `'antisense_not'` |
| `CRISPR` |  | `'crispr'` |

#### `class Regulation(StrEnum)`

Which direction a gene moved between the two states.

| Attribute | Type | Default |
| --- | --- | --- |
| `UP` |  | `'up'` |
| `DOWN` |  | `'down'` |

#### `class GeneState(StrEnum)`

Whether a transcript must be present or absent for the circuit to fire.

| Attribute | Type | Default |
| --- | --- | --- |
| `ON` |  | `'ON'` |
| `OFF` |  | `'OFF'` |

#### `class LogicOperator(StrEnum)`

Boolean operators a circuit can be built from.

| Attribute | Type | Default |
| --- | --- | --- |
| `AND` |  | `'AND'` |
| `OR` |  | `'OR'` |
| `NOT` |  | `'NOT'` |
| `IDENTITY` |  | `'IDENTITY'` |

#### `class SegmentKind(StrEnum)`

Parts of an assembled construct.

| Attribute | Type | Default |
| --- | --- | --- |
| `PROMOTER` |  | `'promoter'` |
| `SWITCH` |  | `'switch'` |
| `PAYLOAD` |  | `'payload'` |
| `TERMINATOR` |  | `'terminator'` |
| `BACKBONE` |  | `'backbone'` |

#### `class AssemblyStandard(StrEnum)`

iGEM assembly standards, which decide the prohibited restriction sites.

| Attribute | Type | Default |
| --- | --- | --- |
| `RFC10` |  | `'RFC10'` |
| `RFC1000` |  | `'RFC1000'` |

#### `class DesiredOutcome(StrEnum)`

What a circuit expresses when it fires.

| Attribute | Type | Default |
| --- | --- | --- |
| `GFP` |  | `'gfp'` |
| `MCHERRY` |  | `'mcherry'` |
| `LUCIFERASE` |  | `'luciferase'` |
| `ANTIBIOTIC` |  | `'ampr'` |
| `APOPTOSIS` |  | `'apoptosis'` |
| `CUSTOM` |  | `'other'` |

#### `class SampleMetadata`

`@dataclass(frozen=True, slots=True)`

Which columns of the count matrix are control and which are condition.

| Attribute | Type | Default |
| --- | --- | --- |
| `control_samples` | `tuple[str, ...]` |  |
| `condition_samples` | `tuple[str, ...]` |  |

#### `class DgeRow`

`@dataclass(frozen=True, slots=True)`

One gene's differential-expression result, as DESeq2 and friends report it.

| Attribute | Type | Default |
| --- | --- | --- |
| `gene_id` | `str` |  |
| `symbol` | `str` |  |
| `base_mean` | `float` |  |
| `log2_fold_change` | `float` |  |
| `p_adj` | `float` |  |
| `lfc_se` | `float \| None` | `None` |
| `stat` | `float \| None` | `None` |
| `p_value` | `float \| None` | `None` |

| Status | Method | Purpose |
| --- | --- | --- |
| `BUILT` | `@property def regulation(self) -> Regulation` | Which way this gene moved. Sign of the fold change, nothing more. |

#### `class DgeTable`

`@dataclass(frozen=True, slots=True)`

The parsed differential-expression input.

| Attribute | Type | Default |
| --- | --- | --- |
| `rows` | `tuple[DgeRow, ...]` |  |

| Status | Method | Purpose |
| --- | --- | --- |
| `BUILT` | `def by_gene_id(self) -> dict[str, DgeRow]` | Index the rows for lookup. Build once; the table is scanned repeatedly. |

#### `class CountMatrix`

`@dataclass(frozen=True, slots=True)`

Normalised or raw counts, genes by samples.

| Attribute | Type | Default |
| --- | --- | --- |
| `gene_ids` | `tuple[str, ...]` |  |
| `samples` | `tuple[str, ...]` |  |
| `counts` | `tuple[tuple[float, ...], ...]` |  |
| `metadata` | `SampleMetadata` |  |

| Status | Method | Purpose |
| --- | --- | --- |
| `BUILT` | `@property def shape(self) -> tuple[int, int]` | ``(genes, samples)``, matching numpy's convention. |

#### `class SelectedGene`

`@dataclass(frozen=True, slots=True)`

Stage 1 output — a gene that separates the two cell states.

| Attribute | Type | Default |
| --- | --- | --- |
| `gene_id` | `str` |  |
| `symbol` | `str` |  |
| `regulation` | `Regulation` |  |
| `log2_fold_change` | `float` |  |
| `p_adj` | `float` |  |
| `control_percentile` | `float` |  |
| `condition_percentile` | `float` |  |
| `condition_specificity` | `float` |  |
| `score` | `float` |  |

#### `class TriggerCandidate`

`@dataclass(frozen=True, slots=True)`

Stage 2 output — a sub-segment of a transcript, ranked as a possible input.

| Attribute | Type | Default |
| --- | --- | --- |
| `trigger_id` | `str` |  |
| `gene_id` | `str` |  |
| `symbol` | `str` |  |
| `sequence` | `str` |  |
| `start_index` | `int` |  |
| `openness` | `float` |  |
| `accessibility` | `float` |  |
| `mfe` | `float` |  |
| `off_target_penalty` | `float` |  |
| `segment_specificity` | `float` |  |
| `gc_content` | `float` |  |
| `aug_indexes` | `tuple[int, ...]` | `()` |
| `stop_indexes` | `tuple[int, ...]` | `()` |
| `ribosome_occupancy` | `float \| None` | `None` |
| `score` | `float` | `0.0` |

| Status | Method | Purpose |
| --- | --- | --- |
| `BUILT` | `@property def length(self) -> int` | Window length in nucleotides. With ``start_index``, locates it exactly. |

#### `class Constraints`

`@dataclass(frozen=True, slots=True)`

The researcher's limits, carried into every stage that has to respect them.

| Attribute | Type | Default |
| --- | --- | --- |
| `max_triggers` | `int` | `2` |
| `min_separation` | `float` | `0.5` |
| `max_p_adj` | `float` | `0.05` |
| `trigger_lengths` | `tuple[int, ...]` | `(30, 36)` |
| `max_switch_length` | `int` | `200` |
| `forbidden_motifs` | `tuple[str, ...]` | `()` |
| `standard` | `AssemblyStandard` | `AssemblyStandard.RFC10` |

#### `class Compatibility`

`@dataclass(frozen=True, slots=True)`

Whether a gate family can realise a trigger set, and why not if it cannot.

| Attribute | Type | Default |
| --- | --- | --- |
| `ok` | `bool` |  |
| `reason` | `str` | `''` |

| Status | Method | Purpose |
| --- | --- | --- |
| `BUILT` | `@classmethod def yes(cls) -> 'Compatibility'` | This family can realise the trigger set. |
| `BUILT` | `@classmethod def no(cls, reason: str) -> 'Compatibility'` | It cannot. ``reason`` is shown to the researcher, so write it for them. |

#### `class TriggerSet`

`@dataclass(frozen=True, slots=True)`

The inputs to one circuit.

| Attribute | Type | Default |
| --- | --- | --- |
| `activators` | `tuple[TriggerCandidate, ...]` |  |
| `repressors` | `tuple[TriggerCandidate, ...]` | `()` |

| Status | Method | Purpose |
| --- | --- | --- |
| `BUILT` | `@property def arity(self) -> int` | Total inputs. Checked against a family's ``max_inputs``. |
| `BUILT` | `@property def logic_type(self) -> str` | Human-readable shape of this input set, for display and for the summary line. |
| `BUILT` | `@property def trigger_ids(self) -> tuple[str, ...]` | Every trigger id, activators first. Recorded on the design for traceability. |

#### `class GateDesign`

`@dataclass(frozen=True, slots=True)`

Stage 3 output — one concrete switch built for one trigger set.

| Attribute | Type | Default |
| --- | --- | --- |
| `design_id` | `str` |  |
| `gate_kind` | `GateKind` |  |
| `host` | `Host` |  |
| `trigger_set` | `TriggerSet` |  |
| `sequence` | `str` |  |
| `dot_bracket` | `str` | `''` |
| `structure_deviation` | `float` | `0.0` |
| `mfe_on` | `float` | `0.0` |
| `mfe_off` | `float` | `0.0` |
| `mfe_trigger` | `float` | `0.0` |
| `binding_site_accessibility` | `float` | `0.0` |
| `binding_site_off_target` | `float` | `0.0` |
| `translation_score` | `float` | `0.0` |
| `architecture` | `dict` | `field(default_factory=dict)` |
| `score` | `float` | `0.0` |

| Status | Method | Purpose |
| --- | --- | --- |
| `BUILT` | `@property def length(self) -> int` | Switch length in nucleotides, against ``Constraints.max_switch_length``. |

#### `class Rejection`

`@dataclass(frozen=True, slots=True)`

Why a candidate was excluded. Never discarded silently (rule 8).

| Attribute | Type | Default |
| --- | --- | --- |
| `reason` | `str` |  |
| `filter_name` | `str` | `''` |

#### `class BooleanExpression`

`@dataclass(frozen=True, slots=True)`

A circuit's logic as a tree, not a string.

| Attribute | Type | Default |
| --- | --- | --- |
| `operator` | `LogicOperator` |  |
| `operands` | `tuple['BooleanExpression \| str', ...]` |  |

| Status | Method | Purpose |
| --- | --- | --- |
| `BUILT` | `@classmethod def gene(cls, gene_id: str) -> 'BooleanExpression'` | A leaf: this gene, unmodified. The base case every expression builds from. |
| `BUILT` | `def evaluate(self, active: frozenset[str]) -> bool` | True when this expression fires, given the set of present transcripts. |
| `BUILT` | `def gene_ids(self) -> tuple[str, ...]` | Every gene this expression references, in order, without duplicates. |
| `BUILT` | `def complexity(self) -> int` | Component count — the axis a circuit's score is traded off against. |
| `BUILT` | `def render(self) -> str` | ``A AND (B OR C) AND NOT D``. |

#### `class LogicGene`

`@dataclass(frozen=True, slots=True)`

One gene as the circuit diagram draws it.

| Attribute | Type | Default |
| --- | --- | --- |
| `name` | `str` |  |
| `role` | `str` |  |
| `state` | `GeneState` |  |
| `direction` | `Regulation` |  |

#### `class LogicGraph`

`@dataclass(frozen=True, slots=True)`

The Boolean structure, in the shape the results view renders.

| Attribute | Type | Default |
| --- | --- | --- |
| `genes` | `tuple[LogicGene, ...]` |  |
| `mid_gate` | `LogicOperator` |  |
| `outer_gate` | `LogicOperator` |  |
| `invert` | `bool` |  |
| `output` | `str` |  |
| `caption` | `str` |  |

#### `class Segment`

`@dataclass(frozen=True, slots=True)`

One stretch of the assembled construct.

| Attribute | Type | Default |
| --- | --- | --- |
| `kind` | `SegmentKind` |  |
| `name` | `str` |  |
| `sequence` | `str` |  |

| Status | Method | Purpose |
| --- | --- | --- |
| `BUILT` | `@property def length_bp(self) -> int` | Segment length. Drives the proportional arcs on the plasmid map. |

#### `class Plasmid`

`@dataclass(frozen=True, slots=True)`

The assembled construct. Data plus arithmetic — no behaviour.

| Attribute | Type | Default |
| --- | --- | --- |
| `segments` | `tuple[Segment, ...]` |  |

| Status | Method | Purpose |
| --- | --- | --- |
| `BUILT` | `@property def length_bp(self) -> int` | Total construct length. Synthesis vendors price and cap on this. |
| `BUILT` | `@property def sequence(self) -> str` | The whole construct, segments concatenated in order. |
| `BUILT` | `@property def gc_content(self) -> float` | Percent G+C over the whole construct. Extremes hurt synthesis. |

#### `class ConfusionMatrix`

`@dataclass(frozen=True, slots=True)`

Circuit ON/OFF against condition/control samples.

| Attribute | Type | Default |
| --- | --- | --- |
| `true_positive` | `int` |  |
| `false_positive` | `int` |  |
| `false_negative` | `int` |  |
| `true_negative` | `int` |  |

| Status | Method | Purpose |
| --- | --- | --- |
| `BUILT` | `@property def sensitivity(self) -> float` | Fraction of condition samples the circuit correctly fires on. Recall. |
| `BUILT` | `@property def specificity(self) -> float` | Fraction of control samples the circuit correctly stays dark on. |
| `BUILT` | `@property def separation_margin(self) -> float` | Youden's J — how cleanly the circuit tells the two states apart. 0 is chance. |

#### `class CircuitCandidate`

`@dataclass(frozen=True, slots=True)`

Stage 4 output — a complete, scored circuit.

| Attribute | Type | Default |
| --- | --- | --- |
| `circuit_id` | `str` |  |
| `expression` | `BooleanExpression` |  |
| `logic_graph` | `LogicGraph` |  |
| `designs` | `tuple[GateDesign, ...]` |  |
| `confusion` | `ConfusionMatrix` |  |
| `output` | `str` |  |
| `score` | `float` | `0.0` |
| `rejection` | `Rejection \| None` | `None` |

| Status | Method | Purpose |
| --- | --- | --- |
| `BUILT` | `@property def complexity(self) -> int` | Component count — the axis score is traded against in the Pareto filter. |
| `BUILT` | `@property def is_rejected(self) -> bool` | True when this circuit was excluded. Its ``rejection`` says why (rule 8). |

#### `class PlasmidDesign`

`@dataclass(frozen=True, slots=True)`

Stage 5 output — an orderable construct.

| Attribute | Type | Default |
| --- | --- | --- |
| `plasmid_id` | `str` |  |
| `circuit_id` | `str` |  |
| `plasmid` | `Plasmid` |  |
| `standard` | `AssemblyStandard` |  |
| `violations` | `tuple[str, ...]` | `()` |

| Status | Method | Purpose |
| --- | --- | --- |
| `BUILT` | `@property def is_compliant(self) -> bool` | True when the construct breaks no assembly-standard rule and can be ordered. |

#### `class ToolRequirement`

`@dataclass(frozen=True, slots=True)`

An external tool a gate family needs, and the version it was validated against.

| Attribute | Type | Default |
| --- | --- | --- |
| `name` | `str` |  |
| `version` | `str` |  |
| `optional` | `bool` | `False` |

#### `class Hit`

`@dataclass(frozen=True, slots=True)`

One near-match found in the transcriptome.

| Attribute | Type | Default |
| --- | --- | --- |
| `gene_id` | `str` |  |
| `start` | `int` |  |
| `mismatches` | `int` |  |
| `identity` | `float` |  |

#### `class OffTargetReport`

`@dataclass(frozen=True, slots=True)`

What an off-target scan found, and what it costs the candidate.

| Attribute | Type | Default |
| --- | --- | --- |
| `hits` | `tuple[Hit, ...]` |  |
| `penalty` | `float` |  |

| Status | Method | Purpose |
| --- | --- | --- |
| `BUILT` | `@property def worst_identity(self) -> float` | Closest off-target match found. 1.0 means an exact duplicate exists. |

#### `class FoldResult`

`@dataclass(frozen=True, slots=True)`

Structure and free energy from one fold. Cached by the tool that produced it.

| Attribute | Type | Default |
| --- | --- | --- |
| `structure` | `str` |  |
| `energy` | `float` |  |

#### `class StructureMatch`

`@dataclass(frozen=True, slots=True)`

How closely a predicted fold matches the intended one.

| Attribute | Type | Default |
| --- | --- | --- |
| `deviation` | `float` |  |
| `p_target_fold` | `float` |  |

#### `class ValidationResult`

`@dataclass(frozen=True, slots=True)`

Whether a design passes the hard rules, and every reason it does not.

| Attribute | Type | Default |
| --- | --- | --- |
| `ok` | `bool` |  |
| `violations` | `tuple[str, ...]` | `()` |

| Status | Method | Purpose |
| --- | --- | --- |
| `BUILT` | `@classmethod def passed(cls) -> 'ValidationResult'` | The design obeys every hard rule. |
| `BUILT` | `@classmethod def failed(cls, *violations: str) -> 'ValidationResult'` | It does not. Pass **every** violation, not just the first — a generator being tuned is far easier to fix when it reports all its problems at once. |

#### `class QcReport`

`@dataclass(frozen=True, slots=True)`

What the quality check found before anything expensive runs.

| Attribute | Type | Default |
| --- | --- | --- |
| `ok` | `bool` |  |
| `warnings` | `tuple[str, ...]` | `()` |
| `errors` | `tuple[str, ...]` | `()` |
| `stats` | `dict` | `field(default_factory=dict)` |

## Layer 2 · Sequences — S6, the most-reinvented module in the repo

Pure functions over nucleotide strings: no state, no dependencies, all BUILT. If you are about to write a reverse-complement, a GC%, a codon split, a translation or a sliding window, it is already here. Note `gc_content` returns **percent (0-100)**, not a fraction.

### `engine.sequences` · S6

`src/engine/sequences.py`

S6 — sequence facts. Pure functions, no state, no dependencies.

| Constant | Type | Value |
| --- | --- | --- |
| `RNA_BASES` |  | `frozenset('ACGU')` |
| `DNA_BASES` |  | `frozenset('ACGT')` |
| `START_CODON` |  | `'AUG'` |
| `STOP_CODONS` |  | `frozenset({'UAA', 'UAG', 'UGA'})` |
| `CODON_TABLE` | `dict[str, str]` | `{'UUU': 'F', 'UUC': 'F', 'UUA': 'L', 'UUG': 'L', 'CUU': 'L', 'CUC': 'L', 'CUA': 'L', 'C…` |

| Status | Function | Purpose |
| --- | --- | --- |
| `BUILT` | `def to_rna(sequence: str) -> str` | Uppercase and convert T to U. Researchers paste DNA as often as RNA. |
| `BUILT` | `def to_dna(sequence: str) -> str` | Uppercase and convert U to T. Assembly standards and vendors speak DNA. |
| `BUILT` | `def is_valid_rna(sequence: str) -> bool` | True for a non-empty sequence of A, C, G, U only. Empty is not valid. |
| `BUILT` | `def reverse_complement(sequence: str, *, dna: bool = False) -> str` | Reverse complement. A switch's binding site is the trigger's reverse complement. |
| `BUILT` | `def gc_content(sequence: str) -> float` | Percent G+C. Extremes hurt synthesis and folding alike. |
| `BUILT` | `def codons(sequence: str, frame: int = 0) -> list[str]` | Split into codons from a reading frame, dropping any trailing partial codon. |
| `BUILT` | `def translate(sequence: str, frame: int = 0, *, stop_at_stop: bool = True) -> str` | Translate to single-letter amino acids. Unknown codons become 'X'. |
| `BUILT` | `def find_augs(sequence: str, frame: int \| None = None) -> tuple[int, ...]` | Every AUG position. |
| `BUILT` | `def find_stops(sequence: str, frame: int = 0) -> tuple[int, ...]` | In-frame stop codon positions. A switch's coding region must contain none. |
| `BUILT` | `def longest_homopolymer(sequence: str) -> tuple[str, int]` | The longest single-base run, as ``(base, length)``. |
| `BUILT` | `def hamming(a: str, b: str) -> int` | Mismatches between two equal-length sequences. |
| `BUILT` | `def windows(sequence: str, length: int, step: int = 1) -> list[tuple[int, str]]` | Sliding windows as ``(start, subsequence)`` — the basis of trigger scanning. |

## Layer 3 · Scoring — the single ranking authority

The metric vocabulary lives in `DEFAULT_V1` and nowhere else. `GateFamily.evaluate_design` must return **raw** values keyed by exactly those metric names; a name that is not in the profile is silently dropped and the candidate is scored as if the metric were missing, which is `missing_behavior='worst'`. No module may normalise or weight on its own.

### `engine.scoring`

`src/engine/scoring/__init__.py`

*Empty file — no docstring, no public symbols, no re-exports.*

### `engine.scoring.normalize`

`src/engine/scoring/normalize.py`

Turning heterogeneous raw metrics into comparable normalized values.

| Status | Function | Purpose |
| --- | --- | --- |
| `BUILT` | `def normalize_value(raw: float \| None, spec: MetricSpec) -> float \| None` | Map a raw value onto 0-1 where 1.0 is best. ``None`` if it cannot be normalized. |
| `BUILT` | `def build_metrics(raw_values: dict[str, float \| None], profile: ScoringProfile) -> list[MetricValue]` | Build the full metric list for one candidate, in profile order. |
| `BUILT` | `def weighted_score(metrics: list[MetricValue], profile: ScoringProfile) -> float \| None` | Weighted mean of normalized values, on 0-1. |
| `BUILT` | `def failed_filter(raw_values: dict[str, float \| None], profile: ScoringProfile) -> HardFilter \| None` | Return the first hard filter this candidate fails, or ``None`` if it passes all. |
| `BUILT` | `def rank_candidates(scored: list[tuple[str, float \| None]]) -> dict[str, int]` | Assign contiguous 1-based ranks, best first. Unscored candidates are not ranked. |

### `engine.scoring.profiles`

`src/engine/scoring/profiles.py`

Versioned scoring profiles.

| Constant | Type | Value |
| --- | --- | --- |
| `TREAT_AS_WORST` |  | `'worst'` |
| `SKIP` |  | `'skip'` |
| `DEFAULT_V1` |  | `ScoringProfile(name='default', version='v1', metrics=[MetricSpec(name='state_separation…` |
| `PROFILES` | `dict[str, ScoringProfile]` | `{DEFAULT_V1.name: DEFAULT_V1}` |

| Status | Function | Purpose |
| --- | --- | --- |
| `BUILT` | `def get_profile(name: str) -> ScoringProfile` | Look up a profile by name, validating it before returning. |
| `BUILT` | `def available_profiles() -> list[str]` | Profile names a submission may request. Surfaced at ``GET /api/version``. |

#### `class MetricSpec`

`@dataclass(frozen=True, slots=True)`

The declaration of one metric, per design map 12.

| Attribute | Type | Default |
| --- | --- | --- |
| `name` | `str` |  |
| `direction` | `str` |  |
| `weight` | `float` |  |
| `valid_range` | `tuple[float, float]` |  |
| `missing_behavior` | `str` | `TREAT_AS_WORST` |
| `description` | `str` | `''` |

#### `class HardFilter`

`@dataclass(frozen=True, slots=True)`

A disqualifying threshold. Failing one rejects the candidate before ranking.

| Attribute | Type | Default |
| --- | --- | --- |
| `metric` | `str` |  |
| `minimum` | `float \| None` | `None` |
| `maximum` | `float \| None` | `None` |
| `reason` | `str` | `''` |

#### `class ScoringProfile`

`@dataclass(frozen=True, slots=True)`

A versioned, complete description of how candidates are compared.

| Attribute | Type | Default |
| --- | --- | --- |
| `name` | `str` |  |
| `version` | `str` |  |
| `metrics` | `list[MetricSpec]` |  |
| `hard_filters` | `list[HardFilter]` | `field(default_factory=list)` |
| `tie_breakers` | `list[str]` | `field(default_factory=list)` |

| Status | Method | Purpose |
| --- | --- | --- |
| `BUILT` | `@property def label(self) -> str` | ``default-v1``. What gets recorded on a run and shown in the report. |
| `BUILT` | `def spec(self, metric_name: str) -> MetricSpec \| None` | The declaration for one metric, or ``None`` if this profile ignores it. |
| `BUILT` | `def validate(self) -> None` | Fail loudly on an inconsistent profile rather than producing a silent bad score. |

## Layer 4 · Gate tools — the scientific primitives

Constructed once per run by `engine.pipeline.build_tools` and injected. `engine.gates.tools.folding` is one of only two modules in the engine permitted to `import RNA`; everything else folds through a `FoldEngine` instance it was handed, so the cache and the temperature stay shared.

### `engine.gates.tools`

`src/engine/gates/tools/__init__.py`

Scientific primitives shared across the gate families.

*No public symbols — the docstring is the whole file.*

### `engine.gates.tools.binding` · S3

`src/engine/gates/tools/binding.py`

S3 — trigger/switch hybridisation energy.

| Status | Function | Purpose |
| --- | --- | --- |
| `BUILT` | `def hybridization_energy(switch: str, trigger: str, folder: FoldEngine) -> float` | Free energy released when a trigger binds its switch. |

### `engine.gates.tools.codons` · S8

`src/engine/gates/tools/codons.py`

S8 — codon usage and synonymous rewriting.

#### `class CodonOptimizer`

Synonymous-codon search and translation scoring for one host.

| Status | Method | Purpose |
| --- | --- | --- |
| `BUILT` | `def __init__(self, host: Host, usage_table: dict[str, float] \| None = None) -> None` |  |
| `STUB` | `def variants(self, cds: str, target_pairing: str \| None = None) -> list[str]` | Synonymous rewrites of a coding sequence: same protein, different bases. |
| `STUB` | `def translation_score(self, cds: str) -> float` | How well a sequence's codons suit the host. |

### `engine.gates.tools.folding` · S2, S4

`src/engine/gates/tools/folding.py`

S2, S4 — RNA secondary structure prediction for gate designs.

| Status | Function | Purpose |
| --- | --- | --- |
| `STUB` | `def structure_match(dot_bracket: str, target_structure: str) -> StructureMatch` | **S4** · S4 — compare a predicted structure against the one a generator intended. |

#### `class FoldEngine` · S2

S2 — minimum free energy, ensemble properties and suboptimal structures.

| Status | Method | Purpose |
| --- | --- | --- |
| `BUILT` | `def __init__(self, temperature: float = 37.0, cache_size: int = 100000) -> None` |  |
| `BUILT` | `@cache def mfe(self, sequence: str) -> FoldResult` | Fold a sequence and return its most stable predicted structure. |
| `BUILT` | `@cache def partition(self, sequence: str) -> float` | Ensemble free energy over all structures, not just the most stable one. |
| `STUB` | `def ensemble_defect(self, sequence: str, target: str) -> float` | How far the predicted ensemble sits from an intended structure. |
| `BUILT` | `def base_pair_probabilities(self, sequence: str) -> list[list[float]]` | Probability that each pair of positions is bonded, over the whole ensemble. |
| `STUB` | `def suboptimal(self, sequence: str, delta: float = 2.0) -> list[FoldResult]` | Every structure within an energy window of the MFE. |
| `BUILT` | `def versions(self) -> dict[str, str]` | The tool versions this run was computed with. |

### `engine.gates.tools.translation` · S9

`src/engine/gates/tools/translation.py`

S9 — translation initiation strength.

#### `class TranslationScorer`

Initiation strength for one host, dispatching on its track.

| Status | Method | Purpose |
| --- | --- | --- |
| `BUILT` | `def __init__(self, host: Host) -> None` |  |
| `STUB` | `def score(self, sequence: str, start_index: int) -> float` | Translation initiation rate for the start codon at ``start_index``. |
| `STUB` | `def rbs_strength(self, sequence: str, start_index: int) -> float` | Prokaryotic: Shine-Dalgarno complementarity and spacing. |
| `STUB` | `def kozak_match(self, sequence: str, start_index: int) -> float` | Eukaryotic: agreement with the Kozak consensus. |
| `STUB` | `def ramp_is_unstructured(self, sequence: str, start_index: int) -> bool` | Whether the region just downstream of the AUG is open enough to translate. |

## Layer 5 · Gate families — where a switch chemistry goes

`GateFamily` is the one real class hierarchy in the engine. A ported gate module becomes a subclass here: set the ClassVars, implement the five methods, add one `register(...)` line. Nothing else in the codebase or the frontend needs to change.

### `engine.gates`

`src/engine/gates/__init__.py`

*Empty file — no docstring, no public symbols, no re-exports.*

### `engine.gates.antisense`

`src/engine/gates/antisense.py`

Antisense NOT gate.

#### `class AntisenseNotGate(GateFamily)`

Post-transcriptional silencing. The pipeline's inverting element.

| Attribute | Type | Default |
| --- | --- | --- |
| `name` |  | `'antisense'` |
| `version` |  | `'0.1.0'` |
| `kind` |  | `GateKind.ANTISENSE_NOT` |
| `label` |  | `'Antisense Repression'` |
| `description` |  | `'Post-transcriptional silencing'` |
| `supported_hosts` | `ClassVar[frozenset[Host]]` | `frozenset({Host.ECOLI, Host.YEAST, Host.HUMAN})` |
| `max_inputs` |  | `1` |
| `available` |  | `True` |
| `UTR_LENGTHS` | `ClassVar[tuple[int, ...]]` | `(8, 10, 12, 14)` |
| `SPACER_LENGTHS` | `ClassVar[tuple[int, ...]]` | `(5, 7, 9)` |
| `RBS_PROKARYOTIC` | `ClassVar[str]` | `'AGGAGGA'` |
| `KOZAK_EUKARYOTIC` | `ClassVar[str]` | `'GCCACC'` |
| `PAYLOAD_HEAD_LENGTH` | `ClassVar[int]` | `30` |
| `WINDOW_STEP` | `ClassVar[int]` | `3` |
| `MIN_TRIGGER_ACCESSIBILITY` | `ClassVar[float]` | `0.3` |

| Status | Method | Purpose |
| --- | --- | --- |
| `BUILT` | `def __init__(self, host: Host, folder: FoldEngine, codons: CodonOptimizer, payload: str) -> None` |  |
| `BUILT` | `def required_tools(self) -> list[ToolRequirement]` | External tools this family needs, checked before a run starts. |
| `BUILT` | `def is_compatible(self, trigger_set: TriggerSet, constraints: Constraints) -> Compatibility` | Can this family invert this trigger set? |
| `BUILT` | `def generate_designs(self, trigger_set: TriggerSet, constraints: Constraints) -> Iterator[GateDesign]` | Build an antisense element that silences the payload when the trigger is present. |
| `BUILT` | `def evaluate_design(self, design: GateDesign) -> dict[str, float \| None]` | Measure a silencing design. |
| `BUILT` | `def emit_sequence(self, design: GateDesign) -> str` | The synthesis-ready sequence. |

### `engine.gates.base`

`src/engine/gates/base.py`

The GateFamily interface.

#### `class GateFamily(ABC)`

Base class for every switch chemistry.

| Attribute | Type | Default |
| --- | --- | --- |
| `name` | `ClassVar[str]` | `''` |
| `version` | `ClassVar[str]` | `''` |
| `kind` | `ClassVar[GateKind]` |  |
| `label` | `ClassVar[str]` | `''` |
| `description` | `ClassVar[str]` | `''` |
| `supported_hosts` | `ClassVar[frozenset[Host]]` | `frozenset()` |
| `max_inputs` | `ClassVar[int]` | `1` |
| `available` | `ClassVar[bool]` | `False` |

| Status | Method | Purpose |
| --- | --- | --- |
| `BUILT` | `def supports(self, host: Host) -> bool` | Whether this family can be used for this organism. |
| `ABSTRACT` | `def required_tools(self) -> list[ToolRequirement]` | External tools this family needs. Checked before a run starts. |
| `ABSTRACT` | `def is_compatible(self, trigger_set: TriggerSet, constraints: Constraints) -> Compatibility` | Can this family realise this trigger set? Cheap checks only — expensive evaluation happens later, and only for designs that survive this. |
| `ABSTRACT` | `def generate_designs(self, trigger_set: TriggerSet, constraints: Constraints) -> Iterator[GateDesign]` | Produce candidate realisations. **Yields**, because a family exploring a length window across thousands of trigger sets produces far too many designs to hold in a list. |
| `ABSTRACT` | `def evaluate_design(self, design: GateDesign) -> dict[str, float \| None]` | Measure a design. Returns **raw** values keyed by metric name. |
| `ABSTRACT` | `def emit_sequence(self, design: GateDesign) -> str` | The synthesis-ready sequence for this design. |
| `BUILT` | `def emit_artifacts(self, design: GateDesign, output_dir: str) -> list[ArtifactRef]` | Family-specific files. Optional — the default produces none. |
| `BUILT` | `def describe(self, design: GateDesign) -> str` | One-line human summary. Overridable, with a reasonable default. |

### `engine.gates.crispr`

`src/engine/gates/crispr.py`

CRISPR-derived sgRNA gate.

#### `class CrisprGate(GateFamily)`

Transcriptional control via a trigger-gated guide RNA.

| Attribute | Type | Default |
| --- | --- | --- |
| `name` |  | `'crispr'` |
| `version` |  | `'0.0.0-planned'` |
| `kind` |  | `GateKind.CRISPR` |
| `label` |  | `'CRISPR-Cas sgRNA Gate'` |
| `description` |  | `'Transcriptional control · iSBH'` |
| `supported_hosts` | `ClassVar[frozenset[Host]]` | `frozenset({Host.YEAST, Host.HUMAN})` |
| `max_inputs` |  | `1` |
| `available` |  | `False` |

| Status | Method | Purpose |
| --- | --- | --- |
| `BUILT` | `def __init__(self, host: Host, folder: FoldEngine) -> None` |  |
| `BUILT` | `def required_tools(self) -> list[ToolRequirement]` | External tools this family needs, checked before a run starts. |
| `BUILT` | `def is_compatible(self, trigger_set: TriggerSet, constraints: Constraints) -> Compatibility` | Can this family build anything for this trigger set on this host? |
| `STUB` | `def generate_designs(self, trigger_set: TriggerSet, constraints: Constraints) -> Iterator[GateDesign]` | Build a hairpin-blocked sgRNA the trigger unblocks. |
| `STUB` | `def evaluate_design(self, design: GateDesign) -> dict[str, float \| None]` | Measure a guide design, on the same metric names as every other family. |
| `BUILT` | `def emit_sequence(self, design: GateDesign) -> str` | The synthesis-ready sequence. |

### `engine.gates.registry`

`src/engine/gates/registry.py`

Gate family lookup.

| Status | Function | Purpose |
| --- | --- | --- |
| `BUILT` | `def register(family: type[GateFamily]) -> type[GateFamily]` | Make a gate family visible to the pipeline and to the API. |
| `BUILT` | `def get_family(name: str) -> type[GateFamily]` | Look up a family class by name. |
| `BUILT` | `def available_families(host: Host \| None = None) -> list[str]` | Names a submission may legitimately request. |
| `BUILT` | `def describe_families(host: Host \| None = None) -> list[GateFamilyInfo]` | Everything the UI needs to render the mechanism choices. |

### `engine.gates.toehold`

`src/engine/gates/toehold.py`

Toehold switches — single input, and two-input AND.

#### `class ToeholdGate(GateFamily)`

Single-input toehold switch.

| Attribute | Type | Default |
| --- | --- | --- |
| `name` |  | `'toehold'` |
| `version` |  | `'0.1.0-stub'` |
| `kind` |  | `GateKind.TOEHOLD` |
| `label` |  | `'Toehold Riboswitch'` |
| `description` |  | `'Translational control · pre-mRNA'` |
| `supported_hosts` | `ClassVar[frozenset[Host]]` | `frozenset({Host.ECOLI, Host.YEAST, Host.HUMAN})` |
| `max_inputs` |  | `1` |
| `available` |  | `True` |
| `toehold_lengths` | `ClassVar[tuple[int, ...]]` | `(12, 15, 18)` |

| Status | Method | Purpose |
| --- | --- | --- |
| `BUILT` | `def __init__(self, host: Host, folder: FoldEngine, translation: TranslationScorer, codons: CodonOptimizer) -> None` |  |
| `BUILT` | `def required_tools(self) -> list[ToolRequirement]` | External tools this family needs, checked before a run starts. |
| `STUB` | `def is_compatible(self, trigger_set: TriggerSet, constraints: Constraints) -> Compatibility` | Can this family build anything for this trigger set? |
| `STUB` | `def generate_designs(self, trigger_set: TriggerSet, constraints: Constraints) -> Iterator[GateDesign]` | Build candidate switches for one trigger set. |
| `STUB` | `def evaluate_design(self, design: GateDesign) -> dict[str, float \| None]` | Measure one design. |
| `BUILT` | `def emit_sequence(self, design: GateDesign) -> str` | The synthesis-ready sequence. |

#### `class ToeholdAndGate(ToeholdGate)`

Two-input AND toehold.

| Attribute | Type | Default |
| --- | --- | --- |
| `name` |  | `'toehold_and'` |
| `version` |  | `'0.1.0-stub'` |
| `kind` |  | `GateKind.TOEHOLD_AND` |
| `label` |  | `'AND Toehold'` |
| `description` |  | `'Two-input translational AND'` |
| `max_inputs` |  | `2` |

| Status | Method | Purpose |
| --- | --- | --- |
| `STUB` | `def generate_designs(self, trigger_set: TriggerSet, constraints: Constraints) -> Iterator[GateDesign]` | Build a switch that opens only when **both** triggers are present. |

### `engine.gates.notebooks._fixtures`

`src/engine/gates/notebooks/_fixtures.py`

Shared setup for the per-gate notebooks under this folder.

| Status | Function | Purpose |
| --- | --- | --- |
| `BUILT` | `def bootstrap() -> pathlib.Path` | Put ``<repo>/src`` on ``sys.path`` and say where it pointed. |
| `BUILT` | `def fold_engine(real: bool = False, temperature: float = 37.0) -> object` | The folder to hand a gate. |
| `BUILT` | `def sample_trigger(*, trigger_id: str = 'trig-000001', gene_id: str = 'b0002', symbol: str = 'thrA', sequence: str \| None = None, length: int = 36, start_index: int = 120, seed: int = 2026) -> TriggerCandidate` | One made-up :class:`~engine.domain.TriggerCandidate` with plausible values. |
| `BUILT` | `def sample_trigger_set(n_activators: int = 1, n_repressors: int = 0) -> TriggerSet` | A :class:`~engine.domain.TriggerSet` of made-up triggers. |
| `BUILT` | `def sample_constraints(**overrides) -> Constraints` | A :class:`~engine.domain.Constraints` with library defaults; each keyword overrides one field (e.g. ``max_switch_length=160``). |
| `BUILT` | `def sample_design(gate: GateFamily, trigger_set: TriggerSet \| None = None, *, sequence: str \| None = None) -> GateDesign` | A hand-built :class:`~engine.domain.GateDesign` for the output helpers. |
| `BUILT` | `def toehold(host: Host = Host.ECOLI, *, real_fold: bool = False) -> ToeholdGate` | A wired :class:`~engine.gates.toehold.ToeholdGate`. Hosts: ECOLI, YEAST, HUMAN. |
| `BUILT` | `def toehold_and(host: Host = Host.ECOLI, *, real_fold: bool = False) -> ToeholdAndGate` | A wired :class:`~engine.gates.toehold.ToeholdAndGate` (two-input AND). |
| `BUILT` | `def antisense(host: Host = Host.ECOLI, *, payload: str, real_fold: bool = False) -> AntisenseNotGate` | A wired :class:`~engine.gates.antisense.AntisenseNotGate`. |
| `BUILT` | `def crispr(host: Host = Host.HUMAN, *, real_fold: bool = False) -> CrisprGate` | A wired :class:`~engine.gates.crispr.CrisprGate`. Eukaryotic only — hosts YEAST and HUMAN; ECOLI is rejected by ``is_compatible`` with a host-specific message. |
| `BUILT` | `def describe_gate(gate: GateFamily) -> None` | Print a gate's class-level declarations — the contract it advertises before you call anything on it. |
| `BUILT` | `def attempt(label: str, call) -> object \| None` | Run ``call()`` and display the result. |

#### `class StubFoldEngine`

A stand-in for :class:`~engine.gates.tools.folding.FoldEngine`.

| Attribute | Type | Default |
| --- | --- | --- |
| `temperature` |  | `37.0` |

| Status | Method | Purpose |
| --- | --- | --- |
| `BUILT` | `def mfe(self, sequence: str) -> FoldResult` |  |
| `BUILT` | `def partition(self, sequence: str) -> float` |  |
| `BUILT` | `def ensemble_defect(self, sequence: str, target: str) -> float` |  |
| `BUILT` | `def base_pair_probabilities(self, sequence: str) -> list[list[float]]` |  |
| `BUILT` | `def suboptimal(self, sequence: str, delta: float = 2.0) -> list[FoldResult]` |  |
| `BUILT` | `def versions(self) -> dict[str, str]` |  |

## Layer 6 · Stages — the six steps of a run

Stages hold configuration, never accumulated state. Each takes its tools by constructor injection and calls them; a stage that folds, scans or screens by itself has re-forked a rule that exists to be shared.

### `engine.stages`

`src/engine/stages/__init__.py`

The pipeline stages.

*No public symbols — the docstring is the whole file.*

### `engine.stages.circuits`

`src/engine/stages/circuits.py`

Stage 4 — circuit design and scoring.

#### `class CircuitDesigner`

Turn an up/down gene pattern into ranked, buildable circuits.

| Status | Method | Purpose |
| --- | --- | --- |
| `BUILT` | `def __init__(self, evaluator: 'ConfusionEvaluator', max_terms: int = 4) -> None` |  |
| `STUB` | `def design(self, genes: list[SelectedGene], designs: Iterable[GateDesign], counts: CountMatrix) -> Iterator[CircuitCandidate]` | Yield scored circuits, buildable from the switches that exist. |
| `STUB` | `def enumerate_expressions(self, genes: list[SelectedGene]) -> Iterator[BooleanExpression]` | Generate Boolean expressions reproducing the genes' up/down pattern. |

#### `class ConfusionEvaluator`

Scores a circuit by how it behaves on the actual samples.

| Status | Method | Purpose |
| --- | --- | --- |
| `BUILT` | `def __init__(self, off_target: OffTargetScanner) -> None` |  |
| `STUB` | `def evaluate(self, expression: BooleanExpression, counts: CountMatrix, threshold: float) -> ConfusionMatrix` | Run an expression over every sample and tally the four outcomes. |
| `STUB` | `def cross_talk_penalty(self, designs: list[GateDesign]) -> float` | Interference between a circuit's own switches. |

### `engine.stages.folding` · S1

`src/engine/stages/folding.py`

S1 — local accessibility profiling, the primitive behind trigger selection.

#### `class FoldProfiler` · S1

S1 — per-position unpaired probability in *local* folding context.

| Status | Method | Purpose |
| --- | --- | --- |
| `BUILT` | `def __init__(self, window: int = 80, max_span: int = 40, unpaired: int = 10) -> None` |  |
| `STUB` | `def profile(self, sequence: str) -> list[float]` | Unpaired probability at every position of a transcript. |
| `STUB` | `def openness(self, sequence: str, start: int, end: int) -> float` | Mean unpaired probability across a segment. The map's ``Trigger Openness``. |

### `engine.stages.genes`

`src/engine/stages/genes.py`

Stage 1 — gene selection.

#### `class GeneSelector`

Keep the genes that actually separate the two cell states.

| Status | Method | Purpose |
| --- | --- | --- |
| `BUILT` | `def __init__(self, constraints: Constraints, atlas: dict[str, float] \| None = None) -> None` |  |
| `STUB` | `def select(self, counts: CountMatrix, dge: DgeTable) -> list[SelectedGene]` | Filter, score and rank genes; return a shortlist with an up/down call. |

### `engine.stages.motifs` · S7

`src/engine/stages/motifs.py`

S7 — prohibited motif screening.

| Constant | Type | Value |
| --- | --- | --- |
| `RFC10_SITES` | `dict[str, str]` | `{'EcoRI': 'GAATTC', 'XbaI': 'TCTAGA', 'SpeI': 'ACTAGT', 'PstI': 'CTGCAG', 'NotI': 'GCGG…` |
| `RFC1000_SITES` | `dict[str, str]` | `{'BsaI': 'GGTCTC', 'BsaI_rc': 'GAGACC', 'SapI': 'GCTCTTC', 'SapI_rc': 'GAAGAGC'}` |
| `RNASE_SITES` | `dict[str, str]` | `{}` |
| `RBP_MOTIFS` | `dict[str, str]` | `{}` |
| `MAX_HOMOPOLYMER` |  | `5` |

#### `class Violation`

`@dataclass(frozen=True, slots=True)`

One prohibited motif found, and where.

| Attribute | Type | Default |
| --- | --- | --- |
| `motif` | `str` |  |
| `name` | `str` |  |
| `start` | `int` |  |
| `kind` | `str` |  |

#### `class MotifScreener`

Rejects or penalises sequences carrying prohibited motifs.

| Status | Method | Purpose |
| --- | --- | --- |
| `BUILT` | `def __init__(self, standard: AssemblyStandard = AssemblyStandard.RFC10, *, extra_motifs: dict[str, str] \| None = None, max_homopolymer: int = MAX_HOMOPOLYMER) -> None` |  |
| `BUILT` | `def violations(self, sequence: str) -> tuple[Violation, ...]` | Every prohibited motif in this sequence. Empty means compliant. |
| `BUILT` | `def is_compliant(self, sequence: str) -> bool` | True when nothing prohibited is present. A yes/no wrapper over ``violations``. |

### `engine.stages.off_target` · S5

`src/engine/stages/off_target.py`

S5 — off-target scanning, in both directions.

#### `class OffTargetScanner`

Finds near-matches of a sequence in the host transcriptome.

| Status | Method | Purpose |
| --- | --- | --- |
| `BUILT` | `def __init__(self, transcriptome: dict[str, str], max_mismatch: int = 2) -> None` |  |
| `STUB` | `def build_index(self) -> None` | Prepare the search structure. Call once, before any scanning. |
| `STUB` | `def find_similar(self, sequence: str) -> tuple[Hit, ...]` | The primitive. Every method below is interpretation of these hits. |
| `STUB` | `def scan_trigger(self, trigger: str) -> OffTargetReport` | Direction (b) — is this trigger sponged by other transcripts? |
| `STUB` | `def scan_switch(self, binding_site: str) -> OffTargetReport` | Direction (a) — can non-cognate RNA cross-activate this switch? |

### `engine.stages.plasmids`

`src/engine/stages/plasmids.py`

Stage 5 — plasmid construction.

#### `class PlasmidBuilder`

Assembles a circuit onto a backbone and checks it can be built.

| Status | Method | Purpose |
| --- | --- | --- |
| `BUILT` | `def __init__(self, screener: MotifScreener, codons: CodonOptimizer, standard: AssemblyStandard = AssemblyStandard.RFC10, backbone: tuple[Segment, ...] = ()) -> None` |  |
| `STUB` | `def build(self, circuit: CircuitCandidate, outcome: DesiredOutcome) -> PlasmidDesign` | Lay out one circuit as an orderable construct. |
| `STUB` | `def payload_segment(self, outcome: DesiredOutcome) -> Segment` | The coding sequence for the chosen output. |

### `engine.stages.quality` · S15

`src/engine/stages/quality.py`

S15 — input quality control.

#### `class InputQualityCheck`

Validates the uploaded count matrix before the pipeline starts.

| Status | Method | Purpose |
| --- | --- | --- |
| `BUILT` | `def __init__(self, min_samples_per_group: int = 2) -> None` |  |
| `STUB` | `def check(self, counts: CountMatrix, metadata: SampleMetadata) -> QcReport` | Inspect the matrix and report what is wrong with it. |

### `engine.stages.reporting`

`src/engine/stages/reporting.py`

Stage 6 — the compiler's output.

#### `class StructureRenderer`

Figures for structures and circuits.

| Status | Method | Purpose |
| --- | --- | --- |
| `STUB` | `def render_structure(self, design: GateDesign, output_dir: str) -> ArtifactRef` | Draw a switch's predicted secondary structure. |
| `STUB` | `def render_circuit(self, circuit: CircuitCandidate, output_dir: str) -> ArtifactRef` | Draw a circuit's logic diagram. |

#### `class ReportBuilder`

Assembles every artefact a run produces, including the PDF.

| Status | Method | Purpose |
| --- | --- | --- |
| `BUILT` | `def __init__(self, renderer: StructureRenderer) -> None` |  |
| `STUB` | `def build(self, circuits: list[CircuitCandidate], plasmids: list[PlasmidDesign], output_dir: str) -> list[ArtifactRef]` | Write every artefact and return references to them. |

### `engine.stages.switches`

`src/engine/stages/switches.py`

Stage 3 — switch design and validation.

#### `class SwitchDesigner`

Dispatches trigger sets to the gate families that can realise them.

| Status | Method | Purpose |
| --- | --- | --- |
| `BUILT` | `def __init__(self, families: list, validator: 'SwitchValidator', host: Host) -> None` |  |
| `STUB` | `def design(self, triggers: Iterable[TriggerCandidate], constraints: Constraints) -> Iterator[GateDesign]` | Yield validated switch designs. |
| `STUB` | `def build_trigger_sets(self, triggers: Iterable[TriggerCandidate], constraints: Constraints) -> Iterator[TriggerSet]` | Combine individual triggers into the input sets a circuit can use. |

#### `class SwitchValidator`

The hard rules a switch must obey, whichever family produced it.

| Status | Method | Purpose |
| --- | --- | --- |
| `BUILT` | `def __init__(self, folder: FoldEngine, off_target: OffTargetScanner, screener: MotifScreener, translation: TranslationScorer) -> None` |  |
| `STUB` | `def validate(self, design: GateDesign) -> ValidationResult` | Check one design against every hard rule. |

### `engine.stages.triggers`

`src/engine/stages/triggers.py`

Stage 2 — trigger scoring.

#### `class TriggerScorer`

Rank every sub-segment of every selected gene as a possible switch input.

| Status | Method | Purpose |
| --- | --- | --- |
| `BUILT` | `def __init__(self, profiler: FoldProfiler, off_target: OffTargetScanner, screener: MotifScreener) -> None` |  |
| `STUB` | `def score(self, genes: list[SelectedGene], sequences: dict[str, str], constraints: Constraints) -> Iterator[TriggerCandidate]` | Yield ranked trigger candidates across every selected gene. |

## Layer 7 · Top level — contract, errors, composition

`engine.contract` and `engine.client` are the **only** modules Platform code may import. `engine.pipeline` is the single assembly point: tools are constructed there once and passed down.

### `engine`

`src/engine/__init__.py`

*Empty file — no docstring, no public symbols, no re-exports.*

### `engine.artifacts`

`src/engine/artifacts.py`

Writing engine output files.

| Status | Function | Purpose |
| --- | --- | --- |
| `BUILT` | `def sha256_file(path: str \| Path) -> str` | Streaming SHA-256 of a file. Never loads the whole file into memory. |
| `BUILT` | `def sha256_bytes(data: bytes) -> str` | SHA-256 of an in-memory payload, for content already held as bytes. |
| `BUILT` | `def write_artifact(output_dir: str \| Path, name: str, content: str \| bytes, *, kind: str, media_type: str, candidate_ref: str \| None = None) -> ArtifactRef` | Write one artifact and return its reference. |

### `engine.client`

`src/engine/client.py`

The Platform-facing engine interface.

| Constant | Type | Value |
| --- | --- | --- |
| `ProgressFn` |  | `Callable[[int, str], bool]` |

| Status | Function | Purpose |
| --- | --- | --- |
| `BUILT` | `def load_engine(dotted_path: str) -> EngineClient` | Instantiate an engine client from a dotted path, e.g. ``engine.client.MockEngine``. |

#### `class EngineClient(Protocol)`

`@runtime_checkable`

What the Platform depends on. Implementations must be safe to call from a worker.

| Status | Method | Purpose |
| --- | --- | --- |
| `PROTOCOL` | `def run(self, request: JobRequest, on_progress: ProgressFn) -> JobResult` | Execute one job to completion, reporting progress as it goes. |
| `PROTOCOL` | `def capabilities(self) -> EngineCapabilities` | What this engine supports. |

#### `class LocalEngine`

Runs the real scientific pipeline in-process. Step 5.

| Attribute | Type | Default |
| --- | --- | --- |
| `ENGINE_VERSION` |  | `'local-0.1.0-stub'` |

| Status | Method | Purpose |
| --- | --- | --- |
| `BUILT` | `def run(self, request: JobRequest, on_progress: ProgressFn) -> JobResult` | Delegate to the real pipeline. |
| `BUILT` | `def capabilities(self) -> EngineCapabilities` | The families and profiles actually installed in this build. |

#### `class MockEngine`

Deterministic fake science.

| Attribute | Type | Default |
| --- | --- | --- |
| `ENGINE_VERSION` |  | `'mock-1.0.0'` |

| Status | Method | Purpose |
| --- | --- | --- |
| `BUILT` | `def capabilities(self) -> EngineCapabilities` | The same registries the real engine reports, so a mock run configures identically to a real one. |
| `BUILT` | `def run(self, request: JobRequest, on_progress: ProgressFn) -> JobResult` | Run a fake job, deterministically. |

### `engine.contract`

`src/engine/contract.py`

The Platform ⇄ Engine contract.

| Constant | Type | Value |
| --- | --- | --- |
| `SCHEMA_VERSION` |  | `'1'` |
| `HIGHER_BETTER` |  | `'HIGHER_BETTER'` |
| `LOWER_BETTER` |  | `'LOWER_BETTER'` |
| `INPUT_DE` |  | `'de'` |
| `INPUT_DIRECT` |  | `'direct'` |
| `SUCCEEDED` |  | `'succeeded'` |
| `FAILED` |  | `'failed'` |
| `CANCELLED` |  | `'cancelled'` |

#### `class JobRequest`

`@dataclass(frozen=True, slots=True)`

An immutable request for one scientific computation.

| Attribute | Type | Default |
| --- | --- | --- |
| `schema_version` | `str` |  |
| `run_id` | `str` |  |
| `idempotency_key` | `str` |  |
| `input_mode` | `str` |  |
| `input_path` | `str` |  |
| `input_checksum` | `str` |  |
| `trigger_sequence` | `str` |  |
| `organism` | `str` |  |
| `params` | `dict` |  |
| `gate_families` | `list[str]` |  |
| `scoring_profile` | `str` |  |
| `seed` | `int \| None` |  |
| `output_dir` | `str` |  |

| Status | Method | Purpose |
| --- | --- | --- |
| `BUILT` | `@property def is_direct_trigger(self) -> bool` | True when the researcher pasted a sequence instead of uploading a table. |
| `BUILT` | `def mock_options(self) -> dict` | Options consumed by MockEngine. Ignored by every real implementation. |

#### `class GateFamilyInfo`

`@dataclass(frozen=True, slots=True)`

One selectable switch mechanism, as the engine describes itself.

| Attribute | Type | Default |
| --- | --- | --- |
| `name` | `str` |  |
| `label` | `str` |  |
| `description` | `str` |  |
| `available` | `bool` |  |

#### `class EngineCapabilities`

`@dataclass(frozen=True, slots=True)`

What this engine build can do.

| Attribute | Type | Default |
| --- | --- | --- |
| `engine_version` | `str` |  |
| `schema_version` | `str` |  |
| `gate_families` | `list[GateFamilyInfo]` |  |
| `scoring_profiles` | `list[str]` |  |

| Status | Method | Purpose |
| --- | --- | --- |
| `BUILT` | `@property def available_families(self) -> list[str]` | Names the Platform will accept on a submission. |

#### `class MetricValue`

`@dataclass(frozen=True, slots=True)`

One measured property of a candidate, with its scoring metadata preserved.

| Attribute | Type | Default |
| --- | --- | --- |
| `name` | `str` |  |
| `raw_value` | `float \| None` |  |
| `normalized_value` | `float \| None` |  |
| `weight` | `float` |  |
| `direction` | `str` |  |

#### `class ArtifactRef`

`@dataclass(frozen=True, slots=True)`

A file the engine produced, addressed relative to ``JobRequest.output_dir``.

| Attribute | Type | Default |
| --- | --- | --- |
| `kind` | `str` |  |
| `path` | `str` |  |
| `media_type` | `str` |  |
| `checksum_sha256` | `str` |  |
| `candidate_ref` | `str \| None` | `None` |

#### `class CandidateResult`

`@dataclass(frozen=True, slots=True)`

One proposed circuit.

| Attribute | Type | Default |
| --- | --- | --- |
| `ref` | `str` |  |
| `rank` | `int \| None` |  |
| `overall_score` | `float \| None` |  |
| `gate_family` | `str` |  |
| `logic_type` | `str` |  |
| `triggers` | `dict` |  |
| `design` | `dict` |  |
| `summary` | `str` |  |
| `metrics` | `list[MetricValue]` | `field(default_factory=list)` |
| `warnings` | `list[str]` | `field(default_factory=list)` |
| `is_rejected` | `bool` | `False` |
| `rejection_reason` | `str` | `''` |

#### `class JobResult`

`@dataclass(frozen=True, slots=True)`

The versioned result manifest.

| Attribute | Type | Default |
| --- | --- | --- |
| `schema_version` | `str` |  |
| `engine_version` | `str` |  |
| `status` | `str` |  |
| `candidates` | `list[CandidateResult]` | `field(default_factory=list)` |
| `artifacts` | `list[ArtifactRef]` | `field(default_factory=list)` |
| `warnings` | `list[str]` | `field(default_factory=list)` |
| `error` | `str \| None` | `None` |
| `input_checksum` | `str` | `''` |
| `params` | `dict` | `field(default_factory=dict)` |

| Status | Method | Purpose |
| --- | --- | --- |
| `BUILT` | `@property def accepted(self) -> list[CandidateResult]` | Non-rejected candidates, in rank order. |
| `BUILT` | `@property def rejected(self) -> list[CandidateResult]` | Excluded candidates, each carrying its reason. Never silently dropped. |

### `engine.errors`

`src/engine/errors.py`

Engine error hierarchy.

#### `class EngineError(Exception)`

Base class for every engine failure.

#### `class InputValidationError(EngineError)`

The input data is unusable — wrong schema, missing columns, unsupported organism.

#### `class ChecksumMismatchError(EngineError)`

The input file does not match the checksum recorded at submission time.

#### `class UnsupportedGateFamilyError(EngineError)`

A requested gate family is not registered in this engine build.

#### `class ScoringProfileError(EngineError)`

The requested scoring profile is unknown, or its metric set is inconsistent.

#### `class JobCancelled(EngineError)`

Raised internally when a progress callback reports that the run should stop.

### `engine.pipeline`

`src/engine/pipeline.py`

The real scientific pipeline.

| Constant | Type | Value |
| --- | --- | --- |
| `ProgressFn` |  | `Callable[[int, str], bool]` |
| `STAGE_WEIGHTS` | `dict[str, int]` | `{'Validating inputs': 2, 'Selecting genes': 5, 'Scoring triggers': 25, 'Designing switc…` |

| Status | Function | Purpose |
| --- | --- | --- |
| `STUB` | `def build_tools(request: JobRequest, host: Host) -> dict[str, object]` | Construct every tool **once** per run, and hand them back for wiring. |
| `STUB` | `def run_pipeline(request: JobRequest, on_progress: ProgressFn) -> JobResult` | Execute the full pipeline for one job. |

### `engine.store` · S11, S13

`src/engine/store.py`

S11, S13 — provenance and pruning.

#### `class CandidateStore`

Stable IDs, provenance, and a CSV snapshot per stage.

| Status | Method | Purpose |
| --- | --- | --- |
| `BUILT` | `def __init__(self, output_dir: str, run_id: str) -> None` |  |
| `BUILT` | `def mint_id(self, kind: str) -> str` | Allocate a stable, readable identifier. |
| `STUB` | `def snapshot(self, stage: str, records: Sequence[Any]) -> ArtifactRef` | Write what a stage produced, as an inspectable CSV. |
| `STUB` | `def load_snapshot(self, stage: str) -> list[dict]` | Read a snapshot back, to re-run one stage without re-running the pipeline. |

#### `class Objective`

`@dataclass(frozen=True, slots=True)`

One axis of a Pareto comparison.

| Attribute | Type | Default |
| --- | --- | --- |
| `field` | `str` |  |
| `maximize` | `bool` | `True` |

#### `class ParetoFilter` · S13

S13 — keep only the non-dominated candidates.

| Status | Method | Purpose |
| --- | --- | --- |
| `BUILT` | `def __init__(self, objectives: Sequence[Objective]) -> None` |  |
| `STUB` | `def frontier(self, records: Sequence[Any]) -> list[Any]` | Keep only the candidates nothing else beats on every axis. |
| `STUB` | `def top_k(self, records: Sequence[Any], k: int, key: str = 'score') -> list[Any]` | Cap how much passes from one stage to the next. |

---

Generated by `tools/gen_api_surface.py` from `src/engine/`. Regenerate with `uv run python tools/gen_api_surface.py`.
