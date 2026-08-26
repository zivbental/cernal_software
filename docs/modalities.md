# Design modalities

A CERNAL run is defined by **four independent choices**. Each is a *modality* — an axis
with a small, closed set of values, where every value changes what the engine actually
computes. Together they are the wizard, the `params_snapshot`, and the search space.

This document explains each axis in full: what the values mean biologically, what they
change downstream, which combinations are legal, and what is built versus planned.

| Axis | Values | Chosen in | Stored as | Status |
|---|---|---|---|---|
| **A · Input** — how the trigger gets in | `de` · `direct` | Wizard step 1 | `AnalysisRun.input_mode` | Both built |
| **B · Host** — which organism | `ecoli` · `yeast` · `human` | Wizard step 1 | `params_snapshot.organism` | Vocabulary built, rules pending |
| **C · Gate** — the switch chemistry | `toehold` · `toehold_and` · `antisense` · `crispr` | Wizard step 2 | `AnalysisRun.gate_families` | Interface built, bodies pending |
| **D · Output** — what it expresses | `gfp` · `mcherry` · `luciferase` · `ampr` · `apoptosis` · `other` | Wizard step 3 | `params_snapshot.payload.outputs` | Vocabulary built, payloads pending |

They are independent by design: a run is one point in **A × B × C × D**, and nothing in
the engine couples two axes except where biology forces it (§5).

---

## 1. Axis A — Input modality

*How does the engine learn what the circuit should respond to?*

There are two entirely different entry paths, and they diverge at the very front of the
pipeline. This is not a convenience toggle — the two modes use different halves of the
system.

### A1 · Differential expression — `de`

**The discovery path.** The researcher uploads a differential-expression table (the
output of DESeq2, edgeR or similar) comparing a control state to a condition state.
CERNAL finds the triggers itself.

```jsonc
{"input_mode": "de", "dataset_id": "…"}          // trigger_sequence is empty
```

What happens, in order:

| Stage | What it does with the table |
|---|---|
| `InputQualityCheck` | Distributions, outliers, batch structure. Everything downstream is wasted if the input is unusable, so this runs first |
| `GeneSelector` | Keeps genes that genuinely *separate* the two states: big enough fold change, significant adjusted p, and expressed in a usable absolute range in both states |
| `TriggerScorer` | Slides a window along each surviving gene's transcript and ranks **every sub-segment** by openness, off-target load, GC and forbidden motifs |
| everything below | Works on `TriggerCandidate` records, and no longer cares where they came from |

**A trigger is not a gene.** It is a specific window at a specific offset in a specific
transcript, and most windows are unusable — buried in structure, shared with paralogues,
or GC-extreme. That is why `TriggerScorer` exists as its own stage and why its output is
the pipeline's pruning point (§6).

*Constraints that apply here:* `min_separation` (minimum |log2 fold change|), `max_p_adj`
(conventionally 0.05), `trigger_lengths` (which window sizes to scan).

*Upload validation is deliberately shallow* — readable file, expected columns present,
sane row count, parseable numerics — and synchronous, so the researcher learns
immediately whether the file is usable. Deep scientific validation is the engine's job at
run time. An `INVALID` dataset uploads successfully (so the report can be read) but
cannot be submitted.

*The open dependency:* the DE table has gene **identifiers**, not **sequences**. Where
the transcript sequences come from is the single largest unanswered question in the whole
engine — see [ROADMAP.md](ROADMAP.md) open question Q1.

### A2 · Direct trigger mRNA — `direct`

**The skip-discovery path.** The researcher already knows the transcript and pastes it
in. There is no dataset at all.

```jsonc
{"input_mode": "direct", "trigger_sequence": "AUGGCUAA…"}   // dataset_id is null
```

Stages 1 and 2 do not run. The pasted sequence becomes a single `TriggerCandidate`
directly, and the pipeline picks up at `SwitchDesigner`.

What this costs, and it is worth being explicit because the UI cannot show it:

- **No `SelectedGene` records**, so no fold changes and no percentiles.
- **No confusion matrix.** `CircuitDesigner` scores a circuit by evaluating it against
  the researcher's actual samples; with no count matrix there are no samples to evaluate
  against. The most honest number the pipeline produces is unavailable in this mode.
- **No `state_separation` metric**, which is the highest-weighted metric in `default-v1`.

So a `direct` run answers *"is this a good switch for this sequence?"* while a `de` run
answers *"is this a good circuit for telling these two cell states apart?"*. They are
different questions and the second is the product's real claim.

