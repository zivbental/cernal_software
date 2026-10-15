# Final-screening benchmark boundaries and reproduction

## What was measured

The recorded run is **synthetic software overhead only**. It calls the actual
`read_json` duplicate-key-rejecting decoder, `CommonMechanismAdapter.parse_result`,
and `SafetyGate.evaluate`. No Common Mechanism executable, real database, biological
search, or mocked CLI was executed. Invented JSON statuses are software test inputs,
not actual screening results, and synthetic PASS is not evidence of biological safety.

Reproduce from the repository root in the existing development environment:

```sh
PYTHONPATH=src UV_CACHE_DIR=/tmp/uv-cache uv run --no-sync \
  python tools/benchmark_final_screening.py --repeats 20 \
  --output docs/evidence/ibbis-overhead-2026-10-15.json
```

The evidence file records raw timing samples, source SHA-256 hashes (including the
benchmark), the checkout's HEAD, Python/platform, available disk, and executable
availability. Source hashes identify the tested working-tree content; HEAD alone
does not include uncommitted work. Rerunning replaces this evidence file, so use a
new output name when retaining multiple runs.

Inputs are repetitive ACGT toy strings of 41, 100, 1,000, 10,000 and 100,000 bases,
with batches of 1, 8 and 64. The 100,000 × 64 case is explicitly skipped because
it exceeds the one-million-base batch cap. Every valid size combination exercises
invented Pass, Flag, Error and Unknown aggregate statuses, asserting the resulting
PASS, BLOCK, HOLD_SYSTEM and HOLD_SYSTEM software decisions. These are four selected
software paths, not exhaustive branch coverage and not biological sensitivity,
specificity, false-positive or false-negative measurements. No hazardous sequence
corpus, evasive variants, or functional sequence design is involved.

There are 112 measured combinations: 14 size/batch combinations × four statuses ×
two modes, with 20 repetitions each. Both modes read and decode JSON, validate the
result, and evaluate policy on every call:

- `fresh_adapter`: constructs a new adapter object each call.
- `reused_adapter`: reuses that object, without caching any verdict.

Both modes warm imports and filesystem pages once before timing. “Fresh” is not
an OS-cold or database-cold run. Sustained-load throughput is sequential, not a
parallel capacity or contention measurement. Tracemalloc measures one separate call
outside the timed repetitions, excluding prebuilt inputs and measuring Python
allocations only. RSS is the process-lifetime high-water mark, not per-case incremental
memory. Timings include the expected-policy assertion and are noisy on shared hardware.
JSON fixture size scales with batch count, while sequence validation/hashing also
scales with the number of bases. Empty hit lists do not model hit-dense output.

## Observed run, 2026-10-15

Python 3.13.5 on Linux x86-64; nine logical CPUs reported. Selected median elapsed
milliseconds for reused-adapter, synthetic Pass cases:

| Bases per toy input | Batch | Median milliseconds | Sequential inputs/second |
| ---: | ---: | ---: | ---: |
| 41 | 1 | 0.047 | 19,420 |
| 41 | 64 | 1.504 | 42,292 |
| 1,000 | 64 | 2.235 | 28,369 |
| 10,000 | 64 | 6.849 | 9,329 |
| 100,000 | 8 | 6.185 | 1,293 |

Throughput uses total elapsed time across repetitions rather than the reciprocal
of the median. The separate traced peak was 104,598 bytes for the 100,000 × 8
synthetic Pass reused-adapter case. See the JSON for every mode/status, raw samples,
95th-percentile nearest-rank measurements, allocation peaks and process RSS.

These numbers exclude CLI startup, software/database inventory verification, FASTA
serialization, all external searches, and output generation. In particular, the
production adapter hashes every inventoried database file before **and after** each
run. Internal subprocess batches remain bounded at 64 records/one million bases,
and all results are held until the final inventory check succeeds. At approximately
40 GB extracted database size, that is roughly 80 GB of logical file reads per run,
excluding searches; physical storage traffic depends
on filesystem caching. No claim about full-tool throughput follows from parser timings.

## Why real execution was not attempted

