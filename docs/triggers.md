# Stage 2 — what it takes to choose a trigger

**Status:** Built (E2b, `direct` path). T1-T3 below shipped; §6 records what was actually
built and one deliberate divergence from this document's own first-draft recommendation,
found during implementation review.
**Question it answers:** *"A researcher pastes an RNA sequence. Sometimes it is the trigger.
Sometimes it is a whole transcript we are supposed to find triggers in. What does CERNAL do
today, and what should it do?"*
**Companion documents:** [`ROADMAP.md`](ROADMAP.md) §2 Q1 and §5 E2 are the tasks this is a
subset of; [`smoke-run.md`](smoke-run.md) and [`plasmids.md`](plasmids.md) are the same
exercise for stages 3 and 5, and the model this follows;
[`modalities.md`](modalities.md) §A2 defines what `direct` mode is;
[`engine.md`](engine.md) is the architecture.

> **This is a design document, not a planning file.** [ROADMAP.md](ROADMAP.md) is the
> single place work is recorded. §10 below gives the rows to paste into it. This file
> holds the *evidence and the reasoning*; the ROADMAP holds the *work*.

Every measurement below was run against this commit, against the real `ToeholdGate`, the
real `SwitchValidator` and the real `FoldProfiler` — no mocks. The transcript used
throughout is the 711 nt mCherry CDS, because that is what a researcher actually pasted
in and got zero candidates from.

---

## 1. The verdict

**Three findings, and the first one reframes the whole problem.**