### Enforcement

Exactly one input source, enforced in the schema rather than in a code path:

```python
# apps/analyses/models.py — CheckConstraint "run_has_exactly_one_input_source"
Q(input_mode="de", dataset__isnull=False) | Q(input_mode="direct", dataset__isnull=True)
```

A `de` run without a dataset has nothing to analyse; a `direct` run without a sequence
likewise. Neither can be written to the database.

### Status

| | |
|---|---|
| Model, constraint, API, wizard | **Built** |
| `de` path through the engine | Stubbed — stages 1–2 raise `NotImplementedError` |
| `direct` path through the engine | Stubbed — the branch that skips stages 1–2 is not written |
| `MockEngine` | Handles both, producing identical-looking output. **The difference is invisible on mock science** |

---

## 2. Axis B — Host modality

*Which organism is this circuit for?*

```python
class Host(StrEnum):
    ECOLI = "ecoli"
    YEAST = "yeast"
    HUMAN = "human"
```

The important part is that **the design rules follow the track, not the individual
organism**:

```python
class Track(StrEnum):
    PROKARYOTIC = "prokaryotic"  # E. coli
    EUKARYOTIC = "eukaryotic"  # yeast, human
```

`Host.track` is a property, not a stored field, so the mapping cannot drift.

### What the track actually decides

This is the substantive content of the axis — everything else about a host is data.

| Decision | Prokaryotic | Eukaryotic |
|---|---|---|
| **Translation initiation** | A ribosome binding site (Shine–Dalgarno) placed in the hairpin loop | Kozak context; the scanning ribosome model applies instead |
| **What `TranslationScorer` measures** | RBS strength | Kozak match |
| **Which gates are available** | toehold, AND toehold, antisense NOT | those three **plus** CRISPR |
| **Where the payload's start codon can sit** | Downstream of the loop RBS | Constrained by scanning — an upstream AUG in the switch is a real hazard |

### What the *host* (not the track) decides

| Decision | Why it is per-host, not per-track |
|---|---|
| **Codon usage table** | Yeast and human codon preferences differ substantially, though both are eukaryotic. `CodonOptimizer` holds the organism's table |
| **Off-target reference** | The transcriptome to scan against is the organism's. Human is orders of magnitude larger than *E. coli*, so this is also a performance axis |
| **Expression atlas** | `condition_specificity` needs a reference atlas per organism — a gene expressed strongly in the target *and* throughout the body is a poor trigger for anything therapeutic |

### The claim that makes this axis small

CERNAL's founding premise is that **RNA switches follow universal thermodynamics
regardless of host**. A hairpin's stability is a property of the sequence, not of the
cell it sits in. So the organism affects the *frame* around the switch — initiation
signals, codon choice, which transcriptome to avoid — much more than the switch itself.

That is why `ToeholdGate` takes `host` as a **constructor parameter rather than being
subclassed** per track. Two subclasses would be the right design if the method bodies
genuinely diverged; today they differ by which constant goes in the loop, and a parameter
carries that. The split is recorded as available if the bodies ever do diverge.

### A known inconsistency

There are currently **two** places an organism is recorded, and they disagree:

| Where | Type | Value today |
|---|---|---|
| `Project.organism` | `CharField(100)`, free text | `"E. coli"` — the frontend's project form is a text input |
| `params_snapshot["organism"]` | one of `ecoli` · `yeast` · `human` | set by the wizard's organism picker |

`JobRequest.organism` is populated from **`project.organism`** — the free-text one — while
the engine's pipeline sketch reads `Host(request.params["organism"])`. Nothing breaks
today because no engine code parses it yet, and `MockEngine` ignores it. It will break the
moment `build_tools` tries to select a codon table. Recorded as task **P1** in
[ROADMAP.md](ROADMAP.md).

### Status

| | |
|---|---|
| `Host` / `Track` enums, `supported_hosts` on every family | **Built** |
| Wizard organism picker | **Built** |
| Per-host capability reporting (`available_families(host)`) | **Built** in the registry; **not yet wired** to `GET /api/version`, so the wizard cannot grey CRISPR out for *E. coli* |
| Codon tables, atlases, transcriptomes | Not started — no data source chosen |

---

## 3. Axis C — Gate modality

*Which chemistry realises the logic?*

This is the axis with the most science in it, and the one the `GateFamily` plugin
interface exists to keep open. Four families are registered; one is selectable.

