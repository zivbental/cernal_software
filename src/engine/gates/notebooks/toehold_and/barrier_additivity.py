"""Does the barrier ADD to another arm, and what does an epsilon-constraint on it buy?

    uv run python src/engine/gates/notebooks/toehold_and/barrier_additivity.py

The barrier is weak alone -- +0.179 on Green's 168, +0.280 on his 13 -- and its standalone picks
have failed mechanistic checks by three separate routes. What made it worth keeping was never its
own correlation but its **additivity**: it is nearly orthogonal to everything else we score
(agreement -0.050 with A_M gain, +0.282 with dG_rbs_linker), so it can carry information the base
arm does not.

Two different questions, measured separately because they are answered by different data:

1. **Does adding it lift a base arm?** Measurable on Green's libraries, where measured ON/OFF
   exists: compare rho(base) against rho of the percentile aggregate of base and barrier, swept
   over the weight. If the aggregate never beats the base alone, the additivity is a story.

2. **What does an epsilon-constraint buy?** Not measurable on Green -- an epsilon-constraint is
   cell-relative and his switches have no cells -- so it is measured on our own population, as
   "among designs holding eps of the cell's best base value, how much barrier does the best one
   gain, and how much base value does it give up". That is the form asked for: a design with a
   comparable base score but a better barrier.
"""

import argparse
import csv
import statistics as st
import sys
from pathlib import Path

NB = Path(__file__).resolve().parent
sys.path.insert(0, str(NB.parents[4] / "src"))
sys.path.insert(0, str(NB))

import objective_panel as op  # noqa: E402
from metric_correlations import _num, spearman  # noqa: E402

#: Base arms to test the barrier against, as (column in the Green CSVs, label, lower_is_better).
GREEN_ARMS = (
    ("A_M_gain", "A_M gain", False),
    ("dG_rbs_linker", "dG_rbs_linker", False),
    ("A_M_ratio", "A_M ratio", False),
)


def percentile(values: list[float], lower_is_better: bool) -> list[float]:
    """Rank each value in [0, 100] with 100 = best, the same transform the panel uses."""
    ordered = sorted(values)
    out = []
    for value in values:
        below = 100.0 * sum(1 for v in ordered if v < value) / len(ordered)
        out.append(100.0 - below if lower_is_better else below)
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--eps", type=float, nargs="*", default=[0.7, 0.8, 0.9])
    args = parser.parse_args(argv)

    results = NB / "results"

    print("=== 1. does the barrier lift a base arm, on Green's measured libraries? ===")
    print("    Green's CSVs carry no barrier column -- it was never computed on his switches by")
    print("    the calibration, and objective_vs_green computes it live. So this reads whichever")
    print("    of them has one and says so when it does not.\n")
    for lib in ("g168", "g13"):
        path = results / f"{lib}.csv"
        if not path.exists():
            continue
        rows = [
            {k: _num(v) for k, v in r.items()} for r in csv.DictReader(path.open(encoding="utf-8"))
        ]
        rows = [r for r in rows if r.get("on_off") is not None]
        has_barrier = any(r.get("barrier") is not None for r in rows)
        print(f"  {lib}: {len(rows)} switches, barrier column present: {has_barrier}")
        if not has_barrier:
            continue
        for column, label, lower in GREEN_ARMS:
            usable = [r for r in rows if r.get(column) is not None and r.get("barrier") is not None]
            if len(usable) < 10:
                continue
            ys = [r["on_off"] for r in usable]
            base = [r[column] for r in usable]
            bar = [r["barrier"] for r in usable]
            sign = -1.0 if lower else 1.0
            alone = sign * spearman(base, ys)
            pct_base = percentile(base, lower)
            pct_bar = percentile(bar, True)
            print(f"    {label:16s} alone {alone:+.4f}")
            for weight in (0.4, 0.5, 0.6, 0.7, 0.8):
                mixed = [
                    weight * b + (1.0 - weight) * c for b, c in zip(pct_base, pct_bar, strict=True)
                ]
                rho = spearman(mixed, ys)
                mark = "  <-- beats the base alone" if rho > alone else ""
                print(f"      weight {weight:.1f} on the base: {rho:+.4f}{mark}")

    print("\n\n=== 2. what an epsilon-constraint on the barrier buys, on our own population ===")
    rank = op.gating(op.population(results))
    cells = op._group(rank)
    print(f"    {len(rank):,} gating designs in {len(cells)} cells\n")

    for column, label, lower in (
        ("f2_gain", "A_M gain", False),
        ("dG_rbs_linker", "dG_rbs_linker", False),
    ):
        print(f"  base arm: {label}")
        usable_cells = []
        for cell in cells.values():
            pool = [r for r in cell if r.get(column) is not None and r.get("barrier") is not None]
            if len(pool) >= 2:
                usable_cells.append(pool)
        if not usable_cells:
            print("    no cell has two designs carrying both -- skipped\n")
            continue
        print(f"    {len(usable_cells)} cells with at least two designs carrying both")
        for eps in args.eps:
            gained, gave_up, moved, alone_only = [], [], 0, 0
            pool_sizes = []
            for pool in usable_cells:
                values = [r[column] for r in pool]
                best_base = min(values) if lower else max(values)
                # **A RATIO TOLERANCE IS WRONG FOR A SIGNED QUANTITY.** `A_M gain` is positive, so
                # "keep 80% of the cell's best" means what it sounds like. `dG_rbs_linker` is
                # NEGATIVE and less-negative is better, so a cell's best might be -4.2 while
                # `0.8 * -4.2 = -3.36` is BETTER than the best -- nothing passes, and this raised
                # on an empty pool instead of quietly returning the base pick.
                #
                # The tolerance is therefore a fraction of the cell's own RANGE: keep every design
                # within `(1 - eps)` of the span from its best to its worst. On a positive quantity
                # whose worst sits near zero that is close to the ratio form, and on a signed one it
                # is the only version that means anything.
                worst = max(values) if lower else min(values)
                slack = (1.0 - eps) * abs(best_base - worst)
                if lower:
                    keep = [r for r in pool if r[column] <= best_base + slack]
                else:
                    keep = [r for r in pool if r[column] >= best_base - slack]
                if not keep:
                    keep = [r for r in pool if r[column] == best_base]
                pool_sizes.append(len(keep))
                if len(keep) == 1:
                    alone_only += 1
                base_pick = (
                    max(pool, key=lambda r: r[column])
                    if not lower
                    else min(pool, key=lambda r: r[column])
                )
                eps_pick = min(keep, key=lambda r: r["barrier"])
                gained.append(base_pick["barrier"] - eps_pick["barrier"])
                gave_up.append(abs(base_pick[column] - eps_pick[column]))
                moved += eps_pick is not base_pick
            print(
                f"      eps={eps:.2f}  reorders {moved:3d}/{len(usable_cells)} cells"
                f"  barrier gained mean {st.fmean(gained):+.3f} max {max(gained):+.3f} kcal/mol"
                f"  |{label} given up| mean {st.fmean(gave_up):.4f}"
            )
            print(
                f"               pool left: median {st.median(pool_sizes):.1f}"
                f"  cells with only one option {alone_only}/{len(usable_cells)}"
            )
        print()

    print("    A reorder with a positive 'barrier gained' is the case asked about: a design with a")
    print("    comparable base score and a better barrier. Where 'gained' is ~0 the constraint")
    print("    found nothing to trade and the arm is the base arm under another name.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
