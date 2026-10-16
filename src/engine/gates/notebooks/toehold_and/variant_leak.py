"""The AND-ness the BENCH will measure, on the four recoded transcripts rather than four tubes.

    uv run python src/engine/gates/notebooks/toehold_and/variant_leak.py --resume

**Why the sweep's AND-ness is the wrong number to order on.** The sweep scores four tubes by
*omitting* strands: state 10 is ``switch & trigger_A`` with no B strand present at all. The
experiment cannot omit a strand -- it realises state 10 with a transcript whose B window has been
synonymously recoded, so the tube still holds a full-length mRNA. If that recoded strand can still
participate in opening the switch, the construct fires on trigger A alone and the gate is not a
gate, however good its AND-ness looked.

**It happens, and it was found by eye on a figure rather than by any column.** On pair
``507/260/4`` the design chosen by the A_M ratio arm opens its arms at **0.70** kcal/mol in the
real ON state and at **0.86** in the transcript meant to realise state 10 -- indistinguishable --
against the **5.48** the sweep recorded for ``switch & A`` alone. The recoded B alone costs 17.72,
so it does not open the gate by itself; it opens it *together with* trigger A. The recoder removed
B's identity as a trigger and not its ability to help.

So this measures, per design, the opening cost of the arms in each of the four transcripts the
bench will actually build, and reports

    andness_variant = cost(original) - min(cost of the three recoded transcripts)

the same subtraction as the sweep's ``andness``, over the tubes that will exist. A design whose
``andness_variant`` is near zero or positive has no gate on the bench no matter what the sweep
said.

**The recode is per pair, not per panel.** ``codon_variants`` recodes every window of a role across
the whole panel at once, because one transcript then serves every design in it. Here each pair is
recoded on its own windows, which is the same operation restricted to one pair -- so the number is
a property of the design and does not change when the panel's other pair changes.

Streamed and resumable: one design is four folds, and the whole gating set is minutes rather than
seconds.
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

import codon_variants as cv  # noqa: E402
import objective_energy as oe  # noqa: E402
import objective_panel as op  # noqa: E402
from full_sweep import read_fasta  # noqa: E402

from engine.gates.tools.folding import FoldEngine  # noqa: E402

FIELDS = (
    "switch",
    "pair",
    "geom",
    "open_orig",
    "open_var_01",
    "open_var_10",
    "open_var_00",
    "andness_variant",
    "leak_10",
    "leak_01",
    "leak_00",
)


def recoded_pair(transcript: str, row: dict, tables: tuple) -> tuple[str, str]:
    """This pair's two recoded transcripts: A's windows recoded, and B's."""
    amino, fraction, groups = tables
    a_window = [(int(row["a_start"]), int(row["a_end"]))]
    b_window = [(int(row["b_start"]), int(row["b_end"]))]
    recoded_a, _ = cv.recode_windows(transcript, a_window, amino, fraction, groups)
    recoded_b, _ = cv.recode_windows(transcript, b_window, amino, fraction, groups)
    return recoded_a, recoded_b


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default="variant_leak")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--scope", default="gating", choices=("feasible", "gating"))
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
    amino, fraction = cv.load_codon_table(NB / "data" / "ecoli_codon_usage_table.csv")
    tables = (amino, fraction, cv.synonyms(amino))
    folder = FoldEngine(37.0)

    # One recode per PAIR, cached: every design in a cell shares the pair's windows, and the
    # recoding is string work on a 711 nt transcript that would otherwise run once per design.
    cache: dict[str, tuple[str, str]] = {}
    started = time.time()
    with path.open("a" if done else "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        if not done:
            writer.writeheader()
        for index, row in enumerate(todo):
            key = f"{row['a_start']}:{row['a_end']}:{row['b_start']}:{row['b_end']}"
            if key not in cache:
                cache[key] = recoded_pair(transcript, row, tables)
            recoded_a, recoded_b = cache[key]
            switch = row["switch"]
            lo_a, hi_a = int(row["a_start"]), int(row["a_end"])
            lo_b, hi_b = int(row["b_start"]), int(row["b_end"])
            rna = lambda s: s.upper().replace("T", "U")  # noqa: E731
            trig_a, trig_b = rna(transcript[lo_a:hi_a]), rna(transcript[lo_b:hi_b])
            rec_a, rec_b = rna(recoded_a[lo_a:hi_a]), rna(recoded_b[lo_b:hi_b])
            arms = oe.main_stem_arms(switch)

            def cost(*strands, switch=switch, arms=arms):
                return folder.open_penalty("&".join((switch, *strands)), arms)

            # Each transcript carries BOTH windows; only the named one is recoded. So the 01
            # transcript is `recoded_a` -- trigger A destroyed, B intact -- and it is folded with
            # both strands present, because both exist in that tube.
            orig = cost(trig_a, trig_b)
            var_01 = cost(rec_a, trig_b)
            var_10 = cost(trig_a, rec_b)
            var_00 = cost(rec_a, rec_b)
            offs = [v for v in (var_01, var_10, var_00) if v is not None]
            record = {
                "switch": switch,
                "pair": row["pair"],
                "geom": row["geom"],
                "open_orig": None if orig is None else round(orig, 4),
                "open_var_01": None if var_01 is None else round(var_01, 4),
                "open_var_10": None if var_10 is None else round(var_10, 4),
                "open_var_00": None if var_00 is None else round(var_00, 4),
                # The sweep's subtraction, over the tubes that will exist. A measurement that
                # could not be made stays None -- never 0.0, which would read as a perfect gate.
                "andness_variant": (
                    None if orig is None or not offs else round(orig - min(offs), 4)
                ),
                # How much CHEAPER each recoded tube is than the state it stands for, as the sweep
                # scored that state by omitting a strand. Positive means the transcript leaks.
                "leak_10": (
                    None
                    if var_10 is None or row.get("open_10") is None
                    else round(float(row["open_10"]) - var_10, 4)
                ),
                "leak_01": (
                    None
                    if var_01 is None or row.get("open_01") is None
                    else round(float(row["open_01"]) - var_01, 4)
                ),
                "leak_00": (
                    None
                    if var_00 is None or row.get("open_00") is None
                    else round(float(row["open_00"]) - var_00, 4)
                ),
            }
            writer.writerow({k: ("" if v is None else v) for k, v in record.items()})
            if (index + 1) % 100 == 0:
                handle.flush()
                rate = (time.time() - started) / (index + 1)
                print(
                    f"    {index + 1:,}/{len(todo):,}  {rate:.3f}s each, "
                    f"{rate * (len(todo) - index - 1) / 60:.1f} min left",
                    flush=True,
                )
    print(f"  wrote {path.name} in {(time.time() - started) / 60:.1f} min")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
