# Stage 5 — what it takes to make a circuit orderable

**Status:** Assessment. Nothing here is built yet.
**Question it answers:** *"What stops `PlasmidBuilder` turning a designed switch into a
construct someone could actually order?"*
**Companion documents:** [`ROADMAP.md`](ROADMAP.md) §5 E5 is the task this is a subset of;
[`smoke-run.md`](smoke-run.md) is the same exercise for stage 3 and the model this
follows; [`domain-model.md`](domain-model.md) has `PlasmidDesign`'s field-level shape;
[`engine.md`](engine.md) is the architecture.

> **This is a design document, not a planning file.** [ROADMAP.md](ROADMAP.md) is the
> single place work is recorded. §10 below gives the rows to paste into it. This file
> holds the *evidence and the reasoning*; the ROADMAP holds the *work*.

---

## 1. The verdict

**The code is the small half. The data is the whole problem.**

Stage 5 is not like the stages around it. `CircuitDesigner` above it and `ReportBuilder`
below it are both genuinely hard *algorithms*. `PlasmidBuilder.build()` is concatenation,
a regex screen, and a frame check — perhaps eighty lines, and every tool it needs is
already built and tested.

What it cannot do is emit a single base. Measured against this commit:

```
$ find src/engine -type f \( -name "*.fasta" -o -name "*.fa" -o -name "*.gb" \
      -o -name "*.json" -o -name "*.csv" -o -name "*.tsv" -o -name "*.txt" \) \
      ! -path "*__pycache__*"
(nothing)
```

There is **no sequence data of any kind under `src/engine/`** — the only non-Python files
are the gate notebooks. No promoter, no terminator, no backbone, no payload CDS.
`PlasmidBuilder` is asked to lay parts onto a backbone and the parts do not exist. Nor is
there anywhere to put them today: `pyproject.toml` declares no package data, so the first
data file also brings a packaging decision with it.

That is a different kind of blocker from the one [`smoke-run.md`](smoke-run.md) found.
There, the science worked and the wiring was missing. Here the wiring is trivial and the
*inputs* are missing — and three of the four missing inputs have never been asked for.
[ROADMAP.md](ROADMAP.md) records **Q11** (payload sequences). Promoter, terminator and
backbone are not yet questions at all.

**So the useful output of this document is a question, not a patch.** §4 asks it.

---

## 2. What is actually in place

More than the stub count suggests. Every probe below was run against this commit.

**The builder constructs; only its two bodies are missing.**

```
constructed: PlasmidBuilder
  standard=RFC10  backbone=()
  .build()           -> NotImplementedError(Step 5)
  .payload_segment() -> NotImplementedError(Step 5)
```

**`MotifScreener` — the compliance half — is fully built**, RFC10 and RFC1000 site
tables included, and its `Violation.__str__` already formats exactly what
`PlasmidDesign.violations` stores.

**ID minting works**, and `CandidateStore.mint_id` already documents `plasmid` as one of
its prefixes:

```
mint_id('plasmid') -> plasmid-000001, plasmid-000002
```

**`CodonOptimizer` does not.** Both methods raise, and the table they would need is
empty:

```
usage_table loaded for ecoli: {}
  .translation_score() -> NotImplementedError(Step 5 — codon adaptation index or equivalent)
  .variants()          -> NotImplementedError(Step 5)
```

This matters because `payload_segment`'s docstring specifies running each CDS through
`codons.translation_score` and rewriting with `codons.variants`. **Neither is available,
and both need a codon-usage table that also has no home.** §5 builds stage 5 without
them, deliberately.

---

## 3. Stage 5 does not have to wait for stage 4

`build(circuit: CircuitCandidate, ...)` reads like a hard dependency on `CircuitDesigner`,
which is four stubs away. It is not.

A `direct` run has exactly one trigger, one switch and one output. The circuit is
therefore trivial, and every type needed to express it is already real. Hand-built
against this commit:

```
CircuitCandidate hand-built OK:
  id=circ-000001 output=GFP designs=1
  complexity=1  is_rejected=False
  expression.render()='pasted'
  evaluate(frozenset({'pasted'}))=True
```

This is the same move `pipeline._direct_trigger` already makes for stages 1–2:
[`modalities.md`](modalities.md) §A2 says a direct run *"picks up at `SwitchDesigner`"*,
and the pasted sequence simply **is** the one trigger. The identical logic says a direct
run's circuit **is** the one switch.

**Recommendation: build stage 5 on the direct path that already works**, synthesising the
single-gene circuit the way `_direct_trigger` synthesises the single trigger. That keeps
stage 5 unblocked by stage 4, Q6 and Q7, and it lights up a screen the SPA already
renders — today a real `LocalEngine` run sends `plasmid_segments: []` and the plasmid map
draws nothing, while `MockEngine` fabricates five segments so the demo looks complete.

