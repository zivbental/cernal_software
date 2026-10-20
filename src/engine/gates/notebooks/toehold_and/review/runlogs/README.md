# Run logs — the provenance behind the quoted numbers

This record describes 29 historical console logs from the A0 research sweeps,
written by the `run_*.ps1` wrappers. They are research provenance, not CERNAL runtime
inputs. **Only this README is tracked in this directory on the assessed main
revision.** The former statement that all 29 logs were committed was incorrect.
The logs cannot be recovered from this directory in a fresh clone; do not treat
their quoted excerpts as independently available raw evidence.

| family | n | what it recorded |
|---|---|---|
| `shard_*.log` | 5 | the first full objective sweep: designs skipped by closure and by rare codon, designs stopped at the ON ceiling, and the score distribution per shard |
| `completions_*.log` | 6 | `complete_panel.py` — the 40-column completion pass |
| `hp_*.log` | 6 | the hairpin pass |
| `ied_*.log` | 6 | the IED completion pass |
| `fill_*.log` | 6 | the gap-filling re-runs |

## What they are evidence for

The following retained excerpt describes the shape of a `shard_0.log` run:

```
  transcript 711 nt from mCherry_original.txt
  skipped 9,000 designs by closure
  skipped 19,750 designs by rare codon
  shard 0 of 5
  ...
  wrote 4,315 new rows to obj_full_p3_0.csv (3,924 stopped at the ON ceiling, 391 measured in full)
  score over 6,324: median 73.54  mean 72.94  sd 8.52  best 47.04  worst 96.43  (lower is better)
```

Two things only these files hold:

* **The ON ceiling's real rejection rate.** 3,924 of 4,315 stopped there — the measurement behind
  "scoring the ON tube first gives a 5.2x speedup", which is why the funnel is ordered as it is.
* **`ied_0.log` is the run that produced almost nothing** — it stops at `1/2471 written 1`. That
  is the `--shards 6 --shard 0` invocation that argparse rejected: `--shard` takes `i/n` as ONE
  argument. The log is the record of that, and the reason the flag is documented the way it is.

## Reproducing rather than trusting them

A log records one run's configuration and execution. It cannot be reconstructed
exactly from a later CSV or a later run. Some generated CSVs are recoverable through
the pinned research archive; other local outputs are not. See the
[reproduction map](../../../../../../../docs/prokaryotic-and-reproducibility.md)
for recovery commands and evidence that remains unavailable. A fresh run must
record its own revision, inputs and settings rather than silently replacing the
historical record.
