"""Query the full sweep without loading it — and say plainly what it cannot tell you.

    # once, after stage 1 finishes: build the compact copy
    uv run python src/engine/gates/notebooks/toehold_and/sweep_analysis.py --build

    # then, as often as you like
    uv run python src/engine/gates/notebooks/toehold_and/sweep_analysis.py
    uv run python src/engine/gates/notebooks/toehold_and/sweep_analysis.py --sql "SELECT ..."

**What this can and cannot answer.** Stage 1 folds no switches. Nothing in its 32 columns
is a gate observable: there is no ``p_open``, no ``separation``, no ``A_M``, no state
resolution at all. What it holds is the enumerated design space plus the screens that are
cheap enough to compute for all of it — GC geometry, the scheme-C stem energies, and the
three fixed-alignment main-stem energies.

So every question of the form *"which design is better?"* is out of scope here and belongs
to stage 2. The questions in scope are *"what did we actually enumerate, how do the axes
move the cheap metrics, and which of them are redundant with each other?"* — which is what
decides how stage 2 should spend its folding budget.

``lock_energy`` in particular is the strongest single predictor we have (rho -0.938 against
locked(10)) and is what stage 2 selects on, but a strong lock is **not** a working gate:
the same measurement series found designs with excellent locks and no separation at all.
Ranking by it here would be exactly the mistake the four-tube evaluation exists to prevent.

**Why duckdb and a Parquet copy.** The CSV is ~926 MB at the full grid. duckdb queries it
in place without loading it, so a group-by over 1.49 M rows runs in seconds and a few
hundred MB. ``--build`` additionally writes a Parquet copy with the 161-nt ``switch``
column dropped — it is a quarter of the file and is needed only for stage 2's folding, not
for any analysis — which makes every later query near-instant. The CSV is never modified.
"""

import argparse
import sys
from pathlib import Path

import duckdb

RESULTS = Path(__file__).resolve().parent / "results"

#: Columns that identify one trigger pair. ``x_start`` alone does not -- see
#: ``full_sweep.PAIR_KEY_COLUMNS``; the 1036 pairs carry only 373 distinct x_start values.
PAIR_KEY = "x_start, xstar_start, a_start, a_end, b_start, b_end"

#: The four axes stage 1 actually varies. ``PENDING_LENGTH_AXES`` in full_sweep.py are
#: recorded as constant columns and are deliberately not listed here: they are not swept
#: yet, and treating a constant column as an axis invents a finding.
AXES = ("closure", "upper3", "lower3", "island")

#: The cheap metrics, grouped by what they measure. Kept explicit so a new column added to
#: stage 1 does not silently join an analysis it was never meant to be part of.
STEM_METRICS = ("lock_energy", "a_site_energy", "b_site_energy", "ddg_pref")
MAIN_METRICS = ("stem_dG", "grip_alone", "grip_with_x")
GC_METRICS = ("gc_bottom3", "gc_top3", "gc_gradient", "gc_balance")


def _source(con, args) -> str:
    """The table expression to query: the Parquet copy if built, else the CSV itself."""
    parquet = RESULTS / f"{args.out}_analysis.parquet"
    csv = RESULTS / f"{args.out}_cheap.csv"
    if parquet.exists() and not args.csv:
        return f"read_parquet('{parquet.as_posix()}')"
    if not csv.exists():
        sys.exit(f"{csv} not found -- run stage 1 first")
    return f"read_csv_auto('{csv.as_posix()}')"


def _build(con, args) -> int:
    """Write the compact Parquet copy, dropping the one column analysis never needs."""
    csv = RESULTS / f"{args.out}_cheap.csv"
    if not csv.exists():
        sys.exit(f"{csv} not found -- run stage 1 first")
    parquet = RESULTS / f"{args.out}_analysis.parquet"
    src = f"read_csv_auto('{csv.as_posix()}')"
    print(f"  reading {csv.name} ({csv.stat().st_size / 1e6:.0f} MB)")
    con.execute(
        f"COPY (SELECT * EXCLUDE (switch) FROM {src}) "
        f"TO '{parquet.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)"
    )
    rows = con.execute(f"SELECT count(*) FROM read_parquet('{parquet.as_posix()}')").fetchone()[0]
    print(
        f"  wrote {parquet.name}: {rows:,} rows, {parquet.stat().st_size / 1e6:.0f} MB "
        f"({csv.stat().st_size / parquet.stat().st_size:.0f}x smaller)\n"
        f"  the switch sequence is dropped here and still lives in the CSV, which stage 2 reads"
    )
    return 0


def _table(rows, headers) -> None:
    widths = [max(len(str(h)), *(len(str(r[i])) for r in rows)) for i, h in enumerate(headers)]
    print("  " + "  ".join(str(h).ljust(w) for h, w in zip(headers, widths, strict=True)))
    print("  " + "  ".join("-" * w for w in widths))
    for row in rows:
        print("  " + "  ".join(str(v).ljust(w) for v, w in zip(row, widths, strict=True)))


def _section(title: str) -> None:
    print(f"\n{'=' * 78}\n  {title}\n{'=' * 78}")


