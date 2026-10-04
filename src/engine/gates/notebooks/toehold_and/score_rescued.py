"""Score the rare-codon-rescued designs, in the shape the panel already reads.

    uv run python src/engine/gates/notebooks/toehold_and/score_rescued.py --shard 0/6

**Why this exists rather than ``full_sweep --stage fold``.** That stage is built to RE-SELECT from a
multi-million-row cheap sweep: it applies a block selection, a per-pair stem cap and an axis-level
check, and refuses the run when a requested level is absent from what its selection kept. Pointed at
the rescued designs it narrowed 92,640 rows to ones carrying only ``SSS`` and ``WSS`` and then
refused, reporting the other five ``lower3`` levels as "absent from rescued_cheap*.csv" when they
are in the files and its own selection had dropped them.

The rescued set is **already selected** -- it is a specific list of sequences -- so re-selection is
the wrong operation. What it needs is the measurement, and that is
``objective_energy.score_design``, the same function the scorer itself calls. Nothing here
reimplements it: this module reads the cheap rows, calls that one function per design with the same
ON ceiling, and writes the columns ``objective_panel.load`` reads.

**What to expect.** Measured on a 200-design sample, **3.0% pass the ON ceiling** against 19.8% for
the original population, with ``open_11`` running min 1.59 / median 13.82 / max 32.26 against a
ceiling of 4.0. The rescue repairs ``main_pre_star`` to keep the switch's own stem Watson-Crick,
which strengthens the stem wherever that pair was weak, and a stronger stem opens less.

**TWO files, and the first version wrote one.** ``objective_panel.load`` makes two passes: over
``*_folded_*.csv`` for the axes and the A_M columns, and over ``obj*.csv`` for the objectives, where
``f1`` is read from ``andness``. A design needs a row in BOTH or it is silently absent -- its switch
never enters ``rows`` and the panel cannot see it. The first full run here wrote only the folded
half and 2,066 correctly scored designs were invisible: ``load`` returned 60,337 rows with 0 tagged
``rescued``.

``drift_fold.emit_obj`` already carries that lesson in its own docstring -- "``drift_fixed.csv``
matches neither glob, which is why the repaired designs were invisible to the panel even after being
fully scored" -- so this is the same mistake twice in one notebook. Both halves are written here,
from the same row, in one pass.

**Why it is still worth the fold.** 71.5% of the rescued designs are ``WSS`` -- 66,240 of them --
and ``WSS`` had **zero** rows in the population, because it installs AGG, a rare arginine, so the
screen deleted all of it. Weak-strong-strong was unreachable, not bad. At a 3% pass rate that is
still ~1,990 designs in an arrangement nothing has ever tested, which is a different thing from
2,780 more designs in arrangements we have."""

import argparse
import csv
import sys
import time
from pathlib import Path

NB = Path(__file__).resolve().parent
sys.path.insert(0, str(NB.parents[4] / "src"))
sys.path.insert(0, str(NB))

import objective_energy as oe  # noqa: E402
from full_sweep import read_fasta  # noqa: E402

from engine.gates.toehold import _mean_unpaired  # noqa: E402
from engine.gates.tools.folding import FoldEngine  # noqa: E402


