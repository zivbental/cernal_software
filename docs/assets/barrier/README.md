# The corrected barrier run

These are the rows behind Figure 7.5 of the model page, the comparison table in its
§ 7.6, and the proposed experimental contrast in its § 9.6. They are tracked rather than
regenerated because the run took an overnight sweep across six processes and, while they
were ignored, this directory existed on exactly one desktop.

Nothing here is a measurement of a molecule. A barrier is the largest energy rise along a
refolding path a heuristic search found, so it is an **upper bound** on the lowest barrier
in the modelled landscape: a large value does not establish that a design is kinetically
protected, and the page says so wherever it quotes one.

## What produced them

| Files | Script | Command | What each row is |
|---|---|---|---|
| `designs_0..5.csv` | `tools/barrier_designs.py` | `tools\run_barrier_designs.cmd 0..5` | one design, rebuilt with its own lever settings, so its barrier sits beside its own leak. Eight designs per cell |
| `best_0..3.csv` | `tools/barrier_designs.py --select best-lock` | `tools\run_barrier_best.cmd 0..5` | the unlevered design the design rule prefers in each cell: highest `lock_minus_a_site` |
| `landing_0..5.csv` | `tools/barrier_landing.py` | `tools\run_barrier.cmd 0..5` | one cell, at its arbitrary stem |
| `on_state_cost.csv` | derived, see below | — | the ON-state opening cost each of the above has to be joined to |

Each shard writes one file and skips keys already present, so a killed window is restarted
by rerunning the same line. `--shard` takes `i/n` as **one** argument.

## Model settings

ViennaRNA 2.7.2, Turner 2004 parameters, 37 °C, with model details passed explicitly per
calculation on an `RNA.md()`; the package's process-global temperature is never written.
`FINDPATH_WIDTH = 10` in both producing scripts. Measured width-independent: the same
barriers come back at 10, 100 and 20000.

## The correction that makes this the canonical run

An earlier run of the same scripts stored `E(end) − E(start)` and called it a barrier.
11.8% of its values were negative, which a barrier cannot be. Two faults, both in one
call:

* `path_findpath_saddle(s1, s2, width, maxE)` takes a search **width** as its third
  argument, not an energy ceiling, and it was being passed one;
* on these molecules the call returned the energy of the end structure rather than the
  maximum along the way — verified 12 times out of 12.

The barrier is now taken from the path itself: `compound.path_findpath(start, end, width)`,
then `max(eval_structure(step)) − eval_structure(start)` over the steps it visited. Over
3,839 designs the corrected values run +4.50 to +25.20 kcal/mol, median +10.60, **none
negative**.

The superseded run is kept outside the repository, in `docs/assets/barrier_superseded/`,
whose own README says why. Its numbers are wrong and are deliberately not tracked.

## `on_state_cost.csv`, and the one input that is not here

`tools/experiment_contrasts.py` joins each barrier row to its ON-state opening cost,
`dG_open_11`, which lives in `docs/assets/axes_c8/rows.csv`. That file is **643 MB** and
cannot be tracked: GitHub rejects any file over 100 MB.

It is not needed in full. Only the designs that carry a barrier reading matter, and only
that one column, so the join is extracted once and tracked here: 3,419 rows, 324 KB,
every barrier design matched. Regenerate it from a local sweep with the key columns
`geom, gene_a, gene_b, x_start, xstar_start, len_x, stem_index, closure, upper3, lower3`,
noting that the barrier files spell the geometry `geom_label` and the grid spells it
`geom`, with the two values mapping as `naive → arm18/inv18/capnone` and
`kim → arm20/inv17/capAUA`.

So: **Figure 7.5 and the § 7.6 table regenerate from this directory alone. The § 9.6
contrast regenerates from this directory plus `on_state_cost.csv`. Nothing here
reproduces the sweep that produced `rows.csv`,** which remains the gap § 9.7 of the page
describes.

## Checksums

SHA-256 over the stored bytes. `.gitattributes` pins these files to LF in the working
copy as well as in the repository, so these digests hold on a Windows clone too — without
that pin a checkout rewrites every newline and an undamaged file hashes wrong.

| File | Rows | Bytes | SHA-256 |
|---|---:|---:|---|
| `best_0.csv` | 77 | 14,499 | `1a5995caa31ba60b…` |
| `best_1.csv` | 77 | 14,271 | `0f07a373ff8f9c1f…` |
| `best_2.csv` | 76 | 14,314 | `30865bab7d6f24af…` |
| `best_3.csv` | 76 | 14,088 | `838e4a42310df61d…` |
| `designs_0.csv` | 519 | 90,225 | `8adaa862950031a6…` |
| `designs_1.csv` | 519 | 90,933 | `17b147b555240636…` |
| `designs_2.csv` | 519 | 89,952 | `54cd82679cf09760…` |
| `designs_3.csv` | 519 | 90,982 | `ef87f1024165aa6c…` |
| `designs_4.csv` | 519 | 89,932 | `5fc76513c4cbc821…` |
| `designs_5.csv` | 518 | 90,767 | `3b93eb5061006b1c…` |
| `landing_0.csv` | 70 | 6,184 | `4c3dfbffcb6ce775…` |
| `landing_1.csv` | 70 | 6,522 | `1a6bb2eec11a789f…` |
| `landing_2.csv` | 70 | 6,171 | `e3bcddae3107844e…` |
| `landing_3.csv` | 70 | 6,508 | `b0c5c60dcff4b54e…` |
| `landing_4.csv` | 70 | 6,158 | `0a2db34990b02b91…` |
| `landing_5.csv` | 70 | 6,533 | `69dd35f1472ff1ac…` |
| `on_state_cost.csv` | 3,419 | 323,966 | `385f932b660980da…` |

Verify the lot with `uv run python tools/barrier_checksums.py`, which recomputes them and
prints any file whose digest has moved.
