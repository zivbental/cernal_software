"""The barrier against the equilibrium leak, on molecules that are the same molecule.

Two runs are read, and they differ in which stem of a cell was built:

* **arbitrary stem** -- `landing_*.csv`, the Pareto front's first entry in enumeration
  order, levers at their no-op settings. 420 cells.
* **preferred stem** -- `best_*.csv`, the unlevered design with the highest
  `lock_minus_a_site`, which is the stem the design rule points at and the one a run
  would build on. `lock_minus_a_site` spreads about 40 kcal/mol within a single cell, so
  these are not small differences.

Both are joined to the grid row describing that exact design, so the barrier and the
leak are properties of one molecule rather than of a molecule and a cell average.

Reported per run: the rank correlation, each quantity's spread, and the 2x2 of agreement
at four barrier heights. RT is 0.6163 kcal/mol at 37 C, so a barrier of 3.0 is about a
hundredfold slowdown.

**HAZARD is the firmer column.** findpath walks a heuristic direct path, so the barrier
is an upper bound: a downhill path we found certainly exists, while a barrier we found
may not be the lowest one.
"""

from __future__ import annotations

import argparse
import csv
import math
import pathlib
import statistics as st
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
GRID = ROOT / "docs/assets/axes_c8/rows.csv"
BARRIERS = ROOT / "docs/assets/barrier"
LEAK_GATE = 0.5
CUTS = (0.0, 0.6, 1.5, 3.0)


def spearman(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 8:
        return None

    def ranks(values: list[float]) -> list[float]:
        order = sorted(range(n), key=lambda i: values[i])
        out = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and values[order[j + 1]] == values[order[i]]:
                j += 1
            for k in range(i, j + 1):
                out[order[k]] = (i + j) / 2 + 1
            i = j + 1
        return out

    rx, ry = ranks(xs), ranks(ys)
    mx, my = st.mean(rx), st.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry, strict=True))
    dx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    dy = math.sqrt(sum((b - my) ** 2 for b in ry))
    return None if dx == 0 or dy == 0 else num / (dx * dy)


def report(label: str, pairs: list[tuple[float, float]]) -> None:
    if len(pairs) < 8:
        print(f"\n  {label}: {len(pairs)} designs, too few")
        return
    barriers = [b for b, _ in pairs]
    leaks = [v for _, v in pairs]
    print(f"\n  {label}  --  n = {len(pairs):,} designs")
    print(f"    rho(barrier, leak) ................ {spearman(barriers, leaks):+.3f}")
    print(
        f"    barrier   median {st.median(barriers):+.2f}  min {min(barriers):+.2f}  "
        f"max {max(barriers):+.2f}  kcal/mol"
    )
    print(
        f"    leak      median {st.median(leaks):.3f}  min {min(leaks):.3f}  max {max(leaks):.3f}"
    )
    leaky = [b for b, v in pairs if v >= LEAK_GATE]
    shut = [b for b, v in pairs if v < LEAK_GATE]
    print(f"    equilibrium calls {len(leaky):,} leaky and {len(shut):,} shut")
    print(
        f"      {'barrier above':>14}{'RESCUE':>9}{'HAZARD':>9}"
        f"{'agree reject':>14}{'agree admit':>13}"
    )
    for cut in CUTS:
        rescue = sum(1 for b in leaky if b > cut)
        hazard = sum(1 for b in shut if b <= cut)
        print(
            f"      {cut:>12.1f}  {rescue:>9,}{hazard:>9,}"
            f"{len(leaky) - rescue:>14,}{len(shut) - hazard:>13,}"
        )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grid", type=pathlib.Path, default=GRID)
    parser.add_argument(
        "--barriers",
        type=pathlib.Path,
        default=BARRIERS,
        help="folder of barrier CSVs; the corrected run is docs/assets/barrier",
    )
    args = parser.parse_args(argv)

    csv.field_size_limit(min(sys.maxsize, 2**31 - 1))
    runs: dict[str, dict[tuple, float]] = {}
    for pattern, label in (
        ("landing_*.csv", "arbitrary stem"),
        ("best_*.csv", "preferred stem"),
        ("designs_*.csv", "across the lever grid"),
    ):
        found: dict[tuple, float] = {}
        for path in sorted(args.barriers.glob(pattern)):
            with path.open(newline="", encoding="utf-8") as handle:
                for row in csv.DictReader(handle):
                    if not row.get("b_10"):
                        continue
                    # `designs_*` already carries the leak of its own row, so it needs no
                    # join; the other two are keyed to the unlevered, stem-0 or
                    # best-lock row and are joined below.
                    if row.get("leak"):
                        found[("direct", row["key"])] = (float(row["b_10"]), float(row["leak"]))
                        continue
                    found[
                        (
                            row["geom_label"],
                            row["gene_a"],
                            row["gene_b"],
                            int(float(row["x_start"])),
                            int(float(row["xstar_start"])),
                            int(float(row["len_x"])),
                            int(float(row["stem_index"])),
                        )
                    ] = float(row["b_10"])
        if found:
            runs[label] = found

    if not runs:
        print(f"\n  no barrier files in {BARRIERS}")
        return 0

    need = {k for f in runs.values() for k in f if k[0] != "direct"}
    leaks: dict[tuple, float] = {}
    if need:
        with args.grid.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if row["closure"] != "open_3x3" or row["upper3"] != "trigger_derived":
                    continue
                if row["lower3"] != "trigger_derived" or not row["xstar_engA_10"]:
                    continue
                key = (
                    row["geom"],
                    row["gene_a"],
                    row["gene_b"],
                    int(float(row["x_start"])),
                    int(float(row["xstar_start"])),
                    int(float(row["len_x"])),
                    int(float(row["stem_index"])),
                )
                if key in need:
                    leaks[key] = float(row["xstar_engA_10"])

    for label, found in runs.items():
        pairs: list[tuple[float, float]] = []
        for key, value in found.items():
            if key[0] == "direct":
                pairs.append(value)
            elif key in leaks:
                pairs.append((value, leaks[key]))
        report(label, pairs)
    print("\n  HAZARD is the firmer column: a downhill path we found certainly exists,")
    print("  while a barrier we found may not be the lowest one.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