def _survey(con, src) -> int:
    n, pairs, stems, schemes = con.execute(
        f"SELECT count(*), count(DISTINCT ({PAIR_KEY})), "
        f"count(DISTINCT ({PAIR_KEY}, stem_index)), count(DISTINCT scheme) FROM {src}"
    ).fetchone()
    _section("WHAT IS IN THE FILE")
    print(
        f"  {n:,} designs, {pairs:,} trigger pairs, {stems:,} pair-stem combinations, "
        f"{schemes} distinct schemes"
    )
    print(
        f"  {n // max(stems, 1)} axis points per stem "
        f"(expected 360 = 6 closures x 5 upper3 x 6 lower3 x 2 island)"
    )
    if n % max(stems, 1):
        print("  ** uneven rows per stem -- the file may be from an interrupted run **")

    _section("COVERAGE PER AXIS -- every level should carry the same count")
    for axis in AXES:
        rows = con.execute(
            f"SELECT {axis}, count(*) FROM {src} GROUP BY {axis} ORDER BY 2 DESC"
        ).fetchall()
        counts = {r[1] for r in rows}
        flag = "" if len(counts) == 1 else "   ** UNEVEN **"
        print(f"  {axis:<9} {len(rows)} levels, {rows[0][1]:,} designs each{flag}")
        if flag:
            _table(rows, [axis, "designs"])

    _section("DO THE AXES MOVE THE CHEAP METRICS?")
    print("  Stage 1's axes shape the MAIN hairpin; the stem metrics describe the SECONDARY")
    print("  one. If an axis leaves a metric flat, that is the design working as intended --")
    print("  not a null result -- and it means stage 2 must be what separates those levels.\n")
    for axis in AXES:
        cols = ", ".join(f"round(median({m}),2) AS {m}" for m in (*STEM_METRICS[:1], *MAIN_METRICS))
        rows = con.execute(
            f"SELECT {axis}, count(*) AS n, {cols} FROM {src} GROUP BY {axis} ORDER BY stem_dG"
        ).fetchall()
        print(f"  by {axis}:")
        _table(rows, [axis, "n", "lock_energy", "stem_dG", "grip_alone", "grip_with_x"])
        print()

    _section("THE STATE-10 LEAK, COUNTED ACROSS THE WHOLE SWEEP")
    print("  A thermodynamic AND needs  grip_with_x < stem_dG < grip_alone: trigger A loses")
    print("  to the stem alone and wins only once trigger B has freed sw_xs. Necessary, and")
    print("  measured to be insufficient -- designs satisfying it still scored separation 0.00.")
    print("  So this is a count of how much of the space is even eligible, not a score.\n")
    row = con.execute(
        f"SELECT count(*), "
        f"  sum(CASE WHEN grip_alone > stem_dG THEN 1 ELSE 0 END), "
        f"  sum(CASE WHEN grip_with_x < stem_dG THEN 1 ELSE 0 END), "
        f"  sum(CASE WHEN grip_with_x < stem_dG AND stem_dG < grip_alone THEN 1 ELSE 0 END) "
        f"FROM {src} WHERE stem_dG IS NOT NULL"
    ).fetchone()
    total, loses, wins, both = row
    _table(
        [
            (
                "A loses to the stem alone (grip_alone > stem_dG)",
                f"{loses:,}",
                f"{100 * loses / total:.1f}%",
            ),
            ("A wins with x (grip_with_x < stem_dG)", f"{wins:,}", f"{100 * wins / total:.1f}%"),
            ("BOTH -- the full window", f"{both:,}", f"{100 * both / total:.1f}%"),
        ],
        ["condition", "designs", "share"],
    )

    _section("WHICH CHEAP METRICS ARE REDUNDANT WITH EACH OTHER?")
    print("  Two metrics correlating near +/-1 carry one fact between them, so a Pareto front")
    print("  over both is really a front over one. Pearson, over every row.\n")
    metrics = [*STEM_METRICS, *MAIN_METRICS, *GC_METRICS]
    pairs_seen = []
    for i, a in enumerate(metrics):
        for b in metrics[i + 1 :]:
            r = con.execute(f"SELECT corr({a},{b}) FROM {src}").fetchone()[0]
            if r is not None:
                pairs_seen.append((a, b, round(r, 3)))
    pairs_seen.sort(key=lambda t: -abs(t[2]))
    _table(pairs_seen[:12], ["metric A", "metric B", "pearson r"])
    print(f"\n  ({len(pairs_seen)} pairs computed; the 12 strongest shown)")

    _section("WHAT THIS RUN CANNOT TELL YOU")
    for finding in (
        "No design here has been folded. There is no p_open, no separation, no A_M and no "
        "state resolution, so nothing above ranks designs by whether they gate.",
        "lock_energy is the best single predictor we have and still not a performance "
        "measure: designs with excellent locks were measured at separation 0.00.",
        "toehold_trim, rbs_loop_len and secondary_arm are constant columns here, not axes. "
        "They need an assemble() change before they can be swept.",
        "Stage 2 produces the four-tube observables, and only for the subset it folds.",
    ):
        words, line = finding.split(), ""
        first = True
        for word in words:
            if len(line) + len(word) + 1 > 74 and line:
                print(f"  {'* ' if first else '  '}{line}")
                line, first = word, False
            else:
                line = f"{line} {word}".strip()
        print(f"  {'* ' if first else '  '}{line}")
    print()
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default="sweep", help="stage 1's --out prefix")
    parser.add_argument("--build", action="store_true", help="write the compact Parquet copy")
    parser.add_argument("--csv", action="store_true", help="query the CSV even if Parquet exists")
    parser.add_argument("--sql", help="run one query against the sweep and print it")
    args = parser.parse_args(argv)

    con = duckdb.connect()
    if args.build:
        return _build(con, args)
    src = _source(con, args)
    if args.sql:
        # `sweep` is the name the query should use, so ad-hoc SQL never has to know
        # whether it is reading Parquet or CSV.
        con.execute(f"CREATE VIEW sweep AS SELECT * FROM {src}")
        result = con.execute(args.sql)
        rows = result.fetchall()
        if rows:
            _table(rows, [d[0] for d in result.description])
            print(f"\n  {len(rows):,} rows")
        else:
            print("  no rows")
        return 0
    print(f"  querying {src.split('(')[1].rstrip(')')}")
    return _survey(con, src)


if __name__ == "__main__":
    raise SystemExit(main())
