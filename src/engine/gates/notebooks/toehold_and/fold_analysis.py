"""Read stage 2's folded designs and say which axis settings actually won.

    uv run python src/engine/gates/notebooks/toehold_and/fold_analysis.py
    uv run python src/engine/gates/notebooks/toehold_and/fold_analysis.py --opens 0.5
    uv run python src/engine/gates/notebooks/toehold_and/fold_analysis.py --sql "SELECT ..."

**Why paired comparisons and not just medians.** A block A run crosses a handful of
pair-stems with all 360 axis points, and pair-stems differ from each other far more than
axis settings do. A marginal median per axis level therefore mostly reports *which
pair-stems happened to land in that level*, which is the same error that made "strongest
locks per closure arm" fold two trigger pairs. So every axis is also scored **paired**:
holding the pair-stem and the other three axes fixed, how often does each level win? That
is a within-design comparison and the pair-stem cancels out of it.

**Why three statistics and not one.** ``SELECTION_SPEC.md`` §1 puts arm E on
``mean_separation`` and arm K on ``log10_rate_advantage``, and §4.4 asks for the joint
``separation`` alongside. They do not agree, and the disagreement is the finding, not noise
to be averaged away. Every table here carries all of them.

**The one threshold, and it is a reported cut, not a filter.** ``A_M(11)`` is the
availability of the RBS/AUG region in the ON state. A design whose ``A_M(11)`` is near zero
never opens *at all*, and a large ``separation`` on such a design is the difference between
two dead states. ``--opens`` sets where "opens" is drawn; the sensitivity of the count to
that choice is printed so the number is never taken on faith. Nothing is removed from the
file or from any ranking.
"""

import argparse
import sys
from pathlib import Path

import duckdb

RESULTS = Path(__file__).resolve().parent / "results"

#: One folded design's pair-stem. Axis effects are measured holding this fixed.
STEM = "x_start, xstar_start, a_start, a_end, b_start, b_end, stem_index"

#: The four swept axes, each with the other three (so a paired comparison holds them fixed).
AXES = ("closure", "upper3", "lower3", "island")

#: Arm E, the joint form §4.4 asks for beside it, arm K, and the ON-state availability that
#: decides whether any of the other three mean anything.
STATISTICS = ("mean_separation", "A_M_gain", "separation", "log10_rate_advantage", "A_M_11")


def _table(rows, headers) -> None:
    if not rows:
        print("  (no rows)")
        return
    widths = [max(len(str(h)), *(len(str(r[i])) for r in rows)) for i, h in enumerate(headers)]
    print("  " + "  ".join(str(h).ljust(w) for h, w in zip(headers, widths, strict=True)))
    print("  " + "  ".join("-" * w for w in widths))
    for row in rows:
        print("  " + "  ".join(str(v).ljust(w) for v, w in zip(row, widths, strict=True)))


def _section(title: str) -> None:
    print(f"\n{'=' * 78}\n  {title}\n{'=' * 78}")


def _wrap(text: str, width: int = 74) -> None:
    words, line, first = text.split(), "", True
    for word in words:
        if len(line) + len(word) + 1 > width and line:
            print(f"  {'* ' if first else '  '}{line}")
            line, first = word, False
        else:
            line = f"{line} {word}".strip()
    print(f"  {'* ' if first else '  '}{line}")