```python
class GateKind(StrEnum):
    TOEHOLD = "toehold"
    TOEHOLD_AND = "toehold_and"
    ANTISENSE_NOT = "antisense_not"
    CRISPR = "crispr"
```

| Family | Inputs | Acts on | Hosts | Default state | Status |
|---|---|---|---|---|---|
| `toehold` — Toehold Riboswitch | 1 | translation | all three | OFF | **Selectable**, bodies stubbed |
| `toehold_and` — AND Toehold | 2 | translation | all three | OFF | **Selectable** ⚠️, bodies stubbed |
| `antisense` — Antisense Repression | 1 | translation | all three | **ON** | Planned — `available=False` |
| `crispr` — CRISPR-Cas sgRNA Gate | 1 | **transcription** | yeast, human | OFF | Planned — `available=False` |

⚠️ `ToeholdAndGate` subclasses `ToeholdGate` and does not override `available`, so it
inherits `True` and the wizard offers it. Its methods raise `NotImplementedError`, so a
submission requesting it passes validation and then fails at run time under `LocalEngine`.
Either set `available = False` until E4 lands, or accept it deliberately. Task **P9** in
[ROADMAP.md](ROADMAP.md).

### C1 · Toehold switch — the default

**The mechanism.** A toehold switch is an mRNA that will not translate itself until told
to. It folds into a hairpin. The ribosome binding site sits in the **loop** — reachable —
while the **start codon** is buried in the **stem**, so the ribosome can bind but cannot
start. Hanging off the 5′ end is a single-stranded **toehold**, complementary to the
trigger.

When the trigger appears, it pairs with the toehold and then unzips the stem by branch
migration. The start codon is freed, translation begins, and the payload downstream is
expressed.

```
        OFF                                    ON
                                         trigger
     ┌──stem──┐                          ═══════
  5'─┤ (AUG)  ├─loop(RBS)─payload    5'─┬────────────── AUG ─ payload ──▶ protein
     │        │                         └ toehold paired, stem unzipped
   toehold ───┘
   (single-stranded)
```

**What makes a design good** — and why this is a search rather than a formula:

- The OFF hairpin must be **stable enough** that nothing translates without the trigger
  (low leakage), and
- trigger binding must be **more favourable still**, so the stem actually opens (high
  dynamic range).

Those two pull against each other. A stem stable enough to be truly dark is often too
stable to open. There is no closed form for the optimum, so the engine explores
`toehold_lengths = (12, 15, 18)` per trigger and lets scoring decide. **Widening that
tuple multiplies the whole search space** — it is the cheapest knob for trading runtime
against quality.

**Construction, in six steps** (what `generate_designs` will do):

1. **Binding region** — the reverse complement of the trigger sequence.
2. **Split it** — the first `toehold_len` nucleotides stay single-stranded as the
   toehold; the rest forms the ascending side of the stem.
3. **Loop** — insert the RBS (prokaryotic) or leave Kozak context (eukaryotic), where it
   is accessible in the OFF state.
4. **Descending stem** — complementary to the ascending side, containing the start codon
   so it is sequestered until the stem opens.
5. **Linker** — in frame, joining the switch to the payload; low in structure and free of
   stop codons.
6. **Target structure** — emit the dot-bracket the design is *meant* to fold into. The
   validator compares against it, so a design without one cannot be checked.

**The gotcha that will cost someone a week:** fold the ON state as a **dimer** (`cofold`
with the `&` separator), not as a concatenated single strand. Concatenation produces a
plausible-looking number that means nothing.

**Reference:** Green et al., *Toehold switches: de-novo-designed regulators of gene
expression* (2014).

### C2 · AND toehold — two inputs

Inherits from `ToeholdGate` rather than `GateFamily`, because an AND toehold **is** a
toehold: same chemistry, more inputs.

**The mechanism.** A **serial** stem. The first trigger opens an outer hairpin, which
exposes the toehold for the second, which opens the inner hairpin holding the start
codon. Either trigger alone leaves the construct closed — that is the AND.

Two things are easy to get wrong, and both are recorded in the stub:

- **Order matters.** Trigger A outer with B inner is a different construct from the
  reverse, and they will not perform the same. Generate both and let scoring decide.
- **The intermediate state is real.** With only the first trigger present the switch sits
  half-open. If the start codon is already accessible there, the gate is an **OR wearing
  an AND's shape** — and it will pass every check that only looks at the fully-open and
  fully-closed states. Evaluate the single-trigger states explicitly and treat leakage in
  them as disqualifying.

