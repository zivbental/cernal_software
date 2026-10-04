"""Fold the drift-repaired switches so the panel can actually see them.

    uv run python src/engine/gates/notebooks/toehold_and/drift_fold.py --shard 0/6
    uv run python src/engine/gates/notebooks/toehold_and/drift_fold.py --status

``drift_repair.py`` produces corrected switch SEQUENCES and rescores the four opening energies, but
``objective_panel.load`` joins two sides: the energy scores from ``obj*.csv`` and the folded
observables from ``*_folded_*.csv``. The repaired designs have the first and not the second, so they
carry no ``A_M``, no ``aug_11``, no ``free_xstar`` -- which means no ``f2``, no ``f2_gain`` and no
``lock``, and the panel cannot rank them at all. This writes the missing half.

**Why the repaired designs would otherwise still be rejected.** ``covers_drift`` tests the trigger
WINDOWS, which a patch does not move, so a repaired design looks exactly as drifted as before. The
output therefore carries ``drift_repaired=1`` and ``covers_drift`` honours it -- but only for rows
whose patch ``drift_repair.py --verify`` can re-derive from both transcripts, so the flag cannot be
set by hand on an unchecked sequence.

Shardable and resumable like every other long run here. Measured cost is printed by ``--status``
rather than estimated.
"""

import argparse
import csv
import sys
from pathlib import Path

NB = Path(__file__).resolve().parent
sys.path.insert(0, str(NB.parents[4] / "src"))
sys.path.insert(0, str(NB))

import objective_energy as oe  # noqa: E402
from full_sweep import read_fasta  # noqa: E402

from engine.gates.tools.folding import FoldEngine  # noqa: E402

STATES = ("00", "01", "10", "11")

#: Columns `objective_panel.load` reads off the folded side, plus the axes it carries through.
FIELDS = (
    "switch",
    "drift_repaired",
    *(f"A_M_{s}" for s in STATES),
    *(f"aug_{s}" for s in STATES),
    *(f"free_xstar_{s}" for s in STATES),
    "A_r2_star_00",
    "scheme",
    "closure",
    "upper3",
    "lower3",
    "len_x",
    "xstar_start",
)


def xstar_span(switch: str, len_x: int) -> tuple[int, int]:
    """``x*`` is the last ``len_x`` nt of the secondary hairpin, which closes on ``sws_end``.

    The secondary hairpin is 5'-anchored -- cap(3) r2*(32) sw_x k2* sec_loop sec_z x* -- so only
    the domains after r2* move with the overlap length, and x* is pinned to the hairpin's 3' end.
    ``oe.domains`` covers the main hairpin only, which is why this is derived here.
    """
    sws_end = len(switch) - 75
    return (sws_end - len_x, sws_end)


def mean_unpaired(matrix, lo: int, hi: int) -> float:
    return sum(1.0 - sum(matrix[i]) for i in range(lo, hi)) / (hi - lo)


