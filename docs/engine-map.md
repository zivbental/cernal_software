# Engine map

> Visual companion to [`engine-classes.md`](engine-classes.md) (what each class is) and
> [`engine-design.md`](engine-design.md) (why it is shaped that way).
>
> Diagrams are Mermaid — they render in GitHub, in VS Code with a Markdown preview, and
> in Obsidian.

**Legend used throughout:** green = built and tested · amber = partly built ·
grey = to build in Step 5.

---

## 1. The whole system

Where the engine sits, and what the boundary actually separates.

```mermaid
flowchart TB
    subgraph browser["Browser"]
        SPA["React SPA<br/>wizard · progress · results"]
    end

    subgraph platform["CERNAL Platform — Django"]
        API["api/<br/>24 endpoints"]
        SVC["apps/analyses/services.py<br/>run state machine"]
        DB[("SQLite<br/>8 models")]
        WORKER["django-q2 worker"]
    end

    SEAM{{"engine.contract + engine.client<br/>THE BOUNDARY"}}

    subgraph engine["CERNAL Engine — no Django"]
        PIPE["pipeline/<br/>6 stages"]
        GATES["gates/<br/>GateFamily"]
        TOOLS["tools/<br/>S1–S9"]
        SCORE["scoring/<br/>S10"]
    end

    SPA -->|"HTTPS /api/"| API
    API --> SVC
    SVC --> DB
    SVC -->|"enqueue"| WORKER
    WORKER --> SEAM
    SEAM --> PIPE
    PIPE --> GATES
    PIPE --> TOOLS
    PIPE --> SCORE
    GATES --> TOOLS
    SEAM -.->|"JobResult"| SVC

    classDef built fill:#dcfce7,stroke:#15803d,color:#14532d
    classDef todo fill:#f4f4f5,stroke:#a1a1aa,color:#3f3f46
    classDef seam fill:#fef3c7,stroke:#b45309,color:#78350f
    class SPA,API,SVC,DB,WORKER,SCORE built
    class PIPE,GATES,TOOLS todo
    class SEAM seam
```

Everything green is done. **The engine is the remaining work**, and the boundary is what
lets it be done without touching anything above it.

---

## 2. The pipeline

Six stages, and the record each one produces. Read left to right.

```mermaid
flowchart LR
    IN1[/"RNA-seq counts<br/>.csv"/]
    IN2[/"DGE results<br/>.csv"/]
    IN3[/"Organism<br/>+ desired outcome"/]

    QC["InputQualityCheck<br/><i>S15</i>"]
    GS["GeneSelector"]
    TS["TriggerScorer"]
    SD["SwitchDesigner"]
    CD["CircuitDesigner"]
    PB["PlasmidBuilder"]
    RB["ReportBuilder"]

    R1(["SelectedGene[]"])
    R2(["TriggerCandidate[]"])
    R3(["SwitchDesign[]"])
    R4(["CircuitCandidate[]"])
    R5(["PlasmidDesign[]"])
    OUT[/"JobResult<br/>+ artifacts + PDF"/]

    IN1 --> QC --> GS
    IN2 --> GS
    IN3 --> SD
    GS --> R1 --> TS --> R2 --> SD --> R3 --> CD --> R4 --> PB --> R5 --> RB --> OUT
    R1 -.-> CD
    R2 -.-> CD
    R1 -.-> PB

    classDef stage fill:#f4f4f5,stroke:#71717a,color:#27272a
    classDef record fill:#e0e7ff,stroke:#4f46e5,color:#1e1b4b
    classDef io fill:#fff7ed,stroke:#c2410c,color:#7c2d12
    class QC,GS,TS,SD,CD,PB,RB stage
    class R1,R2,R3,R4,R5 record
    class IN1,IN2,IN3,OUT io
```

Dotted lines are the map's "inputs [12] [15]" — later stages reading earlier records
directly, not only their immediate predecessor.

**The pruning point is `TriggerScorer` → `SwitchDesigner`.** Everything downstream scales
with how many trigger candidates survive, which is why that filter sets the compute budget
([step-5 §3](step-5-engine-plan.md)).

---

## 3. Which stage uses which tool

The S1–S9 dependency map. This is the diagram that shows why the tools are worth building
first.