**Both triggers may come from the same gene.** Two windows on one transcript is a
legitimate AND design, so `TriggerSet` deliberately does not deduplicate by `gene_id`.

**The cost of this modality is combinatorial.** Trigger sets grow as the square of the
surviving trigger count, which is why `max_triggers` defaults to 2 and why 3 is out of
scope without a cluster: top 50 genes in pairs is ~1,225 sets; top 200 genes in triples
is ~1.3 million.

### C3 · Antisense NOT — the inverting element

**The mechanism.** An antisense RNA complementary to the payload's ribosome binding site
and start region pairs with it and blocks translation. Expression is **ON by default**
and switched **OFF** when the trigger appears — the opposite of a toehold.

**Why the pipeline needs it.** That inversion is what makes `NOT` buildable, and
therefore what lets a circuit use a **down-regulated** gene as an input. Without it only
UP genes are usable and **half the differential-expression signal is wasted**. This is
the family that connects `Regulation.DOWN` to `GeneState.OFF`.

**An unsettled design choice**, which is the scientific team's:

- the trigger transcript **is** the antisense, acting directly on the payload; or
- the trigger drives expression of a **separate** antisense RNA.

The first is simpler and needs no extra transcriptional unit; the second gives
amplification. The design rules differ, so this must be settled before implementation.

**The safety inversion, and it is the most important sentence on this page.** An antisense
NOT gate is ON by default, so a **failed** gate *expresses the payload* rather than
staying dark. For a reporter that is harmless. For an apoptosis inducer it is not. See
§5.

### C4 · CRISPR sgRNA gate — the different class of application

**The mechanism.** An sgRNA's **spacer** — the part that finds the DNA target — is
sequestered inside a hairpin, so Cas cannot be guided anywhere. A trigger opens that
hairpin (the same strand-displacement idea as a toehold, applied to a guide instead of a
start codon), and the freed sgRNA directs Cas to a promoter. The pipeline map calls this
an internally-blocked sgRNA hairpin, **iSBH**.

**Why it is worth the extra machinery.** Toehold and antisense act on **translation** of
a payload the construct carries. CRISPR acts on **transcription**, and can therefore
regulate genes **already in the genome** — a different and much larger class of
application.

**Eukaryotic only.** This is the reason `supported_hosts` exists on `GateFamily` at all
rather than a single `available` flag, and the reason capabilities should be reported per
host: the wizard must grey CRISPR out for *E. coli* rather than accept a submission that
cannot be built.

**Three things that differ from every other family:**

1. **The spacer comes from the target gene, not the trigger.** Every other family in this
   engine derives its sequence from the trigger. This one does not, and it trips people up.
2. **The scaffold is sacred.** The constant Cas-binding region must not be disturbed.
   Validate scaffold structure *separately* from switching behaviour — a design that
   switches beautifully and misfolds the scaffold does nothing.
3. **Off-target has a second meaning.** The spacer can guide Cas to unintended **genomic**
   sites. That is a search against the genome, not the transcriptome, and
   `OffTargetScanner` as specified does not do it. It needs its own treatment before this
   family ships.

**An unresolved configuration question:** the effector. dCas9 fused to an **activator**
turns the target gene on; fused to a **repressor** it turns it off. That choice changes
what the circuit *means* and it currently has no home in the run configuration.

### How four unlike chemistries stay comparable

This is the central problem the scoring layer solves, and it is worth stating plainly:
**a family that scored its own designs could not be compared with another family.**

So the contract is:

- `evaluate_design` returns **raw** values only, keyed by the metric names in
  `engine.scoring.profiles` — `gate_folding_energy`, `predicted_leakage`,
  `dynamic_range`, `trigger_accessibility`, `gc_content`, and the rest.
- Normalization, weighting, hard filters and ranking belong to `engine.scoring`, which is
  **already implemented and tested**.
- Missing values are `None`, never a sentinel like `-1`. The scoring layer handles missing
  explicitly; a sentinel silently becomes a real number and poisons the ranking.

**The trap in sharing metric names.** `predicted_leakage` means *residual expression
without the trigger* for a toehold, and *residual expression **with** the trigger* for an
antisense NOT. Same name, same direction (lower is better), **opposite biological event**.
The report must say so, because the column header cannot.

### Adding a family

A new chemistry is one module plus one `register()` call:

1. Subclass `GateFamily` in `engine/gates/`, setting `name`, `version`, `kind`, `label`,
   `description`, `supported_hosts`, `max_inputs`.
