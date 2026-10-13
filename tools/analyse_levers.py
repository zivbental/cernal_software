"""Did each design decision help — asked CONDITIONALLY, and per trigger pair.

Run it on the night run's output, while it is still running or after:

    uv run python tools/analyse_levers.py --out axes_c8

**The question this answers, and why the obvious version of it is wrong.** "Does ``wobble_GU``
beat ``trigger_derived``?" compared across all designs gave 17.7% against 16.4%, which reads as
nothing. It is not nothing, it is diluted: on 43.3% of assemblies the natural bottom three pairs
already have Green's two-strong-one-weak, so the lever writes nothing and those designs ARE the
control. Averaging them in pulls any real effect toward zero. The question has to be asked only
where the lever had work to do, which is what ``lower3_strong_before`` is for.

**And it is asked per trigger pair, never per row.** A (pair, geometry) cell fixes the two trigger
windows and the geometry, so inside one cell the only thing that differs is the design decision.
Pooling across cells mixes that with between-pair variation, which is far larger -- measured on
this architecture, the pooled and within-cell answers for one pair of arms came out +0.44 and
-0.856, opposite signs. So every comparison here is a paired one inside a cell, and the report is
a count of cells won, lost and tied, with the median paired difference beside it.

**What counts as "better" is the outcome, not the conversion.** The lever's job is a better gate,
not a particular stem composition, so the outcomes compared are the ones that say whether it gates:
``separation``, the two leak terms, ``A_M_ratio``, ``ied_gain``. How many positions were converted
is the conditioning variable, not the result.

Every rate is printed with its ``n``, and every distribution with mean, sd, min and max beside the
median -- a median alone has argued both sides on this project before.
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

#: What "better" means. Each entry is (column, higher_is_better, label).
OUTCOMES: tuple[tuple[str, bool, str], ...] = (
    ("separation", True, "separation (log2, ON vs worst OFF)"),
    ("xstar_engA_10", False, "x* taken by A alone (the leak)"),
    ("mainpre_engA_10", False, "main stem reached by A alone"),
    ("A_M_ratio", True, "A_M ratio"),
    ("ied_gain", True, "IED gain, RBS loop to linker"),
    ("A_M_11", True, "A_M in the ON state"),
)

#: The levers, and what makes a design's row comparable to its control. Each is
#: (axis column, control level, treated level, conditioning column, a predicate on it).
LEVERS: tuple[tuple[str, str, str, str, str], ...] = (
    ("lower3", "trigger_derived", "wobble_GU", "lower3_strong_before", "!= 2"),
    ("upper3", "trigger_derived", "WWW_UAU", "upper3_changed", "is True"),
    ("upper3", "trigger_derived", "WWW_AUA", "upper3_changed", "is True"),
)


def cell_of(row: dict) -> tuple:
    """The (pair, geometry) cell. Everything else in the key is a design decision."""
    return (row["gene_a"], row["gene_b"], row["x_start"], row["xstar_start"], row["geom"])


def partner_of(row: dict, axis: str) -> tuple:
    """A design's identity with ONE axis removed, so it can be paired with its control."""
    return (
        cell_of(row),
        row["stem_index"],
        row["len_x"],
        *(row[other] for other in ("closure", "upper3", "lower3") if other != axis),
    )


def number(row: dict, key: str) -> float | None:
    value = row.get(key, "")
    if value in ("", None):
        return None
    try:
        parsed = float(value)
    except ValueError:
        return None
    return parsed if math.isfinite(parsed) else None


def spread(label: str, values: list[float], width: int = 36) -> None:
    if not values:
        print(f"  {label:{width}s} no values")
        return
    sd = st.stdev(values) if len(values) > 1 else 0.0
    print(
        f"  {label:{width}s} n={len(values):5d}  median {st.median(values):+8.4f}  "
        f"mean {st.mean(values):+8.4f}  sd {sd:7.4f}  min {min(values):+8.4f}  "
        f"max {max(values):+8.4f}"
    )


def conditioned(row: dict, column: str, predicate: str) -> bool | None:
    """Did this lever have work to do on this design? ``None`` when the column is missing."""
    raw = row.get(column, "")
    if raw in ("", None):
        return None
    if predicate == "is True":
        return raw.strip().lower() in ("true", "1")
    if predicate == "!= 2":
        value = number(row, column)
        return None if value is None else value != 2
    raise ValueError(f"unknown predicate {predicate!r}")