def a_m_states(folder: FoldEngine, switch: str, trig_a: str, trig_b: str) -> dict[str, float]:
    """``A_M`` in all four tubes, plus the gain against the worst OFF state.

    ``score_design`` does not produce these -- they come from the gate's own
    ``four_tube_observables`` on the sweep's path -- and ``objective_panel.load`` derives both
    ``f2`` and ``f2_gain`` from them. Without them a rescued design loads with ``f2=None`` and is
    unrankable by the two arms the panel actually uses, which is what the first run did.

    Nearly free here: ``score_design`` has already folded all four tubes and ``FoldEngine`` caches
    on the instance, so these are cache hits -- measured 0.454 s cold against 0.0072 s warm.

    The span is ``main_z`` through ``main_pre``, 18 nt, **including the AUG between them**, which is
    what A_M means everywhere else in this notebook. A different span here would produce a second
    number for one quantity.
    """
    domains = oe.domains(switch)
    span = (domains["main_z"][0], domains["main_pre"][1])
    out: dict[str, float] = {}
    for state, strands in (
        ("00", switch),
        ("01", f"{switch}&{trig_b}"),
        ("10", f"{switch}&{trig_a}"),
        ("11", f"{switch}&{trig_a}&{trig_b}"),
    ):
        matrix = folder.pooled_pair_probabilities(strands)
        out[f"A_M_{state}"] = None if matrix is None else round(_mean_unpaired(matrix, *span), 6)
    off = [out[f"A_M_{s}"] for s in ("00", "01", "10")]
    # The WORST of the three OFF states, not state 10 alone: an AND that leaks in any one of them is
    # broken, so the worst is the honest comparator -- the same rule the sweep uses.
    if out["A_M_11"] is None or any(v is None for v in off):
        out["A_M_gain"] = None
    else:
        out["A_M_gain"] = round(out["A_M_11"] - max(off), 6)
    return out


#: Columns ``objective_panel.load`` reads off a ``*_folded_*.csv``, plus the axis columns the panel
#: groups and filters by. Written in this order so the file is readable beside the sweep's own.
FIELDS = (
    "switch",
    "scheme",
    "closure",
    "upper3",
    "lower3",
    "len_x",
    "xstar_start",
    "a_start",
    "a_end",
    "b_start",
    "b_end",
    "A_M_00",
    "A_M_01",
    "A_M_10",
    "A_M_11",
    "A_M_gain",
    "aug_11",
    "open_00",
    "open_01",
    "open_10",
    "open_11",
    "andness",
    "barrier",
    "separation",
    "lock",
    "lock01",
    "d_off",
    "A_r2_star_00",
    "access_a",
    "access_b",
    "access",
    "skipped",
    "source",
    "rescued",
)


