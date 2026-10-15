"""The corrected barrier against the one it replaces, on the same designs.

Section 7.6 of the model page rests on three numbers about the preferred-stem designs:
the span of the barrier, its correlation with the equilibrium leak, and how many clear
3.0 kcal/mol. All three were computed from a quantity that turned out to be
``E(end) - E(start)`` rather than a barrier (see ``barrier_validate.py``), so all three
have to be recomputed before any of them is quoted again.

This joins the two runs on the design key and prints both, so the page can be corrected
against a measurement rather than an assumption about which way the number moved.

Run::

    uv run python tools/barrier_compare.py \\
        --old docs/assets/barrier --new docs/assets/barrier_fixed
"""

from __future__ import annotations

import argparse
import csv
import math
import pathlib
import statistics


def spearman(xs: list[float], ys: list[float]) -> float | None:
    """Rank correlation, with ties averaged. None when either side has no spread."""
    if len(xs) < 3:
        return None

    def ranks(values: list[float]) -> list[float]:
        order = sorted(range(len(values)), key=lambda i: values[i])
        out = [0.0] * len(values)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
                j += 1
            shared = (i + j) / 2 + 1
            for k in range(i, j + 1):
                out[order[k]] = shared
            i = j + 1
        return out

    rx, ry = ranks(xs), ranks(ys)
    mx, my = statistics.fmean(rx), statistics.fmean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry, strict=True))
    dx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    dy = math.sqrt(sum((b - my) ** 2 for b in ry))
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


def load(folder: pathlib.Path, pattern: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for path in sorted(folder.glob(pattern)):
        for row in csv.DictReader(path.open(newline="", encoding="utf-8")):
            if row.get("b_10") not in (None, "", "None"):
                out[row["key"]] = row
    return out


def describe(label: str, values: list[float]) -> None:
    negative = sum(1 for v in values if v < 0)
    over = sum(1 for v in values if v > 3.0)
    print(
        f"  {label:<22} n={len(values):<5} min={min(values):+7.2f} max={max(values):+7.2f} "
        f"span={max(values) - min(values):6.2f} median={statistics.median(values):+7.2f} "
        f"mean={statistics.fmean(values):+7.2f} sd={statistics.stdev(values):5.2f}"
    )
    print(f"  {'':22} negative={negative} ({100 * negative / len(values):.1f}%)  above 3.0={over}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Corrected barrier against the old one.")
    parser.add_argument("--old", type=pathlib.Path, required=True)
    parser.add_argument("--new", type=pathlib.Path, required=True)
    parser.add_argument("--pattern", default="best*.csv")
    args = parser.parse_args(argv)

    old = load(args.old, args.pattern)
    new = load(args.new, args.pattern)
    shared = sorted(set(old) & set(new))
    print(f"  old {len(old)} rows, new {len(new)} rows, {len(shared)} joined on the design key")
    if not shared:
        raise SystemExit("  nothing joined -- check the folders and the pattern")

    old_b = [float(old[k]["b_10"]) for k in shared]
    new_b = [float(new[k]["b_10"]) for k in shared]
    leak = [float(old[k]["leak"]) for k in shared if old[k].get("leak") not in (None, "", "None")]

    print("\n  THE QUANTITY")
    describe("stored (E_end-E_start)", old_b)
    describe("corrected (path max)", new_b)
    moved = [n - o for o, n in zip(old_b, new_b, strict=True)]
    print(
        f"\n  corrected minus stored: median {statistics.median(moved):+.2f}, "
        f"min {min(moved):+.2f}, max {max(moved):+.2f}"
    )
    agree = spearman(old_b, new_b)
    print(f"  rank correlation between the two readings: {agree:+.3f}" if agree else "  no spread")

    if len(leak) == len(shared):
        print("\n  AGAINST THE EQUILIBRIUM LEAK")
        print(f"  leak range {min(leak):.4f} - {max(leak):.4f}")
        for label, values in (("stored", old_b), ("corrected", new_b)):
            rho = spearman(values, leak)
            if rho is None:
                print(f"    rho({label:<9}, leak) undefined -- one side has no spread")
            else:
                print(f"    rho({label:<9}, leak) = {rho:+.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