def _survey(con, opens: float) -> int:
    n, designs, stems, pairs = con.execute(
        f"SELECT count(*), count(DISTINCT ({STEM}, closure, upper3, lower3, island)), "
        f"count(DISTINCT ({STEM})), count(DISTINCT (x_start, xstar_start, a_start, a_end, "
        f"b_start, b_end)) FROM f"
    ).fetchone()
    _section("WHAT IS IN THE FILE")
    print(f"  {n:,} folded designs, {stems} pair-stems, {pairs} trigger pairs")
    if designs != n:
        print(f"  ** {n - designs} duplicate design keys -- the file may merge two runs **")

    _section("DOES IT OPEN AT ALL? -- everything below depends on this")
    _wrap(
        "A_M(11) is the ON-state availability of the RBS/AUG region. Where it is near zero "
        "the switch is shut in every state, and a large `separation` is then the difference "
        "between two dead states rather than a working gate."
    )
    print()
    rows = []
    for thr in (0.1, 0.2, 0.3, 0.5, 0.7):
        c = con.execute(f"SELECT count(*) FROM f WHERE A_M_11 > {thr}").fetchone()[0]
        rows.append((f"A_M(11) > {thr}", f"{c:,}", f"{100 * c / n:.1f}%"))
    _table(rows, ["threshold", "designs", "share"])
    print(f"\n  `--opens` is set to {opens}; the rows above are why that choice is reported,")
    print("  not hidden. Nothing is filtered out of the file or out of any ranking.")

    _section("DO THE RANKING STATISTICS AGREE?")
    _wrap(
        "Two statistics correlating near +/-1 carry one fact between them. Two near zero are "
        "measuring different things, and ranking on either alone silently discards the other."
    )
    print()
    rows = []
    seen = set()
    for a in STATISTICS:
        for b in STATISTICS:
            if a != b and (b, a) not in seen:
                seen.add((a, b))
                r = con.execute(f"SELECT round(corr({a},{b}),3) FROM f").fetchone()[0]
                rows.append((a, b, r))
    rows.sort(key=lambda t: -abs(t[2] if t[2] is not None else 0))
    _table(rows, ["statistic A", "statistic B", "pearson r"])

    for axis in AXES:
        others = ", ".join(a for a in AXES if a != axis)
        _section(f"AXIS: {axis}")
        _table(
            con.execute(f"""
            SELECT {axis}, count(*) AS n,
                   round(median(mean_separation), 4) AS mean_sep,
                   round(median(A_M_gain), 4) AS A_M_gain,
                   round(median(separation), 2) AS joint_sep,
                   round(median(A_M_11), 4) AS A_M_11,
                   sum(CASE WHEN A_M_11 > {opens} THEN 1 ELSE 0 END) AS opens
            FROM f GROUP BY {axis} ORDER BY mean_sep DESC""").fetchall(),
            [axis, "n", "mean_sep", "A_M_gain", "joint_sep", "A_M_11", "opens"],
        )
        # A median ranks the typical design; a panel orders individual ones. A level can
        # have the worst median and still hold the best construct, so the spread and the
        # maximum are shown beside it -- measured on the real data, `closed_CAU` has the
        # best conditional median of any closure and ZERO designs in the overall top 500,
        # while `open_3x3` holds 410 of them on five times the standard deviation.
        print()
        print("  by mean/sd/max, and share of the overall top 500 on mean_separation:")
        _table(
            con.execute(f"""
            WITH top AS (SELECT {axis} AS lvl FROM f ORDER BY mean_separation DESC LIMIT 500)
            SELECT f.{axis}, round(avg(f.mean_separation), 4) AS mean,
                   round(stddev(f.mean_separation), 4) AS sd,
                   round(max(f.mean_separation), 4) AS best,
                   round(quantile_cont(f.mean_separation, 0.99), 4) AS p99,
                   (SELECT count(*) FROM top WHERE top.lvl = f.{axis}) AS in_top_500
            FROM f GROUP BY f.{axis} ORDER BY best DESC""").fetchall(),
            [axis, "mean", "sd", "best", "p99", "in top 500"],
        )
        wins = con.execute(f"""
            SELECT {axis}, count(*) AS wins FROM (
              SELECT *, row_number() OVER (PARTITION BY {STEM}, {others}
                                           ORDER BY mean_separation DESC) AS rn FROM f)
            WHERE rn = 1 GROUP BY {axis} ORDER BY wins DESC""").fetchall()
        total = sum(w for _, w in wins)
        print("\n  paired on mean_separation, pair-stem and the other three axes held fixed:")
        print("   " + ",  ".join(f"{a} {w}" for a, w in wins) + f"   (of {total})")

        # The marginal and the paired view can disagree, and when they do the paired one is
        # the comparison that controls for which pair-stems landed where.
        cond = con.execute(f"""
            SELECT {axis}, count(*) AS n, round(median(mean_separation), 4) AS mean_sep,
                   round(median(separation), 2) AS joint_sep
            FROM f WHERE A_M_11 > {opens} GROUP BY {axis} ORDER BY mean_sep DESC""").fetchall()
        print(f"\n  among designs that open (A_M(11) > {opens}) only:")
        _table(cond, [axis, "n", "mean_sep", "joint_sep"])

    _section("DOES EACH RULE IMPROVE A DESIGN? -- paired effect, not share of winners")
    _wrap(
        "Share-of-winners says how often a level comes first; it does not say by how much, "
        "and a level that wins narrowly everywhere is worth less than one that wins rarely "
        "but hugely. This holds the pair-stem and the other three axes fixed and reports the "
        "median CHANGE in mean_separation from switching that one level to its best "
        "alternative -- the improvement the rule actually buys."
    )
    print()
    for axis in AXES:
        others = ", ".join(a for a in AXES if a != axis)
        rows = con.execute(f"""
            WITH ranked AS (
              SELECT {axis} AS lvl, mean_separation AS v,
                     max(mean_separation) OVER (PARTITION BY {STEM}, {others}) AS best_here,
                     count(*) OVER (PARTITION BY {STEM}, {others}) AS siblings
              FROM f)
            SELECT lvl, count(*) AS n,
                   round(median(v - best_here), 4) AS median_gap_to_best,
                   round(avg(v - best_here), 4) AS mean_gap_to_best,
                   sum(CASE WHEN v = best_here THEN 1 ELSE 0 END) AS times_best
            FROM ranked WHERE siblings > 1
            GROUP BY lvl ORDER BY median_gap_to_best DESC""").fetchall()
        print(f"  {axis} -- 0.0 means this level IS the best of its group:")
        _table(rows, [axis, "n", "median gap", "mean gap", "times best"])
        print()

    _section("WHICH COMBINATIONS WIN? -- what the pipeline should actually keep")
    _wrap(
        "Axes are reported one at a time everywhere above, which cannot show an interaction: "
        "a level can be mediocre alone and essential in company. This ranks the full "
        "(closure, upper3, lower3, island) points, which is what a funnel would keep."
    )
    print()
    _table(
        con.execute(f"""
        SELECT closure, upper3, lower3, island, count(*) AS n,
               round(median(mean_separation), 4) AS median,
               round(max(mean_separation), 4) AS best,
               sum(CASE WHEN A_M_11 > {opens} THEN 1 ELSE 0 END) AS opens
        FROM f GROUP BY ALL ORDER BY best DESC LIMIT 12""").fetchall(),
        ["closure", "upper3", "lower3", "island", "n", "median", "best", "opens"],
    )
    print()
    print("  the same, ranked on the median instead -- a different set means the best")
    print("  combinations are not the most reliable ones:")
    _table(
        con.execute(f"""
        SELECT closure, upper3, lower3, island, count(*) AS n,
               round(median(mean_separation), 4) AS median,
               round(max(mean_separation), 4) AS best,
               sum(CASE WHEN A_M_11 > {opens} THEN 1 ELSE 0 END) AS opens
        FROM f GROUP BY ALL ORDER BY median DESC LIMIT 12""").fetchall(),
        ["closure", "upper3", "lower3", "island", "n", "median", "best", "opens"],
    )

    _section(f"DESIGNS THAT BOTH OPEN AND SEPARATE (A_M(11) > {opens}), TOP 12")
    top = con.execute(f"""
        SELECT closure, upper3, lower3, island, scheme, x_start, stem_index,
               round(mean_separation,4), round(A_M_gain,4), round(A_M_11,3),
               round(separation,2), round(log10_rate_advantage,2)
        FROM f WHERE A_M_11 > {opens} ORDER BY mean_separation DESC LIMIT 12""").fetchall()
    _table(
        top,
        [
            "closure",
            "upper3",
            "lower3",
            "island",
            "scheme",
            "x@",
            "stem",
            "mean_sep",
            "A_M_gain",
            "A_M_11",
            "joint_sep",
            "log10_kin",
        ],
    )
    distinct = len({(r[5], r[6]) for r in top})
    print(f"\n  those 12 rows come from {distinct} distinct pair-stem(s).")
    if distinct <= 2:
        print("  ** a top table drawn from one or two pair-stems describes those pair-stems,")
        print("  ** not the axes. Read the paired tables above instead.")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default="sweep", help="stage 2's --out prefix")
    parser.add_argument(
        "--opens",
        type=float,
        default=0.3,
        help="A_M(11) above which a design counts as opening (reported, never filtered)",
    )
    parser.add_argument("--sql", help="run one query against a view named `f`")
    args = parser.parse_args(argv)

    # A phase is one file when folded in a single process and one per shard when folded
    # across cores, so both spellings must work. This looked for `{out}_folded.csv` only,
    # which meant every sharded run's analysis exited with "not found" -- and because the
    # orchestrator only tailed the log, three phases finished with no analysis at all.
    sources = sorted(RESULTS.glob(f"{args.out}_folded*.csv"))
    if not sources:
        sys.exit(f"no {args.out}_folded*.csv in {RESULTS} -- run --stage fold first")
    files = ", ".join(f"'{p.as_posix()}'" for p in sources)
    con = duckdb.connect()
    # union_by_name so a shard written by a slightly different build still lines up by
    # column name rather than by position.
    con.execute(f"CREATE VIEW f AS SELECT * FROM read_csv_auto([{files}], union_by_name=true)")
    if args.sql:
        result = con.execute(args.sql)
        rows = result.fetchall()
        _table(rows, [d[0] for d in result.description])
        print(f"\n  {len(rows):,} rows")
        return 0
    print(f"  querying {len(sources)} file(s): {', '.join(p.name for p in sources)}")
    return _survey(con, args.opens)


if __name__ == "__main__":
    raise SystemExit(main())