2. Implement `required_tools`, `is_compatible`, `generate_designs`, `evaluate_design`,
   `emit_sequence`.
3. `register(YourFamily)` in `engine/gates/registry.py`.

Nothing else in the engine, the API or the frontend changes. Planned families are
*deliberately included* in `describe_families()` with `available=False`, so the wizard
shows them greyed out with their real label — flipping `available` on the class changes
the UI with no frontend release.

---

## 4. Axis D — Output modality

*What does the circuit express when it fires?*

```python
class DesiredOutcome(StrEnum):
    GFP = "gfp"
    MCHERRY = "mcherry"
    LUCIFERASE = "luciferase"
    ANTIBIOTIC = "ampr"
    APOPTOSIS = "apoptosis"
    CUSTOM = "other"
```

| Value | What it is | Reads out as |
|---|---|---|
| `gfp` | Green fluorescent protein | Visual — microscopy, flow cytometry |
| `mcherry` | Red fluorescent protein | Visual, spectrally separable from GFP |
| `luciferase` | Bioluminescent enzyme | Visual, higher sensitivity, needs substrate |
| `ampr` | Antibiotic resistance (AmpR · KanR) | **Positive selection** — survivors are the ones that fired |
| `apoptosis` | Programmed cell death inducer | **Negative selection** — a kill-switch |
| `other` | User-pasted coding sequence | Whatever the researcher wants |

### They are one list, not two tiers

The original design split these into "reporting genes" and "selective markers". That
implied a hierarchy which does not exist: **a circuit expressing GFP and one expressing
AmpR are the same kind of construct with a different payload.** Both are a coding
sequence placed in frame downstream of the switch.

The same reasoning removed `marker` from `SegmentKind`:

```python
class SegmentKind(StrEnum):
    PROMOTER = "promoter"
    SWITCH = "switch"
    PAYLOAD = "payload"  # a selective marker IS the payload
    TERMINATOR = "terminator"
    BACKBONE = "backbone"
```

A selective marker *is* the payload, not an add-on beside it. The vocabulary is stable
because the frontend colours the plasmid map by it — adding a value means the map needs a
colour for it.

### What actually differs between outputs

Less than you would expect, which is why this axis is cheap:

| Differs | Does not differ |
|---|---|
| The payload segment's **sequence and length**, which drives plasmid length and synthesis cost | The switch design — a toehold does not know what it is gating |
| **Codon optimisation** of the payload for the host | Every folding, leakage and off-target metric |
| The **linker** and any in-frame fusion constraints | The circuit's Boolean logic |
| **What a failure means** (§5) | The scoring profile |

**Each selected output gets its own set of plasmid candidates.** Selecting GFP and AmpR
does not produce a dual-payload construct; it produces two families of candidates from
the same circuits.

### Status

| | |
|---|---|
| `DesiredOutcome` enum, `SegmentKind`, wizard selector, `PlasmidBuilder.payload_segment` signature | **Built** |
| Actual payload sequences | **Not present.** There is no sequence library for GFP, AmpR or anything else |
| `custom_sequence` validation | Not built — no ORF check, no stop-codon check, no length cap |
| GenBank export | Not built — needs a real annotated construct |

---

## 5. Where the axes interact

They are mostly independent. Here is every place they are not.

### B × C — host restricts gate

```python
available_families(Host.ECOLI)  # toehold, toehold_and, antisense
available_families(Host.HUMAN)  # …plus crispr
```

Availability is a function of **(gate, host)**, not of gate alone. This is enforced in
`GateFamily.supports()` and reported through `available_families(host)`.

> **Not yet wired end to end.** `GET /api/version` currently reports families without a
> host, so the wizard cannot grey CRISPR out for *E. coli*. A submission that cannot be
> built is caught at run time instead of at submit time. Task **P2** in
> [ROADMAP.md](ROADMAP.md).

### A × C — input mode restricts arity

A `direct` run supplies exactly one trigger sequence, so `toehold_and` has nothing to
build a second input from. `is_compatible` should refuse with a reason the researcher can
act on — *"this gate takes two inputs and only one sequence was supplied"*, not *"arity
mismatch"*.

### C × D — the safety asymmetry

This deserves its own line because it is the one combination that is dangerous rather
than merely broken.