```mermaid
flowchart LR
    subgraph tools["engine/tools/ — shared primitives"]
        S1["FoldProfiler<br/><i>S1 · openness</i>"]
        S2["FoldEngine<br/><i>S2 · MFE, ensemble</i>"]
        S3["hybridization_energy<br/><i>S3</i>"]
        S4["structure_match<br/><i>S4</i>"]
        S5["OffTargetScanner<br/><i>S5</i>"]
        S6["sequences<br/><i>S6</i>"]
        S7["MotifScreener<br/><i>S7</i>"]
        S8["CodonOptimizer<br/><i>S8</i>"]
        S9["TranslationScorer<br/><i>S9</i>"]
    end

    TS["TriggerScorer"]
    GEN["GateFamily<br/>generators"]
    VAL["SwitchValidator"]
    CD["CircuitDesigner"]
    PB["PlasmidBuilder"]
    SC["scoring<br/><i>S10</i>"]

    TS --> S1 & S5 & S6 & S7
    GEN --> S2 & S3 & S6 & S8
    VAL --> S2 & S4 & S5 & S6 & S7 & S9
    CD -->|"cross-talk only"| S5
    PB --> S7 & S8
    TS --> SC
    VAL --> SC
    CD --> SC

    classDef tool fill:#f4f4f5,stroke:#71717a,color:#27272a
    classDef built fill:#dcfce7,stroke:#15803d,color:#14532d
    classDef user fill:#e0e7ff,stroke:#4f46e5,color:#1e1b4b
    class S1,S2,S3,S4,S5,S6,S7,S8,S9 tool
    class SC built
    class TS,GEN,VAL,CD,PB user
```

`FoldEngine` (S2) and `sequences` (S6) are used by nearly everything — build them first
and well. `scoring` (S10) is already done, and every stage that ranks anything goes
through it.

A tool takes sequences and returns facts; it never knows which stage called it. What
differs between callers is the *question* and the *interpretation*, and both live in the
stage — see [engine-classes §4a](engine-classes.md). `CircuitDesigner` is the one
qualified arrow: it reuses the off-target penalties already stored upstream and only
searches for cross-talk between a circuit's own components.

---

## 3a. Classes and methods

Two kinds of arrow, and the difference between them is the whole answer to "why not put
shared methods on the base class":

- **`<|--` inheritance** — *"a toehold **is** a gate"*. Points up to the base.
- **`o--` composition** — *"a toehold **uses** folding"*. Points sideways to a tool.

### Gate families

```mermaid
classDiagram
    class GateFamily {
        <<abstract>>
        +str name
        +str version
        +frozenset supported_hosts
        +int max_inputs
        +is_compatible(trigger_set, constraints) Compatibility
        +generate_designs(trigger_set, constraints) Iterator
        +evaluate_design(design) dict
        +emit_sequence(design) str
        +describe(design, metrics) str
    }

    class ToeholdGate {
        +Host host
        +generate_designs() Iterator
        +evaluate_design() dict
        -_build_switch(trigger, toehold_len) str
    }

    class ToeholdAndGate {
        +generate_designs() Iterator
        -_interleave(trigger_a, trigger_b) str
    }

    class AntisenseNotGate {
        +generate_designs() Iterator
        +evaluate_design() dict
    }

    class CrisprGate {
        +frozenset supported_hosts
        +generate_designs() Iterator
    }

    class FoldEngine {
        +mfe(seq) FoldResult
        +partition(seq) PartitionResult
        +ensemble_defect(seq, target) float
        +versions() dict
    }

    class TranslationScorer {
        +Host host
        +score(seq) float
    }

    class CodonOptimizer {
        +CodonUsageTable table
        +variants(cds) list
        +translation_score(cds) float
    }

    GateFamily <|-- ToeholdGate
    ToeholdGate <|-- ToeholdAndGate
    GateFamily <|-- AntisenseNotGate
    GateFamily <|-- CrisprGate

    ToeholdGate o-- FoldEngine
    ToeholdGate o-- TranslationScorer
    ToeholdGate o-- CodonOptimizer
    AntisenseNotGate o-- FoldEngine
    CrisprGate o-- FoldEngine
```

`FoldEngine` sits to the side because `TriggerScorer` needs it too, and a trigger scorer
is not a gate. Everything gate-specific — `describe`, the ABC's contract — lives on
`GateFamily`, exactly as expected.

### A stage in detail

The same pattern one level up. `SwitchDesigner` **is** nothing; it **uses** everything.

