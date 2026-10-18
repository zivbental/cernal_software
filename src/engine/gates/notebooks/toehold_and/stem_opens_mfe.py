"""Does the main hairpin open in the MFE of the ON tube, and what would filtering on it cost?

    uv run python src/engine/gates/notebooks/toehold_and/stem_opens_mfe.py

**The question.** ``engaged_arm_11`` sums pair probabilities over the whole ensemble: "how much of
``main_pre*`` is paired to trigger A on average". The report's figures draw the **MFE** structure,
so a design can pass that floor and still show a shut main hairpin in the picture of its ON tube --
which is what prompted this. ``engages_stem_mfe`` asks the MFE question instead: of the positions
trigger A is paired to in the single most probable structure of tube 11, what share land on the
ascending arm.

**Streamed and resumable**, because every run here has to be: it writes each design as it is
measured and ``--resume`` skips what is already in the file.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

NB = Path(__file__).resolve().parent
sys.path.insert(0, str(NB.parents[4] / "src"))
sys.path.insert(0, str(NB))

import objective_energy as oe  # noqa: E402
import objective_panel as op  # noqa: E402
from full_sweep import read_fasta  # noqa: E402

from engine.gates.tools.folding import FoldEngine  # noqa: E402

FIELDS = ("switch", "pair", "geom", "engages_stem_mfe", "n_contacts", "n_on_arm")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default="stem_opens_mfe")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--scope",
        default="feasible",
        choices=("feasible", "gating"),
        help="feasible is where the other filters act, so it is the honest denominator",
    )
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args(argv)

    results = NB / "results"
    population = op.population(results)
    rows = population if args.scope == "feasible" else op.gating(population)
    if args.limit:
        rows = rows[: args.limit]
    print(f"  {len(rows):,} {args.scope} designs")

    path = results / f"{args.out}.csv"
    done: set[str] = set()
    if args.resume and path.exists():
        with path.open(encoding="utf-8") as handle:
            done = {r["switch"] for r in csv.DictReader(handle)}
        print(f"  --resume: {len(done):,} already measured")
    todo = [r for r in rows if r["switch"] not in done]
    if not todo:
        print("  nothing left to measure")
        return 0

    transcript = read_fasta(NB / "mCherry_original.txt")
    folder = FoldEngine(37.0)
    new = not path.exists() or not done
    started = time.time()
    with path.open("a" if done else "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        if new:
            writer.writeheader()
        for index, row in enumerate(todo):
            switch = row["switch"]
            trig_a = transcript[int(row["a_start"]) : int(row["a_end"])].upper().replace("T", "U")
            trig_b = transcript[int(row["b_start"]) : int(row["b_end"])].upper().replace("T", "U")
            contacts = oe.a_contacts(
                folder, f"{switch}&{trig_a}&{trig_b}", len(switch), len(trig_a)
            )
            on_arm = contacts & oe.ascending_arm(switch)
            writer.writerow(
                {
                    "switch": switch,
                    "pair": row["pair"],
                    "geom": row["geom"],
                    # None, not 0.0, when A has no contacts at all: that is an unmeasurable
                    # share rather than a share of zero, and the two must not merge.
                    "engages_stem_mfe": ""
                    if not contacts
                    else round(len(on_arm) / len(contacts), 4),
                    "n_contacts": len(contacts),
                    "n_on_arm": len(on_arm),
                }
            )
            if (index + 1) % 200 == 0:
                handle.flush()
                rate = (time.time() - started) / (index + 1)
                left = rate * (len(todo) - index - 1)
                print(
                    f"    {index + 1:,}/{len(todo):,}  {rate:.3f}s each, {left / 60:.1f} min left",
                    flush=True,
                )
    print(f"  wrote {path.name} in {(time.time() - started) / 60:.1f} min")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