| Gate default state | Output | A failed gate means |
|---|---|---|
| Toehold (OFF) | anything | Nothing is expressed. Safe |
| CRISPR (OFF) | anything | No guide, no regulation. Safe |
| **Antisense NOT (ON)** | reporter | Constant fluorescence. Harmless, obviously wrong |
| **Antisense NOT (ON)** | **`apoptosis`** | **Constant kill-switch expression.** A safety failure, not an inconvenience |

The same logic applies to false positives generally: `ConfusionMatrix.false_positive` —
control samples where the circuit fires — is *the dangerous one*, because a kill-switch
firing in healthy cells is a safety failure. Which is why `separation_margin` (Youden's
J) and not accuracy is the headline number: a circuit that fires on everything catches
every true positive and separates nothing, and only the margin says so.

**Requirement:** the report must state a gate's default state alongside its payload. This
is not built. Task **E9** in [ROADMAP.md](ROADMAP.md).

### A × B — off-target reference must match the trigger source

Not a legality constraint but a correctness one: the transcriptome `OffTargetScanner`
indexes **must be the same build** the trigger sequences came from. Loading them
separately is how two references drift apart, and the symptom is off-target penalties
that look plausible and mean nothing.

---

## 6. What each axis costs at run time

Useful when a run is slow and you need to know which knob to turn. Basis: ViennaRNA
2.7.2, ~15 ms to evaluate one design on one core.

| Axis | Effect on the search space |
|---|---|
| **A · input** | `direct` collapses stages 1–2 to nothing. A `direct` run is seconds; a `de` run is minutes |
| **B · host** | Negligible for folding. **Large** for off-target: the human transcriptome is orders of magnitude bigger than *E. coli*'s |
| **C · gate** | The dominant axis. Single-input scales linearly with surviving triggers; **AND scales quadratically**. Each gate family selected multiplies the design count |
| **C · toehold lengths** | Direct multiplier — three lengths means three times the designs |
| **D · output** | Near zero. Each output adds a plasmid assembly per circuit, and assembly is cheap compared with folding |

**The real lever is none of these — it is pruning.** `TriggerScorer` → `SwitchDesigner` is
where the compute budget is set. Filter triggers by fold change, adjusted p and
accessibility *first*, then build combinations from the survivors, and the problem stays
firmly inside one machine. Exhaustive enumeration is what forces a cluster, and it is
rarely the better science anyway.

---

## 7. Where each modality lives in the code

| Axis | Engine enum | Platform field | `params_snapshot` key | API | Frontend |
|---|---|---|---|---|---|
| A · Input | — | `AnalysisRun.input_mode` | `input_mode` | `RunIn.input_mode` | `Steps.tsx` step 1 |
| B · Host | `domain.Host` / `Track` | `Project.organism` ⚠️ | `organism` | `JobRequest.organism` | `Steps.tsx` step 1 |
| C · Gate | `domain.GateKind` | `AnalysisRun.gate_families` | `mechanism` | `RunIn.gate_families`, `GET /api/version` | `Steps.tsx` step 2 |
| D · Output | `domain.DesiredOutcome` | — | `payload.outputs` | — | `Steps.tsx` step 3 |

⚠️ See the inconsistency in §2.

**Two axes have no dedicated Platform column.** Host and output live only inside
`params_snapshot`. That is deliberate — the snapshot is the immutable record of what was
asked, and adding a column for every wizard field would couple the Platform to the
wizard's shape. It does mean neither is queryable in SQL; if filtering runs by organism
ever matters, that is the moment to promote it to a column.

---

## 8. Adding a value to an axis

| Axis | What it takes |
|---|---|
| **A · Input** | A new `InputMode` choice, a migration, a branch in `submit_run`, a branch at the front of the pipeline, and a new leg of the `CheckConstraint`. The heaviest of the four |
| **B · Host** | A new `Host` member, its `track` mapping, a codon table, a transcriptome, and `supported_hosts` review on every family |
| **C · Gate** | One module in `engine/gates/` plus one `register()` call. Nothing else changes — this is what the plugin interface bought |
| **D · Output** | A new `DesiredOutcome` member, a payload sequence in the library, and a colour in the frontend's plasmid map |

The asymmetry is the point. **Gate families are the axis expected to grow**, so that is
the one made cheap.

---

## See also

- [engine.md](engine.md) — how the pipeline, gates, tools and scoring are built
- [ROADMAP.md](ROADMAP.md) — every task that turns the "planned" rows above into "built"
- [domain-model.md](domain-model.md) — the fields these values are stored in
- [api.md](api.md) — how a submission carries them