One honesty constraint comes with it. An all-zero confusion matrix is not neutral:

```
ConfusionMatrix(0, 0, 0, 0).separation_margin = -1.0
```

A direct run has no samples, so its circuit is **not measured**, not measured-as-zero. It
must not be fed to scoring as though it were a real separation of −1.0. Carry it as
unmeasured and say so.

---

## 4. Where do the parts live? — the question this document exists to ask

[CLAUDE.md](../CLAUDE.md) §7 is explicit that the supporting-part database *"has no home
yet"* and says **ask rather than inventing a path**. So: four part classes, and they do
not have the same answer.

| Part | What is needed | Who owns the choice | Default possible? |
|---|---|---|---|
| **Promoter** | One constitutive promoter per host | Scientific team | **Yes, provisionally.** J23119 is the community default for *E. coli* |
| **Terminator** | One strong terminator per host | Scientific team | **Yes, provisionally.** B0015 |
| **Backbone** | Origin of replication + the plasmid's own selection marker | The **lab**, not the software — it depends on the strains and antibiotics actually in use | **No** |
| **Payload CDS** | GFP, mCherry, luciferase, AmpR, apoptosis inducer | **Q11**, open | **No** |

### The proposal

**Promoter, terminator and payload CDS go in a module-level table in
`stages/plasmids.py`, and the backbone stays injected.**

Both halves of that follow decisions this repo has already made:

- **`stages/motifs.py` is the precedent for the table.** It holds `RFC10_SITES`,
  `RNASE_SITES` and `MAX_HOMOPOLYMER` as module constants, with the reasoning written at
  the top: *"the **motif sets** are the part the scientific team owns, and they live in
  the tables below so they can be edited without touching the logic."* A parts catalogue
  is the same shape of problem — scientific data, edited independently of code, reviewed
  in a diff. No new file, no packaging question, no `.md`-to-code drift.
- **The constructor already decided the backbone is injected.** `__init__` takes
  `backbone: tuple[Segment, ...] = ()` — the original author separated it from the
  catalogue on purpose. A backbone is a property of the lab that will transform the
  plasmid, which is exactly the sort of thing that must not be hardcoded in a table.

That leaves three concrete questions for the scientific team, none of which software can
answer:

> **Q12 — Which promoter and terminator, per host?** A provisional J23119/B0015 pair for
> *E. coli* unblocks the build immediately, but yeast and human need their own and the
> defaults must be somebody's decision rather than a placeholder that quietly becomes
> permanent.
>
> **Q13 — What backbone does the team actually build into?** Origin, selection marker,
> and whether it differs per host. Needed as a sequence, not a catalogue number.
>
> **Q11 (already open) — the payload sequences themselves.** Note this is now blocking
> two things, not one: `AntisenseNotGate` requires a real payload at construction today.

Until Q11/Q13 are answered, stage 5 can still be built and tested end to end against a
**caller-supplied** backbone and payload, because both arrive from outside the table.
What it cannot do is pick sensible ones on the researcher's behalf.

---

## 5. The minimal build list

Five items. None needs stage 4, `CodonOptimizer`, or a resolved Q6/Q7.

### P1 · The parts table

Module constants in `stages/plasmids.py`, shaped like `motifs.py`'s: a `dict` keyed by
host for promoter and terminator, and a `dict` keyed by `DesiredOutcome` for payload
CDSs. Each value a DNA string with its part name. Start with whatever Q12 returns and
leave the payload dict empty rather than fabricating a GFP sequence from memory — an
almost-right CDS is far worse than a missing one, because it will be ordered.

### P2 · `payload_segment(outcome)`

Table lookup, then validate like any other input: whole codons, starts with ATG, **no
internal in-frame stop**, no forbidden motifs. `DesiredOutcome.CUSTOM` reads
`params["payload"]["custom_sequence"]` and gets the *same* validation — a pasted CDS is
the least trustworthy input in the system.

**Reuse the rules that already exist.** `AntisenseNotGate.__init__` validates a payload
CDS today — `to_rna`, then `is_valid_rna`, then `payload[:3] != sequences.START_CODON`
— and raises `ValueError` naming what it got. Two different definitions of "a valid
payload" in one engine is precisely the failure [CLAUDE.md](../CLAUDE.md) §1 is about;
use `sequences.START_CODON` and `find_stops`, not a second opinion.

Return `Segment(SegmentKind.PAYLOAD, name, dna)`. No codon optimisation in this pass
(§7). A payload the table cannot supply raises `InputValidationError` naming the outcome,
rather than returning an empty segment that assembles into a silently payload-less
plasmid.

### P3 · `build(circuit, outcome)` — assemble

