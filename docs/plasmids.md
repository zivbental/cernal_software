# Stage 5 — what it takes to make a circuit orderable

**Status:** Built (E5a, `direct` path only). `PlasmidBuilder.build()` and
`.payload_segment()` are real; see §13 for what shipped and where it differs from this
document's original recommendation.
**Question it answers:** *"What stops `PlasmidBuilder` turning a designed switch into a
construct someone could actually order — and should we write the DNA assembly ourselves
or borrow it?"*
**Companion documents:** [`ROADMAP.md`](ROADMAP.md) §5 E5 is the task this is a subset of;
[`smoke-run.md`](smoke-run.md) is the same exercise for stage 3 and the model this
follows; [`domain-model.md`](domain-model.md) has `PlasmidDesign`'s field-level shape;
[`engine.md`](engine.md) is the architecture; [ADR 0007](decisions/0007-biopython-for-genbank-export.md)
is the final dependency decision — **Biopython only, `pydna` rejected** — which
supersedes §5's recommendation below.

> **This is a design document, not a planning file.** [ROADMAP.md](ROADMAP.md) is the
> single place work is recorded. §12 below gives the rows pasted into it. This file
> holds the *evidence and the reasoning*; the ROADMAP holds the *work*.

Every measurement below was run against this commit. Where this document disagrees with
an external brief or with upstream documentation, it is because the claim was tested.
**§5's pydna measurements are kept for the record — they are what motivated looking
harder at the problem — but §13 documents the course correction: further testing found
plain Biopython sufficient on its own, and that is what got built.**

---

## 1. The verdict

**Two findings, and they point in different directions.**

**(a) The code CERNAL would write is the small half. The data is the whole problem.**
`PlasmidBuilder.build()` is concatenation, a screen, and a frame check — perhaps eighty
lines — and every tool it needs is already built. What it cannot do is emit a single base:

```
$ find src/engine -type f \( -name "*.fasta" -o -name "*.fa" -o -name "*.gb" \
      -o -name "*.json" -o -name "*.csv" -o -name "*.tsv" -o -name "*.txt" \) \
      ! -path "*__pycache__*"
(nothing)
```

There is **no sequence data of any kind under `src/engine/`** — the only non-Python files
are the gate notebooks. No promoter, no terminator, no backbone, no payload CDS, and
`pyproject.toml` declares no package data, so the first parts file brings a packaging
decision with it. Three of those four part classes have never been asked for as
questions. §4 asks them.

**(b) The DNA-assembly half should be borrowed, not written — and only the Python half.**
Measured, `pydna` does the parts of this job that are genuinely easy to get subtly wrong,
including one this document had written down as an unavoidable gotcha. Its frontend
counterpart does not fit CERNAL at all. §5 is the evidence for both halves of that
split.

That is a different shape of blocker from the one [`smoke-run.md`](smoke-run.md) found.
There, the science worked and the wiring was missing. Here the wiring is trivial, the
*inputs* are missing, and the interesting engineering question is what to take off the
shelf.

---

## 2. What is actually in place

More than the stub count suggests.

**The builder constructs; only its two bodies are missing.**

```
constructed: PlasmidBuilder
  standard=RFC10  backbone=()
  .build()           -> NotImplementedError(Step 5)
  .payload_segment() -> NotImplementedError(Step 5)
```

**`MotifScreener` — the compliance half — is fully built**, RFC10 and RFC1000 site tables
included, and its `Violation.__str__` already formats exactly what
`PlasmidDesign.violations` stores.

**ID minting works**, and `CandidateStore.mint_id` already documents `plasmid` as one of
its prefixes:

```
mint_id('plasmid') -> plasmid-000001, plasmid-000002
```

**`CodonOptimizer` does not.** Both methods raise, and the table they would need is empty:

```
usage_table loaded for ecoli: {}
  .translation_score() -> NotImplementedError(Step 5 — codon adaptation index or equivalent)
  .variants()          -> NotImplementedError(Step 5)
```

This matters because `payload_segment`'s docstring specifies running each CDS through
`codons.translation_score` and rewriting with `codons.variants`. **Neither is available,
and both need a codon-usage table that also has no home.** §6 builds stage 5 without
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
yet"* and says **ask rather than inventing a path**. Four part classes, and they do not
have the same answer.

