"""Read the population survey's shards and report distributions, not headlines.

    uv run python src/engine/gates/notebooks/toehold_and/survey_summary.py --prefix survey

Every claim this directory makes about the AND gate has so far been carried by one or two
designs, and twice that turned out to matter: a sweep that varied the secondary stem was
varying a domain that leaves the main hairpin byte-identical, and a start-codon result that
looked like a property of the architecture did not reproduce on the next two pairs. This
reads whatever ``population_survey.py`` wrote and answers the only question worth asking of
a population — **how often, and how much does it vary** — with no thresholds applied.

Three things it reports and one it refuses to do:

* ``separation`` and ``separation_no_state_10`` as quantiles, so a reader sees the spread
  rather than a single number and can tell a hard floor from a tight cluster.
* ``dG_open(10) - dG_open(11)`` in units of the measurement floor. ViennaRNA's partition
  function is single precision, so a difference below ~3e-05 kcal/mol is **unresolved, not
  zero**. Counting how many designs sit inside that band, and how far the furthest one
  strays, is the honest form of the claim "states 10 and 11 are the same".
* The start codon's own accessibility, OFF against ON, per design — including how many show
  the inversion (more exposed with the hairpin shut than with trigger A bound) and how many
  do not. One design showing it is an anecdote; a rate is a finding.

It refuses to declare anything "confirmed". It prints counts, quantiles and the worst case,
and where a result is carried by a minority it says which designs and how many.
"""

import argparse
import csv
import math
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[4]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from engine.gates.tools.folding import _FLOAT32_ENERGY_ULP  # noqa: E402


def load(prefix: str) -> list[dict]:
    """Every shard CSV, concatenated. CSV cells are strings, so convert explicitly —
    never with ``float(x or 0)``, which turns an unmeasured value into a real one."""
    directory = Path(__file__).resolve().parent / "results"
    rows: list[dict] = []
    for path in sorted(directory.glob(f"{prefix}_[0-9]*.csv")):
        with path.open(newline="") as handle:
            for raw in csv.DictReader(handle):
                row: dict = {}
                for key, cell in raw.items():
                    if cell == "" or cell is None:
                        row[key] = None
                        continue
                    try:
                        row[key] = float(cell) if "." in cell or "e" in cell.lower() else int(cell)
                    except ValueError:
                        row[key] = cell
                rows.append(row)
    return rows


def quantiles(values: list[float]) -> str:
    if not values:
        return "no data"
    ordered = sorted(values)

    def q(fraction: float) -> float:
        return ordered[min(len(ordered) - 1, int(fraction * len(ordered)))]

    return (
        f"min {ordered[0]:8.3f}  p25 {q(0.25):8.3f}  median {q(0.5):8.3f}  "
        f"p75 {q(0.75):8.3f}  max {ordered[-1]:8.3f}"
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--prefix", default="survey")
    args = parser.parse_args(argv)

    rows = load(args.prefix)
    if not rows:
        print("no shard CSVs found; run population_survey.py first")
        return 1

    hairpins = {r["main_hairpin"] for r in rows if r.get("main_hairpin")}
    print(f"{len(rows)} designs, {len(hairpins)} distinct main hairpins")
    print(f"len_x present: {sorted({r['len_x'] for r in rows})}")
    schemes: dict[str, int] = {}
    for row in rows:
        schemes[row["scheme"]] = schemes.get(row["scheme"], 0) + 1
    print(f"schemes: {schemes}")
    faults = sum(1 for r in rows if r.get("assembly_faults") not in ("-", None))
    print(f"designs with assembly faults: {faults}")

    print("\n--- separation (all three OFF states, so state 10 included) ---")
    print("  " + quantiles([r["separation"] for r in rows if r["separation"] is not None]))
    print("--- separation excluding state 10 ---")
    print(
        "  "
        + quantiles(
            [r["separation_no_state_10"] for r in rows if r["separation_no_state_10"] is not None]
        )
    )

    print("\n--- dG_open per state ---")
    for state in ("00", "01", "10", "11"):
        values = [r[f"dG_open_{state}"] for r in rows if r[f"dG_open_{state}"] is not None]
        print(f"  {state}: " + quantiles(values))

    print("\n--- dG_open(10) - dG_open(11), in units of the measurement floor ---")
    print(f"    (one unit = {_FLOAT32_ENERGY_ULP:.1e} kcal/mol; below it, unresolved not zero)")
    ulps = [r["d10_11_in_ulps"] for r in rows if r["d10_11_in_ulps"] is not None]
    inside = [u for u in ulps if abs(u) <= 1.0]
    print("  " + quantiles(ulps))
    print(f"  within one floor unit: {len(inside)}/{len(ulps)}")
    biggest = max(ulps, key=abs) if ulps else math.nan
    print(
        f"  furthest any design strays: {biggest:+.2f} units = "
        f"{biggest * _FLOAT32_ENERGY_ULP:+.2e} kcal/mol"
    )
    print(f"  for scale, a gate needs about 1.5 kcal/mol = {1.5 / _FLOAT32_ENERGY_ULP:,.0f} units")
    real = [r for r in rows if r["d10_11"] is not None and abs(r["d10_11"]) > 0.01]
    print(f"  designs where states 10 and 11 differ by more than 0.01 kcal/mol: {len(real)}")

    print("\n--- A_M, the main stem's mean unpaired probability ---")
    for state in ("00", "01", "10", "11"):
        values = [r[f"A_M_{state}"] for r in rows if r[f"A_M_{state}"] is not None]
        print(f"  {state}: " + quantiles(values))

    print("\n--- the start codon on its own ---")
    for state in ("00", "01", "10", "11"):
        values = [r[f"aug_{state}"] for r in rows if r[f"aug_{state}"] is not None]
        print(f"  {state}: " + quantiles(values))
    paired = [r for r in rows if r["aug_00"] is not None and r["aug_11"] is not None]
    inverted = [r for r in paired if r["aug_11"] < r["aug_00"]]
    strongly = [r for r in paired if r["aug_11"] < r["aug_00"] - 0.2]
    print(
        f"\n  AUG less accessible ON than OFF: {len(inverted)}/{len(paired)} designs"
        f"  (by more than 0.2: {len(strongly)})"
    )
    print("  " + quantiles([r["aug_11"] - r["aug_00"] for r in paired]) + "   <- change, ON - OFF")
    helps = [r for r in paired if r["aug_11"] > r["aug_00"] + 0.2]
    print(f"  AUG MORE accessible ON than OFF by more than 0.2: {len(helps)}/{len(paired)}")

    print("\n--- does anything predict a design breaking the pattern? ---")
    for field in ("len_x", "lock_energy", "stems_on_front"):
        values = [
            (r[field], abs(r["d10_11"]))
            for r in rows
            if r.get(field) is not None and r["d10_11"] is not None
        ]
        if len(values) > 2:
            print(f"  {field:<16} {_pearson(values):+.3f}  (correlation with |d10_11|)")
    return 0


def _pearson(points: list[tuple[float, float]]) -> float:
    n = len(points)
    mean_x = sum(p[0] for p in points) / n
    mean_y = sum(p[1] for p in points) / n
    cov = sum((x - mean_x) * (y - mean_y) for x, y in points)
    var_x = math.sqrt(sum((x - mean_x) ** 2 for x, _ in points))
    var_y = math.sqrt(sum((y - mean_y) ** 2 for _, y in points))
    return cov / (var_x * var_y) if var_x and var_y else math.nan


if __name__ == "__main__":
    raise SystemExit(main())
