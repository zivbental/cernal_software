"""Analyse the axis-characterisation run: within-cell correlation, bins, interactions, survival.

    uv run python tools/analyse_axes.py --out axes_pfas
    uv run python tools/analyse_axes.py --out axes_pfas --csv docs/assets/axes

Win-rate and lift, which is all the earlier analysis had, answer one question — "which level
reaches its cell's best" — and are blind to three others. This answers all four, and says which
method produced each number so none of them is read as more than it is.

**1. Continuous axes get a within-cell correlation, not a win count.** `a_site_energy`,
`lock_energy`, `lock_minus_a_site`, `ddg_pref` and `l_local_min` are numbers, and asking which
"level" of a number wins is meaningless. Spearman rho is computed **inside each (trigger pair,
geometry) cell** and the distribution of rho over cells is reported — median, mean, sd, and how
many cells fall on each side of zero — with a sign test on that split for a p-value. Pooling the
rows instead would measure the trigger pairs: a design in a good cell looks good for a reason that
is not the axis.

**2. Non-monotonic shapes get bins, because a correlation cannot see them.** Each continuous axis is
cut into quintiles WITHIN its cell and the mean within-cell z-score of each objective is reported
per quintile. A U or an inverted U is then visible as a number; rho would read both as ~0 and a win
count would read them as noise.

**3. Interactions get a two-way table.** For each pair of categorical axes, the mean within-cell
z-score of each objective per combination, with the count in every box. A combination that beats
both of its parts — a particular closure only with a particular upper3 — cannot appear in any
single-axis summary.

**4. Survival is an outcome, not a nuisance.** Measured on the mCherry sweep, survival through the
funnel differs up to 37x between axis levels, so every number computed on survivors alone is
conditioned on the thing being studied. Every table here is therefore reported twice: over designs
measured in full, and over ALL rows with `skipped` as a binary outcome. Where the two disagree, the
disagreement is the finding.

Nothing here is weighted and nothing is combined into a score. The three objectives are reported
side by side because they disagree — opening SEP against the other two most of all — and a
combination would hide exactly that.
"""

from __future__ import annotations

import argparse
import csv
import math
import statistics as st
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "src/engine/gates/notebooks/toehold_and/results"

#: Objectives, all oriented so LOWER is better, as every arm key in this project is.
#: `open_11` is here as the ON state's own cost, not as an arm: it is what the ceiling tests.
OBJECTIVES = ("f1_opening_sep", "a_m_ratio", "ied_gain", "open_11")

#: How each objective is built from the row. Kept here rather than assumed so a reader can see
#: that `a_m_ratio` is a RATIO of two measured openings and inherits a collapsing denominator.
CATEGORICAL = ("closure", "upper3", "lower3", "scheme", "geom")
CONTINUOUS = (
    "a_site_energy",
    "lock_energy",
    "lock_minus_a_site",
    "ddg_pref",
    "l_local_min",
    "len_x",
)


def read_rows(out: str, shards: int = 6) -> list[dict]:
    """Every shard's rows, numbers parsed, with `None` for an empty cell and never 0.0."""
    rows: list[dict] = []
    for i in range(shards):
        path = RESULTS / f"{out}_{i}.csv"
        if not path.exists():
            continue
        with path.open(encoding="utf-8", newline="") as handle:
            for raw in csv.DictReader(handle):
                row: dict = {}
                for key, value in raw.items():
                    text = (value or "").strip()
                    if text == "":
                        row[key] = None
                        continue
                    try:
                        row[key] = float(text)
                    except ValueError:
                        row[key] = text
                rows.append(row)
    return rows


def derive(rows: list[dict]) -> None:
    """Attach the three arms, each from the four tubes, so nothing is read from a stored score.

    `f1_opening_sep` is the OFF-minus-ON opening contrast, `a_m_ratio` the ON/worst-OFF ratio of
    main-stem openness, `ied_gain` the state-11 against worst-OFF difference. All are oriented so
    LOWER is better, matching every ARMS key. A row missing a tube gets `None`, never 0.0 -- on
    every lower-is-better quantity here zero reads as perfect.
    """
    for row in rows:
        on = row.get("open_11")
        offs = [row.get(f"open_{s}") for s in ("00", "01", "10")]
        if on is None or any(v is None for v in offs):
            for name in OBJECTIVES:
                row.setdefault(name, None)
            row["f1_opening_sep"] = None
            row["a_m_ratio"] = None
            row["ied_gain"] = None
            continue
        worst_off = min(offs)  # the OFF state that opens most easily is the leak that matters
        # Opening SEP: how much cheaper the ON state opens than the leakiest OFF state. Negative
        # is a working gate, so lower is better and no sign flip is needed.
        row["f1_opening_sep"] = on - worst_off
        a_on, a_off = row.get("A_M_11"), None
        a_offs = [row.get(f"A_M_{s}") for s in ("00", "01", "10")]
        if a_on is not None and all(v is not None for v in a_offs):
            a_off = max(a_offs)
            # A ratio, so it inherits a collapsing denominator: a tiny worst-OFF makes it enormous
            # without the ON state being better. Negated so lower is better, like the others.
            row["a_m_ratio"] = -(a_on / a_off) if a_off else None
        else:
            row["a_m_ratio"] = None
        ied_on, ied_offs = (
            row.get("dG_open_11"),
            [row.get(f"dG_open_{s}") for s in ("00", "01", "10")],
        )
        if ied_on is not None and all(v is not None for v in ied_offs):
            row["ied_gain"] = -(min(ied_offs) - ied_on)
        else:
            row["ied_gain"] = None


