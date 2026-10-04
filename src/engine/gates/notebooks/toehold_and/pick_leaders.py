"""Carve the leading pair-stems out of finished folds into a fresh stage-1 file.

    uv run python src/engine/gates/notebooks/toehold_and/pick_leaders.py \
        --from p1,p2 --source sweep --top 150 --out leaders

A breadth run folds every pair-stem against a narrow grid; the follow-up wants the opposite,
the full grid against the pair-stems that earned it. This reads the folded output, ranks
**pair-stems** (not designs), and writes the matching subset of the stage-1 CSV under a new
prefix — so the follow-up is an ordinary ``--block C`` run with no new selection code.

**Ranked on ``mean_separation``**, which is arm E per ``SELECTION_SPEC.md`` §1, and by a
pair-stem's **best** design rather than its median: the question is whether any axis setting
makes this pair-stem work, and a pair-stem carried by one good setting is exactly what the
follow-up exists to explore. ``A_M(11)`` is required above ``--opens`` first, because
``separation`` on a switch that never opens is the difference between two dead states
(BLOCK_A_FINDINGS.md §2) and a pair-stem selected on it would waste the whole follow-up.
"""

import argparse
import sys
from pathlib import Path

import duckdb

RESULTS = Path(__file__).resolve().parent / "results"
STEM = "x_start, xstar_start, a_start, a_end, b_start, b_end, stem_index"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--from", dest="sources", required=True, help="comma-separated folded prefixes, e.g. p1,p2"
    )
    parser.add_argument("--source", default="sweep", help="the stage-1 prefix to carve from")
    parser.add_argument("--top", type=int, default=150, help="how many pair-stems to keep")
    parser.add_argument("--out", default="leaders", help="prefix for the new stage-1 file")
    parser.add_argument(
        "--opens",
        type=float,
        default=0.3,
        help="A_M(11) a design must clear to count; a pair-stem needs at least one",
    )
    args = parser.parse_args(argv)

    globs = []
    for prefix in args.sources.split(","):
        prefix = prefix.strip()
        if not prefix:
            continue
        # A run may be one file or one per shard; both spellings are accepted, and a prefix
        # that matches nothing is an error rather than a silently smaller leader set.
        matches = sorted(RESULTS.glob(f"{prefix}_folded*.csv"))
        if not matches:
            sys.exit(f"no folded output matching {prefix}_folded*.csv -- nothing to rank")
        globs.extend(m.as_posix() for m in matches)
    print(f"  ranking pair-stems across {len(globs)} folded file(s)")

    con = duckdb.connect()
    files = ", ".join(f"'{g}'" for g in globs)
    con.execute(f"CREATE VIEW folded AS SELECT * FROM read_csv_auto([{files}], union_by_name=true)")
    total, stems = con.execute(f"SELECT count(*), count(DISTINCT ({STEM})) FROM folded").fetchone()
    opened = con.execute(
        f"SELECT count(DISTINCT ({STEM})) FROM folded WHERE A_M_11 > {args.opens}"
    ).fetchone()[0]
    print(f"  {total:,} folded designs over {stems:,} pair-stems; {opened:,} have a design")
    print(f"  clearing A_M(11) > {args.opens}")
    if not opened:
        sys.exit(f"no pair-stem has a design above A_M(11) {args.opens}; lower --opens")

    leaders = f"""
        SELECT {STEM} FROM folded WHERE A_M_11 > {args.opens}
        GROUP BY {STEM}
        ORDER BY max(mean_separation) DESC, {STEM}
        LIMIT {args.top}"""
    source = RESULTS / f"{args.source}_cheap.csv"
    if not source.exists():
        sys.exit(f"{source} not found")
    target = RESULTS / f"{args.out}_cheap.csv"
    con.execute(f"""
        COPY (SELECT c.* FROM read_csv_auto('{source.as_posix()}') c
              SEMI JOIN ({leaders}) l USING ({STEM}))
        TO '{target.as_posix()}' (HEADER, DELIMITER ',')""")

    kept, rows = con.execute(
        f"SELECT count(DISTINCT ({STEM})), count(*) FROM read_csv_auto('{target.as_posix()}')"
    ).fetchone()
    span = con.execute(f"""
        SELECT round(min(best), 4), round(max(best), 4) FROM (
          SELECT max(mean_separation) AS best FROM folded WHERE A_M_11 > {args.opens}
          GROUP BY {STEM} ORDER BY best DESC LIMIT {args.top})""").fetchone()
    print(f"  wrote {target.name}: {kept:,} pair-stems, {rows:,} stage-1 rows")
    print(f"  their best mean_separation spans {span[1]} down to {span[0]}")
    if kept < args.top:
        print(f"  ** only {kept:,} pair-stems qualified, fewer than the {args.top} asked for **")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
