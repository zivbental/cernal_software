# GitLab CI under the competition runner limit

The competition runner (#67) reports a hard **10-minute job timeout**. A YAML
job timeout cannot raise that runner maximum. The original full backend job was
terminated after 601.84 seconds, while its complete scientific suite takes much
longer. No tests or biological calculations are disabled to fit this limit.

## Required jobs

- `backend-checks` retains Ruff lint/format, Django checks, migration freshness,
  and API-surface freshness checks.
- `backend` runs 16 required pytest shards. Each installs locked dependencies,
  then downloads and verifies all 81 immutable test-profile assets with the existing
  data installer. `backend-checks` uses the same setup. Missing or corrupt assets
  fail closed; pinned URLs, byte counts and SHA-256 checks remain unchanged.
  The optional uv cache is pull-only; successful cache restoration is not required.
- `backend-coverage` depends on every shard and the backend checks. It verifies
  all shard indices are present, every shard exited successfully, every selected
  test started execution, and the disjoint union matches the full collection's
  count and SHA-256 fingerprint. Missing reports, early exits, duplicates, and
  substituted test IDs fail this job.
- `frontend` retains the clean-build regression (including rejection of an injected
  TypeScript error), followed by the complete `npm run check` chain. Its successful
  SPA build is shared with four required `frontend-browser` matrix jobs: `contracts`,
  `rna-viewer-browser`, `screening-browser`, and `run-usability`. These are exactly
  the four commands in `npm run test:browser`; no suite is skipped or allowed to fail.
  Each browser job installs locked npm dependencies and Chromium, then executes its
  suite against that same build. Screenshots/reports are retained per matrix job.
- Python client and real queued-browser checks remain unchanged. Git is
  explicitly installed in slim images that need it for source-link tracking,
  checkout-conversion tests, or provenance.

Reference data is deliberately not passed between jobs as an artifact. In
[pipeline 770346](https://gitlab.igem.org/2026/software/tau-israel/cernal/-/pipelines/770346),
the preparation job verified all 82,601,858 data bytes but the coordinator rejected
the cache archive with HTTP 413 (`Request Entity Too Large`). Downloading the pinned
data in each backend job avoids that artifact limit without changing the data or
requiring cache permissions. This repeats network transfer across jobs and therefore
requires the immutable download source to remain available. Only compact shard
coverage JSON and JUnit reports are transferred to the final audit; the data cache,
environment and application data are not included in backend artifacts.

The frontend transfers only `src/static/app/`, never `node_modules` or browser
binaries. `tools/check_frontend_artifact.mjs` requires an index page and rejects
symlinks or a build at least 8 MiB in total uncompressed size before upload. This
leaves room for archive overhead and avoids the former 82.6 MB reference-data
artifact. The coordinator's exact configured limit is not exposed; actual upload
and matrix-job download success still need confirmation on the competition runner.
No npm dependency cache is uploaded; every frontend job works with a cold `npm ci`.

## Frontend timeout evidence

In [pipeline 770607](https://gitlab.igem.org/2026/software/tau-israel/cernal/-/pipelines/770607),
frontend job 1862690 timed out after 605.17 seconds. Its timestamps show 56 seconds
for npm installation, 220 for the clean-build regression, 82 for `npm run check`,
and 107 for Chromium installation. Browser contracts then took 64 seconds; the
RNA-viewer suite was interrupted by the runner cutoff before screening or run
usability could start. Build/static work and browser installation/tests must not
share one 600-second budget. The four independent browser jobs retain the full
tests while avoiding four additional builds. Setup/download speed still varies;
local timings are not a guarantee of ARM64 competition-runner timing.

Local validation on Windows/Node 24.19.0 used an empty npm cache and a fresh
Chromium directory: npm reported installation in one minute; Chromium installation
took 45.70 seconds. Clean-build took 33.14 seconds, checks 14.70, browser contracts
12.49, RNA viewer 23.06, screening browser 20.86, and run usability 5.30. All passed.
The shared build measured 32 files / 1,133,093 uncompressed bytes. The size guard
also rejected a missing index and an oversized build. YAML graph/required-job
validation confirmed that the matrix exactly matches all four package-script
commands and that backend/client/queued-browser configuration is unchanged.
This validates command preservation, not a Linux ARM64 timing guarantee; verify
the final 25-job pipeline on runner #67 before calling the fix complete.

## Partitioning and timing

`tools/ci_test_shards.py` starts from **the current full pytest collection**.
`tools/ci_test_durations.json` is a scheduling hint, never an allowlist. Newly
added tests are automatically included with conservative fallback weights.
Groups are assigned largest estimated duration first, with deterministic tie
breaking. Ordinary modules stay together. Only profiled, function-scoped slow
modules are split by test ID; introducing a module/class fixture to such a file
fails collection until it is explicitly regrouped and re-profiled. Unittest
class fixtures, including the CRISPR module, remain together.

The initial hints were measured on Python 3.13 on 2026-10-19, at source commit
`3e8482252f3370cc237fc0b579ae217e2ec1184a`, by running each of the 93 modules in a
separate pytest process (up to eight concurrently) and recording JUnit timings,
including setup and teardown. All 3,206 source tests were accounted for. The
slowest module was `test_seed_demo.py` at 289 seconds; its slowest individual test
was 79.8 seconds. After splitting expensive function-scoped modules, the
16-shard estimates are approximately 86–88 seconds each on that host.

These measurements are not a guarantee of competition-runner speed. Its earlier
cold setup took about 52 seconds, but CPU load, package and reference-data downloads,
and report transfer vary. Each shard publishes JUnit timings and the slowest 20 durations
for tuning from actual runner evidence. If a shard still reaches the hard cap,
rebalance measured groups or inspect an individually slow test; never remove
coverage or replace real calculations merely to turn CI green.

Run one shard locally (after normal dependency and test-data installation):

```sh
uv run python tools/ci_test_shards.py run --index 1 --total 16
```

After collecting reports from all 16 executions:

```sh
uv run python tools/ci_test_shards.py verify test-results/backend/shard-*.json
```

The regular `uv run pytest -q` entry point remains the complete unsharded suite,
including on GitHub. Update timing hints from measured setup/call/teardown times
when runtime changes; stale hints affect balance, not collection or coverage.