| Part | What is needed | Who owns the choice | Default possible? |
|---|---|---|---|
| **Promoter** | One constitutive promoter per host | Scientific team | **Yes, provisionally.** J23119 is the community default for *E. coli* |
| **Terminator** | One strong terminator per host | Scientific team | **Yes, provisionally.** B0015 |
| **Backbone** | Origin of replication + the plasmid's own selection marker | The **lab**, not the software — it depends on the strains and antibiotics actually in use | **No** |
| **Payload CDS** | GFP, mCherry, luciferase, AmpR, apoptosis inducer | **Q11**, open | **No** |

### The proposal

**Promoter, terminator and payload CDS go in a module-level table in
`stages/plasmids.py`; the backbone stays injected, and should also be acceptable as an
uploaded GenBank file.**

The first two halves follow decisions this repo has already made:

- **`stages/motifs.py` is the precedent for the table.** It holds `RFC10_SITES`,
  `RNASE_SITES` and `MAX_HOMOPOLYMER` as module constants, with the reasoning written at
  the top: *"the **motif sets** are the part the scientific team owns, and they live in
  the tables below so they can be edited without touching the logic."* A parts catalogue
  is the same shape of problem — scientific data, edited independently of code, reviewed
  in a diff. No new file, no packaging question.
- **The constructor already decided the backbone is injected.** `__init__` takes
  `backbone: tuple[Segment, ...] = ()` — the original author separated it from the
  catalogue on purpose. A backbone is a property of the lab that will transform the
  plasmid, which must not be hardcoded in a table.

The third half is new, and it is a direct consequence of §5: **once Biopython is present,
"supply your own backbone" costs almost nothing**, because a real backbone already exists
in the world as an annotated `.gb` file with its AmpR and origin features marked. That
turns Q13 from "someone must type out a sequence" into "point at the file you already
use", which is a much easier question to answer.

> **Q12 — Which promoter and terminator, per host?** A provisional J23119/B0015 pair for
> *E. coli* unblocks the build immediately, but yeast and human need their own and the
> defaults must be somebody's decision rather than a placeholder that quietly becomes
> permanent.
>
> **Q13 — What backbone does the team actually build into?** Origin, selection marker,
> and whether it differs per host. **A GenBank file of the plasmid the lab already
> transforms is the ideal answer** — the annotations come with it.
>
> **Q11 (already open) — the payload sequences themselves.** Note this is blocking two
> things, not one: `AntisenseNotGate.__init__` requires a real payload CDS today, and
> validates that it starts with a start codon.

Until Q11/Q13 are answered, stage 5 can still be built and tested end to end against a
**caller-supplied** backbone and payload, because both arrive from outside the table.

---

## 5. Build it or borrow it? — the OpenCloning question, measured

An integration brief proposes adopting the OpenCloning ecosystem for this stage. Its
central recommendation is right, its frontend recommendation is not, and both halves are
testable rather than arguable. Everything in this section was run.

### 5.1 What `pydna` actually gives — POC run in full

The brief's Phase-1 spike, executed: a fixture backbone with AmpR and origin features, a
CERNAL gate sequence, a GFP payload, assembled and serialised.

```
assembled: 271 bp   circular=True
features carried through: 4
  CDS             0-80   AmpR
  rep_origin     80-160  pUC ori
  misc_feature  162-208  toehold switch sw-000001
  CDS           208-271  GFP

gate occurrences in construct: 1
payload occurrences:           1
backbone occurrences:          1
```

Feature coordinates survive concatenation and land where they should. The CERNAL gate
appears **exactly once, byte for byte**. GenBank round-trip:

```
header: LOCUS  name  271 bp  DNA  circular  UNK 01-JAN-1980
sequence identical after round-trip: True
features preserved: 4
custom cernal_* qualifiers survived on 2 feature(s):
  toehold switch sw-000001: cernal_role=logic_gate, cernal_gate_family=toehold, cernal_gate_id=sw-000001
  GFP: cernal_role=payload
```

That settles an open question in the brief's §6, which says to *"check BioPython/GenBank
serialization behavior before settling on qualifier names"*: **arbitrary `cernal_*`
qualifiers survive serialisation and reparse intact.** Output is deterministic across
runs.

**And then the finding that decides it.** §7.3 of this document records that
`Plasmid.sequence` is a linear concatenation, so a restriction site formed across the
circular origin join is invisible. Biopython handles that natively:

```
the origin join reads: ...GAA|TTC... = GAATTC
EcoRI on the LINEAR same sequence:   []
EcoRI on the CIRCULAR record:        [61]
```

