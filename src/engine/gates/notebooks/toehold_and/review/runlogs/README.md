# Run logs — the provenance behind the quoted numbers

These 29 files were sitting loose in the repository root. They are **ours, not CERNAL's**: the
console output of the A0 sweep's sharded runs, written by the `run_*.ps1` wrappers. None was ever
tracked by git, so nothing had been committed and nothing was lost by moving them — but they are
not disposable either, because several numbers this work quotes are only recorded here. iGEM asks
that a reader be able to re-run any statistic we state, and that starts with knowing what was run.

They are tracked from here on, at 134 KB in total.

| family | n | what it recorded |
|---|---|---|
| `shard_*.log` | 5 | the first full objective sweep: designs skipped by closure and by rare codon, designs stopped at the ON ceiling, and the score distribution per shard |
| `completions_*.log` | 6 | `complete_panel.py` — the 40-column completion pass |
| `hp_*.log` | 6 | the hairpin pass |
| `ied_*.log` | 6 | the IED completion pass |
| `fill_*.log` | 6 | the gap-filling re-runs |

## What they are evidence for

Read `shard_0.log` for the shape of a sweep run:

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

A log is a record, not a result. Everything in them is regenerable from `results/` by the drivers
in the directory above; the point of keeping them is that a number quoted in the write-up can be
traced to the run that produced it. Where a log and a current run disagree, the current run wins
and the log says what changed.
