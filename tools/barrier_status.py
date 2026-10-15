"""How far the state-10 landing barrier run has got, read off the shard files.

Reads only; starts nothing and writes nothing, so it is safe to run while the shards are
going. Prints per shard and in total, with the spread of what has been measured so far --
a progress count alone cannot say whether the numbers mean anything yet.
"""

import csv
import pathlib
import statistics as st
import time

HERE = pathlib.Path(__file__).resolve().parent.parent / "docs/assets/barrier"


def main() -> int:
    files = sorted(HERE.glob("landing_*.csv"))
    if not files:
        print(f"\n  no shard files yet in {HERE}")
        print("  start them with:  tools\run_barrier.cmd 0   (then 1..5)")
        return 0

    now = time.time()
    rows: list[dict] = []
    print(f"\n  {'shard':>7}{'rows':>9}{'last written':>16}{'size':>10}")
    for path in files:
        with path.open(newline="", encoding="utf-8") as fh:
            mine = list(csv.DictReader(fh))
        rows.extend(mine)
        idle = now - path.stat().st_mtime
        state = f"{idle:,.0f}s ago" if idle < 3600 else f"{idle / 3600:.1f}h ago"
        flag = "  <- STALLED?" if idle > 600 else ""
        print(
            f"  {path.stem.split('_')[-1]:>7}{len(mine):>9,}{state:>16}"
            f"{path.stat().st_size / 1024:>9.0f}K{flag}"
        )

    values = [float(r["b_10"]) for r in rows if r["b_10"]]
    secs = [float(r["s_10"]) for r in rows if r["s_10"]]
    print(
        f"\n  {len(rows):,} designs measured, {len(values):,} with a path found "
        f"({len(rows) - len(values):,} gave up at the ceiling)"
    )
    if secs:
        print(
            f"  {st.mean(secs):.2f} s per design per shard "
            f"-> about {3600 * 6 / st.mean(secs):,.0f} designs an hour across six"
        )
    if len(values) >= 8:
        ordered = sorted(values)
        negative = sum(1 for v in values if v < 0)
        print("\n  the barrier to trigger A landing on x* with NO trigger B, kcal/mol")
        print(
            f"    median {st.median(values):+.2f}   mean {st.mean(values):+.2f}   "
            f"min {ordered[0]:+.2f}   max {ordered[-1]:+.2f}"
        )
        print(
            f"    {negative:,} of {len(values):,} ({negative / len(values):.1%}) are "
            f"NEGATIVE -- A lands downhill, with no barrier at all"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