def observables(folder: FoldEngine, switch: str, trig_a: str, trig_b: str, len_x: int) -> dict:
    """The folded half, over the same spans the sweep used.

    ``A_M`` is ``main_z`` through ``main_pre`` -- 18 nt including the AUG, identical in both
    geometries. ``d_off`` is NOT computed: it needs the intended dot-bracket, which only the
    generator has, and it is reported rather than thresholded so its absence costs no filter.
    """
    dom = oe.domains(switch)
    arm = (dom["main_z"][0], dom["main_pre"][1])
    xstar = xstar_span(switch, len_x)
    out: dict[str, object] = {}
    tubes = {
        "00": switch,
        "01": f"{switch}&{trig_b}",
        "10": f"{switch}&{trig_a}",
        "11": f"{switch}&{trig_a}&{trig_b}",
    }
    for state, strands in tubes.items():
        matrix = folder.pooled_pair_probabilities(strands)
        out[f"A_M_{state}"] = round(mean_unpaired(matrix, *arm), 6)
        out[f"aug_{state}"] = round(mean_unpaired(matrix, *dom["aug"]), 6)
        out[f"free_xstar_{state}"] = round(mean_unpaired(matrix, *xstar), 6)
        if state == "00":
            out["A_r2_star_00"] = round(mean_unpaired(matrix, 3, 35), 6)
    out["xstar_start"] = xstar[0]
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repaired", default="drift_fixed", help="results/<name>.csv to read")
    parser.add_argument("--out", default="drift_folded", help="results/<name>_<shard>.csv")
    parser.add_argument("--shard", default="", help="i/n")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args(argv)

    results = NB / "results"
    source = results / f"{args.repaired}.csv"
    if not source.exists():
        print(f"  {source.name} does not exist -- run drift_repair.py first.")
        return 1
    with source.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    if args.status:
        done = set()
        for path in sorted(results.glob(f"{args.out}*.csv")):
            with path.open(encoding="utf-8") as handle:
                done |= {
                    r["switch"] for r in csv.DictReader(handle) if r.get("A_M_11") not in (None, "")
                }
        print(f"  {len(rows):,} repaired designs in {source.name}")
        print(f"  folded so far:        {len(done):,}")
        print(f"  still to fold:        {len(rows) - len(done):,}")
        if len(done) < len(rows):
            print("\n  continue with (six shards in parallel):")
            print(
                "    0..5 | ForEach-Object { Start-Process -NoNewWindow uv -ArgumentList "
                "@('run','python','src/engine/gates/notebooks/toehold_and/drift_fold.py',"
                f"'--shard',\"$_/6\",'--out','{args.out}') }}"
            )
        else:
            print("\n  complete. Rebuild the panel and these designs compete for slots.")
        return 0

    # `_0` and not "" when unsharded: `objective_panel.load` globs `*_folded_*.csv`, which needs a
    # second underscore, so `drift_folded.csv` would be written, look finished, and never be read.
    tag = "_0"
    if args.shard:
        index, total = (int(v) for v in args.shard.split("/"))
        rows = [r for i, r in enumerate(rows) if i % total == index]
        tag = f"_{index}"
        print(f"  shard {index} of {total}: {len(rows):,} designs")
    if args.limit:
        rows = rows[: args.limit]

    path = results / f"{args.out}{tag}.csv"
    done: dict[str, dict] = {}
    if path.exists():
        with path.open(encoding="utf-8") as handle:
            done = {r["switch"]: r for r in csv.DictReader(handle) if r.get("switch")}
        print(f"  resuming: {len(done):,} already folded in {path.name}")

    folder = FoldEngine(37.0)
    transcript = read_fasta(NB / "mCherry_original.txt")
    written = 0
    mode = "a" if done else "w"
    with path.open(mode, encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(FIELDS), extrasaction="ignore")
        if mode == "w":
            writer.writeheader()
        for number, row in enumerate(rows):
            if row["switch"] in done:
                continue
            len_x = int(row["len_x"])
            trig_a = transcript[int(row["a_start"]) : int(row["a_end"])]
            trig_b = transcript[int(row["b_start"]) : int(row["b_end"])]
            out = {
                "switch": row["switch"],
                # Set here and nowhere else: `covers_drift` trusts this column, so it is written
                # only beside a freshly computed fold of a sequence drift_repair produced.
                "drift_repaired": 1,
                "scheme": row.get("scheme"),
                "closure": row.get("closure"),
                "upper3": row.get("upper3"),
                "lower3": row.get("lower3"),
                "len_x": len_x,
            }
            out.update(observables(folder, row["switch"], trig_a, trig_b, len_x))
            writer.writerow(out)
            handle.flush()
            written += 1
            if number % 25 == 0:
                print(f"    {number + 1}/{len(rows)}  written {written:,}", flush=True)
    print(f"\n  wrote {written:,} folded rows to {path.name}")
    emit_obj(results, args.repaired, rows, transcript, folder)
    return 0


#: Columns `objective_panel.load` reads off the energy side.
OBJ_FIELDS = (
    "switch",
    "a_start",
    "a_end",
    "b_start",
    "b_end",
    "len_x",
    "open_00",
    "open_01",
    "open_10",
    "open_11",
    "andness",
    "barrier",
    "access_a",
    "access_b",
)


def emit_obj(
    results: Path, repaired: str, rows: list[dict], transcript: str, folder: FoldEngine
) -> None:
    """The energy half, under a name `load` will glob.

    ``drift_repair.py`` already rescored all four tubes, so nothing is refolded here -- this is a
    rename and a reshape. It is written as ``obj_drift.csv`` because ``load`` globs ``obj*.csv``;
    ``drift_fixed.csv`` matches neither glob, which is why the repaired designs were invisible to
    the panel even after being fully scored.

    ``access_a``/``access_b`` come from the cached accessibility table and not from a fresh fold:
    they are properties of the trigger WINDOW on the transcript, and a patch does not move the
    windows, so the values the sweep already computed are the right ones.
    """
    path = results / "obj_drift.csv"
    table = oe.accessibility_table(
        folder,
        transcript,
        {(int(r["a_start"]), int(r["a_end"])) for r in rows}
        | {(int(r["b_start"]), int(r["b_end"])) for r in rows},
        results / "accessibility.csv",
    )
    existing: dict[str, dict] = {}
    if path.exists():
        with path.open(encoding="utf-8") as handle:
            existing = {r["switch"]: r for r in csv.DictReader(handle) if r.get("switch")}
    for row in rows:
        out = {key: row.get(key) for key in OBJ_FIELDS if key in row}
        out["switch"] = row["switch"]
        out["access_a"] = table.get((int(row["a_start"]), int(row["a_end"])))
        out["access_b"] = table.get((int(row["b_start"]), int(row["b_end"])))
        existing[row["switch"]] = out
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(OBJ_FIELDS), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(existing.values())
    print(f"  wrote {len(existing):,} energy rows to {path.name} (the half `load` globs as obj*)")


if __name__ == "__main__":
    sys.exit(main())