CERNAL would otherwise hand-roll this, and hand-rolling it means re-deriving the correct
wrap length per enzyme and getting the reported coordinate right. **This is the strongest
single argument for the dependency**: it is not that the assembly is hard, it is that the
*circular* correctness conditions are easy to believe you have handled.

### 5.2 What it costs, measured

```
21 packages, 119 MB installed
largest: numpy 32M (+27M libs), Bio 17M, networkx 13M, pydivsufsort 8.4M, pyfiglet 5.7M
import pydna.dseqrecord: 0.33s      django imported? False
```

Boundary-safe — it imports nothing from Django, so [`tests/test_boundary.py`](../tests/test_boundary.py)
stays green. `numpy` was already planned for the `engine` extra by [ROADMAP.md](ROADMAP.md)
E0, so the marginal cost over the planned baseline is roughly 50 MB and ~19 packages.

Licences of the direct additions:

| Package | Version | Licence |
|---|---|---|
| `pydna` | 5.5.16 | BSD |
| `biopython` | 1.88 | **`LicenseRef-Biopython-License-Agreement`** — permissive and MIT-like, but **not a standard SPDX identifier**, and a licence scanner will flag it |
| `opencloning-linkml` | 1.0.0 | MIT |
| `networkx` | 3.6.1 | BSD-3-Clause |
| `seguid`, `pydivsufsort` | — | MIT |

Two notes worth carrying into the dependency review the brief's §14 asks for. First,
Biopython's non-SPDX licence reference is the one line item that needs a human decision
rather than a checkbox. Second, and unexpectedly:

> **`pydna` already depends on `opencloning-linkml`.** Installing pydna pulls
> OpenCloning's LinkML data model in automatically.

That answers the brief's §11.1 question — *"can CERNAL construct OpenCloning
workflow/provenance objects without running FastAPI?"* — in the affirmative, and for
free. The OpenCloning-compatible provenance export it lists as a stretch goal does not
require the OpenCloning **backend service**, which CERNAL's §15 deployment constraints
rule out anyway.

### 5.3 The frontend packages do not fit, and the measurement is not close

The brief's Phase 6 proposes `@opencloning/ui`, falling back to the viewer underneath it.
Both were checked against what CERNAL actually is.

| | CERNAL frontend | `@opencloning/ui@1.9.2` | `@teselagen/ove@0.8.42` (the viewer underneath) |
|---|---|---|---|
| React | **19.2** | built for MUI 5 / React 18 | pins `react: ^18.3.1` |
| Styling | Tailwind + 26 Radix packages | **MUI 5** + emotion | **Blueprint.js 3.54** |
| State | none (React Query) | **Redux** via `@opencloning/store` | **Redux + redux-form + redux-act + redux-thunk + reselect** |
| Direct deps | 50 total | 15, incl. axios, zip.js | **46**, incl. `recompose`, `shortid`, `popper.js` v1 |

`@opencloning/ui` hard-depends on `@opencloning/store`, so the Redux stack is not
optional. Taking either one means adding a **second design system and a state library**
to a React 19 app that has neither, against a peer range that does not include React 19.

And the decisive part:

> **CERNAL already renders a plasmid map.** `frontend/src/components/results/PlasmidRing.tsx`
> is 149 lines, already draws proportional arcs sized by real base-pair length, and
> already colours by `SegmentKind`. It is not missing a viewer. It is missing *data* —
> today it receives `plasmid_segments: []` from every real run.

The brief's own §19 says *"do not fork the entire OpenCloning frontend just to get a
plasmid circle."* Measured, that applies to importing it too.

**Recommendation: decline both frontend packages.** Feed the existing `PlasmidRing` real
segments (§6 P5). If richer inspection — feature-level hover, sequence view — is wanted
later, that is a separate decision to take on its own merits, with `@teselagen/ove`'s 46
dependencies and React 18 pin priced in honestly.

### 5.4 Verdict, and what needs an ADR

**Take the Python half. Leave the JavaScript half. Do not add a service.**

```
CERNAL engine (pure Python, no Django)
      │
      ├── PlasmidBuilder ──► pydna / Biopython     ← borrow: circular records,
      │                                               annotations, GenBank, restriction
      └── artifacts ──► GenBank · FASTA · manifest

CERNAL React (React 19, Tailwind)
      └── PlasmidRing (already exists) ◄── real segments from the API
```