```mermaid
classDiagram
    class SwitchDesigner {
        +GateRegistry registry
        +Host host
        +design(triggers, constraints) Iterator
        -_dispatch(trigger_set) GateFamily
    }

    class SwitchValidator {
        +validate(design) ValidationResult
        -_check_structure(design) float
        -_check_sequence_rules(design) list
    }

    class GateRegistry {
        +register(family) type
        +get_family(name) type
        +available_families(host) list
        +describe_families() list
    }

    class FoldEngine {
        +mfe(seq) FoldResult
        +ensemble_defect(seq, target) float
    }

    class OffTargetScanner {
        +SequenceLibrary transcriptome
        +int max_mismatch
        +find_similar(seq) list
        +scan_trigger(trigger) OffTargetReport
        +scan_switch(binding_site) OffTargetReport
    }

    class MotifScreener {
        +violations(seq) list
    }

    SwitchDesigner o-- GateRegistry
    SwitchDesigner o-- SwitchValidator
    SwitchValidator o-- FoldEngine
    SwitchValidator o-- OffTargetScanner
    SwitchValidator o-- MotifScreener
```

### Who holds which tool

The whole composition picture. Every arrow is "holds an instance of", and each tool is
constructed **once** per run and passed in.

```mermaid
flowchart LR
    subgraph stages["Stages"]
        GS["GeneSelector"]
        TS["TriggerScorer"]
        SD["SwitchDesigner"]
        SV["SwitchValidator"]
        CD["CircuitDesigner"]
        PB["PlasmidBuilder"]
    end

    subgraph fams["Gate families"]
        TG["ToeholdGate"]
        AG["AntisenseNotGate"]
        CG["CrisprGate"]
    end

    subgraph tools["Tools — constructed once, shared"]
        FE["FoldEngine"]
        FP["FoldProfiler"]
        OT["OffTargetScanner"]
        MS["MotifScreener"]
        CO["CodonOptimizer"]
        TR["TranslationScorer"]
        SQ["sequences<br/><i>module, no state</i>"]
    end

    TS --> FP & OT & MS & SQ
    SD --> TG & AG & CG
    SV --> FE & OT & MS & TR
    TG & AG & CG --> FE
    TG --> CO & TR
    CD --> OT
    PB --> MS & CO
    GS --> SQ

    classDef s fill:#e0e7ff,stroke:#4f46e5,color:#1e1b4b
    classDef f fill:#fef3c7,stroke:#b45309,color:#78350f
    classDef t fill:#f4f4f5,stroke:#71717a,color:#27272a
    class GS,TS,SD,SV,CD,PB s
    class TG,AG,CG f
    class FE,FP,OT,MS,CO,TR,SQ t
```

**`FoldEngine` is constructed once per run**, so its cache is shared across every stage
and every family. Construct it inside each class instead and you get four caches, four
sets of ViennaRNA parameters, and scores that are not comparable.

```python
# engine/pipeline.py — wire the tools once, hand them down
def run_pipeline(request, on_progress):
    folder   = FoldEngine()
    profiler = FoldProfiler(window=80, max_span=40, unpaired=10)
    off      = OffTargetScanner(transcriptome, max_mismatch=2)
    screener = MotifScreener(standard=AssemblyStandard.RFC10)

    triggers = TriggerScorer(profiler, off, screener).score(genes, sequences)
    switches = SwitchDesigner(registry, SwitchValidator(folder, off, screener)).design(...)
```

That function is the only place that knows how the pieces fit together. Everything else
receives what it needs.

---

## 3b. Where the code lives

Yes — **everything under `src/engine/`**. Not one file, and not one file per class either.

> **A module is a topic, not a class.** Related classes live together: `ToeholdGate` and
> `ToeholdAndGate` share `toehold.py`; `SwitchDesigner` and `SwitchValidator` share
> `switches.py`.

