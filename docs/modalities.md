# Supported inputs, hosts, mechanisms and outputs

Source baseline: `66a6d265577810e8943709f3e5bb21bffdab212c` (16 October 2026).
See [status](status.md) for release evidence and pending work.

These choices describe actual application routes, not the full research search space.
Use `GET /api/version` / `LocalEngine.capabilities()` for a running build, including
host restrictions. Enum membership and research notebooks do not establish availability.

## Inputs

| Input mode | Supplied evidence | What the application does |
|---|---|---|
| `direct` | One RNA/DNA sequence or single FASTA record | Normalizes to RNA, validates alphabet and 20–10,000 nt length; uses a short exact trigger or scans a longer transcript |
| `gene` | A reference gene identifier | Resolves a bundled transcript, freezes/checks the sequence, then uses the sequence route and records reference provenance |
| `de` | A differential-expression table | Verifies bytes/checksum, parses results, resolves IDs, selects genes and scans their bundled transcripts |

A direct or named-gene input carries no observed DE comparison; its `state_separation`
is unmeasured. DE input is already analyzed expression data: CERNAL does not run DESeq2
or infer replicate-level performance from a fold-change table. See [gene selection](genes.md)
and [trigger selection](triggers.md).

## Hosts and mechanisms

| Host | Translation track | Reference scope | Application toeholds |
|---|---|---|---|
| `ecoli` | Prokaryotic | RefSeq CDS, K-12 MG1655 | generic or prokaryotic |
| `c_acnes` | Prokaryotic | RefSeq CDS, ATCC 6919 | generic or prokaryotic |
| `yeast` | Eukaryotic | RefSeq CDS, S288C | generic or eukaryotic |
| `human` | Eukaryotic | Ensembl 116 mature transcripts, GRCh38.p14 | generic or eukaryotic |

Generic means family name `toehold`; track-specific names are `prokaryotic_toehold`
and `eukaryotic_toehold`. Reference availability does not establish complete alias or
isoform coverage, expression context, or experimental function in that host.

`eukaryotic_toehold_and` is available for Human/yeast DE input, with two selected
up-regulated genes (the same canonical gene may supply both windows), one gate and
no mixed families. It requires `max_triggers=2` and `max_circuit_gates=1`; direct and
single-reference-gene modes do not support this family. See [AND guide](and-gate.md).
Generic/prokaryotic research AND, antisense and CRISPR are unavailable application
routes. Single-input defaults remain one trigger and one gate; there is no general
physical multi-gate compiler.

## Outputs and assembly

Implemented catalog outcomes are `gfp`, `mcherry`, `luciferase`, `ampr` and `kanr`;
`other` requires an explicit valid custom CDS. Resistance outputs are E. coli-only.
`apoptosis` is an enum value without an available catalog output. Each supported
requested output is evaluated separately with each retained gate.

Codon optimization is explicit (`payload.optimize_codons`); it is not an automatic
license to replace the supplied CDS. Sequence and optimization provenance are retained.
The fusion's function remains experimental, including resistance and secretion effects.

Catalog backbones are E. coli-only. Other hosts require a suitable user-supplied GenBank
vector or receive an expression cassette without a backbone. Human uses CMV/hGH parts
and defaults to assembly standard `none`; this does not design cloning overlaps or a
wet-lab assembly protocol. [`plasmids.md`](plasmids.md) explains construction, checks,
exports and release eligibility.

## Choosing and interpreting a run

1. Identify the intended input evidence and exact reference/contrast.
2. Choose a host-compatible mechanism, output and vector.
3. Record constraints, budget, seed, folding configuration and scoring profile.
4. Inspect warnings, rejected candidates and missing metrics before comparing ranks.
5. Treat the result as a computational design requiring experimental testing.

See [scientific interpretation](scientific-interpretation.md), [catalog governance](catalog-governance.md)
and [current status](status.md) for the evidence boundaries.

## Historical evidence

The [preserved design and development record](archive/scientific-design/modalities.md)
contains earlier measurements, alternatives and decisions. It is historical evidence,
not current implementation guidance.