> **Superseded — see §13.** This was the verdict *before* implementation. Building P3/P4
> against real fixtures found that the "borrow" box above only needed Biopython, not
> pydna: circular concatenation and restriction screening turned out to be a few lines
> of pure Python once actually written, and GenBank export alone does not need pydna's
> `Dseqrecord` layer. [ADR 0007](decisions/0007-biopython-for-genbank-export.md) is the
> decision that was actually shipped. The frontend and service verdicts below stand
> unchanged.

The brief is right that a library integration beats standing up OpenCloning's FastAPI
service, and CERNAL's deployment constraints say the same thing independently.

**This needs an ADR before the dependency lands.** [docs/README.md](README.md) requires
one for *"adding a service (Redis, Postgres, Docker, S3) or splitting the repository"*.
Adding 21 packages and 119 MB to an engine whose entire dependency story today is
ViennaRNA is the same class of decision: it is hard to reverse once stage 5, stage 6's
GenBank export and the artifact format all assume Biopython records. The ADR should
record the Biopython licence reference, the React-19 incompatibility that rules out the
frontend packages, and the fact that `opencloning-linkml` arrives with pydna.
**[ADR 0007](decisions/0007-biopython-for-genbank-export.md) is the ADR that landed —
Biopython only, pydna evaluated and rejected on measurement.**

---

## 6. The minimal build list

Five items. None needs stage 4, `CodonOptimizer`, or a resolved Q6/Q7.

> **As built (§13): P3/P4 use plain Biopython, not pydna.** The text below is kept as
> written before implementation because the shape of the work did not change — only the
> dependency did. Read "pydna/Biopython" as "Biopython" throughout this section.

### P1 · The parts table

Module constants in `stages/plasmids.py`, shaped like `motifs.py`'s: a `dict` keyed by
host for promoter and terminator, and a `dict` keyed by `DesiredOutcome` for payload
CDSs. Start with whatever Q12 returns and leave the payload dict **empty** rather than
fabricating a GFP sequence from memory — an almost-right CDS is far worse than a missing
one, because it will be ordered.

### P2 · `payload_segment(outcome)`

Table lookup, then validate like any other input: whole codons, starts with ATG, **no
internal in-frame stop**, no forbidden motifs. `DesiredOutcome.CUSTOM` reads
`params["payload"]["custom_sequence"]` and gets the *same* validation — a pasted CDS is
the least trustworthy input in the system.

**Reuse the rules that already exist.** `AntisenseNotGate.__init__` validates a payload
CDS today — `to_rna`, then `is_valid_rna`, then `payload[:3] != sequences.START_CODON` —
and raises `ValueError` naming what it got. Two different definitions of "a valid
payload" in one engine is precisely the failure [CLAUDE.md](../CLAUDE.md) §1 is about.

### P3 · `build(circuit, outcome)` — assemble

Layout, in order: **promoter → switch → payload → terminator → backbone**, each a
`Segment` carrying its own `kind` so the map can label it.

`PlasmidDesign`, `Plasmid` and `Segment` stay CERNAL's types. As built, `build()` and
`payload_segment()` import no external library at all — concatenation is plain string
work on CERNAL's own types. Biopython appears only inside `to_genbank()`, the export
function, for the same reason nothing outside `gates/tools/folding.py` imports `RNA`.

Two rules that are easy to get wrong:

- **Convert the switch to DNA.** `GateDesign.sequence` is RNA by contract. §7.1.
- **Attribute every violation to a segment.** Positions are into the assembled string;
  the researcher needs to know *which part* carries the offending site, because that
  decides whether it is theirs to change.

Then check, and **record rather than repair**:

1. Restriction screening over the **whole assembled construct, treated as circular**
   (§5.1). `MotifScreener` still owns the RFC10/RFC1000 vocabulary and the homopolymer
   rule; Biopython's circular search is what makes the origin join visible.
2. Reading-frame continuity from the switch's ATG through the payload.
3. Total length against a synthesis cap — a module constant, owned by the team, like
   `MAX_HOMOPOLYMER`.

Stringify with `str(violation)`: `PlasmidDesign.violations` is `tuple[str, ...]`, and
`Violation.__str__` was written for it.

### P4 · Annotate, and export GenBank

