"""How much of the design grid has actually been measured, per cell?

Run::

    uv run python tools/audit_grid_coverage.py --out axes_c8

A characterisation table can look complete and not be. The overnight ``axes_c8`` run
covered all sixteen closures and all six gene pairs, and still left 44.6% of the grid
unbuilt, because ``--grid-stride 2`` gave each shard half the closure blocks and each cell
is handled by exactly one shard. Counting rows, or counting distinct closures, says
nothing about that. The quantity that matters is **how many of the grid's points exist
inside one cell**, because every comparison this project makes is paired within a cell: a
design and its control have to differ in one axis and agree on everything else, and a
missing half-cell silently removes the pairs rather than reporting them.

So this reports, per cell, the fraction of ``len(CLOSURES) x len(UPPER3) x len(LOWER3)``
points present, and summarises where the holes are. It reads the engine's own axis
declarations rather than restating the grid size, so it cannot disagree with what
``generate_designs`` walks.

A cell here is one ``(gene_a, gene_b, x_start, xstar_start, geom)``: one trigger pair in
one geometry. Stems are counted separately, because ``stem_order="front_tops"`` has no
quota and legitimately returns a different number per pair.
"""

from __future__ import annotations

import argparse
import csv
import pathlib
import statistics as st
import sys
from collections import Counter, defaultdict

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from engine.gates.toehold import ProkaryoticToeholdAndGate as Gate

RESULTS = (
    pathlib.Path(__file__).resolve().parent.parent
    / "src/engine/gates/notebooks/toehold_and/results"
)


def cell_of(row: dict[str, str]) -> tuple[str, ...]:
    return (row["gene_a"], row["gene_b"], row["x_start"], row["xstar_start"], row["geom"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="axes_c8", help="the run's output prefix")
    parser.add_argument("--shards", type=int, default=6)
    parser.add_argument(
        "--holes",
        type=int,
        default=6,
        help="how many of the least-covered cells to list",
    )
    args = parser.parse_args(argv)

    grid = len(Gate.CLOSURES) * len(Gate.UPPER3) * len(Gate.LOWER3)
    print(
        f"\n  the full grid is {len(Gate.CLOSURES)} closures x {len(Gate.UPPER3)} upper3 "
        f"x {len(Gate.LOWER3)} lower3 = {grid} points per cell"
    )

    points: dict[tuple[str, ...], set[tuple[str, str, str]]] = defaultdict(set)
    stems: dict[tuple[str, ...], set[str]] = defaultdict(set)
    per_closure: Counter[str] = Counter()
    rows = measured = 0
    skipped: Counter[str] = Counter()

    found = []
    for index in range(args.shards):
        path = RESULTS / f"{args.out}_{index}.csv"
        if not path.exists():
            continue
        found.append(path.name)
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                rows += 1
                cell = cell_of(row)
                points[cell].add((row["closure"], row["upper3"], row["lower3"]))
                stems[cell].add(row["stem_index"])
                per_closure[row["closure"]] += 1
                reason = row.get("skipped") or ""
                if reason:
                    skipped[reason] += 1
                else:
                    measured += 1

    if not points:
        print(f"  no rows found for {args.out!r} in {RESULTS}")
        return 1

    covered = [len(value) for value in points.values()]
    missing = sum(grid - value for value in covered)
    total = grid * len(points)

    print(f"  read {len(found)} shard files, {rows:,} rows")
    print(f"  {measured:,} fully measured ({measured / rows:.1%}), {len(points)} cells\n")

    print("  grid points present per cell")
    print(
        f"    min {min(covered)}   median {st.median(covered):.0f}   "
        f"mean {st.mean(covered):.1f}   max {max(covered)}   of {grid}"
    )
    print(f"    sd {st.pstdev(covered):.1f}")
    complete = sum(1 for value in covered if value == grid)
    print(
        f"    cells with the WHOLE grid: {complete} of {len(points)} "
        f"({complete / len(points):.1%})"
    )
    print(f"\n  MISSING {missing:,} of {total:,} grid points  ({missing / total:.1%})")
    if missing:
        median_stems = st.median([len(value) for value in stems.values()])
        print(
            f"  at a median {median_stems:.0f} stems per cell that is roughly "
            f"{missing * median_stems:,.0f} designs still to build"
        )
        print("  -> tools\\run_axes_complete.cmd builds exactly those and nothing else")

    print("\n  stems per cell (no quota, so this varies by design)")
    counts = [len(value) for value in stems.values()]
    print(f"    min {min(counts)}   median {st.median(counts):.0f}   max {max(counts)}")

    if skipped:
        print("\n  rows present but not fully measured, by reason")
        for reason, count in skipped.most_common():
            print(f"    {reason:24s} {count:>8,}  ({count / rows:.1%})")

    print("\n  closures, by how many rows carry them")
    width = max(per_closure.values())
    for name, _ in Gate.CLOSURES:
        count = per_closure.get(name, 0)
        bar = "#" * round(42 * count / width) if count else ""
        flag = "" if count else "   <- ABSENT"
        print(f"    {name:18s}{count:>8,}  {bar}{flag}")

    if args.holes:
        print(f"\n  the {args.holes} least-covered cells")
        worst = sorted(points.items(), key=lambda kv: len(kv[1]))[: args.holes]
        for cell, present in worst:
            gene_a, gene_b, x_start, xstar_start, geom = cell
            print(
                f"    {gene_a}/{gene_b} x{x_start} xs{xstar_start} {geom:20s} "
                f"{len(present):>3} of {grid}"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
