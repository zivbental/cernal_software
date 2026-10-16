# 0007 — Biopython for GenBank export, not pydna

**Status:** Accepted
**Extends:** E5a ([ROADMAP.md](../ROADMAP.md)), evidence in [plasmids.md](../plasmids.md) §5

## Context

Stage 5 (`PlasmidBuilder`) needs to concatenate parts into a circular construct,
preserve feature annotations through that concatenation, screen the assembled sequence
for restriction sites, and export GenBank. An integration brief proposed evaluating the
OpenCloning ecosystem for this, centred on `pydna`. [plasmids.md](../plasmids.md) §5
tested that proposal rather than reasoning about it, and testing narrowed it further
than the brief anticipated.

**The circular-restriction-site problem does not need a library.** `Plasmid.sequence`
is a linear concatenation, so a site formed across the origin join is invisible to a
linear scan — the finding that originally motivated this ADR. Measured: padding the
sequence with its own prefix (`sequence + sequence[:longest_site - 1]`) and re-running
`MotifScreener.violations()` — CERNAL's own regex-based screener, unchanged — catches
the wrapped site correctly, with no new dependency. `Bio.Restriction`'s enzyme
database was never adopted: it would have been a second, independently-maintained
definition of "which sites are forbidden" beside `MotifScreener`'s `RFC10_SITES` table,
which is exactly the duplication [CLAUDE.md](../CLAUDE.md) §1 warns against.

**The assembly itself does not need a library either.** CERNAL's own `Plasmid` and
`Segment` (`engine/domain.py`) already concatenate parts and compute total length in
pure Python; there is nothing for `Dseqrecord`'s `+`/`.looped()` to add there.

**GenBank export is the one real requirement**, and testing it in isolation — plain
`Bio.SeqRecord` with `annotations["topology"] = "circular"`, no `pydna` involved —
round-trips correctly: sequence, features, arbitrary `cernal_*` qualifiers, and
topology all survive a `.format("gb")` / `SeqIO.read()` cycle intact.

**pydna was evaluated directly and rejected on measurement.** Its own Phase-1-style
spike worked, and it does depend only on Biopython plus `numpy` beyond its own
data-model layer (`opencloning-linkml`, `pydivsufsort`, `seguid`, `pyfiglet`,
`networkx` — 21 packages, 119 MB total). But every capability that spike exercised —
circular concatenation, annotation preservation, GenBank export — is covered by
Biopython alone, at roughly a tenth of the footprint (2 packages beyond what
[ROADMAP.md](../ROADMAP.md) E0 already budgets: Biopython plus the `numpy` it
requires). pydna also introduced its own gotcha with no compensating benefit:
`Dseqrecord(SeqIO.read(...))` on a parsed record silently drops circular topology
while sequence and features still compare equal — plain `Bio.SeqIO.read()` does not
have this problem, because it returns a `SeqRecord`, not a `Dseqrecord`.

## Decision

Add **Biopython only** as an engine dependency, confined to one function in
`src/engine/stages/plasmids.py` — the GenBank-export adapter — following the same
containment rule already applied to `RNA` (only `gates/tools/folding.py` and
`stages/folding.py` import it) and to Django (never inside `src/engine/`).
`PlasmidBuilder.build()` and `.payload_segment()` use no Biopython import at all: they
work entirely in CERNAL's own `Segment`/`Plasmid`/`PlasmidDesign` types plus
`sequences.py` and `MotifScreener`, exactly as the original stub signatures implied
before any dependency was considered. A `SeqRecord` is constructed, and discarded, only
inside the export function — it never crosses back into engine or Platform code.

**Explicitly out of scope, and rejected on measurement, not on principle:**

- **`pydna`.** Superseded by the finding above: nothing it offers over plain Biopython
  is actually used once the circular-screening and assembly logic turned out not to
  need a library at all.
- **The OpenCloning frontend packages** (`@opencloning/ui`, and the Open Vector Editor
  underneath it). `@opencloning/ui` hard-depends on Redux (via `@opencloning/store`)
  and MUI 5; `@teselagen/ove` pulls 46 direct dependencies including Blueprint.js, a
  full Redux stack, and packages unmaintained since 2018, and pins `react: ^18.3.1`.
  CERNAL is React 19.2, Tailwind, 26 Radix packages, no Redux, no MUI — adopting either
  means a second design system and state library in an app that has neither, against a
  peer range that excludes the React version CERNAL runs. CERNAL also already renders
  a plasmid map (`PlasmidRing.tsx`); it is missing real segment data, not a viewer.
- **The OpenCloning backend service.** [ROADMAP.md](../ROADMAP.md)'s deployment
  constraints (one web process, one worker, no second service) already rule this out.

## Consequences

**Gained.** Annotated, standards-conformant GenBank export with arbitrary CERNAL
qualifiers, at a cost of one dependency this project already needs for its own reasons
once `numpy` lands ([ROADMAP.md](../ROADMAP.md) E0).

**Given up.** Nothing measurable — no capability tested in [plasmids.md](../plasmids.md)
§5 required more than this. Biopython's licence is
`LicenseRef-Biopython-License-Agreement` — permissive and MIT-like in substance, but
**not a standard SPDX identifier**, so it needs its own line in
[attribution.md](../attribution.md) rather than folding into an "MIT" table row (done
in the same commit as the dependency).

**Gotcha recorded so nobody re-discovers it while adding pydna later:** if a future
change adopts `pydna` for real multi-fragment assembly work (Golden Gate, Gibson —
neither is in scope here), `Dseqrecord(SeqIO.read(...))` silently drops circular
topology while sequence and features still compare equal; `pydna.parsers.parse` keeps
it, and any parse-back test must assert topology explicitly rather than only sequence
and features.

**Revisit when** stage 5 needs a named wet-lab assembly protocol (Gibson overhangs,
Golden Gate/MoClo positions) rather than a composition — that is a real reason to
reconsider `pydna`'s assembly helpers or OpenCloning's Syntax Builder, priced on its own
merits against what it would add over Biopython at that point. It is also a real reason
the frontend recommendation above might be revisited separately, on its own merits.