Every CERNAL-produced region becomes a feature: `promoter`, `CDS` for the payload,
`terminator`, `misc_feature` for the switch, and the backbone's own features preserved
from whatever it was loaded from. Standard GenBank keys only; CERNAL metadata goes in
qualifiers (`cernal_role`, `cernal_gate_id`, `cernal_candidate_id`), which §5.1 measured
as surviving the round-trip.

Emit through `engine.artifacts.write_artifact` with `kind="genbank"` — a kind
[`reporting.py`](../src/engine/stages/reporting.py) already names — so it flows through
the existing checksum and download path with no new storage anywhere.

### P5 · Wire it into the direct pipeline

Synthesise the one-gene `CircuitCandidate` (§3), call `build` once per requested output,
and populate `design["plasmid_segments"]` with `{kind, name, length_bp}` per segment —
the shape `PlasmidSegment` already expects. **Sequences do not go on the wire**; they
belong in the GenBank and FASTA artifacts.

**Done when:** a `direct` run under `LocalEngine` returns candidates whose plasmid map
renders real proportional arcs, and whose GenBank artifact opens in SnapGene or Benchling
with the switch, payload and backbone features labelled.

---

## 7. Gotchas that will otherwise cost an afternoon

Each measured against this commit.

### 7.1 A switch is RNA; a plasmid is DNA

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

### 7.2 The junction site — the classic assembly failure

Neither part carries EcoRI. Joining them creates one:

```
left  part ends ...TCCATGGAAT   violations: 0
right part starts TCATGGTGAG... violations: 0
assembled (56 bp)               violations: 1
  -> restriction site 'EcoRI' (GAATTC) at position 24
```

Screening parts individually finds nothing. This is why both the stub docstring and
[ROADMAP.md](ROADMAP.md) E5 say to screen the assembly.

### 7.3 The circular join — the failure the *assembled* screen still misses

Screening the assembly is necessary and not sufficient. `Plasmid.sequence` is a linear
concatenation, and a restriction enzyme does not care where we chose to start writing the
sequence down:

```
linear scan of 55 bp:          1 violations
scan across the origin join:   2 violations
  -> missed by the linear scan: restriction site 'EcoRI' (GAATTC) at position 55
```

**§5.1 is the answer to this one** — Biopython's restriction search takes the topology as
an argument and finds it. Hand-rolling it is possible and is exactly where an off-by-one
lives.

### 7.4 Frame continuity — silent, and invisible to every other check

Fusing a payload onto a switch naively:

```
fused switch+payload: 74 nt, AUGs at (22, 43, 48)
first AUG at 22; in-frame stops downstream: (30,)
frame length from AUG: 52 nt (1 nt out of frame)
translates to: MAKLNGSMSW
```

Ten residues, then a premature stop — and the frame does not close. That construct
**assembles, screens clean, prices normally and expresses nothing.** The stub docstring
calls this join *"the one most likely to go wrong"*; `sequences.find_stops` and
`find_augs` make the check three lines.

### 7.5 A GenBank round-trip silently linearises the construct — in pydna, not in what shipped

The file is written correctly and Biopython parses the topology correctly. The **pydna
wrapper is where it would be lost, if pydna were in the path**:

```
LOCUS line:                      ... 32 bp  DNA  circular ...
Biopython annotations[topology]: circular
naive Dseqrecord(SeqRecord):     circular = False      ← wrong
pydna.parsers.parse():           circular = True       ← correct
```

Sequence identical, features identical, topology quietly gone. Any parse-back test that
checks only sequence and features will pass while asserting nothing about the one
property that makes it a plasmid. **As built, this landmine is moot — `to_genbank()`
never constructs a `Dseqrecord`, only a plain `Bio.SeqRecord`, which does not have this
problem.** It is recorded here, and in [ADR 0007](decisions/0007-biopython-for-genbank-export.md),
so it doesn't get rediscovered if `pydna` is ever adopted later for real multi-fragment
assembly. `tests/engine/test_plasmids.py`'s GenBank round-trip test still asserts
topology explicitly, on principle.

### 7.6 Repair policy is not uniform across the construct

Violations are recorded, not silently repaired — with one exception, and the boundary
matters:

- **Inside the payload CDS**, a synonymous rewrite can remove a site without changing the
  protein. Legitimate once `CodonOptimizer` exists, and must be *reported* when done.
- **Inside the switch**, never. Its structure was validated in stage 3; changing a base
  to remove a restriction site silently invalidates the fold that justified the design.

### 7.7 Two smaller ones

