"""One CELL printed in full, so the axis-effect method can be checked rather than taken on trust.

A cell is every design sharing one trigger pair AND one geometry. Inside a cell the transcript, both
windows and both arm lengths are identical, so the ONLY thing that differs between its designs is
the design decisions: closure, upper3, lower3, scheme. That is what makes a cell a controlled
comparison and a pooled average not one.

For each of the three arms this prints every design's value, marks the cell's best, and then shows
exactly the three numbers the summary table is built from:

    rate    how often this level is the cell winner, over all cells that hold two or more levels
    chance  1/k for a cell holding k distinct levels -- what a level that does nothing would score
    lift    rate / chance.  1.0 = indistinguishable from luck.  2.0 = wins twice as often as luck.
            0.4 = wins LESS often than luck, i.e. the level is actively worse.
    gap     when the level does not win, how far its best design sits from the winner, in the arm's
            own units. 0.000 means it loses by nothing -- a tie. A large gap means it loses badly.

Every arm key is oriented so LOWER is better, which is why the winner is a minimum.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[6]
NB = ROOT / "src/engine/gates/notebooks/toehold_and"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(NB))

import objective_panel as op  # noqa: E402

ARMS = {"IED gain": "ied_gain", "A_M ratio": "f2", "opening SEP": "f1"}

rows = op.population(NB / "results")
cells: dict = {}
for row in rows:
    cells.setdefault((row["pair"], row["geom"]), []).append(row)


# The cell with the most distinct closures, so the comparison it supports is the widest available.
def spread(group):
    return len({str(r["closure"]) for r in group})


key = max(cells, key=lambda k: (spread(cells[k]), len(cells[k])))
cell = sorted(cells[key], key=lambda r: (str(r["closure"]), str(r["upper3"]), str(r["lower3"])))
print(f"cell = trigger pair {key[0]}, geometry {key[1]}")
print(f"  {len(cell)} designs, {spread(cell)} distinct closures")
print("  the transcript, both windows and both arm lengths are IDENTICAL across these rows")

best = {
    arm: min(cell, key=lambda r: r[col])[col]
    for arm, col in ARMS.items()
    if any(r.get(col) is not None for r in cell)
}

print(
    f"\n  {'closure':12s}{'upper3':16s}{'lower3':16s}{'scheme':12s}"
    + "".join(f"{arm:>16s}" for arm in ARMS)
)
for r in cell:
    marks = []
    for arm, col in ARMS.items():
        v = r.get(col)
        if v is None:
            marks.append(f"{'--':>16s}")
        else:
            win = " <= BEST" if v == best.get(arm) else ""
            marks.append(f"{v:>8.3f}{win:<8s}")
    print(
        f"  {r['closure']!s:12s}{r['upper3']!s:16s}{r['lower3']!s:16s}"
        f"{r['scheme']!s:12s}" + "".join(marks)
    )

print("\n  so THIS cell votes:")
for arm, col in ARMS.items():
    if arm not in best:
        continue
    winner = min((r for r in cell if r.get(col) is not None), key=lambda r: r[col])
    k = len({str(r["closure"]) for r in cell if r.get(col) is not None})
    print(
        f"    {arm:14s} winner closure = {winner['closure']!s:12s}"
        f"(one vote; every closure in this cell also gets 1/{k} of expected-by-luck)"
    )

print(
    "\n  and the loser's gap, on opening SEP, is what separates 'lost narrowly' from 'lost badly':"
)
col = ARMS["opening SEP"]
by_closure: dict[str, float] = {}
for r in cell:
    if r.get(col) is None:
        continue
    name = str(r["closure"])
    by_closure[name] = min(by_closure.get(name, float("inf")), r[col])
floor = min(by_closure.values())
for name, value in sorted(by_closure.items(), key=lambda kv: kv[1]):
    print(f"    {name:12s} best in cell {value:>9.3f}   gap to the winner {value - floor:>8.3f}")
