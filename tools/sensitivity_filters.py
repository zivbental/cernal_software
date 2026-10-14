"""How much of a conclusion survives moving the threshold that produced it?

    uv run python tools/sensitivity_filters.py --out axes_c8
    uv run python tools/sensitivity_filters.py --out axes_c8 --into docs/assets/axes_c8

**Why this is not optional.** Every statement of the form "closure X beats closure Y" in this
project is made over designs that passed the ON ceiling, and the ceiling rejects most of them --
74.8% on the run before this one. A conclusion drawn on the survivors of a filter is a conclusion
about a population that filter shaped, and "it would have come out the same at a different
cutoff" is a claim, not a given. This sweeps the cutoff and reports which conclusions hold over
which range, and which flip.

**Downward only, and that is a hard limit of the data rather than a choice.** The ceiling is read
against ``dG_open_11``, which ``measure_design`` records on EVERY design before the ceiling
decides -- so a stricter ceiling can be re-applied after the fact by discarding rows, and the
answer is exact. A *looser* one cannot: the three OFF tubes were never folded for a design the
ceiling stopped, so every contrast is absent there and no amount of analysis recovers it. The
sweep therefore runs from the run's own setting downward, and says so in its output rather than
leaving a reader to assume the range was chosen.

**Two kinds of threshold, kept apart.**

* the ON CEILING, which shaped the table: sweeping it changes *which designs exist* in the
  analysis, so both the survivor count and every conclusion move.
* POST-HOC FLOORS on measured metrics, which did not shape the table: applying one only narrows
  an already-measured population. These are the thresholds `objective_panel.feasible` applies at
  selection time, asked here of the characterisation run instead.

**What counts as a conclusion holding.** For each (categorical axis, contrast) the levels are
ranked by their mean within-cell z-score -- the same statistic ``analyse_axes`` reports, so the
numbers are comparable with that report rather than a second ranking. A conclusion holds while
the best level is unchanged; the range over which that is true is the headline. The full ordering
is printed too, because a top level that survives while the order beneath it churns is a weaker
result than one where nothing moves, and only the ordering shows the difference.
"""

from __future__ import annotations

import argparse
import csv
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

# ruff: noqa: E402 - the sibling tool must be importable from this directory.
from analyse_axes import (
    CATEGORICAL,
    CONTRASTS,
    cells_of,
    derive,
    read_rows,
    zscores,
)

#: The columns the ON ceiling has ever been read against, newest first. It CHANGED at gate
#: version 0.6.0: before it the ceiling was read against `open_11`, the main stem's 15-nt arms,
#: and afterwards against `dG_open_11`, the 31-nt ribosome window. The same numeric setting means
#: two different things either side of that change.
#:
#: **Which one a table used is inferred from the table, not assumed.** `gate_version` has been
#: empty on a real run, so the declaration cannot be trusted to be there -- but the filter leaves
#: a signature that cannot lie: every design the ceiling let through must satisfy it. So the
#: column the ceiling was read against is the one where NO surviving design exceeds the setting.
#: Guessing wrong is not a cosmetic error: `open_11` spans 15 nt inside `dG_open_11`'s 31, so
#: opening the larger window always costs at least as much, and a design that passed at
#: `open_11 <= 8` routinely has `dG_open_11 > 8`. Read the wrong column and those designs look
#: like missing data.
CEILING_COLUMNS = ("dG_open_11", "open_11")
CEILING_COLUMN = CEILING_COLUMNS[0]


def applied_ceiling_column(measured: list[dict], ceiling: float | None) -> tuple[str, dict]:
    """Which column the ceiling was actually read against, and the evidence for each candidate.

    A surviving design cannot exceed the threshold that let it survive, so the candidate with no
    survivors above the setting is the one that was applied. Returns the column and, per
    candidate, how many measured designs are missing it and how many exceed the setting.
    """
    evidence: dict[str, tuple[int, int]] = {}
    for column in CEILING_COLUMNS:
        absent = sum(1 for r in measured if not isinstance(r.get(column), float))
        over = (
            0
            if ceiling is None
            else sum(
                1 for r in measured if isinstance(r.get(column), float) and r[column] > ceiling
            )
        )
        evidence[column] = (absent, over)
    for column in CEILING_COLUMNS:
        absent, over = evidence[column]
        if absent == 0 and over == 0:
            return column, evidence
    # Nothing is clean; fall back to whichever has fewest designs contradicting it.
    best = min(CEILING_COLUMNS, key=lambda c: evidence[c][0] + evidence[c][1])
    return best, evidence