Layout, in order: **promoter → switch → payload → terminator → backbone**, each a
`Segment` carrying its own `kind` so the map can label it.

Two rules that are easy to get wrong:

- **Convert the switch to DNA.** `GateDesign.sequence` is RNA by contract. §6.1.
- **Attribute every violation to a segment.** `screener.violations` returns positions
  into the assembled string; the researcher needs to know *which part* carries the
  offending site, because that decides whether it is theirs to change.

Then check, and **record rather than repair**:

1. `screener.violations` over `plasmid.sequence` — the whole assembly, never the parts.
2. Reading-frame continuity from the switch's ATG through the payload.
3. Total length against a synthesis cap (a module constant, owned by the team, like
   `MAX_HOMOPOLYMER`).

Stringify with `str(violation)` — `Violation.__str__` was written for this and
`PlasmidDesign.violations` is `tuple[str, ...]`, not `tuple[Violation, ...]`.

### P4 · Screen across the origin join

A plasmid is circular; `Plasmid.sequence` is a linear concatenation. §6.3 measures what
that misses. Screen `sequence + sequence[:k-1]` for the longest site length `k`, and
attribute anything found past the end to the junction.

### P5 · Wire it into the direct pipeline

Synthesise the one-gene `CircuitCandidate` (§3), call `build` once per requested output,
and populate `design["plasmid_segments"]` with `{kind, name, length_bp}` per segment —
the shape the SPA's `PlasmidSegment` already expects. **Sequences do not go on the wire**;
they belong in the FASTA the reporting stage writes.

**Done when:** a `direct` run under `LocalEngine` returns candidates whose plasmid map
renders real proportional arcs, and whose `violations` list is empty for a clean design
and populated for a deliberately dirty one.

---

## 6. Gotchas that will otherwise cost an afternoon

Each measured against this commit.

### 6.1 A switch is RNA; a plasmid is DNA

`GateDesign.sequence` is *"the switch, RNA, uppercase"*. Vendors, GenBank and every
restriction site in `motifs.py` are DNA.

```
switch as stage 3 emits it: GGGUUUAACAGAGGAGAUAAAGAUGGCUAAGCUUAACGGAUCCAUG
after to_dna():             GGGTTTAACAGAGGAGATAAAGATGGCTAAGCTTAACGGATCCATG
```

`Segment.length_bp` is right either way, so **nothing downstream will complain**. The
construct simply goes to a vendor with U's in it. Convert once, at the boundary, with
`sequences.to_dna`.

The compliance check will not save you, because it converts internally — measured, same
screener, same sequence:

```
RNA input violations: ["restriction site 'EcoRI' (GAATTC) at position 8"]
DNA input violations: ["restriction site 'EcoRI' (GAATTC) at position 8"]
identical: True
```

That is correct behaviour for a screener and exactly why the mistake survives: the one
step that inspects the sequence most closely is indifferent to it.

### 6.2 The junction site — the classic assembly failure

Neither part carries EcoRI. Joining them creates one:

```
left  part ends ...TCCATGGAAT   violations: 0
right part starts TCATGGTGAG... violations: 0
assembled (56 bp)               violations: 1
  -> restriction site 'EcoRI' (GAATTC) at position 24
```

Screening parts individually finds nothing. This is why both the stub docstring and
[ROADMAP.md](ROADMAP.md) E5 say to screen the assembly — and why P3 must not "optimise"
by screening parts once and caching.

### 6.3 The circular join — the failure the *assembled* screen still misses

Screening the assembly is necessary and not sufficient. A restriction enzyme does not
care where we chose to start writing the sequence down:

```
linear scan of 55 bp:          1 violations
scan across the origin join:   2 violations
  -> missed by the linear scan: restriction site 'EcoRI' (GAATTC) at position 55
```

### 6.4 Frame continuity — silent, and invisible to every other check

Fusing a payload onto a switch naively:

```
fused switch+payload: 74 nt, AUGs at (22, 43, 48)
first AUG at 22; in-frame stops downstream: (30,)
frame length from AUG: 52 nt (1 nt out of frame)
translates to: MAKLNGSMSW
```

Ten residues, then a premature stop — and the frame does not close (52 nt leaves 1 nt
over). That construct **assembles, screens clean, prices normally and expresses
nothing.** The stub docstring
calls this join *"the one most likely to go wrong"*; `sequences.find_stops` and
`find_augs` are built and make the check three lines.

### 6.5 Repair policy is not uniform across the construct

The stub says violations are recorded, not silently repaired — with one exception, and
the boundary matters:

- **Inside the payload CDS**, a synonymous rewrite can remove a site without changing the
  protein. Legitimate (once `CodonOptimizer` exists), and must be *reported* when done.
