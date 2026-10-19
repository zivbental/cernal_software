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
- Frontend and client/browser checks remain required and unchanged. Git is
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
