"""Pairs of designs the equilibrium cannot tell apart and the path reading can.

Section 7.6 ends on a disagreement between two readings of the same state, and the
useful thing to do with a disagreement is design the comparison that settles it. That is
not the same as naming a best candidate, which the ranking evidence does not support
(section 9.8). It is the weaker and better-founded thing: pairs chosen so that the only
quantity that differs between them is the one under dispute.

A pair qualifies when all of this holds:

* **both are called leaky by the equilibrium**, above 0.99, so that reading predicts the
  same outcome for both and cannot be what separates them;
* **their ON-state opening costs are within a tolerance of each other**, so neither is
  expected to turn on better than the other;
* **their path barriers are far apart**, which is the quantity in dispute;
* **they share a cell** where possible, so the transcripts and both windows are fixed
  and the pair differs by construction alone.

The output is a table of contrasts, not a ranking. Nothing here claims either member
will work.

Run::

    uv run python tools/experiment_contrasts.py
    uv run python tools/experiment_contrasts.py --gap 10 --on-tolerance 0.3 --pairs 6
"""

from __future__ import annotations

import argparse
import csv
import glob
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BARRIERS = ROOT / "docs/assets/barrier"
GRID = ROOT / "docs/assets/axes_c8/rows.csv"

#: Above this the equilibrium is saying the same thing about both members of a pair.
LEAKY = 0.99


def grid_on_state() -> dict[tuple, float]:
    """The ON-state cost of opening the ribosome's window, per design."""
    csv.field_size_limit(min(sys.maxsize, 2**31 - 1))
    out: dict[tuple, float] = {}
    with GRID.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            value = row.get("dG_open_11")
            if value in (None, "", "None"):
                continue
            key = (
                row["geom"],
                row["gene_a"],
                row["gene_b"],
                int(float(row["x_start"])),
                int(float(row["xstar_start"])),
                int(float(row["len_x"])),
                int(float(row["stem_index"])),
                row["closure"],
                row["upper3"],
                row["lower3"],
            )
            out[key] = float(value)
    return out


GEOM = {"naive": "arm18/inv18/capnone", "kim": "arm20/inv17/capAUA"}


def measured() -> list[dict]:
    """Every design carrying both readings, joined to its ON-state cost."""
    on_state = grid_on_state()
    out = []
    for path in sorted(glob.glob(str(BARRIERS / "designs_*.csv"))):
        with open(path, newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if row["b_10"] in ("", "None") or row.get("leak") in (None, "", "None"):
                    continue
                key = (
                    GEOM.get(row["geom_label"], row["geom_label"]),
                    row["gene_a"],
                    row["gene_b"],
                    int(float(row["x_start"])),
                    int(float(row["xstar_start"])),
                    int(float(row["len_x"])),
                    int(float(row["stem_index"])),
                    row["closure"],
                    row["upper3"],
                    row["lower3"],
                )
                cost = on_state.get(key)
                if cost is None:
                    continue
                out.append(
                    {
                        "cell": key[:6],
                        "key": row["key"],
                        "geom": row["geom_label"],
                        "genes": f"{row['gene_a']}x{row['gene_b']}",
                        "closure": row["closure"],
                        "upper3": row["upper3"],
                        "lower3": row["lower3"],
                        "leak": float(row["leak"]),
                        "barrier": float(row["b_10"]),
                        "on_cost": cost,
                    }
                )
    return out


def contrasts(rows: list[dict], gap: float, tolerance: float, wanted: int) -> list[tuple]:
    """Pairs that agree on the equilibrium and on the ON state, and differ on the path."""
    leaky = [r for r in rows if r["leak"] > LEAKY]
    found: list[tuple] = []
    by_cell: dict[tuple, list[dict]] = {}
    for row in leaky:
        by_cell.setdefault(row["cell"], []).append(row)

    # Within a cell first: the transcripts and both windows are then fixed, so the pair
    # differs by construction alone and nothing about the biology is confounded. This
    # is the comparison worth having and it is almost never available -- the barrier
    # does not vary inside a trigger pair, which is the finding in 7.6.
    for group in by_cell.values():
        group.sort(key=lambda r: r["barrier"])
        for low in group:
            for high in reversed(group):
                if high["barrier"] - low["barrier"] < gap:
                    break
                if abs(high["on_cost"] - low["on_cost"]) <= tolerance:
                    found.append((low, high, "same trigger pair"))
                    break
            if len(found) >= wanted:
                return found[:wanted]

    # Then across pairs, which is where a large barrier difference lives. The two
    # transcripts differ along with the barrier, so this is a confounded comparison and
    # is labelled as one. Matching on ON-state cost removes the confound the model can
    # see; it says nothing about the ones it cannot.
    ladder = sorted(leaky, key=lambda r: r["barrier"])
    for low in ladder:
        for high in reversed(ladder):
            if high["barrier"] - low["barrier"] < gap:
                break
            if low["cell"] == high["cell"]:
                continue
            if abs(high["on_cost"] - low["on_cost"]) <= tolerance:
                found.append((low, high, "DIFFERENT trigger pairs"))
                break
        if len(found) >= wanted:
            break
    return found[:wanted]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Propose experimental contrasts.")
    parser.add_argument("--gap", type=float, default=8.0, help="least barrier difference")
    parser.add_argument("--on-tolerance", type=float, default=0.5, help="ON costs within this")
    parser.add_argument("--pairs", type=int, default=5)
    args = parser.parse_args(argv)

    rows = measured()
    print(f"  {len(rows):,} designs carry both readings and an ON-state cost")
    leaky = [r for r in rows if r["leak"] > LEAKY]
    print(f"  {len(leaky):,} of them the equilibrium calls leaky above {LEAKY}")

    pairs = contrasts(rows, args.gap, args.on_tolerance, args.pairs)
    if not pairs:
        print("  no pair meets the tolerances; loosen --gap or --on-tolerance")
        return 1

    print(
        f"\n  {len(pairs)} contrast(s): barrier at least {args.gap} apart, ON-state cost "
        f"within {args.on_tolerance} kcal/mol, equilibrium leak above {LEAKY} for both\n"
    )
    header = (
        f"  {'':3}{'genes':12}{'geometry':7}{'closure':14}{'upper3':17}{'lower3':17}"
        f"{'leak':>8}{'ON':>7}{'barrier':>9}"
    )
    for index, (low, high, how) in enumerate(pairs, 1):
        print(f"  contrast {index} -- {how}, {low['genes']}")
        print(header)
        for tag, row in (("lo", low), ("hi", high)):
            geom = "kim" if "inv17" in row["geom"] else "naive"
            print(
                f"  {tag:3}{row['genes']:12}{geom:7}{row['closure']:14}"
                f"{row['upper3']:17}{row['lower3']:17}"
                f"{row['leak']:8.4f}{row['on_cost']:7.2f}{row['barrier']:9.2f}"
            )
        print(
            f"      the equilibrium separates them by {abs(high['leak'] - low['leak']):.4f}; "
            f"the path barrier by {high['barrier'] - low['barrier']:.2f} kcal/mol\n"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