#: The objective half's columns. ``load`` reads ``f1`` from ``andness`` and will drop any row whose
#: ``andness`` is missing, so the same measurement serves both files and only the shape differs.
OBJ_FIELDS = (
    "switch",
    "andness",
    "separation",
    "barrier",
    "open_00",
    "open_01",
    "open_10",
    "open_11",
    "access_a",
    "access_b",
    "d_off",
    "a_start",
    "a_end",
    "b_start",
    "b_end",
    "len_x",
    "source",
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--shard", default="", metavar="i/n", help="score only shard i of n")
    parser.add_argument("--from", dest="prefix", default="rescued_cheap")
    parser.add_argument("--out", default="rescued_folded")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--resume",
        action="store_true",
        help="append to the existing output and skip designs already in it. This module streams "
        "a row per design but shipped WITHOUT resume, and the first full run was stopped at a two "
        "hour limit about 65%% through -- 2,066 scored designs survived only because of the "
        "streaming, and all the rest of the work was lost. Every long run here has to do both",
    )
    parser.add_argument(
        "--keep-all",
        action="store_true",
        help="write every design, including those the ON ceiling rejects. Off by default: at a 3% "
        "pass rate that is 97% of the file spent on rows every filter downstream will drop",
    )
    args = parser.parse_args(argv)

    results = NB / "results"
    sources = sorted(results.glob(f"{args.prefix}_*.csv"))
    if not sources:
        print(f"  no {args.prefix}_*.csv in {results}")
        return 1

    rows = []
    for path in sources:
        with path.open(encoding="utf-8") as handle:
            rows.extend(csv.DictReader(handle))
    print(f"  {len(rows):,} designs across {len(sources)} file(s)")

    if args.shard:
        index, _, count = args.shard.partition("/")
        index, count = int(index), int(count or 0)
        if not 0 <= index < count:
            print(f"  bad --shard {args.shard}")
            return 1
        # An even stride, not a block: the cheap files are ordered by axis, so a contiguous block
        # would give one shard all of one level and tell us nothing about the others.
        rows = rows[index::count]
        print(f"  shard {index} of {count}: {len(rows):,} designs")
    if args.limit:
        rows = rows[: args.limit]

    transcript = read_fasta(NB / "mCherry_original.txt")
    folder = FoldEngine(37.0)
    name = f"{args.out}_{args.shard.partition('/')[0]}" if args.shard else args.out
    path = results / f"{name}.csv"
    # The objective half. `load` globs obj*.csv and skips any stem containing "smoke" or "panel",
    # so the name has to start with obj and avoid both.
    obj_path = results / f"obj_{name}.csv"

    # What a previous run already scored. Keyed on the switch, read from THIS shard's file only:
    # the shards partition the designs by an even stride, so another shard's file cannot hold one
    # of ours, and reading them all would make six processes contend for six files.
    done: set[str] = set()
    if args.resume and path.exists():
        with path.open(encoding="utf-8") as handle:
            done = {r["switch"] for r in csv.DictReader(handle) if r.get("switch")}
        print(f"  resuming: {len(done):,} designs already in {path.name}")
    elif args.resume:
        print(f"  --resume asked for but {path.name} does not exist; starting fresh")

    # Only designs that PASS are written, so a switch absent from the file was either rejected by
    # the ceiling or never reached. Those are different, and the distinction cannot be recovered
    # from the output -- so a resume re-scores everything it cannot find, and the rejected ones
    # cost their fold again. That is the price of a file that holds only the passers, and it is
    # cheaper than carrying 97% rejected rows through every downstream join.
    mode = "a" if (args.resume and done) else "w"
    written = kept = skipped = failed = resumed = 0
    start = time.perf_counter()
    with (
        path.open(mode, encoding="utf-8", newline="") as handle,
        obj_path.open(mode, encoding="utf-8", newline="") as obj_handle,
    ):
        writer = csv.DictWriter(handle, fieldnames=list(FIELDS), extrasaction="ignore")
        obj_writer = csv.DictWriter(obj_handle, fieldnames=list(OBJ_FIELDS), extrasaction="ignore")
        if mode == "w":
            writer.writeheader()
            obj_writer.writeheader()
        for position, row in enumerate(rows):
            switch = row.get("switch")
            if not switch:
                failed += 1
                continue
            if switch in done:
                resumed += 1
                continue
            try:
                a_lo, a_hi = int(row["a_start"]), int(row["a_end"])
                b_lo, b_hi = int(row["b_start"]), int(row["b_end"])
            except (KeyError, TypeError, ValueError):
                failed += 1
                continue
            # The rescue should have removed every rare codon; checked rather than trusted, because
            # a replacement can create one at a neighbouring position in the same 9-nt run.
            if any(c in oe.RARE_CODONS for c in oe.early_codons(switch)):
                failed += 1
                continue
            observed = oe.score_design(
                folder,
                switch,
                transcript[a_lo:a_hi],
                transcript[b_lo:b_hi],
                transcript=transcript,
                site_a=(a_lo, a_hi),
                site_b=(b_lo, b_hi),
                on_ceiling=oe.ON_CEILING,
            )
            if observed.get("skipped"):
                skipped += 1
                if not args.keep_all:
                    continue
            else:
                kept += 1
            record = {
                **row,
                **observed,
                **a_m_states(folder, switch, transcript[a_lo:a_hi], transcript[b_lo:b_hi]),
                "switch": switch,
                "source": "rescued",
                "rescued": 1,
            }
            writer.writerow(record)
            obj_writer.writerow(record)
            written += 1
            if position % 500 == 0 or position == len(rows) - 1:
                rate = (time.perf_counter() - start) / max(position + 1, 1)
                print(
                    f"  {position + 1}/{len(rows)}  kept {kept:,}  over ceiling {skipped:,}"
                    f"  {rate:.2f}s/design",
                    flush=True,
                )

    elapsed = time.perf_counter() - start
    print(
        f"\n  wrote {written:,} rows to {path.name} and {obj_path.name} in {elapsed / 60:.1f} min"
    )
    if resumed:
        print(f"    skipped {resumed:,} already scored by an earlier run")
    print(
        f"    passed the ON ceiling: {kept:,}   rejected by it: {skipped:,}   unusable: {failed:,}"
    )
    if kept + skipped:
        print(f"    pass rate {100.0 * kept / (kept + skipped):.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