#: Post-hoc floors: a metric, whether a LOW value is the rejection, and what the floor means.
#: Every one of these is a measurement on the row, so applying it discards rows and nothing more.
#: The names are the engine's; a typo is caught by `--check` below rather than reading as a column
#: of empty cells that rejects nothing.
POST_HOC: tuple[tuple[str, bool, str], ...] = (
    ("aug_11", True, "the start codon must be reachable in the ON state"),
    ("A_M_11", True, "the main stem must open in the ON state"),
    ("access_a", True, "trigger A's toehold must be accessible"),
    ("barrier", False, "the refolding barrier out of the ON state"),
    ("xstar_engA_10", False, "trigger A alone must not take x*"),
    ("mainpre_engA_10", False, "trigger A alone must not reach the main stem"),
    ("hairpin_worst_10", True, "both hairpins must hold with A alone"),
    ("hairpin_worst_00", True, "both hairpins must hold at rest"),
)


def best_levels(rows: list[dict], axis: str, contrast: str) -> list[tuple[str, float, int]]:
    """Levels of one axis ranked by mean within-cell z-score of one contrast, best first.

    Within-cell, because pooling across cells measures the trigger pairs: a design in an easy
    cell looks good for a reason that is not the axis. Lower is better throughout, so the best
    level is the most negative one.
    """
    pooled: dict[str, list[float]] = {}
    for group in cells_of(rows).values():
        z = zscores(group, contrast)
        for row in group:
            if id(row) not in z or row.get(axis) is None:
                continue
            pooled.setdefault(str(row[axis]), []).append(z[id(row)])
    ranked = [(level, st.fmean(values), len(values)) for level, values in pooled.items() if values]
    return sorted(ranked, key=lambda item: item[1])