```
src/engine/
├── contract.py        crosses the boundary          ~200 lines   ✅ built
├── client.py          MockEngine · LocalEngine      ~350         ✅ built
├── errors.py          the exception hierarchy       ~40          ✅ built
├── domain.py          ALL records + enums           ~300         ★ start here
├── pipeline.py        run_pipeline — wiring only    ~80          ★
├── store.py           CandidateStore · ParetoFilter ~150         ★
│
├── tools/
│   ├── folding.py     FoldEngine · FoldProfiler · structure_match   S1 S2 S4
│   ├── binding.py     hybridization_energy                          S3
│   ├── off_target.py  OffTargetScanner                              S5
│   ├── sequences.py   pure functions, no class                      S6
│   ├── motifs.py      MotifScreener                                 S7
│   ├── codons.py      CodonOptimizer                                S8
│   └── translation.py TranslationScorer                             S9
│
├── gates/
│   ├── base.py        GateFamily ABC                ✅ built
│   ├── registry.py    GateRegistry                  ✅ built
│   ├── toehold.py     ToeholdGate + ToeholdAndGate  ★
│   ├── antisense.py   AntisenseNotGate              ★
│   └── crispr.py      CrisprGate                    ★
│
├── scoring/           ✅ built and tested — S10
│   ├── profiles.py    MetricSpec · HardFilter · ScoringProfile
│   └── normalize.py   normalize · weighted_score · rank
│
├── stages/
│   ├── quality.py     InputQualityCheck             S15
│   ├── genes.py       GeneSelector
│   ├── triggers.py    TriggerScorer
│   ├── switches.py    SwitchDesigner + SwitchValidator
│   ├── circuits.py    CircuitDesigner + ConfusionEvaluator
│   ├── plasmids.py    PlasmidBuilder
│   └── reporting.py   ReportBuilder + StructureRenderer   S14
│
└── runner/
    └── gcs_entry.py   container entrypoint
```

### Why these groupings

| Choice | Reason |
|---|---|
| **`domain.py` as one file** | Records reference each other constantly. Splitting them early invites circular imports. Split into a `domain/` package when it passes ~400 lines, not before |
| **`tools/` by scientific topic** | `folding.py` holds S1, S2 and S4 because they all wrap ViennaRNA and share its cache. Splitting them would mean three modules importing `RNA` |
| **One module per gate chemistry** | A new family is a new file plus one `register()` call. Nothing else changes |
| **`stages/` mirrors the pipeline map** | Someone reading the map can find the code by name |
| **`pipeline.py` is one flat file** | It only wires things together. If it grows past ~150 lines, logic has leaked into it |

### The import rule

Dependencies point **downward only**, which is what keeps any of it testable in isolation:

```
runner  →  pipeline  →  stages  →  gates  →  tools  →  domain
                            ↘  scoring  ↗
```

`tools/` imports nothing but `domain` and its scientific library. `domain` imports
nothing at all. So a tool can be tested with no pipeline, and a stage tested with fake
tools.

**Nothing imports upward.** A tool that needs to know which stage called it is the
signal something is in the wrong place.

---

## 4. Gate families

The one real class hierarchy, and the host constraint the pipeline map specifies.

```mermaid
flowchart TB
    ABC["GateFamily <i>(ABC)</i><br/>is_compatible · generate_designs<br/>evaluate_design · emit_sequence"]

    T1["ToeholdGate<br/>1 input"]
    T2["ToeholdAndGate<br/>2 inputs"]
    AN["AntisenseNotGate<br/>1 input, inverting"]
    CR["CrisprGate<br/>1 input"]

    REG["GateRegistry<br/>name → class"]
    PRO(["Prokaryotic<br/><i>E. coli</i>"])
    EUK(["Eukaryotic<br/><i>yeast · human</i>"])

    ABC --> T1 & T2 & AN & CR
    REG --> ABC
    T1 & T2 & AN --> PRO
    T1 & T2 & AN & CR --> EUK

    classDef abc fill:#fef3c7,stroke:#b45309,color:#78350f
    classDef fam fill:#f4f4f5,stroke:#71717a,color:#27272a
    classDef built fill:#dcfce7,stroke:#15803d,color:#14532d
    classDef host fill:#e0e7ff,stroke:#4f46e5,color:#1e1b4b
    class ABC abc
    class T1,T2,AN,CR fam
    class REG built
    class PRO,EUK host
```

**CRISPR is eukaryotic only.** That is why `GateFamily` needs `supported_hosts` rather
than a single `available` flag, and why capabilities should be reported per host — so the
wizard greys CRISPR out when *E. coli* is selected ([engine-classes §7](engine-classes.md)).

---

## 5. Types, and what crosses the boundary