- **`PlasmidSegment.kind` in the frontend still lists `"marker"`**, which `SegmentKind`
  deliberately dropped (*"a selective marker **is** the payload"*). A real plasmid will
  never emit it. Stale union, worth trimming when P5 lands.
- **The map is dominated by the backbone.** Arcs are proportional, so a ~1.5 kb backbone
  beside a ~90 nt switch renders the switch as a sliver. Worth knowing before someone
  reports it as a bug.

---

## 8. What we deliberately skip — and what it costs

| Skipped | Why | What it costs |
|---|---|---|
| **Codon optimisation of the payload** | `CodonOptimizer` is two stubs and an empty table (§2) | The payload is emitted verbatim. A payload whose opening codons disturb the switch stem is *reported*, not fixed |
| **`translation_score` on the fused CDS** | Same | `GateDesign.translation_score` keeps its `0.0` default — but 0.0 is a *measured-worst* value, not a missing one. Prefer leaving the metric absent to scoring it as zero ([CLAUDE.md](../CLAUDE.md) §3) |
| **A named wet-lab assembly protocol** | Gibson, Golden Gate and restriction/ligation are different promises, and choosing one is a biology decision | The construct is a **composition**, not a cloning plan. §9 says how to label it |
| **Emitting RFC10 prefix/suffix scars** | Compliance *checking* and standard-compliant *formatting* are different jobs | Checked against RFC10, but not itself a drop-in RFC10 part |
| **Multi-switch layout** | Needs a scientific answer (below) | Single-switch circuits only — which is every `direct` run |
| **OpenCloning frontend packages** | §5.3, measured | The existing `PlasmidRing` renders the map; no feature-level hover or sequence view yet |
| **An OpenCloning service** | [ROADMAP.md](ROADMAP.md) deployment constraints, and the library covers it | No cloning-history UI. `opencloning-linkml` still allows exporting a compatible workflow file later |

The multi-switch question should be asked alongside Q12/Q13. When a circuit needs several
switches — `A AND NOT B` with an antisense NOT — the stub says each needs *"its own
promoter and terminator"*, which is a layout rule. It does not say whether each
transcriptional unit carries its own payload copy or only the one driving the output
does. That changes the construct, and it is a biology decision.

---

## 9. Say what this is, and what it is not

A GenBank file that opens cleanly in SnapGene looks finished in a way a score does not.
CERNAL already refuses to let `MockEngine` output pass as prediction — the footer says
*"Mock engine — results are simulated"* — and the same discipline applies harder here,
because this artifact is the one someone spends money on.

- Call it a **computationally assembled construct**, never "ready to order" or
  "validated".
- Surface the violations and the assumptions next to the download, not behind it.
- A construct built with no named assembly method has not been claimed to be clonable by
  any particular protocol. Say so rather than implying Gibson because the code could have
  used it.
- When the payload came from the table rather than from codon-optimised design, that is a
  fact about the construct and belongs in the manifest.

---

## 10. How we will know it worked

**Status: done, for the `direct` path — see §13.** Checked off against
`tests/engine/test_plasmids.py` (36 tests) and a manual end-to-end run through the real
Django platform layer.

1. `tests/engine/test_plasmids.py` — a clean design produces `is_compliant=True`; EcoRI
   seeded across a junction produces exactly one violation naming EcoRI; a site across
   the **origin join** is caught; an out-of-frame payload is caught. **Done.**
2. A golden fixture: one small backbone, one gate, one payload, locked down by final
   sequence checksum, length, topology, and feature names in order. Parse back with
   `Bio.SeqIO.read()` and assert **topology explicitly** (§7.5 — pydna is not in the
   path, so its landmine does not apply, but the assertion is kept anyway). **Done.**
3. A `direct` run under `LocalEngine` returns `plasmid_segments` with four kinds
   (promoter, switch, payload, terminator — no backbone configured yet, §4/Q13), lengths
   summing to `Plasmid.length_bp`, and no `U` in any emitted sequence. **Done**, verified
   through `apps.analyses.services.submit_run`/`execute_run`, not just engine unit tests.
4. The GenBank artifact opens correctly — verified by parsing it back with Biopython and
   checking topology and feature count; not yet manually opened in SnapGene or Benchling.
5. `tests/test_boundary.py` still passes — Biopython imports no Django. **Done**; also
   true that pydna was never added, so its own import chain is moot.
