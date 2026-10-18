# Cleared-result policy correction and real acceptance run

The new `commec-resolved-findings-v2` policy accepts the real MG1655/mCherry result
after complete screening and integrity verification. Both final records received
COMPLETE/PASS; the cassette's native `Flag (Cleared)` annotations remain in its
audit. The final stored-release check returned true and generated FASTA, GenBank
and SBOL files. This is a local benchmark deployment identity, not production
activation or biological safety/function certification.

## Reason and change

Commit `ade940f77287a80810a486b50a03a4975300e0f5` introduced the draft exact-Pass
policy, explicitly blocking both cleared and unresolved native findings. This was
new conservative adapter behavior, not a legacy UI rule or parsing accident.
Pinned Common Mechanism 2.1.0 distinguishes low-concern-cleared findings from
unresolved concerns. The original real benchmark demonstrated this distinction
with a known reporter match.

The correction validates aggregate, primary-stage and hit statuses together.
Cleared acceptance requires both primary and low-concern supporting hits;
malformed metadata/coordinates, unknown steps/statuses, incomplete or inconsistent
records do not authorize release. Unresolved Flag/Warning, including mixed
cleared/unresolved findings, remain blocked. Native search thresholds, full-query
scope, database content, inventory checks, timeout cleanup and sequence binding
are unchanged. Native query annotations are retained in audit/release records
and included in the result digest. Old policy manifests and grants are invalid;
operators must revalidate and re-screen under v2.

References: [pinned status and aggregation definitions](https://github.com/ibbis-bio/common-mechanism/blob/24fe0390978eb66d13db4f91c18f122d051b1a65/commec/config/result.py),
[native low-concern implementation](https://github.com/ibbis-bio/common-mechanism/blob/24fe0390978eb66d13db4f91c18f122d051b1a65/commec/screeners/check_low_concern.py).
The committed unedited native fixture and its provenance are in
[`tests/fixtures/ibbis`](../../tests/fixtures/ibbis/).

## Actual end-to-end observation

The isolated implementation includes current main
`66a6d265577810e8943709f3e5bb21bffdab212c` merged into the IBBIS branch in
`a91cfb2`. Exact executed application file hashes are in
[`real-run.json`](ibbis-cleared-policy-2026-10-18/real-run.json); these were verified
against the worktree after execution. The operator manifest was created only for
the explicit benchmark child process and was not installed into any service.

Used the same real cached BV-BRC catalog `ecoli__138294__67644164`, MG1655
heat-shock comparison, seed 42, one toehold design, three selected genes, mCherry,
no backbone and no selectable marker. CSV SHA-256:
`452d25b413d6c3f3a6eec321da41adfe166578c95fc17492c2bc1fe5012f1cf0`.
This is a historical 3,000-row selection with incomplete hypothesis-universe
metadata and no p/adjusted-p values; no statistical validity or wet-lab function
claim is made. Native folding and the original configured final-output/export
path ran in one LocalEngine invocation, without substituted screening results.

| Phase | Seconds |
|---|---:|
| Whole LocalEngine run, including generation and export | 271.0606 |
| Pre-screen integrity | 24.2156 |
| Native screening batch including parsing | 210.8637 |
| Post-screen integrity | 31.9261 |
| Remaining generation/export/bookkeeping combined | 4.0551 |

The service wall time was 272.414 seconds. Both original final sequences matched
the previous benchmark: switch 83 bases, complete linear expression cassette 958
bases, no exact duplicates. The latter is named `plasmid` internally but contains
no circular vector backbone. Export verification independently parsed the FASTA
and GenBank and matched their hashes to their screening audits; every artifact
checksum also matched. Private sequence-bearing artifacts remain on the laptop.
The sequence-free inventory and verification receipt are included here.

Complete official database: 130 files, 41,031,158,338 logical bytes, inventory
digest `2852dd4f71a6e657fb6b979ecb59ba33479d31e6e2e19fc5fcda40a611e5f055`.
Software inventory digest:
`fc17fe9a4dde5648bf8f526ca01c4f3c448b6166869e8cff6a3c8bf13821376f`.
Common Mechanism 2.1.0/schema 0.6; revisions biorisk 1.2, control_lists 1.1,
best_match 1.0, low_concern 1.1. The installation is the unchanged previously
validated official tool/database environment. No databases or packages were newly
downloaded, and no legal agreement was accepted in this correction task.

Ziv-Laptop/WSL: Core Ultra 9 288V, 8 logical CPUs, 32 GiB Windows RAM,
15.36 GiB WSL RAM, SSD. Before this run WSL reported 11,802,247,168 bytes available
RAM and 872,949,690,368 bytes available on its filesystem. Two screening threads,
CPUQuota 200%, Nice 10, MemoryMax 6G, MemorySwapMax 0; CLI timeout 900 seconds,
service bound 1,100 seconds. Tool/database paths were read-only. Lightweight
frontend verification ran concurrently; this is not an idle-machine benchmark.

Cgroup CPU: 462.5597 seconds; peak charged memory including cache: 6 GiB;
41,256 memory-limit events; zero OOM/OOM kills. Largest child lifetime RSS:
8,757,248 KiB. RSS and cgroup charge measure different things (including shared
pages/cache ownership), so the 6 GiB charge cap is not a claimed RSS cap.

An initial attempt omitted the provisioned search-tool bin directory from the
systemd service PATH. Its native subprocess failed after 2.07 seconds and both
outputs correctly stayed FAILED/HOLD_SYSTEM; no sequence export was authorized.
That receipt is retained as `initial-path-failure.json`. The successful retry
changed the service PATH, retained all screening constraints, and used a fresh
output directory. No failed observation was overwritten.

## Reproduction and validation

Use [`tools/benchmark_ibbis_cleared_policy.py`](../../tools/benchmark_ibbis_cleared_policy.py)
with the existing pinned installation and a fresh output directory. Set
`PYTHONPATH` to this checkout's `src`, put the installation's `env/bin` on PATH,
and set `PYTHONDONTWRITEBYTECODE=1`, `OPENBLAS_NUM_THREADS=1`, `OMP_NUM_THREADS=2`.
Run with the existing CERNAL Python environment and the systemd resource limits
above; retain the database/software read-only mounts. The script refuses to
overwrite an output directory. The supplied installation inventories must cover
the full environment/database; reducing them is not a supported speed option.

Focused regression run: **224 passed**, covering parser, SafetyGate, process
cleanup and API release disclosure. Includes the original native output, 18
cleared status/stage combinations, inconsistent and mixed-result negative cases,
annotation digest binding and prior-policy rejection. Same-length placeholders
in parser unit tests are not represented as biologically screened inputs.

Ruff lint/format, generated API documentation check and Django system check passed.
Frontend production build and full `npm run check` passed, including 39 screening
contracts and 16 RNA-display contracts. A first typecheck before route generation
failed because the fresh checkout lacked its ignored route tree; the normal Vite
build generated it, after which all checks passed. No frontend source was changed.

The complete repository suite and PR CI are tracked in the PR/review handoff.
Do not merge while either required verification or the requested review remains
outstanding. No repository protection settings were changed.