**(a) Trigger selection is already written.** `TriggerScorer.score`
(`stages/triggers.py:142-193`) is **built and tested** — a real sliding-window scan that
screens motifs, slices a per-transcript accessibility profile, folds each window, records
AUG/stop positions, and keeps a top-K per gene. It was ported from a validated external
script (PR #14) and has its own test file. This was not a stub anyone needs to write.

**It has never been called.** `TriggerScorer` is constructed nowhere in `src/` — only in
`tests/engine/test_triggers.py`. `build_tools` does not build it, `run_pipeline` does not
call it.

**(b) One stub blocks it, and the fix is already precedented.** `score()` calls
`self.off_target.scan_trigger(window)` at line 166, and that method raises:

```
OffTargetScanner({}).scan_trigger("ACGU…") -> NotImplementedError: Step 5
```

So the scanner cannot run today at all. But `direct` mode has no transcriptome to scan
against in the first place, and `_direct_trigger` already decided what to do about that
(`pipeline.py:451-456`): record `0.0`/`1.0` as "clean", say so, and move on. Applying the
same decision one layer down is what unblocks stage 2 on the `direct` path — **without
answering Q1**, exactly as E5a shipped stage 5 without stage 4.

**(c) The selection criteria screen the wrong object.** This is the finding that matters
scientifically. `TriggerScorer` screens the **window**; every failure that actually kills a
design is a property of the **assembled switch**. Measured over all 676 36-nt windows of
mCherry:

```
rejected by TriggerScorer's window screen :  31
actually unusable at switch level         : 337

  screen says bad AND switch bad          :  31
  screen says bad BUT switch fine         :   0   <- no false positives
  screen says FINE but switch bad         : 306   <- 91% of failures, missed
```

The screen is *sound* and *radically incomplete*. A trigger-selection stage that passes
91% of unusable windows is not selecting.

---

## 2. What is actually in place

The dependency chain, measured. One link is broken.

| Component | Status | Note |
|---|---|---|
| `sequences.windows` (S6) | ✅ built | The sliding window itself |
| `MotifScreener.violations` (S7) | ✅ built | Restriction sites, homopolymers |
| `FoldEngine.mfe` (S2) | ✅ built and cached | Per-window folding energy |
| `FoldProfiler.profile`/`.openness` (S1) | ✅ built | E2a-4. Windowed RNAplfold |
| **`TriggerScorer.score`** | ✅ **built and tested** | Never called from `src/` |
| `OffTargetScanner.scan_trigger` (S5) | ✗ **STUB** | **The one blocker.** Raises `Step 5` |
| `GeneSelector.select` (stage 1) | ✗ stub | Only needed for `de`; `direct` can synthesise |
| A transcriptome (`sequences` dict) | ✗ **Q1** | Only needed for `de`; in `direct` the paste *is* the transcript |

`tests/engine/test_triggers.py`'s own docstring says *"`FoldProfiler` and
`OffTargetScanner` are still stubs"*. That is now half stale — `FoldProfiler` was built in
E2a-4. Worth correcting when this stage is touched.

---

## 3. The ambiguity the input box hides

A pasted RNA sequence can mean two different things, and the wizard has one box for both:

| The researcher means | Typical length | What they want |
|---|---|---|
| **"This *is* my trigger."** | 30–36 nt | Build a switch against exactly this |
| **"This is my target transcript — find triggers in it."** | 100s–1000s nt (sRNA, lncRNA, mRNA) | Scan it, rank windows, pick good ones |

**Today the engine always assumes the first**, silently. `_direct_trigger`'s docstring is
explicit — *"the pasted sequence **is** the one trigger, at full length, offset 0"*.

That is a defensible contract for case 1 and a **silent wrong answer** for case 2, because
the whole paste does not get used. `ToeholdGate.generate_designs` takes
`reverse_complement(trigger.sequence)` and consumes only its first `toehold + 18`
nucleotides, which is the **tail** of the original:

```
pasted length: 711
binding_region[:36]      : UUACUUGUACAGCUCGUCCAUGCCGCCGGUGGAGUG
revcomp(last 36 of paste): UUACUUGUACAGCUCGUCCAUGCCGCCGGUGGAGUG
identical: True
=> the first 675 nt of the paste are structurally unused.
```

Nothing errors. Nothing warns. A 711 nt mRNA silently becomes a switch designed against
its final 36 nucleotides — a biologically arbitrary choice, presented as a result. That is
the failure mode [CLAUDE.md](../CLAUDE.md) §3 exists to prevent, one layer up from where it
usually gets discussed.

**And the arbitrary choice is measurably a bad one.** The accessibility of the tail versus
the best window available in the same transcript:

```
the used last 36nt : openness=0.6014  accessibility(min)=0.000395
BEST 36nt window   : openness=0.5303  accessibility(min)=0.238419  at offset 293
```

A **600×** difference in the metric `DEFAULT_V1` weights at 2.0, discarded by not looking.

### 3.1 Two minimum lengths, neither of them stated

A 27 nt paste — a real one, from a real run — passes the pipeline's own check and then
fails silently:

- `_direct_trigger` (`pipeline.py:430`) rejects below **20 nt**: *"at least 20 nucleotides
  are needed"*.
- `ToeholdGate.is_compatible` rejects below **30 nt**: *"too short to supply a toehold and
  stem even at the shortest swept toehold length"*.

Between 20 and 29 nt a submission is accepted, produces zero designs, and reports
`"No candidate designs passed validation for this trigger"` — a message that names neither
the real limit nor the real reason, because `SwitchDesigner.design` (`switches.py:101-102`)
drops `compatibility.reason` on the floor with `continue`.

---

## 4. The criteria screen the wrong object

§1(c) gave the headline number. Here is what actually kills designs, across all 676 × 3
design attempts on mCherry:

```
per-design rejection reasons:
  1026  expected exactly one AUG
    99  restriction site 'PstI' (CTGCAG)
    51  homopolymer 'Gx6' (GGGGGG)
    38  in-frame stop codon(s) at [59]
    27  homopolymer 'Gx7' (GGGGGGG)
    26  in-frame stop codon(s) at [56]
    …
```

**The dominant failure by an order of magnitude is the AUG count** — and it is structurally
invisible to a window-level screen, for a reason worth stating plainly:

> The switch contains the trigger's reverse complement **and**, in the descending stem,
> segments reverse-complemented *back*. So an unwanted `AUG` in the finished switch can
> arise from an `AUG` in the window **or** from a `CAU` in it. `TriggerScorer` records
> `aug_indexes = find_augs(window)` — only one of the two directions, and it never filters
> on either; `score` ignores the field entirely.

Half of a real transcript is unusable, and the stage nominally responsible for choosing
usable windows sees almost none of it:

```
windows scanned      : 676
windows usable (>=1) : 339
windows unusable     : 337
```

### 4.1 The ranking formula is a declared placeholder

`score=accessibility * segment_specificity` (`triggers.py:188`), and the code says so
itself — *"a simple, explicitly-labelled placeholder combination … has not been reviewed by
the scientific team yet"*. Two consequences:

- `mfe` and `gc_content` are **computed and then unused** in ranking.
- With off-target stubbed, `segment_specificity` is a constant, so ranking collapses to
  **accessibility alone**.

---

## 5. What it costs — the objection that does not survive measurement

The obvious worry about checking constructibility per window is that it is expensive.
Measured on the 711 nt transcript, both length classes, 1,358 windows:

```
profile 711nt transcript once       :  0.041s
screen + fold + GC over 1358 windows:  0.181s   (0.13 ms/window)
constructibility check, 1358 windows:  0.042s   (0.03 ms/window)
  windows that can actually build    : 630 / 1358
```

**Building every candidate switch and validating it is ~4× cheaper than the MFE fold
`TriggerScorer` already performs per window**, because `generate_designs` and
`SwitchValidator`'s implemented rules are pure string operations — no folding
(`switches.py:213`). A complete, constructibility-aware scan of a real transcript costs
**under a quarter of a second**.

There is no performance argument for screening a proxy instead of the real thing here.

---

## 6. The minimal build list

Five items, in dependency order. None needs Q1, stage 1, or a transcriptome.

> **As built.** T1-T3 shipped. §6.1 below is the one deliberate divergence found during
> implementation review — everything else here matches what was proposed. T4/T5 stayed
> deferred, per this section's own original reasoning.

### T1 · Let the off-target scanner say "nothing to scan" — ✅ built

`scan_trigger` raises today, so `TriggerScorer.score` cannot execute at all. A `direct`
submission has no transcriptome by construction. Give the empty-index case a defined,
honest answer — a zero-penalty `OffTargetReport` plus a run-level warning that off-target
was **not measured** — reusing the wording `_direct_trigger` already settled on
(`pipeline.py:451-456`), rather than inventing a second convention.

**Do not** let this silently read as "clean" in the report. Unmeasured and clean are
different claims, and §9 is about not conflating them.

**Shipped exactly as proposed**, in both `OffTargetScanner.scan_trigger`/`.scan_switch`
(`stages/off_target.py`) and a one-time warning in `build_tools()`.

### T2 · Decide trigger-versus-transcript, and scan when it is a transcript — ✅ built, on a threshold

**Recommendation: always scan, and report the offset.** A 36 nt paste has exactly one
window, so the "precise trigger" case is the *n = 1* case of the general one — no mode
flag, no magic length threshold, one code path. Synthesise the single `SelectedGene` the
way `_direct_trigger` synthesises the `TriggerCandidate` and `_build_plasmid` synthesises
the `CircuitCandidate` (this pattern is now established twice), hand the paste in as the
transcript, and let the built `TriggerScorer.score` do its job.

The alternative — an explicit "this is my trigger / find triggers for me" control in the
wizard — is more honest about intent and costs a UI change plus a params field. Worth
doing **if** researchers turn out to want to force exactness; not worth doing first, since
with *n = 1* there is no other window to be surprised by.

Either way: **name the window that was chosen, with its offset**, in the run's warnings and
in the candidate's `design` JSON. A trigger the researcher did not type must never appear
without its provenance.

> **§6.1 — superseded by measurement.** "Always scan, no magic length threshold" is what
> was proposed above; it is not what shipped. Scanning unconditionally was measured, at
> implementation time, to take the existing `direct`-path reference scenario (the fixed
> 36 nt trigger every test and `smoke-run.md` itself uses) from **3 candidate designs to
> 7** — because even an exact, deliberately-sized 36 nt paste has seven 30 nt sub-windows
> once `constraints.trigger_lengths = (30, 36)` is swept over it. That directly
> contradicts an existing, already-shipped principle in
> [smoke-run.md §5](smoke-run.md): *"Three designs from one trigger at default
> constraints — which is exactly what a smoke run wants. Do not widen trigger_lengths to
> 'get more results.'"*
>
> **What shipped instead:** scan only when the paste is longer than
> `max(constraints.trigger_lengths)` — derived from the run's own configured window
> sizes, not a hardcoded constant, so it moves if `trigger_lengths` is ever overridden.
> At or under that length, behaviour is byte-for-byte what it always was. This keeps
> the "no magic threshold" property in spirit (the cutoff is a computed property of the
> constraints already in play, not an arbitrary number) while preserving the documented
> reference behaviour. Also added: a `MAX_TRIGGER_LENGTH` upper bound (10,000 nt) — a
> pathological paste (a plasmid or genome, pasted by mistake) has no cancellation
> checkpoint mid-scan, so an unbounded top end was a real gap this document's own §5
> measurement did not price in.
>
> **A gap this closed as a side effect, not by design:** §3.1's 20-29 nt gray zone
> (passes the ≥20 nt floor, then silently fails `ToeholdGate.is_compatible`'s 30 nt
> footprint check) is now correctly reported, because T3's `on_incompatible` surfaces
> `Compatibility.reason` regardless of whether scanning happens — the fix was in T3, not
> in the threshold choice.
>
> **Also found and fixed during review, not originally scoped here:** `TriggerScorer`
> mints its own `f"trig-{gene_id}-{start}-{length}"` IDs rather than going through
> `CandidateStore`, contradicting `TriggerCandidate.trigger_id`'s own documented contract
> ("minted by `CandidateStore`"). Harmless while nothing outside its own tests
> constructed one; re-minted through `store.mint_id("trig")` at the point this is first
> exposed in a real run, without touching `triggers.py`'s tested code.

### T3 · Stop discarding the reasons — ✅ built

Three places currently drop the explanation of why nothing survived:

- `SwitchDesigner.design` (`switches.py:101-102`) — `if not compatibility.ok: continue`.
- The same loop discards every `ValidationResult.violations`.
- `run_pipeline` can then only emit its generic *"No candidate designs passed validation"*.

Collect them and surface a summary: *"1,358 windows scanned, 630 constructible, 0 survived
scoring — 1,026 rejected for a second start codon."* This is the single highest
value-per-line change in this document, and it is independent of everything else here.

**Shipped as two separate, optional callbacks** on `SwitchDesigner.design` —
`on_incompatible`/`on_invalid` — kept apart rather than one merged tally, because
`Compatibility` rejections are counted per trigger-set and `ValidationResult` rejections
per generated design, different units that would otherwise misleadingly compare as one
total. Messages are generalized for bucketing (positions and counts collapsed, e.g. every
"expected exactly one AUG, found N at [...]" merges regardless of which AUG count or
positions), but the **displayed** text is always one real, unmodified example message,
never the generalized template.

**One bug this exposed, found only by tracing what scanning would newly make reachable,
not anticipated in this document's first draft:** `ToeholdAndGate` and its two
host-specific subclasses have `available = True` inherited from `ToeholdGate`, while
`generate_designs` is an unconditional `NotImplementedError`. A single-trigger `direct`
run never reached it (arity always rejects a 1-activator set first); a scanned,
multi-candidate run can produce real 2-activator trigger sets, which would have reached
`generate_designs` and crashed the run uncaught — `LocalEngine.run()` only catches
`JobCancelled`/`EngineError`. Fixed by adding the three AND family names to
`pipeline._UNBUILDABLE_FAMILIES`, the same "skip and say why" mechanism already used for
`antisense` — no `engine/gates/` edit needed.

### T4 · Make the length classes follow the gates — still open

`Constraints.trigger_lengths` is `(30, 36)`; `ToeholdGate`'s footprints are
`toehold + 18 = (30, 33, 36)`. Measured:

```
a 30nt trigger yields 1 design(s)
a 33nt trigger yields 2 design(s)
a 36nt trigger yields 3 design(s)
```

So a 30 nt window silently explores one third of the design space a 36 nt window does, and
the `toehold_length=15` variant is unreachable from either declared class. Derive the
scanned lengths from the participating families' actual footprints rather than a constant
that half-matches.

### T5 · Rank on constructibility, once T1–T4 are in — not needed as built

Given §5's timings, the cheapest and most predictive filter available is *"can a real
switch be built from this window?"* — 91% of the failures the current screen misses.
Because `stages → gates` is a **downward** import ([CLAUDE.md](../CLAUDE.md) §4), a stage may
legally ask a gate family this.

But prefer the smaller change first: `SwitchDesigner` *already* filters unconstructible
designs. Once T2 feeds it 1,358 windows instead of 1, its existing filter finds the 630
that build, and nothing new is needed. Make `TriggerScorer` gate-aware only if ranking —
not merely surviving — turns out to need it.

**Confirmed as built, without touching `TriggerScorer`.** `_direct_trigger` feeds
`TriggerScorer.score`'s already-ranked, already-top-K output straight into
`SwitchDesigner.design`, which already discards anything unconstructible on its own — this
was the actual, only mechanism exercised in the mCherry re-run below. `TriggerScorer`
itself was never made gate-aware, because *ranking* has not yet needed to be — surviving
was enough to turn the reported failure into real candidates.

**Done when:** a `direct` run given a full mRNA returns candidates built against a named,
justified window, and a run that returns none says which rule rejected how many. ✅ —
resubmitting the exact 711 nt mCherry CDS from §1 now returns 41 real, non-rejected
candidates, each carrying the scanned window's offset, instead of 0.

---

## 7. Gotchas

- **`reverse_complement` puts the 3′ end first.** Every "which part of the trigger is used"
  intuition is backwards unless you hold this in mind. §3's measurement exists because the
  natural guess — that a long paste uses its *beginning* — is wrong.
- **`AUG` in the window and `CAU` in the window are both dangerous**, for opposite strands
  of the finished switch. Checking one is worse than useless, because it looks like
  checking.
- **`accessibility = min(profile)` is length-confounded.** A minimum over 711 positions is
  dominated by whichever single base is most paired anywhere in the transcript. Taken over
  a whole paste rather than the bound window, it measures length as much as quality.
- **Profile the transcript once, slice per window.** `TriggerScorer` already does this
  (`triggers.py:147`) and its docstring warns that per-window profiling is quadratic. The
  0.041 s in §5 is that decision paying off.
- **`TOP_K_PER_GENE = 50` is a class constant, not a constraint.** Deliberate — the code
  explains why — but it means the search budget is not recorded in `params_snapshot` with
  everything else that shaped a run.

---

## 8. What we deliberately skip — and what it costs

| Skipped | Why | What it costs |
|---|---|---|
| **Real off-target scanning** | `OffTargetScanner` is four stubs and needs Q1's transcriptome | `off_target_penalty` is unmeasured, and `segment_specificity` with it. Must be **reported as unmeasured**, never as 0.0-means-clean |
| **`GeneSelector` / the `de` path** | Blocked on Q1 | `direct` only. One transcript at a time, supplied by the researcher |
| **A reviewed ranking formula** | Q6, and `triggers.py` says its own formula is a placeholder | Windows are ordered by accessibility alone. Good enough to *choose a buildable one*, not to claim the best one |
| **Paralogue-aware specificity** | No paralogue search exists; the code approximates it from the off-target report | Cannot distinguish a gene from its family. For a `direct` run with one pasted transcript, there is nothing to compare against anyway |
| **RNA-class-specific rules** | Nobody has decided them — see §9 | An sRNA, a lncRNA and an mRNA are scanned identically today |

---

## 9. Say what this is, and what it is not

A chosen window is a **recommendation from a partial model**, and the parts that are
missing are not small:

- Off-target is **not measured** on the `direct` path. A window that looks perfectly
  specific has simply never been compared against anything.
- The ranking is **accessibility**, not a validated composite.
- "Constructible" means *this engine's current rules did not reject it* — not that it will
  work in a cell.

Report the window's offset, the number of windows considered, and what was not measured,
next to the result rather than behind it — the same discipline
[plasmids.md](plasmids.md) §9 applies to a GenBank file.

---

## 10. Rows for ROADMAP.md

For §2, the open questions table:

| # | Question | Blocks |
|---|---|---|
| **Q14** | **Does the RNA class change the rules?** A trigger window inside an mRNA's CDS, its 5′UTR, a lncRNA, or a small RNA are not equivalent choices — an sRNA may be functional only as a whole, and a CDS window is dense with start codons (measured: the #1 cause of design rejection). Should the scan prefer, avoid or weight regions by class? | E2b |
| **Q15** | **What makes a trigger good, beyond buildable?** `score = accessibility × segment_specificity` is a self-declared placeholder that ignores the MFE and GC it already computes. Needs a reviewed formula before any ranking is presented as a recommendation | E2b, and Q6 |

For §5, as a carve-out of E2 in the same shape as E2a and E5a:

### E2b · Trigger selection on the `direct` path

`TriggerScorer.score` is **already built and tested** and has never been called. Unblock it
without Q1: give `OffTargetScanner` a defined empty-transcriptome answer (T1), synthesise
the single `SelectedGene` the way `_direct_trigger` synthesises its `TriggerCandidate`,
scan the pasted sequence as the transcript (T2), surface the rejection reasons that three
call sites currently discard (T3), and derive the scanned lengths from the gate families'
real footprints (T4). Constructibility-aware *ranking* (T5) only if ranking needs it —
`SwitchDesigner` already filters, and measured, the check costs 0.03 ms/window.

Blocked on **Q14**, **Q15** for a defensible *ranking*; unblocked for *choosing a window
that builds*.

**Done when:** a `direct` run given a full mRNA returns candidates built against a named
window at a reported offset, a run that returns none names the rule that rejected how many,
and off-target is reported as unmeasured rather than clean.
