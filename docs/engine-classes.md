# Engine class reference

> **Reference document.** Derived from *CERNAL Computational Pipeline Map* (24/8/2026)
> in `Design Maps/`, reconciled with what is already built.
> Design principles are in [`engine-design.md`](engine-design.md); this is the concrete
> inventory of stages, records and tools.
> [`engine-map.md`](engine-map.md) shows the same thing as diagrams.

The pipeline map specifies six stages and fifteen shared functions (S1–S15). This names
them conventionally, sorts them into classes, records and functions, and marks what
already exists.

---

## 1. Naming conventions

Applied throughout, so the codebase reads consistently:

| Kind | Convention | Examples |
|---|---|---|
| **Stage** — runs one pipeline step | Agent noun, `*er` / `*or` | `GeneSelector`, `SwitchDesigner` |
| **Record** — data a stage produced | Singular noun | `SelectedGene`, `TriggerCandidate` |
| **Tool** — a scientific primitive | `*Engine`, `*Scanner`, `*Screener` | `FoldEngine`, `OffTargetScanner` |
| **Family** — polymorphic behaviour | The thing itself | `ToeholdGate`, `AntisenseGate` |
| **Enum** | Singular noun, `StrEnum` | `Host`, `GateKind`, `Regulation` |
| Modules, functions, variables | `snake_case` | `local_fold_profile()` |
| Constants | `UPPER_SNAKE` | `MAX_HOMOPOLYMER` |

Two rules worth stating because the source document mixes styles:

- **No possessive or personal names in code.** "Aviv's generator and validation codes"
  becomes `ToeholdGate` plus the shared tools it was refactored into.
- **Records are named for what they *are*, not which CSV they land in.** `TriggerCandidate`,
  not `GlobalTriggerScoringRow`.

---

## 2. The six stages

Each is a class with one public method, taking the previous stage's records and returning
the next. They hold **read-only configuration**, never accumulated state
([engine-design §3](engine-design.md)).

```python
class GeneSelector:
    """Stage 1 — keep the genes that actually separate the two cell states.

    Big enough fold change, statistically significant, and expressed in a usable
    absolute range in both states: too low gives false negatives, too high gives
    false positives.
    """

    def __init__(self, thresholds: GeneThresholds, atlas: CellAtlas | None = None): ...
    def select(self, counts: CountMatrix, dge: DgeTable) -> list[SelectedGene]: ...


class TriggerScorer:
    """Stage 2 — slide a window along each selected gene's transcript and rank every
    sub-segment by how unpaired it is in local folding context, plus off-target load,
    GC and forbidden motifs. Per length-class, because each gate family needs a
    different footprint.
    """

    def __init__(
        self,
        folder: FoldProfiler,
        off_target: OffTargetScanner,
        screener: MotifScreener,
        length_classes: tuple[int, ...],
    ): ...
    def score(
        self, genes: list[SelectedGene], sequences: SequenceLibrary
    ) -> Iterator[TriggerCandidate]: ...


class SwitchDesigner:
    """Stage 3 — for each (trigger x gate kind), run the architecture-specific generator,
    then validate the fold and the hard sequence rules.

    Dispatches to a GateFamily; owns none of the chemistry itself.
    """

    def __init__(self, registry: GateRegistry, validator: SwitchValidator, host: Host): ...
    def design(
        self, triggers: Iterable[TriggerCandidate], constraints: Constraints
    ) -> Iterator[SwitchDesign]: ...


class CircuitDesigner:
    """Stage 4 — turn the genes' up/down pattern into a Boolean function, generate the
    expressions reproducing it, keep only those buildable from switches actually
    designed upstream, and rank by separation versus complexity.
    """

    def __init__(self, evaluator: ConfusionEvaluator, max_terms: int): ...
    def design(
        self, genes: list[SelectedGene], switches: list[SwitchDesign], counts: CountMatrix
    ) -> Iterator[CircuitCandidate]: ...


class PlasmidBuilder:
    """Stage 5 — lay the winning circuit's parts onto a backbone with promoters,
    terminators, effector domains and the output gene; check assembly-standard
    compliance; export an orderable sequence.
    """

    def __init__(
        self, backbone: BackboneSpec, standard: AssemblyStandard, screener: MotifScreener
    ): ...
    def build(self, circuit: CircuitCandidate, outcome: DesiredOutcome) -> PlasmidDesign: ...


class ReportBuilder:
    """Stage 6 — assemble the evidence a user needs in order to decide whether to order
    a plasmid: designs, structures, confusion tables, separation margins, flags, caveats.
    """

    def build(
        self, run: RunContext, circuits: list[CircuitCandidate], plasmids: list[PlasmidDesign]
    ) -> list[ArtifactRef]: ...
```