def compare(
    rows: list[dict], axis: str, control: str, treated: str, condition: str, predicate: str
) -> None:
    print(f"\n{'=' * 92}")
    print(f"  {axis}:  {treated}  against  {control}")
    print(f"  conditioned on {condition} {predicate} -- where the lever had work to do")
    print(f"{'=' * 92}")

    by_partner: dict[tuple, dict[str, dict]] = defaultdict(dict)
    for row in rows:
        if row[axis] in (control, treated):
            by_partner[partner_of(row, axis)][row[axis]] = row

    both = [p for p in by_partner.values() if control in p and treated in p]
    if not both:
        print("  no design has both levels at the same everything-else. Nothing to compare.")
        return

    eligible, skipped, unknown = [], 0, 0
    for pair in both:
        verdict = conditioned(pair[treated], condition, predicate)
        if verdict is None:
            unknown += 1
        elif verdict:
            eligible.append(pair)
        else:
            skipped += 1
    print(
        f"  {len(both):,} matched pairs of designs. {len(eligible):,} where the lever had work, "
        f"{skipped:,} where it was a no-op, {unknown:,} with the condition unrecorded."
    )
    if skipped:
        print(
            f"  -> an UNCONDITIONAL comparison would average in those {skipped:,} no-ops, which "
            f"are the control by construction and can only dilute the answer."
        )
    if not eligible:
        print("  Nothing eligible, so no conditional answer. Report that, not a null result.")
        return

    for column, higher_better, label in OUTCOMES:
        diffs, cells = [], defaultdict(list)
        for pair in eligible:
            a, b = number(pair[treated], column), number(pair[control], column)
            if a is None or b is None:
                continue
            delta = (a - b) if higher_better else (b - a)
            diffs.append(delta)
            cells[cell_of(pair[treated])].append(delta)
        if not diffs:
            print(f"\n  {label}: measured on neither arm of any eligible pair")
            continue
        won = sum(1 for v in cells.values() if st.median(v) > 0)
        lost = sum(1 for v in cells.values() if st.median(v) < 0)
        tied = len(cells) - won - lost
        print(f"\n  {label}  (positive = the lever helped)")
        spread("    paired difference, per design", diffs, 34)
        print(
            f"      cells: {won} won, {lost} lost, {tied} tied, of {len(cells)}"
            + ("  -- too few cells to read" if len(cells) < 5 else "")
        )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="axes_c8", help="the run's output prefix")
    parser.add_argument("--shards", type=int, default=6)
    args = parser.parse_args(argv)

    rows: list[dict] = []
    for index in range(args.shards):
        path = RESULTS / f"{args.out}_{index}.csv"
        if not path.exists():
            continue
        with path.open(encoding="utf-8", newline="") as handle:
            rows.extend(csv.DictReader(handle))
    if not rows:
        print(f"  no {args.out}_*.csv under {RESULTS}")
        return 1

    full = [r for r in rows if not r.get("skipped")]
    cells = {cell_of(r) for r in rows}
    print(
        f"\n  {len(rows):,} designs, {len(full):,} fully measured "
        f"({len(full) / len(rows):.1%}), {len(cells)} (pair, geometry) cells"
    )
    if not full:
        print("  nothing fully measured yet -- the run has not got past the ON ceiling.")
        return 0

    # The leak terms are measured for EVERY design now, including the ones the ceiling stopped,
    # so this one distribution is over the whole population rather than over the survivors.
    print("\n  the state-10 leak, over ALL designs (measured before the ceiling decides):")
    for column in ("xstar_engA_10", "mainpre_engA_10"):
        values = [v for r in rows if (v := number(r, column)) is not None]
        spread(f"    {column}", values, 34)
        if values:
            print(
                f"      below 0.5: {sum(1 for v in values if v < 0.5)}/{len(values)} = "
                f"{sum(1 for v in values if v < 0.5) / len(values):.1%}"
            )

    for axis, control, treated, condition, predicate in LEVERS:
        compare(full, axis, control, treated, condition, predicate)

    # Closure has no "did it change anything" condition that splits usefully -- every level but
    # one writes a different triplet -- so it is reported per level, within cells, unconditionally.
    print(f"\n{'=' * 92}")
    print("  closure, per level, inside cells -- no conditioning, because every level writes")
    print(f"{'=' * 92}")
    by_level: dict[str, list[dict]] = defaultdict(list)
    for row in full:
        by_level[row["closure"]].append(row)
    print(f"  {'closure':18s}{'n':>7}{'gating':>8}{'rate':>8}{'median separation':>20}")
    for level, group in sorted(
        by_level.items(),
        key=lambda kv: -st.median([number(r, "separation") or 0.0 for r in kv[1]]),
    ):
        seps = [v for r in group if (v := number(r, "separation")) is not None]
        gating = sum(
            1
            for r in group
            if (a := number(r, "xstar_engA_10")) is not None
            and a < 0.5
            and (b := number(r, "xstar_engA_11")) is not None
            and b > 0.9
        )
        print(
            f"  {level:18s}{len(group):>7,}{gating:>8,}{gating / len(group):>8.1%}"
            f"{(st.median(seps) if seps else float('nan')):>20.3f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
