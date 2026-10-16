# Construct assembly, provenance and export

Source baseline: `66a6d265577810e8943709f3e5bb21bffdab212c` (16 October 2026).
See [status](status.md) for release evidence and pending work.

The application builds a sequence-level expression cassette or inserts it into a supplied
backbone. “Plasmid” in a record name does not prove a complete replicating vector, an
executable cloning protocol, or a biologically functional design.

## Physical scope

[`PlasmidBuilder.build`](../src/engine/stages/plasmids.py) accepts one identity expression
with one activating toehold and matching input identity, or the supported one-gate
eukaryotic AND with matching two-input identity. It rejects other physical Boolean
topologies and unsupported mechanisms/repressors. Concatenating switches cannot
implement AND/OR/NOT, even when a logical expression can be enumerated elsewhere.

The compiled order is promoter → switch → payload → terminator. The switch supplies its
initiation AUG; the builder consumes the corresponding payload start and any exactly
matched embedded payload head once, then checks the fusion frame. The resulting protein
is an N-terminal fusion, not necessarily the native payload protein.

In the production pipeline each retained gate is assembled with every requested output.
Folding metrics are then evaluated in switch–payload transcript context. They are not
whole-cell measurements and do not model every vector or transcriptional interaction.

## Parts and host scope

The source tables `PROMOTERS`, `TERMINATORS`, `PAYLOADS`, `PAYLOAD_HOSTS` and `BACKBONES`
in the builder define emitted parts. The [bundled Registry catalog](../src/engine/data/registry/parts.json)
records identities and provenance; refresh tooling is `tools/sync_registry_parts.py`.

- GFP, mCherry and firefly luciferase have catalog CDS entries.
- AmpR and KanR are supported only for E. coli. Source identity is distinct from
  functional resistance after fusion; AmpR secretion can be affected.
- Custom output requires a validated user CDS. Apoptosis has no available catalog payload.
- All four hosts have promoter/terminator entries. Human uses CMV `BBa_I712004` and
  hGH polyadenylation `BBa_K404108`.
- Bundled BioBrick backbones are E. coli-only. A yeast, Human or C. acnes reference does
  not make a bacterial vector compatible with that host.

Optional `payload.optimize_codons` selects a clean synonymous variant through the shared
host optimizer before context folding. Records include original/optimized sequence
hashes, changed codons, seed and unresolved constraints. Without that flag, source
payloads are preserved apart from the explicitly defined fusion junction.
[AIS-China attribution and the pinned C. acnes reference](collaborations.md) must remain
with any corresponding optimization result.

## Backbone and assembly semantics

A custom GenBank backbone is parsed with Biopython, with supported feature coordinates
preserved through the insertion. `backbone.insertion_index` selects the sequence insertion
position; crossing features are represented with transformed joined coordinates. A custom
vector's replication, selection and host compatibility remain user-supplied and unverified.

Without a backbone, the product is an expression cassette. With one, assembly method
`sequence_insertion` describes coordinate compilation; it does not supply cloning overlaps.
Human defaults to `none` unless an assembly standard is explicitly supplied. RFC10 and
RFC1000 select restriction-site checks, not a complete experimental assembly protocol.

## Findings, eligibility and disclosure

The builder checks the full construct, including circular boundary motifs when a backbone
is present. All findings remain visible. Frame failures, forbidden motifs and newly
introduced restriction sites can affect eligibility. Pre-existing backbone restriction
sites and full-construct homopolymers remain assembly caveats rather than automatically
being labeled a nonfunctional ORF.

Eligibility is separate from sequence-release policy. [`safety.py`](../src/engine/safety.py)
and the platform-facing disclosure functions control released sequence views and artifacts.
Neither a policy decision nor a passed motif check demonstrates transcriptome specificity
or biological safety. See [scientific interpretation](scientific-interpretation.md).

## Exports and verification

GenBank is emitted through Biopython and SBOL3 through `sbol3`; these library records do
not cross the engine contract. See [ADR 0007](decisions/0007-biopython-for-genbank-export.md)
for the Biopython choice. Historical pydna proposals do not describe the implementation.
Artifacts must retain their checksum and provenance alongside construct/part identifiers.

Relevant regression coverage includes `tests/engine/test_plasmids.py` and
`tests/engine/test_registry_parts.py`. A successful export, frame check or software test
is not experimental switch, payload or vector validation.

## Historical evidence

The [preserved design and development record](archive/scientific-design/plasmids.md)
contains earlier measurements, alternatives and decisions. It is historical evidence,
not current implementation guidance.
