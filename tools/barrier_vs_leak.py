"""Which designs the equilibrium rejects that the kinetics would rescue, and the reverse.

**The question this answers.** The feasible set rejects a design when trigger A takes
*x\\** with no trigger B present -- an equilibrium occupancy. But equilibrium says where a
molecule settles, not how fast it gets there. A design can be headed for a leaky resting
state and still be protected, if the path there is uphill. Those designs are rejected
today and might not deserve to be.

So the output is a 2x2 and not a correlation. A correlation asks whether two rankings
agree overall; what matters here is a specific disagreement in a specific direction, and
it is a list of cells rather than a coefficient.

    equilibrium says         kinetics says        what it means
    leaks                    barrier              RESCUE -- rejected, maybe wrongly
    shut                     no barrier           HAZARD -- admitted, maybe wrongly
    leaks                    no barrier           agreed, correctly rejected
    shut                     barrier              agreed, correctly admitted

**Two things bound how far this can be read.**

The barrier is an **upper bound**: findpath walks a heuristic direct path, not the
minimum-barrier one. So "no barrier found" is the strong claim -- a downhill path we
found certainly exists -- while "there is a barrier" may only mean we did not find the
cheaper route. The HAZARD count is therefore firmer evidence than the RESCUE count.

And the barrier is computed on the **unlevered** assembly, one stem per trigger pair, so
it belongs to a cell rather than to a single lever point. The equilibrium side is
summarised over that cell's lever points, and a cell is called leaky when most of them
leak.
"""

from __future__ import annotations

import argparse
import collections
import csv
import pathlib
import statistics as st
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
GEOM = {"naive": "arm18/inv18/capnone", "kim": "arm20/inv17/capAUA"}

#: The feasible set's own cut on trigger A taking x* with no trigger B.
LEAK_GATE = 0.5
#: Barrier heights to report the table at, in kcal/mol. RT is 0.6163 at 37 C, so 0.6 is
#: about one thermal unit -- a factor of e -- and 3.0 is about a hundredfold slowdown.
BARRIERS = (0.0, 0.6, 1.5, 3.0)


def read_barriers(folder: pathlib.Path) -> dict[tuple, float]:
    out: dict[tuple, float] = {}
    for path in sorted(folder.glob("landing_*.csv")):
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if not row.get("b_10"):
                    continue
                label = row.get("geom_label") or GEOM.get(row["geom"], row["geom"])
                # xstar_start is part of the identity: four cells share everything
                # else with another cell and silently overwrote each other without it,
                # which is why this read 416 of 420.
                key = (
                    label,
                    row["gene_a"],
                    row["gene_b"],
                    int(float(row["x_start"])),
                    int(float(row["xstar_start"])),
                    int(float(row["len_x"])),
                )
                out[key] = float(row["b_10"])
    return out


def read_leaks(path: pathlib.Path, wanted: set[tuple]) -> dict[tuple, list[float]]:
    csv.field_size_limit(min(sys.maxsize, 2**31 - 1))
    out: dict[tuple, list[float]] = collections.defaultdict(list)
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        leak_at = header.index("xstar_engA_10")
        index = [
            header.index(n) for n in ("geom", "gene_a", "gene_b", "x_start", "xstar_start", "len_x")
        ]
        for row in reader:
            key = (
                row[index[0]],
                row[index[1]],
                row[index[2]],
                int(float(row[index[3]])),
                int(float(row[index[4]])),
                int(float(row[index[5]])),
            )
            if key in wanted and row[leak_at]:
                out[key].append(float(row[leak_at]))
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--barriers", type=pathlib.Path, default=ROOT / "docs/assets/barrier")
    parser.add_argument("--grid", type=pathlib.Path, default=ROOT / "docs/assets/axes_c8/rows.csv")
    args = parser.parse_args(argv)

    barriers = read_barriers(args.barriers)
    if not barriers:
        print(f"\n  no barrier rows yet in {args.barriers}")
        print("  run:  tools\\run_barrier.cmd 0   (then 1..5)")
        return 0
    leaks = read_leaks(args.grid, set(barriers))
    joined = [k for k in barriers if leaks.get(k)]
    print(f"\n  {len(barriers):,} cells measured, {len(joined):,} joined to the grid")
    if len(joined) < 8:
        print("  too few joined to tabulate yet")
        return 0

    share_leaky = {k: sum(1 for v in leaks[k] if v >= LEAK_GATE) / len(leaks[k]) for k in joined}
    leaky = {k for k in joined if share_leaky[k] > 0.5}
    print(
        f"  {len(leaky):,} cells leak at equilibrium in most of their designs, "
        f"{len(joined) - len(leaky):,} do not"
    )

    print(
        f"\n  {'barrier above':>14}{'RESCUE':>10}{'HAZARD':>10}"
        f"{'agreed reject':>16}{'agreed admit':>14}"
    )
    for cut in BARRIERS:
        rescue = sum(1 for k in leaky if barriers[k] > cut)
        hazard = sum(1 for k in joined if k not in leaky and barriers[k] <= cut)
        print(
            f"  {cut:>12.1f}  {rescue:>10,}{hazard:>10,}"
            f"{len(leaky) - rescue:>16,}{len(joined) - len(leaky) - hazard:>14,}"
        )

    cut = 1.5
    rescued = sorted((barriers[k], k) for k in leaky if barriers[k] > cut)
    print(f"\n  the RESCUE list at {cut} kcal/mol: cells the feasible set rejects on the")
    print("  equilibrium leak, with a real barrier in front of that leak")
    if not rescued:
        print("    none")
    for value, key in reversed(rescued[-20:]):
        label, gene_a, gene_b, x_start, len_x = key
        print(
            f"    {value:+7.2f}  {gene_a}>{gene_b}  x_start {x_start:>5}  "
            f"len_x {len_x}  {label}   median leak "
            f"{st.median(leaks[key]):.3f} over {len(leaks[key])} designs"
        )
    if len(rescued) > 20:
        print(f"    ... and {len(rescued) - 20:,} more")

    print("\n  RESCUE is the weaker column: the barrier is an upper bound, so a barrier")
    print("  found may not be the lowest one. HAZARD is the firmer claim -- a downhill")
    print("  path we found certainly exists.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