Plus one that the map calls a footnote and flags as having no home:

```python
class InputQualityCheck:
    """QC (S15) — validate the uploaded matrix before anything runs: distributions,
    PCA, outliers, batch structure.

    The map notes this is 'currently a footnote with no home'. It belongs here, in
    front of GeneSelector, because everything downstream is wasted if the input is
    unusable.
    """

    def check(self, counts: CountMatrix, metadata: SampleMetadata) -> QcReport: ...
```

---

## 3. Records — what each stage produces

Frozen dataclasses. The column lists in the map become fields; the CSVs become *exports*
of these, not the interface between stages ([§6](#6-one-decision-to-settle-candidatestore)).

```python
@dataclass(frozen=True, slots=True)
class SelectedGene:
    """Stage 1 output. Map: 'Selected genes .csv list'."""

    gene_id: str
    symbol: str
    regulation: Regulation  # UP | DOWN
    control_percentile: float
    condition_percentile: float
    condition_specificity: float
    log2_fold_change: float
    p_adj: float
    score: float


@dataclass(frozen=True, slots=True)
class TriggerCandidate:
    """Stage 2 output. Map: 'Global Trigger Scoring .csv list'."""

    trigger_id: str
    gene_id: str
    symbol: str
    start_index: int
    length: int
    sequence: str
    openness: float  # mean unpaired probability (S1)
    mfe: float
    accessibility: float  # local context
    off_target_penalty: float
    segment_specificity: float
    ribosome_occupancy: float | None
    gc_content: float
    aug_indexes: tuple[int, ...]
    stop_indexes: tuple[int, ...]
    score: float


@dataclass(frozen=True, slots=True)
class SwitchDesign:
    """Stage 3 output. Map: 'Switch .csv list' + 'Switch Meta data .csv', merged —
    they describe one thing and splitting them only creates a join."""

    switch_id: str
    trigger_ids: tuple[str, ...]  # 1 or 2 — AND gates take two
    gene_ids: tuple[str, ...]
    gate_kind: GateKind
    host: Host
    sequence: str
    dot_bracket: str
    structure_deviation: float  # ensemble defect vs desired (S4)
    mfe_on: float
    mfe_off: float
    mfe_trigger: float
    binding_site_accessibility: float
    binding_site_off_target: float
    translation_score: float  # codon usage (S8)
    architecture: dict  # stem/loop lengths etc. — family-specific
    score: float


@dataclass(frozen=True, slots=True)
class ConfusionMatrix:
    """The map's confusion table, as a type rather than a docstring.

    Circuit ON/OFF against condition/control samples — the basis of circuit scoring.
    """

    true_positive: int
    false_positive: int
    false_negative: int
    true_negative: int

    @property
    def sensitivity(self) -> float: ...
    @property
    def specificity(self) -> float: ...
    @property
    def separation_margin(self) -> float: ...


@dataclass(frozen=True, slots=True)
class CircuitCandidate:
    """Stage 4 output. Map: 'Circuits scored .csv list'."""

    circuit_id: str
    expression: BooleanExpression
    gene_ids: tuple[str, ...]
    trigger_ids: tuple[str, ...]
    switch_ids: tuple[str, ...]
    confusion: ConfusionMatrix
    complexity: int  # component count — the other Pareto axis
    score: float


@dataclass(frozen=True, slots=True)
class PlasmidDesign:
    """Stage 5 output. Map: appended to the circuits list."""

    plasmid_id: str
    circuit_id: str
    segments: tuple[Segment, ...]
    sequence: str
    standard: AssemblyStandard
    violations: tuple[str, ...]  # empty when compliant

    @property
    def length_bp(self) -> int: ...
```

### Supporting types

```python
@dataclass(frozen=True, slots=True)
class BooleanExpression:
    """A circuit's logic, as a structure rather than a string.

    A parsed form is needed anyway to evaluate it against samples, enumerate
    equivalents, and count complexity — and it renders to the caption the UI shows.
    """

    operator: LogicOperator  # AND | OR | NOT | IDENTITY
    operands: tuple["BooleanExpression | str", ...]

    def evaluate(self, active: frozenset[str]) -> bool: ...
    def complexity(self) -> int: ...
    def render(self) -> str: ...  # "A AND (B OR C) AND NOT D"


@dataclass(frozen=True, slots=True)
class CountMatrix:
    """Map input 2 — RNA-seq counts, with the metadata naming control vs condition."""

    gene_ids: tuple[str, ...]
    samples: tuple[str, ...]
    counts: "np.ndarray"
    metadata: SampleMetadata


@dataclass(frozen=True, slots=True)
class DgeTable:
    """Map input 3 — DESeq2-style results."""

    rows: tuple[DgeRow, ...]


@dataclass(frozen=True, slots=True)
class DgeRow:
    gene_id: str
    symbol: str
    base_mean: float
    log2_fold_change: float
    lfc_se: float
    stat: float
    p_value: float
    p_adj: float
```

### Enums

```python
class Host(StrEnum):
    HUMAN, ECOLI, YEAST


class Track(StrEnum):
    PROKARYOTIC, EUKARYOTIC  # derived from Host


class GateKind(StrEnum):
    TOEHOLD, TOEHOLD_AND, ANTISENSE_NOT, CRISPR


class Regulation(StrEnum):
    UP, DOWN


class LogicOperator(StrEnum):
    AND, OR, NOT, IDENTITY


class AssemblyStandard(StrEnum):
    RFC10, RFC1000


class DesiredOutcome(StrEnum):
    GFP, ANTIBIOTIC, CUSTOM
```

---

## 4. Tools — S1 to S9

The map's shared functions. Each is a **class only where it holds configuration**;
otherwise a module of pure functions. All live under `engine/tools/`.

| Map | Class / module | Shape | Notes |
|---|---|---|---|
| **S1** LocalFoldProfile | `FoldProfiler` | class | Holds `W`, `L`, `u`. `profile(seq) -> np.ndarray`, `openness(seq, start, end) -> float` |
| **S2** FoldEngine | `FoldEngine` | class | Adapter over ViennaRNA. `mfe`, `partition`, `ensemble_defect`, `bppm`, `subopt`. **Cache here** |
| **S3** HybridizationEnergy | `hybridization_energy()` | function | `ΔG_bind = G_complex − (G_switch + G_trigger)`. Stateless |
| **S4** StructureMatch | `structure_match()` | function | `(dot_bracket, target) -> StructureMatch` with `deviation`, `p_target_fold` |
| **S5** OffTargetScan | `OffTargetScanner` | class | Holds the transcriptome and `max_mismatch`. **Both directions**: switch cross-activated, and trigger sponged |
| **S6** SequenceUtils | `sequences.py` | module | `reverse_complement`, `translate`, `find_stops`, `find_augs`, `gc_content`, `longest_homopolymer` |
| **S7** MotifScreen | `MotifScreener` | class | Holds the motif sets. RFC10/RFC1000 sites, RBP motifs, RNase sites, homopolymers > 5 nt |
| **S8** CodonTools | `CodonOptimizer` | class | Holds the organism's usage table. Synonymous search + translation scoring |
| **S9** TranslationInitiationScore | `TranslationScorer` | class | Holds host. RBS strength (prokaryotic) or Kozak match (eukaryotic), plus the downstream ramp check |

```python
class FoldEngine:
    """S2 — the single entry point to ViennaRNA. Nothing else imports RNA.

    Every result is cached: the same subsequence recurs constantly across designs,
    and folding it twice is pure waste.
    """

    def mfe(self, seq: str) -> FoldResult: ...
    def partition(self, seq: str) -> PartitionResult: ...
    def ensemble_defect(self, seq: str, target: str) -> float: ...
    def base_pair_probabilities(self, seq: str) -> "np.ndarray": ...
    def suboptimal(self, seq: str, delta: float) -> list[FoldResult]: ...
    def versions(self) -> dict[str, str]: ...  # recorded on every run


class OffTargetScanner:
    """S5 — both directions, as the toehold spec requires.

    (a) switch cross-activated by non-cognate RNA  -> leak, false positive
    (b) trigger sponged by non-cognate RNA         -> weak ON, false negative
    """

    def scan_switch(self, switch: str) -> OffTargetReport: ...
    def scan_trigger(self, trigger: str) -> OffTargetReport: ...
```

---

## 4a. What makes something a "tool"

A fair question, since the term is doing a lot of work above.

> **A tool is an ordinary class.** What makes it a *tool* is only that it is a
> scientific primitive with no opinion about why you are calling it — so stages and
> gates **use** one rather than inheriting from it.

`FoldEngine` does not know what a toehold is. `OffTargetScanner` does not know what a
trigger is. They take sequences and return facts, the way `sha256()` takes bytes and
returns a digest.

**The test:** does it need to know which stage called it? If yes, it is not a tool — it
is stage logic that leaked into the wrong place.

### The worked example: `OffTargetScanner` in three places

The reasonable objection is that off-target analysis surely means *different code* for a
trigger than for a circuit. That is half right, and the half that differs is the important
part.

**What is genuinely shared** is one hard problem: *given a sequence, find near-matches in
the transcriptome, tolerating mismatches.* That needs an index, a mismatch model, and a
consistent penalty scale. It is fiddly, slow to get right, and identical in all three
places.

**What differs** is which sequence you hand it and what the hits mean — and that lives in
the stage, not the tool.

```python
class OffTargetScanner:
    """S5 — the transcriptome search. No opinion about why you are asking."""

    def __init__(self, transcriptome: SequenceLibrary, max_mismatch: int): ...

    def find_similar(self, sequence: str) -> list[Hit]:
        """The primitive. Everything below is interpretation of these hits."""

    def scan_trigger(self, trigger: str) -> OffTargetReport:
        """Direction (b): is this trigger sponged by non-cognate RNA?
        Consequence: weak ON, false negative."""

    def scan_switch(self, binding_site: str) -> OffTargetReport:
        """Direction (a): can non-cognate RNA cross-activate this switch?
        Consequence: leak, false positive."""
```

Both directions are in the pipeline map's S5 spec, and they are two questions about the
same search — not two searches.

| Caller | Asks | Passes | Does with the answer |
|---|---|---|---|
| `TriggerScorer` | Will this segment be sponged? | The candidate trigger | Feeds `off_target_penalty` on `TriggerCandidate`; drops the worst before switches are designed |
| `SwitchValidator` | Can the wrong RNA open this switch? | The switch's **binding site**, not the whole switch | Feeds `binding_site_off_target` on `SwitchDesign` |
| `CircuitDesigner` | Do this circuit's own parts interfere? | Each trigger against the circuit's *other* switches | Cross-talk penalty; feeds the confusion matrix's false-positive count |

Three different questions, three different interpretations, three different fields on
three different records — over **one** transcriptome index.

> **A correction to the diagram in [engine-map.md](engine-map.md):** `CircuitDesigner`
> should not re-scan the transcriptome. Per-trigger and per-switch penalties are already
> computed and stored upstream; the only genuinely new search is cross-talk *within* the
> circuit's own components. Re-scanning would be both slow and inconsistent with the
> numbers already recorded.

### What happens if you do not share it

This is the failure the pipeline map is guarding against when it says Aviv's code should
be *"refactored into S1–S9 rather than copied per gate"*:

- **Three transcriptome indexes**, built three times, in memory at once.
- **Three mismatch conventions.** Does "2 mismatches" include indels? Each copy answers
  differently, and nobody notices.
- **Three penalty scales.** Now a trigger's off-target number and a switch's off-target
  number are not comparable — and `scoring` normalises both onto one axis as though they
  were. The ranking becomes quietly wrong.
- **A bug fixed once, in one of three places.**

The same argument holds for `FoldEngine`: every generator and every validator folds
sequences, and if each carries its own ViennaRNA parameters, two designs scored on
different days are not comparable.

### Which of the fifteen are really tools

Applying the test — *does it need to know its caller?*

| Genuinely tools | Not tools |
|---|---|
| S1 `FoldProfiler`, S2 `FoldEngine`, S3 `hybridization_energy`, S4 `structure_match`, S5 `OffTargetScanner`, S6 `sequences`, S7 `MotifScreener`, S8 `CodonOptimizer`, S9 `TranslationScorer` | S10 `scoring` — a **layer**, applied once at the end of each stage |
| | S11 `CandidateStore` — **infrastructure**, not science |
| | S12/S13 filters — **policy**, configured per stage |
| | S14 `ReportBuilder` — a **stage** |
| | S15 QC — a **stage** |

Calling all fifteen "shared functions" flattens a real distinction. Only the first row
belongs in `engine/tools/`.

---

## 5. What already exists

Four of the map's items are built and tested. Worth knowing before anyone writes them
again.

| Map | Status | Where |
|---|---|---|
| **S10** ScoreNormalizer + Aggregator | ✅ **Built** | `engine/scoring/normalize.py` — `normalize_value`, `build_metrics`, `weighted_score`, `failed_filter`, `rank_candidates`. The map calls this "currently unowned and load-bearing"; it is neither |
| **S12** FilterEngine | ✅ Partly | `ScoringProfile.hard_filters` + `failed_filter` are declarative per-metric filters. Sequence-level filters (S7) are separate |
| **S13** TopKSelector / ParetoFilter | ⚠️ Half | `rank_candidates` ranks; **Pareto filtering across score-versus-complexity is not built** |
| Gate dispatch | ✅ Built | `GateFamily` ABC + `GateRegistry`. The map's "Dispatch to the track/gate-specific Generator" is exactly this |
| Rejection with reasons | ✅ Built | Enforced by a database constraint on import, not merely by convention |
| Metric normalization contract | ✅ Built | `MetricSpec` with direction, weight, valid range, missing behaviour |

**S10 in particular closes a blocker the map lists as open.** The comparability problem —
mapping heterogeneous raw metrics onto one scale so gate families can be ranked together —
is solved, tested, and already rendering in the UI.

---

## 6. One decision to settle: `CandidateStore`

The map says:

> *CandidateStore owns all persisted inter-stage data (CSV + provenance); every stage
> reads its input and writes its output through it — no stage passes objects directly to
> a non-adjacent stage.*

That is two ideas, and they should be separated because only one of them is free.

**Worth keeping.** Every stage writing an inspectable CSV with stable IDs and provenance
is genuinely valuable: the scientific team can open stage 2's output in Excel, a run is
auditable, and a stage can be re-run from saved input while it is being developed.

**Worth reconsidering.** Making CSV the *only* interface between stages costs real things:

| Cost | Why it bites |
|---|---|
| No streaming | Stage 3 cannot start until stage 2 has written every row. Memory and time both suffer at 100k designs |
| Types are lost | Every read re-parses strings into floats, and a typo in a column name fails at runtime rather than in the type checker |
| Slow | Serialising and re-parsing hundreds of thousands of rows, repeatedly |
| More code | Every record needs a writer, a reader and a schema, in addition to the record itself |

**Recommendation: typed objects between stages, CSV snapshots at stage boundaries.**

```python
class CandidateStore:
    """S11 — stable IDs, provenance, and an inspectable snapshot per stage.

    A recorder, not a bus. Stages pass typed records to each other directly; the store
    writes what passed through, so a run stays auditable without forcing every stage
    to serialise.
    """

    def mint_id(self, kind: str) -> str: ...
    def snapshot(self, stage: str, records: Sequence[Any]) -> ArtifactRef: ...
    def load_snapshot(self, stage: str) -> list[dict]: ...  # for re-running a stage
```

You keep debuggability, provenance and re-runnability; you lose nothing except the
constraint that made streaming impossible. **This is a team decision, not mine** — but it
should be made deliberately, because it is hard to reverse once thirteen stages depend on it.

---

## 7. A dimension the earlier design missed

The map specifies gate availability **per host track**:

> *Prokaryotic: toeholds (1 input, 2 input AND), antisense NOT.*
> *Eukaryotic: toeholds (1 input, 2 input AND), antisense NOT, CRISPR (1 input).*

So availability is a function of `(gate kind, host)` — not a single `available` flag as
`GateFamilyInfo` currently has. CRISPR is available in yeast and human but not *E. coli*.

```python
class GateFamily(ABC):
    name: ClassVar[str]
    supported_hosts: ClassVar[frozenset[Host]]  # NEW
    max_inputs: ClassVar[int]  # NEW — 1 for CRISPR, 2 for AND
```

That flows all the way out: `EngineCapabilities` should report families **per host**, so
the wizard greys out CRISPR when *E. coli* is selected rather than accepting a submission
that cannot be built. A small contract change, and much better than failing at run time.

Also from the map, and currently unmodelled: **"2 inputs can be of the same gene or
trigger."** Two triggers from one gene is a legitimate AND design, so `TriggerSet` must not
deduplicate by gene.

---

## 8. Full mapping

| Map item | Class / module | Status |
|---|---|---|
| User inputs 1–4 | `CountMatrix`, `DgeTable`, `Host`, `DesiredOutcome` | ★ |
| Supporting databases 5–8 | `CodonUsageTable`, `SequenceLibrary`, `CellAtlas`, `BackboneSpec` | ★ |
| QC (S15) | `InputQualityCheck` | ★ |
| Gene Selection | `GeneSelector` → `SelectedGene` | ★ |
| Initial Trigger Scoring | `TriggerScorer` → `TriggerCandidate` | ★ |
| Switches Design | `SwitchDesigner` → `SwitchDesign` | ★ (dispatch built) |
| Circuit Design | `CircuitDesigner` → `CircuitCandidate`, `ConfusionMatrix`, `BooleanExpression` | ★ |
| Plasmid Construction | `PlasmidBuilder` → `PlasmidDesign` | ★ |
| Compiler's Output | `ReportBuilder` | ★ |
| S1 LocalFoldProfile | `FoldProfiler` | ★ |
| S2 FoldEngine | `FoldEngine` | ★ |
| S3 HybridizationEnergy | `hybridization_energy()` | ★ |
| S4 StructureMatch | `structure_match()` | ★ |
| S5 OffTargetScan | `OffTargetScanner` | ★ |
| S6 SequenceUtils | `tools/sequences.py` | ★ |
| S7 MotifScreen | `MotifScreener` | ★ |
| S8 CodonTools | `CodonOptimizer` | ★ |
| S9 TranslationInitiationScore | `TranslationScorer` | ★ |
| **S10 ScoreNormalizer** | `engine/scoring/` | ✅ **built** |
| S11 CandidateStore | `CandidateStore` | ★ — see §6 |
| S12 FilterEngine | `ScoringProfile` + `MotifScreener` | ✅ partly |
| S13 TopK / Pareto | `rank_candidates` + `ParetoFilter` | ⚠️ Pareto missing |
| S14 StructureViz + Report | `StructureRenderer`, `ReportBuilder` | ★ |
| "Aviv's generator and validation codes" | `ToeholdGate` + `SwitchValidator` + S1–S9 | ★ — refactor, do not copy per gate |

---

## 9. Where they live

```
src/engine/
├── domain/
│   ├── inputs.py      CountMatrix · DgeTable · DgeRow · SampleMetadata
│   ├── records.py     SelectedGene · TriggerCandidate · SwitchDesign ·
│   │                  CircuitCandidate · PlasmidDesign · ConfusionMatrix
│   ├── logic.py       BooleanExpression · LogicOperator
│   └── enums.py       Host · Track · GateKind · Regulation · AssemblyStandard
├── tools/
│   ├── folding.py     FoldEngine (S2) · FoldProfiler (S1) · structure_match (S4)
│   ├── binding.py     hybridization_energy (S3)
│   ├── off_target.py  OffTargetScanner (S5)
│   ├── sequences.py   S6
│   ├── motifs.py      MotifScreener (S7)
│   ├── codons.py      CodonOptimizer (S8)
│   └── translation.py TranslationScorer (S9)
├── gates/             GateFamily ABC · registry · toehold · antisense · crispr
├── scoring/           ✅ S10 — already built
├── stages/
│   ├── quality.py     InputQualityCheck (S15)
│   ├── genes.py       GeneSelector
│   ├── triggers.py    TriggerScorer
│   ├── switches.py    SwitchDesigner · SwitchValidator
│   ├── circuits.py    CircuitDesigner · ConfusionEvaluator
│   ├── plasmids.py    PlasmidBuilder
│   └── reporting.py   ReportBuilder · StructureRenderer (S14)
├── store.py           CandidateStore (S11) · ParetoFilter (S13)
└── pipeline/          composition only — calls the stages in order
```

`engine/pipeline/stages.py`'s thirteen stubs become thin wrappers that instantiate a stage
class and call it, so the map's vocabulary and the code's structure stay aligned.

---

## 10. Build order

Bottom-up, because every stage depends on the tools.

| # | Build | Unblocks |
|---|---|---|
| 1 | `domain/` — records and enums | Everything. Pure software, start now |
| 2 | `tools/sequences.py` (S6), `motifs.py` (S7) | No ViennaRNA needed; testable immediately |
| 3 | `tools/folding.py` (S1, S2, S4) | Every generator and validator |
| 4 | `GeneSelector` + `InputQualityCheck` | First real output from real data |
| 5 | `TriggerScorer` | **Blocked on where gene sequences come from** |
| 6 | `ToeholdGate` + `SwitchValidator` | The science proper |
| 7 | `CircuitDesigner` + `ConfusionMatrix` | Scoring circuits, not just switches |
| 8 | `PlasmidBuilder`, `ReportBuilder` | Orderable output |

Items 1 and 2 need no scientific input and no dependencies. **Item 5 is where the open
question bites** — the map lists "Gene sequences database – maybe depends on the .fasta
files" as unresolved, which is the same gap flagged in
[step-5 §10](step-5-engine-plan.md) question 1.