def describe_stability(history: list[tuple[float, list[tuple[str, float, int]]]]) -> str:
    """One line: did the best level hold across the sweep, and where did it first change?"""
    usable = [(setting, ranked) for setting, ranked in history if ranked]
    if len(usable) < 2:
        return "too few settings with data to say"
    winners = [ranked[0][0] for _setting, ranked in usable]
    first = winners[0]
    if all(name == first for name in winners):
        lo = min(setting for setting, _r in usable)
        hi = max(setting for setting, _r in usable)
        orders = {tuple(level for level, *_ in ranked) for _s, ranked in usable}
        tail = (
            "and the whole ordering holds"
            if len(orders) == 1
            else "though the order beneath it moves"
        )
        return f"{first} best over the whole range {lo:.2f} to {hi:.2f}, {tail}"
    for (setting, _ranked), winner in zip(usable, winners, strict=True):
        if winner != first:
            return f"FLIPS: {first} best until {setting:.2f}, then {winner}"
    return "unstable"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="axes_c8", help="which run to read")
    parser.add_argument("--shards", type=int, default=6)
    parser.add_argument("--steps", type=int, default=6, help="how many ceilings to try")
    parser.add_argument(
        "--floor",
        type=float,
        default=None,
        help="lowest ceiling to sweep to; default is the 10th percentile of the column",
    )
    parser.add_argument(
        "--into", default="", help="directory for the tidy tables, as analyse_axes names it"
    )
    parser.add_argument(
        "--column",
        default="",
        choices=("", *CEILING_COLUMNS),
        help=(
            "sweep this column instead of the one inferred from the survivors. Use it to ask "
            "'would the conclusions hold at a threshold this run did not apply' -- for example "
            "--column dG_open_11, which is the span Green's figures are measured over, on a "
            "table that was actually filtered on open_11"
        ),
    )
    args = parser.parse_args(argv)

    rows = read_rows(args.out, args.shards)
    if not rows:
        print(f"  no rows found for {args.out!r}")
        return 1
    derive(rows)

    ceilings_on_row = {row.get("on_ceiling") for row in rows if row.get("on_ceiling") is not None}
    measured = [row for row in rows if not row.get("skipped")]
    share = len(measured) / len(rows)
    print(f"\n  {len(rows):,} rows, {len(measured):,} measured in full ({share:.1%})")
    if len(ceilings_on_row) > 1:
        print(
            f"  WARNING: the table holds {len(ceilings_on_row)} different on_ceiling settings: "
            f"{sorted(ceilings_on_row)}"
        )
        print("  Sweeping a mixed table measures the mixture. Run audit_grid_coverage first.")
    run_ceiling = max(ceilings_on_row) if ceilings_on_row else None

    column, evidence = applied_ceiling_column(measured, run_ceiling)
    if args.column:
        if args.column != column:
            print(f"\n  NOTE: --column {args.column} overrides the inferred {column}. This is a")
            print("  COUNTERFACTUAL sweep: it asks what this population would look like under a")
            print("  threshold the run never applied, which is a fair question and a different one")
            print("  from tightening the filter that shaped it.")
        column = args.column
    print("\n  which column the ceiling was read against, inferred from the survivors:")
    for name in CEILING_COLUMNS:
        absent, over = evidence[name]
        verdict = "consistent" if absent == 0 and over == 0 else "ruled out"
        print(
            f"    {name:14s} {absent:>8,} measured designs missing it, "
            f"{over:>8,} above the setting   {verdict}"
        )
    clean = [c for c in CEILING_COLUMNS if evidence[c] == (0, 0)]
    if not clean:
        print("    NO candidate is clean: every one has survivors above the recorded on_ceiling,")
        print("    so the recorded setting is probably not the one that was applied. Sweeping the")
        print("    least contradicted column, and the range below should be read as indicative.")
    print(f"    -> sweeping {column}")
    if column != CEILING_COLUMNS[0] and clean:
        print(
            f"    NOTE: this table predates the span change, so its {run_ceiling:g} is a cost over"
        )
        print("    the stem's 15-nt arms, NOT the 31-nt ribosome window. It is not comparable with")
        print("    a run at the same number under the newer definition.")

    values = [row[column] for row in rows if isinstance(row.get(column), float)]
    if not values:
        print(f"  no {column} on any row -- nothing to sweep")
        return 1
    top = run_ceiling if run_ceiling is not None else max(values)
    bottom = args.floor if args.floor is not None else st.quantiles(values, n=10)[0]
    if bottom >= top:
        print(f"  the floor {bottom:g} is not below the run's ceiling {top:g}")
        return 1

    step = (top - bottom) / (args.steps - 1)
    settings = [top - i * step for i in range(args.steps)]

    print(f"\n{'=' * 100}\nON CEILING -- swept DOWNWARD from the {top:g} this run used")
    print(f"  Read against {column}, which every surviving row carries, so a stricter ceiling is")
    print("  re-applied exactly. A LOOSER one is unanswerable: the OFF tubes were never folded")
    print("  for a design the ceiling stopped, so no contrast exists there to analyse.")
    print(f"\n    {'ceiling':>9s}{'kept':>10s}{'share':>8s}{'cells':>8s}")
    per_setting: dict[float, list[dict]] = {}
    for setting in settings:
        kept = [
            row for row in measured if isinstance(row.get(column), float) and row[column] <= setting
        ]
        per_setting[setting] = kept
        cells = len(cells_of(kept)) if kept else 0
        share = len(kept) / len(rows)
        print(f"    {setting:>9.2f}{len(kept):>10,}{share:>7.1%}{cells:>8,}")

    print(
        f"\n{'=' * 100}\nCONCLUSION STABILITY -- does the best level hold as the ceiling tightens?"
    )
    print("  Levels ranked by mean within-cell z-score, the statistic analyse_axes reports.")
    print("  Lower is better, so the best level is the most negative.")
    tidy: list[tuple] = []
    #: (metric, cutoff, contrast, axis, best level before the floor, best level after it)
    post_hoc_table: list[tuple] = []
    for contrast, _on, _off, _pick, label in CONTRASTS:
        print(f"\n  {contrast}   ({label})")
        for axis in CATEGORICAL:
            history = []
            for setting in settings:
                ranked = best_levels(per_setting[setting], axis, contrast)
                history.append((setting, ranked))
                for position, (level, mean_z, n) in enumerate(ranked):
                    tidy.append((contrast, axis, setting, position, level, mean_z, n))
            if not any(ranked for _s, ranked in history):
                continue
            print(f"    {axis:10s} {describe_stability(history)}")

    print(f"\n{'=' * 100}\nPOST-HOC FLOORS -- thresholds that did NOT shape this table")
    print("  These are selection-time cutoffs asked of the characterisation run. Applying one")
    print("  only narrows an already-measured population, so the quartiles below are exact.")
    print("  Each row: how many of the fully measured designs a cutoff at that quartile keeps.")
    print("  Read the flip count as a noise check too. A level that was only marginally ahead was")
    print("  never a conclusion, and subsetting reshuffles it; if nearly every comparison flips")
    print("  under a floor that keeps half the designs, the ranking was inside the noise.")
    print(f"\n    {'metric':20s}{'reject':>8s}{'Q1':>9s}{'Q2':>9s}{'Q3':>9s}{'keeps at Q2':>13s}")
    for metric, low_is_bad, meaning in POST_HOC:
        present = [row[metric] for row in measured if isinstance(row.get(metric), float)]
        if len(present) < 20:
            print(f"    {metric:20s}  only {len(present):,} measured values -- not swept")
            continue
        q1, q2, q3 = st.quantiles(present, n=4)
        if low_is_bad:
            kept = sum(1 for value in present if value >= q2)
        else:
            kept = sum(1 for value in present if value <= q2)
        direction = "low" if low_is_bad else "high"
        print(
            f"    {metric:20s}{direction:>8s}{q1:>9.3f}{q2:>9.3f}{q3:>9.3f}"
            f"{kept / len(present):>12.1%}"
        )
        print(f"      {meaning}")
        # Survivor counts alone do not answer the question. A floor that keeps half the designs
        # and leaves every conclusion standing is a different thing from one that keeps half and
        # reverses them, and only re-ranking under the floor tells them apart.
        if low_is_bad:
            kept_rows = [
                r for r in measured if isinstance(r.get(metric), float) and r[metric] >= q2
            ]
        else:
            kept_rows = [
                r for r in measured if isinstance(r.get(metric), float) and r[metric] <= q2
            ]
        flips = []
        for contrast, _on, _off, _pick, _label in CONTRASTS:
            for axis in CATEGORICAL:
                before = best_levels(measured, axis, contrast)
                after = best_levels(kept_rows, axis, contrast)
                if not before or not after:
                    continue
                if before[0][0] != after[0][0]:
                    flips.append(f"{contrast}/{axis}: {before[0][0]} -> {after[0][0]}")
                    post_hoc_table.append((metric, q2, contrast, axis, before[0][0], after[0][0]))
                else:
                    post_hoc_table.append((metric, q2, contrast, axis, before[0][0], before[0][0]))
        if flips:
            print(f"      at its median cutoff, {len(flips)} conclusion(s) change:")
            for line in flips[:4]:
                print(f"        {line}")
            if len(flips) > 4:
                print(f"        ... and {len(flips) - 4} more")
        else:
            print("      at its median cutoff, every best level is unchanged")

    if args.into:
        into = Path(args.into)
        into.mkdir(parents=True, exist_ok=True)
        path = into / "sensitivity.csv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(("contrast", "axis", "ceiling", "rank", "level", "mean_z", "n"))
            writer.writerows(tidy)
        print(f"\n  wrote {path}  ({len(tidy):,} rows)")
        floors = into / "sensitivity_floors.csv"
        with floors.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(("metric", "cutoff", "contrast", "axis", "best_before", "best_after"))
            writer.writerows(post_hoc_table)
        print(f"  wrote {floors}  ({len(post_hoc_table):,} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