6. Two runs with the same seed produce byte-identical constructs. **Implied** by the
   builder having no randomness in its path (CLAUDE.md §6), not yet a dedicated test.

---

## 11. Sequencing

```
ADR: Biopython, not pydna ──► P1 parts table ──► P2 payload_segment ──► P3 build ──► P4 GenBank ──► P5 wire in
        (0007, §13)                ▲                                        ▲
Q12 (promoter/terminator) ─────────┤                     Q13 backbone ──────┘
Q11 (payloads) ────────────────────┘
```

P3 and P4 can be written and tested against hand-made segments **before** any question is
answered — screening, framing and length logic does not care where the bases came from.
Only P5, which puts a construct in front of a researcher, needs Q11 and Q13.

**As built:** P1–P5 all shipped (§13), using a provisional catalogue for Q12
(J23119/B0015) and GFP for Q11's most common case, with Q11's remaining outcomes and
Q13 (backbone) still open — a `direct` run today produces a backbone-less construct
unless one is injected.

---

## 12. Rows for ROADMAP.md

For §2, the open questions table:

| # | Question | Blocks |
|---|---|---|
| **Q12** | Which constitutive promoter and terminator, per host? Provisional J23119/B0015 unblocks *E. coli*; yeast and human need their own, and the defaults need to be a decision rather than a placeholder | E5a |
| **Q13** | What backbone does the team build into? **A GenBank file of the plasmid the lab already transforms is the ideal answer** — origin and marker annotations come with it | E5a |

For §5, as a carve-out of E5 in the same shape as E2a:

### E5a · The first orderable construct — `direct` path only

`PlasmidBuilder` on the single-switch circuit a `direct` run already produces, skipping
stage 4 the way [smoke-run.md](smoke-run.md) skipped stages 1–2. Parts table in
`stages/plasmids.py` following `motifs.py`'s precedent; backbone injected or loaded from
GenBank. Assembly, annotation and GenBank export through **pydna/Biopython**, confined to
`stages/plasmids.py` the way `RNA` is confined to `gates/tools/folding.py`. Restriction
screening on the whole construct **as circular**. Frame continuity from the switch's ATG
through the payload. Violations recorded, never silently repaired. No codon optimisation —
`CodonOptimizer` is still stubbed and its table is empty. Labelled a *computationally
assembled construct* (§9).

Blocked on **Q11**, **Q12**, **Q13** for real parts; unblocked for the logic itself.
**Needs an ADR first** (§5.4).

**Done when:** a `direct` run under `LocalEngine` populates `plasmid_segments` with real
lengths, the existing `PlasmidRing` renders from real data, the GenBank artifact opens
annotated in SnapGene, and `tests/engine/test_plasmids.py` locks in the failure modes in
§7.

### ADR · Adopt Biopython in the engine (pydna rejected) — **done**

Filed as [0007-biopython-for-genbank-export.md](decisions/0007-biopython-for-genbank-export.md).
Records the decision actually shipped: Biopython only, confined to the GenBank-export
function; pydna evaluated directly and rejected once circular screening and assembly
turned out not to need a library at all (§13); Biopython's non-SPDX licence reference
recorded in [attribution.md](attribution.md); the OpenCloning frontend packages and the
OpenCloning service out of scope, with §5.3's measurements as the reason.

---

## 13. What actually got built, and where it differs from §5–§12

E5a shipped. This section is the honest diff between the plan above and
`src/engine/stages/plasmids.py` / `src/engine/pipeline.py` as merged, written after
implementation rather than revising the sections above out from under their own
evidence.

### 13.1 The one real course correction: no pydna

§5 recommended adopting `pydna` alongside Biopython. Building P3 (`build()`) and P4
(`to_genbank`) against real fixtures — not just the brief's Phase-1 spike — found that
nothing past that spike was actually needed:

- **Circular restriction screening** does not need `Bio.Restriction` or `Dseqrecord`.
  `MotifScreener.violations()` gained a `circular: bool = False` keyword; when set, it
  additionally scans `sequence + sequence[:pad]` (padded by the longest configured site
  minus one) and merges in only the newly-found violations. Same regex-based screener,
  same `RFC10_SITES`/`RNASE_SITES` tables, no second definition of "forbidden site" to
  keep in sync with `MotifScreener`'s.
- **Assembly** is `Segment`/`Plasmid` concatenation, which already existed in
  `engine/domain.py` before this work — there was never anything for `Dseqrecord`'s `+`
  to add.
