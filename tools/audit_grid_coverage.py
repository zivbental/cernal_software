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
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from characterise_axes import RUN as RUN_COLUMNS

from engine.gates.toehold import ProkaryoticToeholdAndGate as Gate

#: The settings whose value must not change inside one cell. Taken from `characterise_axes.RUN`
#: so a new setting is audited the day it is added, minus the two that legitimately vary: the
#: accessibility floor's VALUE differs per gene pair under the `mean` rule (the rule is what is
#: comparable, and it is in the list), and `min_access` carries that per-pair value.
VARIES_BY_PAIR = frozenset({"min_access"})
PROVENANCE = tuple(name for name in RUN_COLUMNS if name not in VARIES_BY_PAIR)

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
    #: Every provenance tuple seen, overall and per cell. A cell holding more than one was
    #: built under two different settings, and every comparison in this project is paired
    #: WITHIN a cell -- so such a cell cannot be compared with itself and nothing else says so.
    provenance: Counter[tuple[str, ...]] = Counter()
    per_column: dict[str, Counter[str]] = {name: Counter() for name in PROVENANCE}
    cell_provenance: dict[tuple[str, ...], set[tuple[str, ...]]] = defaultdict(set)
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
                stamp = tuple((row.get(name) or "") for name in PROVENANCE)
                provenance[stamp] += 1
                cell_provenance[cell].add(stamp)
                for name, value in zip(PROVENANCE, stamp, strict=True):
                    per_column[name][value] += 1
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

    # ---- provenance: was the whole table built the same way? ---------------------------
    print("\n  PROVENANCE -- what each row says it was built with")
    print("    `--resume` keys on the design's axis tuple, NOT on these settings, so a run")
    print("    resumed after a setting changed appends rows the old ones cannot be compared")
    print("    with. Every setting is on the row, so this is checkable rather than assumed.")
    for name in PROVENANCE:
        seen = per_column[name]
        if len(seen) <= 1:
            only = next(iter(seen), "")
            print(f"    {name:18s} one value: {only or '(empty)'}")
            continue
        print(f"    {name:18s} {len(seen)} VALUES  <- the table is not uniform on this")
        for value, count in seen.most_common():
            print(f"      {value or '(empty)':24s}{count:>10,}  {count / rows:>7.1%}")

    mixed = {cell: stamps for cell, stamps in cell_provenance.items() if len(stamps) > 1}
    print(f"\n    distinct provenance tuples: {len(provenance)}")
    print(
        f"    cells built under ONE setting: {len(cell_provenance) - len(mixed):,} of "
        f"{len(cell_provenance):,}"
    )
    if mixed:
        share = len(mixed) / len(cell_provenance)
        print(f"    MIXED CELLS: {len(mixed):,} ({share:.1%}) -- a paired comparison inside one of")
        print("    these compares designs built differently. Analyse the largest uniform stratum")
        print("    and report these as excluded, with the count.")
        for cell in sorted(mixed)[:6]:
            gene_a, gene_b, x_start, xstar_start, geom = cell
            print(
                f"      {gene_a}/{gene_b} x{x_start} xs{xstar_start} {geom:20s} "
                f"{len(mixed[cell])} settings"
            )
        if len(mixed) > 6:
            print(f"      ... and {len(mixed) - 6:,} more")
    else:
        print("    -> every cell is internally uniform: a within-cell comparison is sound")

    print("  grid points present per cell")
    print(
        f"    min {min(covered)}   median {st.median(covered):.0f}   "
        f"mean {st.mean(covered):.1f}   max {max(covered)}   of {grid}"
    )
    print(f"    sd {st.pstdev(covered):.1f}")
    complete = sum(1 for value in covered if value == grid)
    print(
        f"    cells with the WHOLE grid: {complete} of {len(points)} ({complete / len(points):.1%})"
    )
    print(f"\n  ABSENT {missing:,} of {total:,} grid points  ({missing / total:.1%})")
    if missing:
        # ABSENT, not MISSING. A results table cannot tell a point that was never
        # attempted from one `generate_designs` declines to build -- a closure patch can
        # leave a domain the assembly rules reject, and the reading-frame repair can fail
        # with no substitution available. Reported as a shortfall and never as a to-do.
        print("  absent is not the same as undone: generate_designs declines some points,")
        print("  and a table cannot tell the two apart. The breakdown below separates them.")

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

        # Which levels the absent points belong to. An axis level that is unbuildable for
    # some trigger pairs goes missing WHOLLY for those cells, so its count is a clean
    # multiple of the other axes' sizes; work left undone is scattered instead. Seeing the
    # shape is what tells the two apart without rebuilding anything.
    print("\n  the absent points, by axis level")
    axes = (
        ("closure", Gate.CLOSURES, 0),
        ("upper3", Gate.UPPER3, 1),
        ("lower3", Gate.LOWER3, 2),
    )
    whole = {
        (closure, upper, lower)
        for closure, _ in Gate.CLOSURES
        for upper, _ in Gate.UPPER3
        for lower, _ in Gate.LOWER3
    }
    absent_points = [point for value in points.values() for point in whole - value]
    for axis_name, levels, slot in axes:
        print(f"    {axis_name}")
        counts = Counter(point[slot] for point in absent_points)
        for level, _ in levels:
            count = counts.get(level, 0)
            share = count / len(absent_points) if absent_points else 0.0
            bar = "#" * round(34 * share) if count else ""
            print(f"      {level:18s}{count:>8,}{share:>8.1%}  {bar}")
        spread = max(counts.values(), default=0) - min(
            (counts.get(level, 0) for level, _ in levels), default=0
        )
        if spread == 0:
            print("      -> flat: this axis is never the reason a point is absent")
        else:
            worst = max(((counts.get(name, 0), name) for name, _ in levels))[1]
            print(f"      -> concentrated in {worst}, which is where to look")

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