- **Inside the switch**, never. Its structure was validated in stage 3; changing a base
  to remove a restriction site silently invalidates the fold that justified the design.

A repair that crosses a segment boundary is the same bug as a junction site, in reverse.

### 6.6 Two smaller ones

- **`PlasmidSegment.kind` in the frontend still lists `"marker"`**, which `SegmentKind`
  deliberately dropped (*"a selective marker **is** the payload"*). A real plasmid will
  never emit it. Stale union, worth trimming when P5 lands.
- **The map is dominated by the backbone.** Arcs are proportional, so a ~1.5 kb backbone
  beside a ~90 nt switch renders the switch as a sliver. Worth knowing before someone
  reports it as a bug.

---

## 7. What we deliberately skip — and what it costs

| Skipped | Why | What it costs |
|---|---|---|
| **Codon optimisation of the payload** | `CodonOptimizer` is two stubs and an empty table (§2) | The payload is emitted verbatim. Expression level is not tuned, and a payload whose opening codons disturb the switch stem is *reported*, not fixed |
| **`translation_score` on the fused CDS** | Same | `GateDesign.translation_score` keeps its `0.0` default. It is one of nine metrics, not a gate — but 0.0 is a *measured-worst* value, not a missing one. Prefer leaving the metric absent to scoring it as zero ([CLAUDE.md](../CLAUDE.md) §3) |
| **Emitting RFC10 prefix/suffix scars** | Compliance *checking* and standard-compliant *formatting* are different jobs; only the first is specified | The construct is checked against RFC10 but is not itself a drop-in RFC10 part. Say so in the report, or someone will assume otherwise |
| **Multi-switch layout** | Needs a scientific answer (below) | Single-switch circuits only — which is every `direct` run |
| **GenBank export** | Stage 6's job, and it wants annotated features | FASTA-level output only. [ROADMAP.md](ROADMAP.md) already lists GenBank under E5 |

The multi-switch question is real and should be asked alongside Q12/Q13. When a circuit
needs several switches — `A AND NOT B` with an antisense NOT — the stub says each needs
*"its own promoter and terminator"*, which is a layout rule. It does not say whether each
transcriptional unit carries its own payload copy or only the one driving the output
does. That changes the construct, and it is a biology decision.

---

## 8. How we will know it worked

1. `tests/engine/test_plasmids.py` — a clean design produces `is_compliant=True`; a
   design seeded with EcoRI across a junction produces exactly one violation naming
   EcoRI and the junction; a wrap-around site is caught; an out-of-frame payload is
   caught.
2. A `direct` run under `LocalEngine` returns `plasmid_segments` with five kinds, lengths
   summing to `Plasmid.length_bp`, and no `U` anywhere in any emitted sequence.
3. The plasmid map renders proportional arcs for a real run, not just under `MockEngine`.
4. Two runs with the same seed produce byte-identical constructs.

---

## 9. Sequencing

```
Q12 (promoter/terminator) ──┐
                            ├──► P1 parts table ──► P2 payload_segment ──► P3 build ──► P4 circular ──► P5 wire in
Q13 (backbone) ─────────────┘                                                                               │
Q11 (payloads) ─────────────────────────────────────────────────────────────────────────────────────────────┘
```

P3 and P4 can be written and unit-tested against hand-made segments **before** any
question is answered — the screening, framing and length logic does not care where the
bases came from. Only P5, which puts a construct in front of a researcher, needs Q11 and
Q13.

---

## 10. Rows for ROADMAP.md

For §2, the open questions table:

| # | Question | Blocks |
|---|---|---|
| **Q12** | Which constitutive promoter and terminator, per host? Provisional J23119/B0015 unblocks *E. coli*; yeast and human need their own, and the defaults need to be a decision rather than a placeholder | E5a |
| **Q13** | What backbone does the team build into — origin and selection marker, as sequences, per host? | E5a |

For §5, as a carve-out of E5 in the same shape as E2a:

### E5a · The first orderable construct — `direct` path only

`PlasmidBuilder` on the single-switch circuit a `direct` run already produces, skipping
stage 4 the way [smoke-run.md](smoke-run.md) skipped stages 1–2. Parts table in
`stages/plasmids.py` following `motifs.py`'s precedent; backbone stays injected.
Assembled-sequence screening **plus** the circular join; frame continuity from the
switch's ATG through the payload; violations recorded, never silently repaired. No codon
optimisation — `CodonOptimizer` is still stubbed, and its table is empty.

Blocked on **Q11**, **Q12**, **Q13** for real parts; unblocked for the logic itself.

**Done when:** a `direct` run under `LocalEngine` populates `plasmid_segments` with real
lengths, the plasmid map renders from real data, and `tests/engine/test_plasmids.py`
locks in the four failure modes in §6.