def cells_of(rows: list[dict]) -> dict:
    """A cell is one trigger pair in one geometry: transcript and both windows held fixed."""
    out: dict = {}
    for row in rows:
        key = (
            row.get("gene_a"),
            row.get("gene_b"),
            row.get("x_start"),
            row.get("xstar_start"),
            row.get("len_x"),
            row.get("geom"),
        )
        out.setdefault(key, []).append(row)
    return out


def spearman(xs: list[float], ys: list[float]) -> float | None:
    """Spearman rho, ties averaged. `None` under three points, where it means nothing."""
    if len(xs) < 3:
        return None

    def ranks(values: list[float]) -> list[float]:
        order = sorted(range(len(values)), key=lambda i: values[i])
        out = [0.0] * len(values)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
                j += 1
            shared = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                out[order[k]] = shared
            i = j + 1
        return out

    rx, ry = ranks(xs), ranks(ys)
    mx, my = st.fmean(rx), st.fmean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry, strict=True))
    dx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    dy = math.sqrt(sum((b - my) ** 2 for b in ry))
    return None if dx == 0 or dy == 0 else num / (dx * dy)


def sign_test_p(positive: int, negative: int) -> float | None:
    """Two-sided sign test on how many cells fall each side of zero. Exact binomial."""
    total = positive + negative
    if total == 0:
        return None
    k = min(positive, negative)
    tail = sum(math.comb(total, i) for i in range(k + 1)) / (2.0**total)
    return min(1.0, 2.0 * tail)


def zscores(group: list[dict], column: str) -> dict[int, float]:
    """Within-cell z-score by row id, so cells of different difficulty can be pooled afterwards."""
    values = [(id(r), r.get(column)) for r in group if r.get(column) is not None]
    if len(values) < 2:
        return {}
    nums = [v for _i, v in values]
    mean = st.fmean(nums)
    sd = st.stdev(nums)
    if sd == 0:
        return {i: 0.0 for i, _v in values}
    return {i: (v - mean) / sd for i, v in values}


