"""Analyse the axis-characterisation run: within-cell correlation, bins, interactions, survival.

    uv run python tools/analyse_axes.py --out axes_c8
    uv run python tools/analyse_axes.py --out axes_c8 --into docs/assets/axes_c8

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
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "src/engine/gates/notebooks/toehold_and/results"

#: The ON/OFF CONTRASTS, and the two terms each one is built from.
#:
#: **Why the terms are reported beside the contrast.** A contrast moves for two different
#: reasons -- the ON state opening better, or the worst OFF state collapsing -- and they are
#: different design stories: one is a gate that turns on, the other is a gate that leaks less.
#: The contrast alone cannot tell them apart. `sep_a_m` is the clearest case: it is a RATIO, so a
#: tiny denominator inflates it without the ON state improving at all.
#:
#: Each entry is (contrast, ON term, worst-OFF term, how the worst OFF is picked, label).
#: `pick` is `min` for a COST (the leakiest OFF state is the one that opens cheapest) and `max`
#: for an ACCESSIBILITY (the worst OFF state is the most open one) -- the same rule, and the same
#: reason, as `measure_design`'s own `worst_max` helper.
CONTRASTS: tuple[tuple[str, str, str, str, str], ...] = (
    ("sep_open", "open_11", "open_off_worst", "min", "main-stem opening, kcal/mol"),
    ("sep_a_m", "A_M_11", "A_M_off_worst", "max", "main-stem openness, ratio"),
    ("sep_ied", "ied_rbs_linker_11", "ied_off_all", "min", "ensemble defect, RBS to linker"),
    ("sep_dg_open", "dG_open_11", "dG_open_off_worst", "min", "W_rank opening, kcal/mol"),
)

#: Objectives, every one oriented so LOWER IS BETTER, which is what the sign of every rho and
#: z-score in this report is read against.
#:
#: Orientation is declared per column and never inferred, because these columns do not agree:
#: `open_*` and `dG_open_*` are COSTS (lower is better in the ON state, higher in an OFF state),
#: `A_M_*` is an unpaired FRACTION (higher is better in the ON state, lower in an OFF state), and
#: `ied_rbs_linker_*` is a defect where higher means more paired (lower is better in the ON state,
#: higher in an OFF state). So a contrast built from them changes sign meaning between families,
#: and an OFF term is not oriented the same way as the ON term it is subtracted from.
#:
#: `-1.0` means the measured column is negated to face lower-is-better. The measured column itself
#: is never overwritten: `value_of` reads it and applies the sign.
ORIENTATION: dict[str, float] = {
    # the contrasts, all already built lower-is-better by `derive`
    "sep_open": 1.0,
    "sep_a_m": 1.0,
    "sep_ied": 1.0,
    "sep_dg_open": 1.0,
    # ON terms -- the ON state should open, so an opening cost and a defect face as measured
    "open_11": 1.0,
    "dG_open_11": 1.0,
    "ied_rbs_linker_11": 1.0,
    "A_M_11": -1.0,
    # worst-OFF terms -- an OFF state should stay shut, so every sign is the ON term's inverse
    "open_off_worst": -1.0,
    "dG_open_off_worst": -1.0,
    "ied_off_all": -1.0,
    "A_M_off_worst": 1.0,
    # the state-10 leak: trigger A alone reaching x* and the main stem. Measured on EVERY design,
    # before the ON ceiling decides, so these two are the only outcomes here that can be analysed
    # over the whole population rather than over survivors.
    "xstar_engA_10": 1.0,
    "mainpre_engA_10": 1.0,
    # mechanism terms: trigger A's toehold accessibility and the cost of opening the main hairpin
    # in state 11. `access_a` is a probability, so higher is better.
    "barrier": 1.0,
    "access_a": -1.0,
    # the engine's OWN ied contrasts, carried as measured for comparison with `sep_ied` above.
    # They differ in which states count as OFF: `ied_gain` references state 00 alone and
    # `ied_gain_worst` the worst of 01 and 10, while `sep_ied` takes the worst of all three.
    "ied_gain": -1.0,
    "ied_gain_worst": -1.0,
}

OBJECTIVES = tuple(ORIENTATION)

#: Which objectives get a two-way interaction table. All of them squares the report for little
#: gain; these are the contrasts, which is where a combination either pays or does not.
INTERACTION_OBJECTIVES = tuple(name for name, *_ in CONTRASTS)

CATEGORICAL = ("closure", "upper3", "lower3", "scheme", "geom")
#: Axes that vary BETWEEN designs of one cell -- the design decisions.
CONTINUOUS = (
    "a_site_energy",
    "lock_energy",
    "lock_minus_a_site",
    "ddg_pref",
)

#: Axes that belong to the TRIGGER PAIR, so they are constant inside every cell and cannot be
#: studied within one. They get their own between-cell section; binning a constant produced two
#: byte-identical "shapes" before this was separated.
PAIR_LEVEL = ("l_local_min", "len_x")


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


def worst_off(row: dict, prefix: str, pick: str) -> tuple[float | None, str | None]:
    """The worst OFF state's value for one measurement family, and WHICH state it was.

    Which OFF state binds the contrast is a result, not bookkeeping. The architecture's central
    claim is that **10 is the hard state** -- trigger A alone must not open the gate, and that is
    the whole difference between a two-input AND and a one-input switch. So "is 10 the binding OFF
    state, and under which lever settings does it stop being?" is answerable by counting, and the
    answer is carried on the row as ``binding_off_<family>``.

    ``None`` -- never 0.0 -- when any of the three states is missing: on a lower-is-better
    quantity a zero reads as perfect and clears every threshold.
    """
    states = ("00", "01", "10")
    values = [row.get(f"{prefix}_{state}") for state in states]
    if any(value is None for value in values):
        return None, None
    chooser = min if pick == "min" else max
    best = chooser(values)
    return best, states[values.index(best)]


def derive(rows: list[dict]) -> None:
    """Attach each ON/OFF contrast and the worst-OFF term it is built from.

    Built from the four tubes rather than read from a stored score, so nothing here depends on a
    ranking written by an earlier run. What it must NOT do is overwrite a measurement the engine
    already made: ``ied_gain`` and ``ied_gain_worst`` are columns ``measure_design`` computes, and
    an earlier version of this function replaced ``ied_gain`` with a ``dG_open`` contrast -- a
    different measurement family, in different units, under the engine's name. ``analyse_levers``
    and ``analyse_closure`` read the same column straight from the CSV, so the one name meant two
    quantities depending on which tool you ran. The contrasts are therefore named ``sep_*`` and
    the measured columns are left exactly as the engine wrote them.
    """
    for row in rows:
        for contrast, on_key, off_key, pick, _label in CONTRASTS:
            off_value, binding = worst_off(row, on_key.rsplit("_11", 1)[0], pick)
            on_value = row.get(on_key)
            row[off_key] = off_value
            row[f"binding_off_{contrast}"] = binding
            if on_value is None or off_value is None:
                row[contrast] = None
                continue
            if contrast == "sep_a_m":
                # A ratio, so it inherits a collapsing denominator: a tiny worst-OFF makes it
                # enormous without the ON state being better, which is why `A_M_11` and
                # `A_M_off_worst` are reported beside it. Negated so lower is better.
                row[contrast] = -(on_value / off_value) if off_value else None
            elif contrast == "sep_ied":
                # `ied` is a defect where higher means more paired, so the gain is the worst OFF
                # state minus the ON state. Negated so lower is better, like the others.
                row[contrast] = -(off_value - on_value)
            else:
                # An opening COST: how much cheaper the ON state opens than the leakiest OFF
                # state. Negative is a working gate, so lower is better and no flip is needed.
                row[contrast] = on_value - off_value


def value_of(row: dict, objective: str) -> float | None:
    """One objective, oriented so LOWER IS BETTER, or ``None`` if it was not measured.

    The orientation lives in ``ORIENTATION`` and is applied here, once, so no caller has to know
    whether a given column is a cost, a fraction or a defect -- and so the measured column on the
    row keeps the sign the engine gave it.
    """
    value = row.get(objective)
    if value is None or isinstance(value, str):
        return None
    return ORIENTATION.get(objective, 1.0) * value


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
    values = [(id(r), value_of(r, column)) for r in group if value_of(r, column) is not None]
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


class Tee:
    """Print to the terminal AND to the report file, so the analysis is not only a scrollback.

    `print` is used throughout rather than a logger because the report is meant to be read as
    text; this keeps that and adds persistence, instead of rewriting every call site.
    """

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = path.open("w", encoding="utf-8", newline="\n")
        self._stdout = sys.stdout
        self.path = path

    def write(self, text: str) -> int:
        self._stdout.write(text)
        self._handle.write(text)
        return len(text)

    def flush(self) -> None:
        self._stdout.flush()
        self._handle.flush()

    def close(self) -> None:
        self._handle.close()


def write_tidy(path: Path, header: tuple[str, ...], records: list[tuple]) -> None:
    """One observation per line, so plotting is a group-by rather than a reshape."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(records)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default="axes_c8", help="which run to read")
    parser.add_argument("--shards", type=int, default=6)
    parser.add_argument("--bins", type=int, default=5, help="quantiles for the shape check")
    parser.add_argument(
        "--into",
        default="",
        help="directory for the report and the tidy tables; defaults to docs/assets/<out>/ so "
        "they sit with the rest of the figure material. Pass 'none' to print only",
    )
    args = parser.parse_args(argv)

    into = None
    tee = None
    if args.into.lower() != "none":
        into = Path(args.into) if args.into else ROOT / "docs/assets" / args.out
        tee = Tee(into / "report.txt")
        sys.stdout = tee

    rows = read_rows(args.out, args.shards)
    if not rows:
        print(f"  nothing in results/{args.out}_*.csv -- run tools\\run_axes.cmd first")
        return 1
    derive(rows)
    full = [r for r in rows if not r.get("skipped")]
    print(f"  {len(rows):,} rows, {len(full):,} in full ({100.0 * len(full) / len(rows):.1f}%)")
    cells = cells_of(rows)
    print(f"  {len(cells):,} cells (trigger pair x geometry)")
    survival_table: list[tuple] = []
    #: (contrast, axis, level, state, n, share). Axis and level are empty on the overall rows.
    binding_table: list[tuple] = []
    correlation_table: list[tuple] = []
    shape_table: list[tuple] = []
    interaction_table: list[tuple] = []
    pair_level_table: list[tuple] = []

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
            survival_table.append((axis, level, len(here), kept, kept / len(here)))

    # ---- 0b. which OFF state binds each contrast ----------------------------------------
    print(f"\n{'=' * 100}\nBINDING OFF STATE -- which of 00/01/10 each contrast is taken against")
    print("  State 10 -- trigger A alone -- is the state that separates a two-input AND from a")
    print("  one-input switch: A on its own must not open the gate. So which OFF state actually")
    print("  binds the contrast is a result. A contrast bound by 00 is being set by the resting")
    print("  structure and says nothing about AND behaviour; one bound by 10 is the real test.")
    print("  Reported per contrast, then per level of each categorical axis, because a lever that")
    print("  moves WHICH state binds has changed the mechanism and not just the margin.")
    for contrast, _on, _off, _pick, label in CONTRASTS:
        column = f"binding_off_{contrast}"
        present = [r for r in rows if r.get(column)]
        if not present:
            continue
        counts = Counter(str(r[column]) for r in present)
        print(f"\n  {contrast}   ({label})   n={len(present):,}")
        for state in ("00", "01", "10"):
            n = counts.get(state, 0)
            share = 100.0 * n / len(present)
            print(f"    state {state}{n:>12,}{share:>7.1f}%")
            binding_table.append((contrast, "", "", state, n, share / 100.0))
        for axis in CATEGORICAL:
            levels = sorted({str(r.get(axis)) for r in present if r.get(axis) is not None})
            if len(levels) < 2:
                continue
            for level in levels:
                here = [r for r in present if str(r.get(axis)) == level]
                if not here:
                    continue
                per = Counter(str(r[column]) for r in here)
                for state in ("00", "01", "10"):
                    binding_table.append(
                        (
                            contrast,
                            axis,
                            level,
                            state,
                            per.get(state, 0),
                            per.get(state, 0) / len(here),
                        )
                    )

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
                    r
                    for r in group
                    if r.get(axis) is not None and value_of(r, objective) is not None
                ]
                if len(usable) < 5:
                    continue
                rho = spearman([r[axis] for r in usable], [value_of(r, objective) for r in usable])
                if rho is not None:
                    rhos.append(rho)
            report_spread(axis, rhos)
            if rhos:
                pos = sum(1 for v in rhos if v > 0)
                neg = sum(1 for v in rhos if v < 0)
                correlation_table.append(
                    (
                        objective,
                        axis,
                        len(rhos),
                        st.median(rhos),
                        st.fmean(rhos),
                        st.stdev(rhos) if len(rhos) > 1 else 0.0,
                        pos,
                        neg,
                        sign_test_p(pos, neg),
                    )
                )

    # ---- 2. shape: quintiles within cell ------------------------------------------------
    print(f"\n{'=' * 100}\nSHAPE -- mean within-cell z-score per within-cell quintile")
    print("  A monotonic axis walks one way; a U or inverted U is the non-monotonic case a")
    print("  correlation reads as ~0 and a win count reads as noise.")
    for axis in CONTINUOUS:
        print(f"\n  {axis}")
        header = f"    {'objective':22s}" + "".join(f"{f'Q{i + 1}':>10s}" for i in range(args.bins))
        print(header + f"{'n/bin':>9s}")
        for objective in OBJECTIVES:
            buckets: list[list[float]] = [[] for _ in range(args.bins)]
            for group in cells.values():
                usable = [
                    r
                    for r in group
                    if r.get(axis) is not None and value_of(r, objective) is not None
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
            print(f"    {objective:22s}{cells_text}{per:>9,}")
            for q, bucket in enumerate(buckets, start=1):
                if bucket:
                    shape_table.append((axis, objective, q, st.fmean(bucket), len(bucket)))

    # ---- 2b. pair-level axes, BETWEEN cells ---------------------------------------------
    print(f"\n{'=' * 100}\nPAIR-LEVEL AXES -- between cells, because a cell holds them fixed")
    print("  `l_local_min` and `len_x` are properties of the trigger pair, so they are constant")
    print("  inside a cell and a within-cell bin of them is a bin of a constant. One point per")
    print("  cell instead: the pair's value against that cell's BEST and MEDIAN objective.")
    for axis in PAIR_LEVEL:
        print(f"\n  {axis}")
        print(f"    {'objective':22s}{'cells':>8s}{'rho(best)':>11s}{'rho(med)':>10s}{'p':>9s}")
        for objective in OBJECTIVES:
            points = []
            for group in cells.values():
                values = [
                    value_of(r, objective) for r in group if value_of(r, objective) is not None
                ]
                axis_values = {r.get(axis) for r in group if r.get(axis) is not None}
                if not values or len(axis_values) != 1:
                    continue
                points.append((axis_values.pop(), min(values), st.median(values)))
            if len(points) < 5:
                print(f"    {objective:22s}{len(points):>9,}  too few cells")
                continue
            xs = [p[0] for p in points]
            rho_best = spearman(xs, [p[1] for p in points])
            rho_med = spearman(xs, [p[2] for p in points])
            # A permutation-free p for a between-cell rho: the sign test does not apply here, so
            # the large-sample approximation is used and labelled as such.
            p_text = "--"
            if rho_best is not None and len(points) > 10:
                z = rho_best * math.sqrt(len(points) - 1)
                p_text = f"{math.erfc(abs(z) / math.sqrt(2)):.2g}"
            print(
                f"    {objective:22s}{len(points):>9,}"
                f"{(f'{rho_best:+.3f}' if rho_best is not None else '--'):>11s}"
                f"{(f'{rho_med:+.3f}' if rho_med is not None else '--'):>13s}{p_text:>10s}"
            )
            pair_level_table.append((axis, objective, len(points), rho_best, rho_med, p_text))

    # ---- 3. interactions ----------------------------------------------------------------
    print(f"\n{'=' * 100}\nINTERACTIONS -- mean within-cell z-score per combination, n in brackets")
    print("  A box that beats both of its margins is an interaction; no single-axis table can")
    print("  show one. Read the n: a box with a handful of designs is not a finding.")
    for i, first in enumerate(CATEGORICAL):
        for second in CATEGORICAL[i + 1 :]:
            for objective in INTERACTION_OBJECTIVES:
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
                        if vals:
                            interaction_table.append(
                                (
                                    first,
                                    r_level,
                                    second,
                                    c_level,
                                    objective,
                                    st.fmean(vals),
                                    len(vals),
                                )
                            )
                        cells_text += (
                            f"{st.fmean(vals):>+9.2f}({len(vals):>4}){'':0s}"
                            if vals
                            else f"{'--':>15s}"
                        )
                    print(f"    {r_level[:18]:18s}{cells_text}")

    if into is not None:
        write_tidy(
            into / "survival.csv",
            ("axis", "level", "rows", "measured", "rate"),
            survival_table,
        )
        write_tidy(
            into / "correlation.csv",
            ("objective", "axis", "n_cells", "median_rho", "mean_rho", "sd_rho", "pos", "neg", "p"),
            correlation_table,
        )
        write_tidy(
            into / "binding_off.csv",
            ("contrast", "axis", "level", "state", "n", "share"),
            binding_table,
        )
        write_tidy(
            into / "shape.csv",
            ("axis", "objective", "quintile", "mean_z", "n"),
            shape_table,
        )
        write_tidy(
            into / "pair_level.csv",
            ("axis", "objective", "n_cells", "rho_best", "rho_median", "p_best"),
            pair_level_table,
        )
        write_tidy(
            into / "interaction.csv",
            ("axis_a", "level_a", "axis_b", "level_b", "objective", "mean_z", "n"),
            interaction_table,
        )
        keys = sorted({k for r in rows for k in r})
        with (into / "rows.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=keys, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        print(f"\n  WHERE THE RESULTS ARE: {into}")
        print("    report.txt        this whole report, kept")
        print(f"    survival.csv      {len(survival_table):>6,} rows -- axis, level, rate")
        print(
            f"    correlation.csv   {len(correlation_table):>6,} rows -- rho per (objective, axis)"
        )
        print(f"    binding_off.csv   {len(binding_table):>6,} rows -- which OFF state binds each")
        print(f"    shape.csv         {len(shape_table):>6,} rows -- the non-monotonic check")
        print(f"    pair_level.csv    {len(pair_level_table):>6,} rows -- between-cell, pair props")
        print(f"    interaction.csv   {len(interaction_table):>6,} rows -- the two-way tables")
        print(f"    rows.csv          {len(rows):>6,} rows -- one per design, {len(keys)} columns")
        print("    Tidy (long) format: one observation per line, so a plot is a group-by.")
        sys.stdout = tee._stdout
        tee.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