```mermaid
flowchart TB
    subgraph internal["Internal to the engine — change freely"]
        direction TB
        CM["CountMatrix<br/>DgeTable"]
        SG["SelectedGene"]
        TC["TriggerCandidate"]
        TSET["TriggerSet"]
        SW["SwitchDesign"]
        BE["BooleanExpression"]
        CONF["ConfusionMatrix"]
        CC["CircuitCandidate"]
        PD["PlasmidDesign"]
    end

    subgraph contract["engine/contract.py — change deliberately"]
        direction TB
        JREQ["JobRequest"]
        CR2["CandidateResult"]
        MV["MetricValue"]
        AR["ArtifactRef"]
        JRES["JobResult"]
    end

    subgraph plat["Platform — never sees the left column"]
        MODELS[("Candidate<br/>CandidateMetric<br/>Artifact")]
    end

    CM --> SG --> TC --> TSET --> SW --> CC
    BE --> CC
    CONF --> CC
    CC --> PD
    PD ==>|"publish_result"| CR2
    CR2 --> JRES
    MV --> CR2
    AR --> JRES
    JREQ -.->|"in"| CM
    JRES ==>|"import_job_result"| MODELS

    classDef internal fill:#f4f4f5,stroke:#71717a,color:#27272a
    classDef contract fill:#fef3c7,stroke:#b45309,color:#78350f
    classDef built fill:#dcfce7,stroke:#15803d,color:#14532d
    class CM,SG,TC,TSET,SW,BE,CONF,CC,PD internal
    class JREQ,CR2,MV,AR,JRES contract
    class MODELS built
```

**Only `publish_result` crosses.** Everything on the left can be redesigned without
touching the API schemas, the database or the frontend — which is the whole return on the
boundary.

---

## 6. Deployment

Where each piece runs once the engine moves to Google Cloud
([gcp-deployment.md](gcp-deployment.md)).

```mermaid
flowchart LR
    subgraph vm["Compute Engine — always on"]
        DJ["Django + worker"]
        DISK[("Persistent disk<br/>SQLite + media")]
    end

    subgraph gcs["Cloud Storage"]
        IN[/"datasets/"/]
        PROG[/"progress.json"/]
        OUT[/"result.json<br/>artifacts/"/]
    end

    subgraph job["Cloud Run Job — on demand"]
        ENTRY["gcs_entry.py<br/><i>stages files</i>"]
        LOCAL["LocalEngine<br/><i>unchanged</i>"]
    end

    DJ --> DISK
    DJ -->|"1 upload"| IN
    DJ -->|"2 jobs.run"| ENTRY
    ENTRY -->|"3 download"| IN
    ENTRY --> LOCAL
    LOCAL --> ENTRY
    ENTRY -->|"4 write"| PROG & OUT
    DJ -->|"5 poll"| PROG
    DJ -->|"6 import"| OUT

    classDef built fill:#dcfce7,stroke:#15803d,color:#14532d
    classDef todo fill:#f4f4f5,stroke:#a1a1aa,color:#3f3f46
    classDef store fill:#fff7ed,stroke:#c2410c,color:#7c2d12
    class DJ,DISK built
    class ENTRY,LOCAL todo
    class IN,PROG,OUT store
```

`LocalEngine` is unchanged in the cloud — `gcs_entry.py` stages files around it, which is
what keeps the pipeline runnable on a laptop.

---

## 7. Status at a glance

```mermaid
flowchart LR
    subgraph done["Built and tested"]
        D1["Platform: models · API<br/>worker · frontend"]
        D2["engine.contract<br/>engine.client"]
        D3["MockEngine"]
        D4["scoring — S10"]
        D5["GateFamily ABC<br/>+ registry"]
        D6["boundary test"]
    end

    subgraph partial["Partly built"]
        P1["S12 FilterEngine<br/><i>metric filters yes,<br/>sequence filters no</i>"]
        P2["S13 TopK / Pareto<br/><i>ranking yes,<br/>Pareto no</i>"]
    end

    subgraph todo["Step 5"]
        T1["domain/ records"]
        T2["tools/ S1–S9"]
        T3["6 stage classes"]
        T4["ToeholdGate"]
        T5["CandidateStore S11"]
        T6["ReportBuilder S14"]
    end

    classDef built fill:#dcfce7,stroke:#15803d,color:#14532d
    classDef part fill:#fef3c7,stroke:#b45309,color:#78350f
    classDef todo2 fill:#f4f4f5,stroke:#a1a1aa,color:#3f3f46
    class D1,D2,D3,D4,D5,D6 built
    class P1,P2 part
    class T1,T2,T3,T4,T5,T6 todo2
```

**Start with `domain/` and `tools/`** — no scientific input needed, no ViennaRNA for S6
and S7, and everything else depends on them.
