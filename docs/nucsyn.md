# NucSyn: external design platform and research provenance

Historical consumer reviewed 16 October 2026 against CERNAL main
[`c1bb92cc085a6bad272298b81bda28c22b1d57f5`](https://github.com/zivbental/cernal_software/commit/c1bb92cc085a6bad272298b81bda28c22b1d57f5)
and the public NucSyn Platform v0.1.2 release. This page documents an existing
research-data interface and credits its upstream source; it does not activate a backend.

## Credit and scientific role

[NucSyn Platform](https://github.com/YehudaLandau/NucSyn-Platform) is an external
RNA inverse-design toolkit released by Yehuda Landau. Credit for its associated work
belongs to Landau, Arbel, Benarroch, Klein, Moree and Tuller; the upstream-requested
citation is below. CERNAL's research notebooks can use externally generated designs
as inputs to further analysis. That upstream contribution should be visible wherever
those designs are discussed, rather than attributed to CERNAL's own generator.

The [official README](https://github.com/YehudaLandau/NucSyn-Platform/blob/v0.1.2/README.md)
describes a Linux x86_64 containerized toolkit. The
[v0.1.2 release](https://github.com/YehudaLandau/NucSyn-Platform/releases/tag/v0.1.2),
published 15 October 2026, supplies an OCI container archive for Docker/Podman and a
checksum asset. This is not a Python dependency installed by CERNAL's lockfile.
The README points to `docs/QUICKSTART.md` inside the distribution. We have not installed
or executed that distribution in this review, and do not claim a verified v0.1.2 CLI/API
or that its output schema is identical to historical runner exports.

## Historical consumer and current application boundary

The source of this connection is the
[historical eukaryotic AND notebook](https://github.com/zivbental/cernal_software/blob/c1bb92cc085a6bad272298b81bda28c22b1d57f5/src/engine/gates/notebooks/toehold_and/toehold_and_eu.ipynb),
particularly **Fusing two ranked single-input designs into an AND candidate**.
It contains a local CSV-consuming research workflow, not a call to the NucSyn executable
or a network service. Its configured CSV locations are machine-specific and are not a
portable reproduction package. The presence of this code establishes an implemented
research interface, not that all historical experiments were rerun or independently verified.

The production route is different: [`LocalEngine`](../src/engine/client.py),
[`pipeline.py`](../src/engine/pipeline.py) and
[`ToeholdGate.generate_designs`](../src/engine/gates/toehold.py) construct and evaluate
candidates using CERNAL code and shared ViennaRNA adapters. No NucSyn runtime dependency
or adapter was found in that audited main path. The production capabilities are described
in [status](status.md) and [engine methods](engine.md). The eukaryotic AND application is now merged, but it generates its own candidates;
that does not activate a NucSyn runtime adapter.

The notebook's older prose about unimplemented gate methods is historical; inspect
current source and capability guards. A NucSyn release, a notebook, and a selectable
application workflow are three separate kinds of evidence.

## Current-main reconciliation

Main `66a6d265577810e8943709f3e5bb21bffdab212c` includes PRs 68/69/81/82. The old notebook linked above
was removed by PR68; its consumer contract and scientific discussion below are retained
as historical provenance, not instructions for a file that still exists on main.
The current [eu_and_v3 notebook](../src/engine/gates/notebooks/toehold_and/eu_and_v3.ipynb)
and [specification](../src/engine/gates/notebooks/toehold_and/eu_and_v3_spec.md) own the
current CSV/replay workflow. It validates input/model/sampling identity and preserves
saved provenance. Do not assume the historical fields or ranking below describe that
replacement. The [application AND route](and-gate.md) uses CERNAL-generated switches,
its own scoring and controls; notebook and application results need not match.
NucSyn attribution, upstream citation and license boundaries below remain applicable.
No container redistribution or runtime integration is introduced here.

## Historical research input contract

The notebook expects two ranked exports, one per target, conventionally named
`results_ranked.csv`. Its recorded example uses topology
`euk_open_5p_kozak_after_stem`. The following contract describes the CERNAL consumer,
not a newly verified universal NucSyn v0.1.2 schema.

| Field | Meaning in the notebook |
|---|---|
| `switch_strand` | Full upstream-designed switch sequence |
| `trigger_seq` | Corresponding trigger sequence |
| `switch_domain_breakdown_json` | Named `name`, `start`, `end` domain records over the switch |
| `postgen_global_rank` | Producer's rank; input row order is retained |

Domain coordinates are zero-based and half-open. The loader normalizes DNA letters to
RNA through shared sequence utilities and rejects missing required fields and invalid
RNA. It checks that the first/last domain boundaries span the switch. **It does not fully
validate adjacency, overlaps, duplicate names or every malformed JSON case.** Do not
present it as a hardened ingestion API. Verify domain consistency before using the data.

Optional producer measurements carried alongside the designs are `sim_score`, `mcc`,
`switch_toehold_unpaired_prob_mean` and `energy_trigger_mfe`. The notebook describes
`sim_score` as lower-is-better. They are read from the CSV, not recalculated or equated
with CERNAL's production score. Missing or nonnumeric optional measurements become
`None`, not zero. A producer schema/version record remains necessary to interpret them.

## Downstream analysis and outputs

The notebook constructs an ordered pair by keeping design A before its `kozak` domain
and design B after its `prefix` domain. This retains one upstream prefix and one
downstream Kozak/reporter context. Domain boundaries, rather than a degenerate Kozak
pattern string, determine the cuts. The cut rule is topology-specific: other domain
arrangements require review, and exchanging A and B changes the construct.

For each retained pair, the shared `FoldEngine` computes minimum-free-energy and
ensemble-energy quantities for the construct alone, with A, with B, and with both
triggers. Separate molecules use `&` separators. The notebook records sequences,
lengths, originating ranks and producer metrics with the new energy measurements.
Default input limits are 10 rows from each file and the recorded folding temperature
is 37 °C; these are notebook settings, not universal recommendations.

Its local rank key is `d_ee_ab`, the both-trigger ensemble energy minus the trigger-free
energy, with more negative values first. It also reports the difference between the
better single-trigger energy change and the both-trigger change as `and_margin_ee`.
This is a research comparison, not the production `engine.scoring` profile and not a
measurement of logical truth-table performance. The energy subtraction does not by
itself supply concentration-dependent occupancy, translation, or complete binding
thermodynamics with all isolated components accounted for.

## Interpretation limits

- A predicted structure/energy is not experimentally measured expression, ON/OFF fold
  change, cellular efficacy, biological safety or proof of an AND gate.
- More-negative raw energy can reflect a longer trigger or construct. Rankings with
  different lengths, inputs, model settings or objective definitions are not interchangeable.
- The source design's upstream score, this notebook's pair ranking and CERNAL's
  production score answer different questions. Preserve their labels and provenance.
- The original CSVs and complete run manifests have not been established by this
  documentation review. Do not attach v0.1.2 to historical results merely because it is
  the latest published release.
- No transcriptome-wide specificity validation or performance equivalence between
  NucSyn and CERNAL is established here. See [scientific interpretation](scientific-interpretation.md).

## Reproducibility checklist

For a publishable reproduction, retain:

1. The producer's actual version and immutable distribution identity, license/permission
   applicable to the intended use, configuration/profile, seed where supported, reference
   inputs and tool versions. If a setting is unavailable, record that explicitly.
2. Original CSV bytes and checksums, target identifiers, topology, full domain annotations,
   row order and producer metric definitions. Do not replace original data with a screenshot.
3. CERNAL commit, notebook and helper versions, RNA folding backend/version, temperature
   and other effective model parameters, A/B order, row limits, cut rules and ranking key.
4. All retained/rejected input rows and reasons, emitted candidate sequences and raw
   state measurements, plus the command or notebook execution record.
5. An explicit distinction between upstream prediction, downstream computation and
   experimental evidence. A rerun is a new run record, not silent replacement of history.

For v0.1.2 specifically, the official release lists archive
`nucsyn-platform-0.1.2-linux-x86_64.tar.gz` (303,698,467 bytes) with SHA-256
`cb3d28865dd63b8c9857a8e8cdb21c922aaef84a52bc7a629c3faacb167ed490`.
This is published metadata, not a locally verified download checksum. Check downloaded
bytes against the official checksum before an authorized installation; pin the actual
image identity and run environment in addition to the human-readable tag.

## Licensing and deployment boundary

NucSyn's [Academic Research License v1.0](https://github.com/YehudaLandau/NucSyn-Platform/blob/v0.1.2/LICENSE)
is separate from CERNAL's license and is not OSI-approved open source. It permits
specified noncommercial research by eligible academic users, including internal research
pipelines and publication of outputs with citation. Its default terms require prior
written licensor permission for incorporation into separately distributed products,
public redistribution, and third-party-accessible hosted functionality. Any separate
permission must be applied to its actual scope; CERNAL's license is not a substitute.

The license also distinguishes external tools and data, including RNAaccess and optional
BLAST+/reference databases, whose acquisition and terms remain separate responsibilities.
Do not assume NucSyn permission grants redistribution rights to those components.
This documentation adds links and attribution only; it does not distribute binaries,
install software, expose a service or change CERNAL's execution path.

## Citation

Use the reference requested in upstream
[`CITATION.md`](https://github.com/YehudaLandau/NucSyn-Platform/blob/v0.1.2/CITATION.md):

Landau Y, Arbel M, Benarroch D, Klein JY, Moree E, Tuller T. Computational design of
toehold switches in eukaryotes and prokaryotes for efficient post-transcriptional control.
*bioRxiv*. 2025. [doi:10.1101/2025.01.15.633215](https://doi.org/10.1101/2025.01.15.633215).

This is a preprint citation, not a claim of peer review. The preprint full text was not
accessible during this review; no paper-specific quantitative claim is imported here.
Cite the actual NucSyn release separately in methods when its use has been verified.