The workspace reports 33,770,192,896 total bytes (31.45 GiB) and approximately
30.92 billion free bytes (28.80 GiB); `commec` is absent from PATH. The official
[installation requirements](https://github.com/ibbis-bio/common-mechanism/wiki/Install)
(accessed 2026-10-15) describe roughly 40 GB extracted databases, recommend at least
50 GB free SSD space and 16 GB RAM, and recommend 16 CPU threads. The database does
not fit this workspace. No database was downloaded and no `commec` installation was
attempted. Real runtime and biological performance remain **unmeasured**.

## Separate full-tool protocol for a provisioned environment

This protocol is **not executed evidence**. Use a suitable Linux host with adequate
SSD space and memory. An operator must first provision the pinned
[v2.1.0 release](https://github.com/ibbis-bio/common-mechanism/tree/v2.1.0) and its
complete database, following the official installation guide, and validate the
operator-owned manifest, revisions, full database inventory and software inventory.
Pin all required executables/libraries and preserve the manifest and hashes with the
run. Do not use reduced databases, skipped searches, auto-update, resume, or a
successful-result cache to improve timing. Keep the effective configuration and
normal screening policy identical across measurements. Verify full-tool outputs
against the adapter's pinned schema rather than assuming compatibility.

On that host, the following command exercises the actual adapter and policy over
the same harmless toy inputs. It retains decisions/statuses without asserting that
real screening should return Pass. Set the manifest path to an existing validated
operator configuration. This does not create or repair that configuration.

```sh
export CERNAL_BENCH_MANIFEST=/absolute/path/operator-screening-manifest.json
mkdir -p full-tool-evidence
/usr/bin/time -v -o full-tool-evidence/process-resources.txt \
  env PYTHONPATH=src UV_CACHE_DIR=/tmp/uv-cache uv run --no-sync python - \
  > full-tool-evidence/measurements.json <<'PY'
import json
import os
import time
from datetime import UTC, datetime
from engine.common_mechanism import load_adapter, screen_final_batch
from tools.benchmark_final_screening import BATCHES, LENGTHS, synthetic_case

manifest_path = os.environ['CERNAL_BENCH_MANIFEST']
rows = []
for length in LENGTHS:
    for batch in BATCHES:
        if length * batch > 1_000_000:
            continue
        submissions, _ = synthetic_case(length, batch, 'Pass')
        adapter = load_adapter(manifest_path)
        for repetition in range(5):
            start = time.perf_counter()
            results = screen_final_batch(submissions, adapter)
            elapsed = time.perf_counter() - start
            rows.append({
                'length_bp': length, 'batch_size': batch,
                'repetition': repetition, 'elapsed_seconds': elapsed,
                'label': 'first observed run' if repetition == 0 else 'repeated full run',
                'decisions': [r.decision.value for r in results],
                'adapter_statuses': [r.adapter_status.value for r in results],
                'inputs_per_second': batch / elapsed,
            })
print(json.dumps({'recorded_at': datetime.now(UTC).isoformat(), 'rows': rows}, indent=2))
PY
```

Every iteration launches a fresh CLI through `screen_many`; repeated runs retain
only the immutable adapter configuration and any OS filesystem cache. “First
observed” is not proof of a cold cache. A genuinely cold measurement requires a
fresh isolated host/container/storage-cache state documented by the operator;
do not drop shared host caches or change security settings for this benchmark.
Record disk/RAM/CPU, tool/dependency/database versions, manifest/source hashes,
thread count, timeout, storage type and cache state. GNU time records process
resource diagnostics; use an isolated cgroup/host memory monitor for aggregate
concurrent parent-plus-child peak memory, because Python tracemalloc cannot measure
BLAST/HMM subprocess allocations. Keep raw per-run wall time and status, and report
failed/held/timeouts separately, never as successful-screen throughput. Diagnose
non-COMPLETE results before interpreting runtime. Preserve the existing timeout
rather than silently relaxing it. Separately report setup time and database bytes
read. For concurrent load, keep per-job thread limits fixed and report queueing,
complete/held counts and host resource saturation; do not omit any screening stages.

These runs would still measure performance on toy inputs only. Establishing
biological validity requires a separate, responsibly governed validation programme
and is outside this benchmark.