def report_spread(label: str, values: list[float]) -> None:
    if not values:
        print(f"  {label:34s} no cell supports it")
        return
    pos = sum(1 for v in values if v > 0)
    neg = sum(1 for v in values if v < 0)
    p = sign_test_p(pos, neg)
    print(
        f"  {label:34s}n {len(values):>5}  median {st.median(values):>+7.3f}  "
        f"mean {st.fmean(values):>+7.3f}  sd {st.stdev(values) if len(values) > 1 else 0.0:>5.3f}  "
        f"+{pos}/-{neg}  p {(f'{p:.2g}') if p is not None else '--':>8s}"
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default="axes_pfas", help="which run to read")
    parser.add_argument("--shards", type=int, default=6)
    parser.add_argument("--bins", type=int, default=5, help="quantiles for the shape check")
    parser.add_argument("--csv", default="", help="also write the tables under this prefix")
    args = parser.parse_args(argv)

    rows = read_rows(args.out, args.shards)
    if not rows:
        print(f"  nothing in results/{args.out}_*.csv -- run tools\\run_axes.cmd first")
        return 1
    derive(rows)
    full = [r for r in rows if not r.get("skipped")]
    print(f"  {len(rows):,} rows, {len(full):,} in full ({100.0 * len(full) / len(rows):.1f}%)")
    cells = cells_of(rows)
    print(f"  {len(cells):,} cells (trigger pair x geometry)")

    # ---- 4. survival first, because every table after it is conditioned on it ------------
    print(f"\n{'=' * 100}\nSURVIVAL -- the outcome, over ALL rows")
    reasons: dict[str, int] = {}
    for row in rows:
        reasons[str(row.get("skipped") or "measured")] = (
            reasons.get(str(row.get("skipped") or "measured"), 0) + 1
        )
    for reason, n in sorted(reasons.items(), key=lambda kv: -kv[1]):
        print(f"  {reason:28s}{n:>9,}  {100.0 * n / len(rows):>5.1f}%")
    for axis in CATEGORICAL:
        levels = sorted({str(r.get(axis)) for r in rows if r.get(axis) is not None})
        if len(levels) < 2:
            continue
        print(f"\n  survival by {axis}")
        print(f"    {'level':20s}{'rows':>9s}{'measured':>10s}{'rate':>8s}")
        for level in levels:
            here = [r for r in rows if str(r.get(axis)) == level]
            kept = sum(1 for r in here if not r.get("skipped"))
            print(f"    {level:20s}{len(here):>9,}{kept:>10,}{100.0 * kept / len(here):>7.1f}%")

    # ---- 1. continuous axes: within-cell Spearman ---------------------------------------
    print(f"\n{'=' * 100}\nCONTINUOUS AXES -- Spearman rho WITHIN each cell")
    print("  rho > 0 means a larger axis value goes with a LARGER (worse) objective, since every")
    print("  objective here is oriented lower-is-better. p is a two-sided sign test on the split.")
    for objective in OBJECTIVES:
        print(f"\n  {objective}")
        for axis in CONTINUOUS:
            rhos = []
            for group in cells.values():
                usable = [
                    r for r in group if r.get(axis) is not None and r.get(objective) is not None
                ]
                if len(usable) < 5:
                    continue
                rho = spearman([r[axis] for r in usable], [r[objective] for r in usable])
                if rho is not None:
                    rhos.append(rho)
            report_spread(axis, rhos)

    # ---- 2. shape: quintiles within cell ------------------------------------------------
    print(f"\n{'=' * 100}\nSHAPE -- mean within-cell z-score per within-cell quintile")
    print("  A monotonic axis walks one way; a U or inverted U is the non-monotonic case a")
    print("  correlation reads as ~0 and a win count reads as noise.")
    for axis in CONTINUOUS:
        print(f"\n  {axis}")
        header = f"    {'objective':18s}" + "".join(f"{f'Q{i + 1}':>10s}" for i in range(args.bins))
        print(header + f"{'n/bin':>9s}")
        for objective in OBJECTIVES:
            buckets: list[list[float]] = [[] for _ in range(args.bins)]
            for group in cells.values():
                usable = [
                    r for r in group if r.get(axis) is not None and r.get(objective) is not None
                ]
                if len(usable) < args.bins * 2:
                    continue
                z = zscores(usable, objective)
                ordered = sorted(usable, key=lambda r: r[axis])
                for position, row in enumerate(ordered):
                    which = min(position * args.bins // len(ordered), args.bins - 1)
                    if id(row) in z:
                        buckets[which].append(z[id(row)])
            if not any(buckets):
                continue
            cells_text = "".join(f"{st.fmean(b):>+10.3f}" if b else f"{'--':>10s}" for b in buckets)
            per = int(st.fmean([len(b) for b in buckets])) if any(buckets) else 0
            print(f"    {objective:18s}{cells_text}{per:>9,}")

    # ---- 3. interactions ----------------------------------------------------------------
    print(f"\n{'=' * 100}\nINTERACTIONS -- mean within-cell z-score per combination, n in brackets")
    print("  A box that beats both of its margins is an interaction; no single-axis table can")
    print("  show one. Read the n: a box with a handful of designs is not a finding.")
    for i, first in enumerate(CATEGORICAL):
        for second in CATEGORICAL[i + 1 :]:
            for objective in ("f1_opening_sep", "a_m_ratio"):
                table: dict[tuple[str, str], list[float]] = {}
                for group in cells.values():
                    z = zscores(group, objective)
                    for row in group:
                        if id(row) not in z:
                            continue
                        key = (str(row.get(first)), str(row.get(second)))
                        table.setdefault(key, []).append(z[id(row)])
                if len(table) < 4:
                    continue
                rows_l = sorted({k[0] for k in table})
                cols_l = sorted({k[1] for k in table})
                if len(rows_l) * len(cols_l) > 80:
                    continue
                print(f"\n  {first} x {second}   objective {objective} (lower is better)")
                print(f"    {'':18s}" + "".join(f"{c[:13]:>15s}" for c in cols_l))
                for r_level in rows_l:
                    cells_text = ""
                    for c_level in cols_l:
                        vals = table.get((r_level, c_level))
                        cells_text += (
                            f"{st.fmean(vals):>+9.2f}({len(vals):>4}){'':0s}"
                            if vals
                            else f"{'--':>15s}"
                        )
                    print(f"    {r_level[:18]:18s}{cells_text}")

    if args.csv:
        target = Path(args.csv)
        target.parent.mkdir(parents=True, exist_ok=True)
        path = target.with_suffix(".rows.csv")
        keys = sorted({k for r in rows for k in r})
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=keys, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        print(f"\n  wrote {path} for plotting ({len(rows):,} rows, {len(keys)} columns)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
