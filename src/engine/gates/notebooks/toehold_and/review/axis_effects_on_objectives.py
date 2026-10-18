"""Which DESIGN DECISIONS move the objectives, measured on the sweep we already have.

The cut has to be decided by data, not by preference, and the data exists: the mCherry sweep
carries every axis on every design. This measures, for each axis level, how often it reaches the
best value in its own (trigger pair, geometry) CELL on each of the three arms.

Within a cell, never pooled. Two designs in different cells have different transcripts and
different windows, so a level that happens to sit in good cells would look good for a reason that
is not the level. The cell is the control; the axis is the variable.

Arms, from ARM_COLUMNS -- all three oriented so LOWER is better:
    IED gain      ied_gain
    A_M ratio     f2
    opening SEP   f1

Reported per level: the number of cells it appears in (n, beside every rate, because a level
present in 7 cells cannot be compared with one present in 300), how often it wins its cell, and
what the expected win rate would be if the level made no difference -- 1/k for a cell holding k
distinct levels. A level that wins at its chance rate is a level the arm cannot see.
"""

import statistics as st
import sys
from pathlib import Path

ROOT = Path(r"C:\Users\Dell\source\repos\cernal_software")
NB = ROOT / "src/engine/gates/notebooks/toehold_and"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(NB))

import objective_panel as op  # noqa: E402

ARMS = {"IED gain": "ied_gain", "A_M ratio": "f2", "opening SEP": "f1"}
AXES = ("closure", "upper3", "lower3", "scheme", "geom")

rows = op.population(NB / "results")
print(f"population: {len(rows):,} feasible designs with percentiles")


# Keyed on (pair, geometry) EXCEPT when geometry is the axis under test, where the cell must span
# both geometries or there is nothing to compare.
def cells_for(axis: str) -> dict:
    out: dict = {}
    for row in rows:
        key = (row["pair"],) if axis == "geom" else (row["pair"], row["geom"])
        out.setdefault(key, []).append(row)
    return out


for axis in AXES:
    cells = cells_for(axis)
    print(f"\n{'=' * 94}\n{axis}")
    for arm, column in ARMS.items():
        wins: dict[str, int] = {}
        seen: dict[str, int] = {}
        chance: dict[str, list[float]] = {}
        gaps: dict[str, list[float]] = {}
        for group in cells.values():
            usable = [r for r in group if r.get(column) is not None and r.get(axis) is not None]
            levels = {str(r[axis]) for r in usable}
            if len(levels) < 2:
                continue
            best = min(usable, key=lambda r: r[column])
            best_value = best[column]
            for level in levels:
                seen[level] = seen.get(level, 0) + 1
                chance.setdefault(level, []).append(1.0 / len(levels))
                # How far this level's best in the cell is from the cell's best, so a level can
                # lose narrowly or badly and the two are not reported as the same thing.
                mine = min(r[column] for r in usable if str(r[axis]) == level)
                gaps.setdefault(level, []).append(mine - best_value)
            wins[str(best[axis])] = wins.get(str(best[axis]), 0) + 1
        if not seen:
            print(f"  {arm}: no cell carries two levels of {axis}")
            continue
        print(
            f"  {arm:14s}{'level':16s}{'cells':>7s}{'wins':>7s}{'rate':>8s}{'chance':>8s}"
            f"{'lift':>8s}{'median gap':>12s}"
        )
        for level in sorted(seen, key=lambda k: -(wins.get(k, 0) / seen[k])):
            n = seen[level]
            w = wins.get(level, 0)
            exp = st.fmean(chance[level])
            gap = st.median(gaps[level])
            print(
                f"  {'':14s}{level:16s}{n:>7,}{w:>7,}{100.0 * w / n:>7.1f}%"
                f"{100.0 * exp:>7.1f}%{(w / n) / exp if exp else float('nan'):>8.2f}{gap:>12.3f}"
            )
