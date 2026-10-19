# Installing pinned reference data

`./do install` installs locked Python dependencies and the runtime reference assets.
For manual setup, after `uv sync --locked --extra dev`, run:

```bash
uv run python tools/install_data.py
uv run python tools/install_data.py --check
```

The default `runtime` profile installs 81 files (82,601,858 bytes): eight transcriptome
FASTA/metadata files, both AIS-China reference packages (58 files), and 15 public
expression-catalog CSVs. `--profile test` installs the same assets because the full
regression suite deliberately exercises real reference packages. Small test fixtures,
catalog provenance manifest, source code, third-party licenses, and compact research
summaries remain tracked. No network is needed by reference resolution at runtime.

## Exact versions, source and provenance

[`data/manifest.json`](../data/manifest.json) pins each destination, URL, byte count and
SHA-256. Installation checks all three, including existing files and cache hits.
Data is downloaded as binary, with no line-ending conversion or recompression.
Missing/corrupt assets fail setup clearly; neither another release nor a different
provider's dataset is substituted. Per-file atomic replacement keeps interrupted
transfers from replacing a usable file. A partially completed overall installation
must be rerun and pass `--check` before use.

The initial download source is the **exact historical CERNAL asset** at immutable
GitHub commit `ca4e3b0d90d43f494ef3647b0098795f804fc2ba`, not the provider's current
release. This interim source is chosen to preserve every byte used by existing
results while shrinking the current source tree. It depends on that commit remaining
reachable in the public GitHub repository. Do not rewrite/delete that history until
an independently verified durable mirror is published and the manifest is reviewed.
No Zenodo publication is assumed. A separate archival release may replace these URLs
only after verifying it delivers the same pinned bytes.

- Human reference: Ensembl GRCh38.p14 release 116 mature cDNA/noncoding transcripts.
  The retained metadata pins original cDNA, ncRNA and GTF URLs and source SHA-256s.
  `tools/sync_human_transcriptome.py` is an explicit maintainer rebuild tool, not an
  installation step. It verifies its raw source downloads/cache before transforming.
- E. coli and yeast: historical NCBI CDS packages and identifier aliases recorded
  in their installed metadata. C. acnes: AIS-China ATCC 6919 reference CDS and aliases.
- AIS-China: upstream `e8a57cf1b5696ed7b3931f6b63ea49afbc5ccbf9`, software 2.0.1,
  reference package `2026-09-06.v1`. Both ATCC 6919 and KPA171202 host packages are
  required by its `ReferenceStore`. Its source/config/license remain tracked and
  downloaded data stays byte-identical. See its retained
  [provenance record](../vendor/ais-china-codon-optimization-v2/PROVENANCE.md).
- Public expression catalog: historical normalized CSVs. Their retained
  [catalog manifest](../src/apps/expression/catalog/manifest.json) preserves original
  source URLs, retrieval dates, CSV hashes, contrast metadata and review state.
  Entries marked `historical_subset_source_total_unknown` or `pending_human_review`
  **remain so**. Downloading them does not establish complete coverage, approve
  interpretation, or claim the original transformation can be recreated from today's
  provider responses. An explicit catalog refresh produces a new reviewed dataset.

### Data rights

Code licensing is not a blanket license for third-party datasets. AIS-China's package
is Apache-2.0 with its LICENSE and attribution retained. Ensembl describes its
[project data as unrestricted with third-party caveats](https://useast.ensembl.org/info/about/legal/disclaimer.html).
NCBI's [data policy](https://www.ncbi.nlm.nih.gov/home/about/policies/) likewise retains
original submitter rights caveats. Expression Atlas publishes data under
[CC BY 4.0](https://www.ebi.ac.uk/gxa/licence.html), requiring attribution. BV-BRC
catalog entries retain source attribution, but dataset-specific rights have not been
independently established here. The manifest records these limits; do not label every
asset Apache-2.0 or treat installation as legal clearance for redistribution.

## Cache and offline use

```bash
# Connected setup: populate a portable content-addressed cache.
uv run python tools/install_data.py --cache-dir /path/to/reference-cache
# Offline setup from that previously verified cache:
uv run python tools/install_data.py --offline --cache-dir /path/to/reference-cache
# Check installed files without network, writes or repairing anything:
uv run python tools/install_data.py --check
```

Installed files and cached objects are owner-readable/writable (mode 0600 on POSIX).
Run setup as the application service account (for example `cernal` in the deployment
unit), or have an operator arrange narrowly scoped ownership before starting the
worker. Running setup as root does not automatically grant another service account
access. The installer does not broaden permissions.

The default cache is `var/data-cache/` (gitignored). Copy this cache through an
approved channel to an offline machine and use `--offline`; every cached object is
rehashed before use. A valid installed file can seed its cache. A missing or corrupt
installed file can be repaired from a valid cache; with no valid cache, offline mode
fails without requesting the network. Online mode may fetch the same exact pinned
asset again. A hash mismatch is an error, never an invitation to accept new bytes.
`--root /path/to/clean-source` supports isolated install verification. Downloaded
paths and caches are ignored by Git; do not force-add them to a source commit.

## Screening remains a separate prerequisite

This installer does **not** download or run arbitrary screening executables, create
credentials, approve policy, mark an IBBIS installation validated, or release sequence
exports. Full-output screening still requires the separately provisioned executable,
versioned database, validated manifest, and operator release policy documented in
[final screening](ibbis-final-output-screening.md). If these requirements are absent or invalid,
release stays fail-closed. Follow the configured adapter's documented setup and
validation process; installing the reference packages above is not screening evidence.

## Generated outputs and Git history

Large generated research CSVs are omitted from the current source tree and covered
by `.gitignore`; compact fixtures and summaries remain. The
[research archive index](../data/research-archive.json) records removed paths, sizes,
SHA-256s and their source commit. To recover a historical output without changing
history, use `git show ca4e3b0d90d43f494ef3647b0098795f804fc2ba:path/to/file > output`.
These historical outputs are not necessary for application installation and are not
downloaded automatically. Research scripts may need the relevant archived input or
an explicitly regenerated output; do not mistake missing research outputs for a
reason to change the reference dataset.

This change shrinks the tracked tip, **not existing GitHub history**. A normal clone
may still transfer historical data. For a size-limited GitLab submission, use a
verified clean source snapshot and ordinary commit on that repository's history;
do not push the full GitHub history or rewrite either shared repository. Record the
source commit and snapshot digest and verify the resulting repository separately.
