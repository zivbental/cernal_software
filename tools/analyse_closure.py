"""The closure axis, and the lever combination, scored on PERFORMANCE rather than on survival.

    uv run python tools/analyse_closure.py --out axes_c8

**Why this exists: survival was the wrong thing to report.** I reported the closure axis as a
survival rate -- what fraction of designs pass the ``open_11 <= 4.0`` ceiling. Survival is not a
performance measure. It says only "the ON state opens far enough to be worth measuring further",
so a design that fails it has no ON state at all and a design that passes is not thereby good. A
higher survival rate means more designs you can go on to evaluate, nothing more. And on this axis
survival and gating turned out to run OPPOSITE ways -- ``open_3x3`` survives 35.1% and gates 12.6%,
``closed_CAU`` survives 7.5% and gates 34.1% -- so reporting survival actively pointed the wrong
way.

So every closure is compared here on the measures that say whether it gates: ``separation``,
``A_M_ratio``, ``ied_gain``, ``ied_gain_worst`` and the two state-10 leak terms. Paired inside a
(pair, geometry) cell against ``open_3x3``, the level that leaves the AUG bulge open, so the
comparison is "what does closing the bulge this way do" with the trigger pair, geometry, stem and
every other axis held fixed.

**And the lever COMBINATION, which was never measured.** ``wobble_GU`` and the ``upper3``
overrides were each compared against doing nothing, separately. They write to different domains --
the bottom three base pairs against the top three -- so they can both be on, and nothing said what
happens when they are. Four arms are compared here: neither, each alone, and both.

Every comparison reports cells won, lost and tied with the total beside it, and the paired
difference's distribution rather than its median alone.
"""

from __future__ import annotations

import argparse
import csv
import math
import statistics as st
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "src" / "engine" / "gates" / "notebooks" / "toehold_and" / "results"

#: (column, higher_is_better, label). These are the PERFORMANCE measures -- what the gate is for.
OUTCOMES: tuple[tuple[str, bool, str], ...] = (
    ("separation", True, "separation (log2)"),
    ("A_M_ratio", True, "A_M ratio"),
    ("ied_gain", True, "IED gain vs state 00"),
    ("ied_gain_worst", True, "IED gain vs worst OFF"),
    ("xstar_engA_10", False, "leak: x* taken by A alone"),
    ("mainpre_engA_10", False, "leak: stem reached by A alone"),
    ("A_M_11", True, "A_M in the ON state"),
)

REFERENCE_CLOSURE = "open_3x3"


def num(row: dict, key: str) -> float | None:
    value = row.get(key, "")
    if value in ("", None):
        return None
    try:
        parsed = float(value)
    except ValueError:
        return None
    return parsed if math.isfinite(parsed) else None


def cell_of(row: dict) -> tuple:
    return (row["gene_a"], row["gene_b"], row["x_start"], row["xstar_start"], row["geom"])


def report(label: str, pairs: list[tuple[dict, dict]], note: str = "") -> None:
    """`pairs` is (treated, control). Positive always means the treated arm was better."""
    print(f"\n  {label}   {len(pairs):,} matched pairs" + (f"   {note}" if note else ""))
    if not pairs:
        print("    nothing matched, so nothing to say")
        return
    print(
        f"    {'measure':32s}{'cells':>7}{'won':>6}{'lost':>6}{'tied':>6}"
        f"{'median diff':>14}{'mean diff':>12}"
    )
    for column, higher_better, name in OUTCOMES:
        diffs: list[float] = []
        cells: dict[tuple, list[float]] = defaultdict(list)
        for treated, control in pairs:
            a, b = num(treated, column), num(control, column)
            if a is None or b is None:
                continue
            delta = (a - b) if higher_better else (b - a)
            diffs.append(delta)
            cells[cell_of(treated)].append(delta)
        if not diffs:
            print(f"    {name:32s}{'--':>7}  not measured on both arms")
            continue
        won = sum(1 for v in cells.values() if st.median(v) > 0)
        lost = sum(1 for v in cells.values() if st.median(v) < 0)
        print(
            f"    {name:32s}{len(cells):>7}{won:>6}{lost:>6}{len(cells) - won - lost:>6}"
            f"{st.median(diffs):>+14.4f}{st.mean(diffs):>+12.4f}"
        )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="axes_c8")
    parser.add_argument("--shards", type=int, default=6)
    args = parser.parse_args(argv)

    rows: list[dict] = []
    for index in range(args.shards):
        path = RESULTS / f"{args.out}_{index}.csv"
        if path.exists():
            with path.open(encoding="utf-8", newline="") as handle:
                rows.extend(csv.DictReader(handle))
    if not rows:
        print(f"  no {args.out}_*.csv under {RESULTS}")
        return 1
    full = [r for r in rows if not r.get("skipped")]
    print(
        f"\n  {len(rows):,} designs, {len(full):,} fully measured, "
        f"{len({cell_of(r) for r in rows})} cells"
    )
    print(
        "\n  Positive ALWAYS means the arm named first was better. For the two leak measures that\n"
        "  means a LOWER value, since a leak is bad -- the sign is already flipped for them.\n"
        "  'cells won' counts (pair, geometry) cells whose median paired difference is above zero."
    )

    # ---- the closure axis, each level against the open bulge ---------------------------
    print(f"\n{'=' * 104}")
    print(f"  CLOSURE: each level against {REFERENCE_CLOSURE}, paired inside a cell")
    print(f"{'=' * 104}")
    index: dict[tuple, dict[str, dict]] = defaultdict(dict)
    for row in full:
        key = (cell_of(row), row["stem_index"], row["len_x"], row["upper3"], row["lower3"])
        index[key][row["closure"]] = row
    levels = sorted({r["closure"] for r in full} - {REFERENCE_CLOSURE})
    for level in levels:
        pairs = [
            (slot[level], slot[REFERENCE_CLOSURE])
            for slot in index.values()
            if level in slot and REFERENCE_CLOSURE in slot
        ]
        report(f"{level} vs {REFERENCE_CLOSURE}", pairs)

    # ---- the lever combination ---------------------------------------------------------
    print(f"\n{'=' * 104}")
    print("  THE LEVERS TOGETHER, which was never measured: both write, to different domains")
    print(f"{'=' * 104}")
    slots: dict[tuple, dict[tuple[str, str], dict]] = defaultdict(dict)
    for row in full:
        key = (cell_of(row), row["stem_index"], row["len_x"], row["closure"])
        slots[key][(row["upper3"], row["lower3"])] = row
    base = ("trigger_derived", "trigger_derived")
    for upper in ("WWW_UAU", "WWW_AUA"):
        arms = {
            "upper3 alone": (upper, "trigger_derived"),
            "wobble alone": ("trigger_derived", "wobble_GU"),
            "both together": (upper, "wobble_GU"),
        }
        for name, arm in arms.items():
            pairs = [
                (slot[arm], slot[base]) for slot in slots.values() if arm in slot and base in slot
            ]
            report(f"{name} ({upper}) vs neither", pairs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
