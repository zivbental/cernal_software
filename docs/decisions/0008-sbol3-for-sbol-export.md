# 0008 — sbol3 for SBOL export, not sbol-utilities

**Status:** Accepted
**Extends:** [0007](0007-biopython-for-genbank-export.md) (same containment rule, applied
to a second format), Phase S ([ROADMAP.md](../ROADMAP.md) §12)

## Context

iGEM's Best Software Tool prize scores six aspects (2025 Judge Handbook p.83). The first
is *"How well is the software compatible with, and does it leverage, existing synthetic
biology standards (e.g. **SBOL**, other RFCs, data formats)?"* — SBOL named outright.
CERNAL already answers the RFC half of that question well: `AssemblyStandard.RFC10`/
`RFC1000` and `MotifScreener`'s `RFC10_SITES` screen BioBrick restriction sites, and ADR
0007 gave GenBank export and import. It emitted no SBOL at all.

**The obvious route was measured and rejected.** `sbol-utilities` is SynBioDex's own
toolkit and advertises exactly what this needs — `sbol-to-genbank` / `genbank-to-sbol`
macros, offline since 2024. Testing it rather than reasoning about it, the way
[plasmids.md](../plasmids.md) §5 tested `pydna`:

- Its GenBank converter **crashes on this repo's Biopython**. `sbol-utilities` 1.0a17
  calls `SeqFeature.strand`, removed in Biopython 1.88 — the version `uv.lock` pins and
  `to_genbank` already uses. Measured: `AttributeError: 'SeqFeature' object has no
  attribute 'strand'` on a plain circular record with two features. This is not a version
  we can simply pin around: downgrading Biopython to restore a removed attribute would
  roll back the dependency ADR 0007 deliberately chose.
- It costs **36 packages** to install, against 15 for `sbol3` alone — it pulls `sbol2`,
  `pyshacl`, `lxml` and `pylatex` to do it. ADR 0007 rejected `pydna` at 21 packages for
  the same reason, and the arithmetic has not changed.

**Going through GenBank was the wrong shape anyway.** A converter would mean CERNAL
renders a `SeqRecord`, then re-parses it into an SBOL document — two lossy hops to
express data the engine already holds exactly. `PlasmidDesign` knows each segment's kind
and boundaries directly, and SBOL's own model (`Component`, `SubComponent`, `Range`) maps
onto it one-to-one.

**Native construction was measured and works.** `sbol3` 1.2 installs and imports on Python
3.13 despite PyPI classifiers stopping at 3.12. A CERNAL-shaped construct built directly —
one `Component` for the plasmid, one `SubComponent` per segment, a `Range` each —
round-trips through `SORTED_NTRIPLES` with **zero validation errors**, and is
**byte-identical across runs** with no uuid and no timestamp in the output.

That last property is not a nicety. `write_artifact` records a SHA-256 of every artifact,
and [CLAUDE.md](../../CLAUDE.md) §6 bans `uuid4` and the wall clock in anything reaching
output. A serializer that stamped documents would make two exports of one design differ,
which is the sort of thing that is noticed much later, as an unreproducible checksum.

## Decision

Add **`sbol3` only**, confined to one function in `src/engine/stages/plasmids.py` —
`to_sbol3(design: PlasmidDesign) -> bytes` — following exactly the containment rule ADR
0007 applied to Biopython and CLAUDE.md §5 applies to `RNA`. A `Document` is built and
discarded inside the function; no SBOL type crosses back into engine or Platform code.

Segment roles are real Sequence Ontology terms. Where a segment is a part CERNAL copied
from the iGEM Registry, the role comes from **that part's own Registry accession**, read
from the bundled catalog `src/engine/data/registry/parts.json`, and the part's Registry
URL is attached as `derived_from` provenance. Where it is not — the switch is designed per
run and exists in no registry — the role comes from a kind-based table and is
`SO:0000804` (`engineered_region`), not a borrowed accession for a part it is not.

**The export sits inside the release gate.** In `pipeline.py` the SBOL artifact is written
in the same block as FASTA and GenBank, below
`if not (... release_allowed ...): continue`. An SBOL document carries the full construct
sequence, so emitting it above that line would hand out precisely what the fail-closed
gate exists to withhold. `tests/engine/test_pipeline.py` asserts both halves: `"sbol"` is
withheld when release is blocked, and present when it is allowed.

**Explicitly out of scope, and rejected on measurement, not on principle:**

- **`sbol-utilities`.** Broken against this repo's Biopython, as above.
- **SBOL2, and any SBOL↔GenBank conversion.** Both formats are produced natively from
  `PlasmidDesign`, which is lossless and cheaper than converting between them.
- **Writing to the Registry.** Needs credentials and would push sequences to an external
  service, which collides head-on with the release gate above. The Registry integration is
  read-only and offline: `tools/sync_registry_parts.py`, run by hand, like
  `tools/sync_transcriptome.py`.

## Consequences

**Gained.** SBOL 3 export beside GenBank, with real SO roles and Registry provenance, for
15 packages and one new import in a module that was already the only one importing a
sequence library. The parts table's standing claim that it was *"verified against the iGEM
Registry API rather than typed from memory"* is now enforced rather than asserted:
`tests/engine/test_registry_parts.py` fails if any of the 15 parts drifts from the
Registry sequence it claims to be, offline, with no network in CI.

**Given up.** `sbol3`'s PyPI classifiers do not list Python 3.13, so the dependency is
supported by measurement rather than by the maintainers' declaration. If a future release
breaks on 3.13, the blast radius is one function and one artifact kind. `sbol3` is MIT
licensed — a standard SPDX identifier, so unlike Biopython it folds into
[attribution.md](../attribution.md)'s existing MIT row.

**Gotcha recorded so nobody re-discovers it.** Every CERNAL identifier contains a hyphen
(`plas-000001`, `circ-000001`), and SBOL display ids forbid hyphens and leading digits.
`sbol3` *raises* on an invalid display id rather than sanitising, so identities are
normalised through `_safe_id` before use — an unnormalised id fails the export outright.
Relatedly, `sbol3.Range` is **1-based inclusive on both ends** while CERNAL coordinates
are 0-indexed with an exclusive end (CLAUDE.md §6); the conversion is pinned by a test
asserting the SBOL and GenBank files place every feature at the same bases.

**Revisit when** either the Registry gains an SBOL endpoint worth submitting to, or
`sbol-utilities` fixes its Biopython incompatibility *and* a need appears that native
construction cannot meet — a genuine SBOL2 consumer, most likely. Neither is true today.