- **GenBank export** round-trips correctly from a plain `Bio.SeqRecord` with
  `annotations["topology"] = "circular"`. No `pydna` wrapper is involved, so §7.5's
  landmine (`Dseqrecord(SeqIO.read(...))` silently dropping topology) never applies to
  the shipped code — it's recorded in §7.5 and [ADR 0007](decisions/0007-biopython-for-genbank-export.md)
  purely so nobody re-discovers it if `pydna` is adopted later for real multi-fragment
  assembly (Gibson, Golden Gate — still out of scope).

Net effect: one dependency (`biopython`), not two. `pyproject.toml` never gained
`pydna`. [ADR 0007](decisions/0007-biopython-for-genbank-export.md) documents this as
the final decision; §5's pydna measurements stand as the evidence that prompted looking
harder at the problem, not as the shipped design.

### 13.2 What's real today, and what's still a placeholder

```
src/engine/stages/plasmids.py
  PROMOTERS   = {Host.ECOLI: ("J23119", ...)}      ← Q12: E. coli only
  TERMINATORS = {Host.ECOLI: ("B0015", ...)}       ← Q12: E. coli only
  PAYLOADS    = {DesiredOutcome.GFP: ("GFP", ...)} ← Q11: GFP only; mCherry, luciferase,
                                                       AmpR, apoptosis inducer still absent
  validate_payload_cds()  — real: to_rna → is_valid_rna → start codon → whole-codon
                             length → trailing-stop-only rule
  PlasmidBuilder.build()          — real
  PlasmidBuilder.payload_segment() — real
  to_genbank()                    — real, the only function in the module that imports
                                     Biopython
```

A `direct` run today can only build a **GFP construct for *E. coli***. Any other
requested output (`mcherry`, `luciferase`, `antibiotic`, `apoptosis`) is skipped with a
warning by `pipeline._resolve_outputs`, or the whole run hard-fails with
`InputValidationError` if every requested output is unbuildable — the same
skip-and-warn-or-hard-fail shape `pipeline.py` already used for gate families. `CUSTOM`
works today: a caller-supplied `params["payload"]["custom_sequence"]` goes through the
identical `validate_payload_cds` check as a catalogue entry.

**Q13 (backbone) is still open.** `PlasmidBuilder(backbone=())` is the default the
pipeline constructs with — a `direct` run's construct today is promoter + switch +
payload + terminator, no origin, no selection marker. `Plasmid.plasmid.segments` is
correspondingly four kinds, not five; §10's original "five kinds" checklist entry
reflected the plan, not the current backbone-less reality.

**`CodonOptimizer` is still stubbed**, exactly as §2 and §8 said it would remain — the
payload is emitted verbatim, never codon-optimised, never rewritten to remove a
restriction site.

### 13.3 Two small design decisions §6 didn't spell out

- **Stage 5 doesn't wait for stage 4, as §3 predicted** — `pipeline._build_plasmid` hand-
  builds a placeholder single-gene `CircuitCandidate` per candidate, mirroring
  `_direct_trigger`'s existing pattern for stages 1–2. That candidate's `ConfusionMatrix`
  and `LogicGraph` are never read by `PlasmidBuilder.build()`; they exist only to satisfy
  the type signature.
- **Frame continuity (§7.4) treats a trailing run of stop codons as one terminal stop**,
  not a violation — real GFP's own CDS ends `...UAA UAA`, and rejecting that would make
  the shipped payload fail its own builder's check. A stop codon *before* the last codon
  is still a violation.

### 13.4 Verification

`tests/engine/test_plasmids.py` (36 tests) covers a clean build, the junction-site case
(§7.2), the circular-origin-join case (§7.3, via injected backbone segments so the
junction is deterministic), frame continuity (§7.4), CUSTOM payload validation, and a
golden fixture locking the exact segment order, lengths (930 bp total) and GenBank
header. `tests/engine/test_pipeline.py` covers the pipeline wiring: real segments in
`plasmid_segments`, a GenBank artifact per accepted candidate, unconfigured/unknown
outputs, mixed buildable/unbuildable outputs, and that circular screening is actually
requested during a run. Beyond engine unit tests, a manual run through
`apps.analyses.services.submit_run`/`execute_run` (the real Django platform layer, real
`LocalEngine`, not `MockEngine`) confirmed a `COMPLETED` run with real GenBank artifacts
and correctly populated `plasmid_segments`/`logic_graph.output`.
