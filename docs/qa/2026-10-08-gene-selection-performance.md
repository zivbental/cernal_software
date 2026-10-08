# Exact gene selection performance comparison

The full bundled `ecoli/92117__44313016.csv` comparison has 3,000 rows. With
`max_genes=3`, both implementations screened the same 1,192 eligible transcripts
(1,161,495 total bases), selected the same three genes with exactly equal scores,
trigger yields and usable-window counts, and emitted identical warnings. No gene
was skipped for a new compute budget and no ranking policy changed.

The independent original per-window implementation took **58.524 seconds**; the
transcript interval/prefix implementation took **0.640 seconds** in this local run
(91.45 times faster). These measurements describe Stage 1 only, on one machine and
one input. They do not predict folding, assembly, or total job time.

The optimized implementation screens motif occurrences once per transcript,
then uses containment ranges and GC prefix counts for each trigger length. Long
homopolymers contribute every contained prohibited minimum-length run. A custom
screener subclass retains the original per-window behavior. Scratch arrays are
local to one transcript; no cross-run or unbounded method cache is added.

The regression suite independently checks exact yields over all assembly standards,
several homopolymer limits, GC boundaries, overlapping motifs/start codons, short
transcripts and a real catalog subset. It also verifies one whole-transcript motif
scan replaces thousands of per-window scans.

Reproduce the full comparison from the repository root with:

```sh
UV_CACHE_DIR=/tmp/cernal-qa-uv PYTHONPATH=$PWD/src uv run --offline --no-sync python tools/benchmark_gene_selection.py
```

The companion JSON records the input digest, constraints, timings and selected
scientific values. The script asserts equal selection and warnings before writing
that report.
