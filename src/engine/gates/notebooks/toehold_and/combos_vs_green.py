"""Which combinations of terms predict a measured switch, across all three libraries?

    uv run python src/engine/gates/notebooks/toehold_and/combos_vs_green.py

**The question.** ``f5`` exists because the Barrier was found to ADD to a base term rather than rank
well alone -- it scores +0.179 against Green's 168 by itself, which is weak, but it improved the
aggregate. That made it the one term we deliberately combine, and nothing had asked whether it is
the only term with that property, or whether its lift survives on the other two libraries.

**Three libraries, because they disagree.** Green's 168 is the first generation, his 13 the
forward-engineered second, VISTA's 189 a different group's. Measured before: **no metric holds its
sign across all three** -- ``A_M_ratio`` runs +0.306 on the 168 and -0.016 on VISTA -- and on VISTA
every objective came out negative with no explanation found. So a metric that works on one library
has not been shown to work, and a VISTA result reads as "this behaves differently here" rather than
as a verdict.

**Sampling noise is the first thing to read, not the rank order.** It is roughly ``1/sqrt(n)``:
**0.08** on the 168, **0.07** on VISTA's 189, and **0.28** on the 13. On the second generation that
is larger than almost every correlation in the table, so there almost nothing is distinguishable
from anything else -- and saying so is more useful than a ranking that implies otherwise.

**How a combination is scored, and that there are no weights.** Each term becomes a PERCENTILE
inside its library, with its own direction applied, and the combination is the mean of the
percentiles -- the same construction ``f4`` and ``f5`` use. Percentiles because the terms are in
different units, and a mean of raw values would rank by whichever has the widest range. Every term
counts equally: there are 13 to 189 switches per library and fitting a weight to them is fitting a
weight to the test set.
"""

import argparse
import csv
import itertools
import statistics as st
import sys
from pathlib import Path

NB = Path(__file__).resolve().parent
sys.path.insert(0, str(NB.parents[4] / "src"))
sys.path.insert(0, str(NB))

from metric_correlations import spearman  # noqa: E402

#: Each term and the sign that makes "higher percentile" mean "better".
#:
#: All of these are columns the calibration files already hold, so nothing here is recomputed and no
#: sequence is folded -- a disagreement between libraries cannot come from two definitions of one
#: quantity. ``aug_z_*`` needs folding and lives in ``window_vs_green.py``; it is reported there on
#: the 168 and is not in this table.
TERMS: dict[str, bool] = {
    # The two-state analogue of AND-ness: the ON state costs less to open than the OFF state.
    "f1": False,
    "A_M_ratio": True,
    "A_M_gain": True,
    # The ON-state opening energy on its own -- "how cheap is the productive state".
    "access": False,
    # Green's strongest single category, in VISTA's statistic, in each state and as a separation.
    # `ied_gain` is off - on, so higher is better, exactly like A_M_gain.
    "ied_on": False,
    "ied_off": False,
    "ied_gain": True,
}

#: Library file -> the column holding the measured ON/OFF.
LIBRARIES: tuple[tuple[str, str], ...] = (
    ("g168", "on_off"),
    ("g13", "on_off"),
    ("vista", "on_off"),
)

#: How a term is read out of a calibration row. A tuple means "first minus second".
SOURCE: dict[str, object] = {
    "f1": ("dG_open_on", "dG_open_off"),
    "A_M_ratio": "A_M_ratio",
    "A_M_gain": "A_M_gain",
    "access": "dG_open_on",
    "ied_on": "ied_rbs_linker_on",
    "ied_off": "ied_rbs_linker_off",
    "ied_gain": "ied_rbs_linker_gain",
}


def noise_for(n: int) -> float:
    """Sampling noise on a Spearman rho over ``n`` switches, as ``1/sqrt(n)``."""
    return 1.0 / (n**0.5) if n else 1.0


def percentiles(values: list[float], higher_is_better: bool) -> list[float]:
    """Each value's percentile inside this set, 100 = best."""
    order = sorted(values)
    out = []
    for value in values:
        below = sum(1 for other in order if other < value)
        pct = 100.0 * below / max(len(order) - 1, 1)
        out.append(pct if higher_is_better else 100.0 - pct)
    return out


def read_library(path: Path, on_off_column: str) -> list[dict]:
    """One row per switch carrying every term, dropping any switch missing one of them."""
    rows = []
    for row in csv.DictReader(path.open(encoding="utf-8")):

        def number(key, row=row):
            raw = row.get(key)
            try:
                return float(raw)
            except (TypeError, ValueError):
                return None

        measured = number(on_off_column)
        if measured is None or measured <= 0:
            continue
        record = {"on_off": measured}
        for name, source in SOURCE.items():
            if isinstance(source, tuple):
                first, second = number(source[0]), number(source[1])
                record[name] = None if first is None or second is None else first - second
            else:
                record[name] = number(source)
        # Every term or none: a combination averaged over a different subset per term is not a
        # combination, and dropping the row is the only honest way to keep the set identical.
        if any(record[name] is None for name in TERMS):
            continue
        rows.append(record)
    return rows


def report(label: str, rows: list[dict]) -> dict[str, float]:
    noise = noise_for(len(rows))
    print(f"\n{'=' * 78}\n  {label}: {len(rows)} switches, sampling noise ~{noise:.2f}\n{'=' * 78}")
    if len(rows) < 8:
        print("  too few switches for a rank order to mean anything; printed for completeness only")
    on_off = [r["on_off"] for r in rows]
    pct = {name: percentiles([r[name] for r in rows], higher) for name, higher in TERMS.items()}
    alone = {name: spearman(pct[name], on_off) for name in TERMS}

    print("\n  each term alone:\n")
    for name, rho in sorted(alone.items(), key=lambda kv: -kv[1]):
        print(f"    {name:12s}{rho:+.4f}")

    print(f"\n  pairs whose lift over their better member clears the noise ({noise:.2f}):\n")
    lifts = []
    for a, b in itertools.combinations(TERMS, 2):
        mean = [st.fmean([x, y]) for x, y in zip(pct[a], pct[b], strict=True)]
        rho = spearman(mean, on_off)
        best = max(alone[a], alone[b])
        lifts.append((rho - best, rho, best, f"{a} + {b}"))
    shown = [t for t in sorted(lifts, reverse=True) if t[0] >= noise]
    if not shown:
        print("    none -- no pair adds anything distinguishable from noise on this library")
    for lift, rho, best, name in shown:
        print(f"    {name:26s}{rho:+.4f}   best member {best:+.4f}   lift {lift:+.4f}")

    print("\n  the five strongest combinations regardless of lift:\n")
    for _lift, rho, best, name in sorted(lifts, key=lambda t: -t[1])[:5]:
        print(f"    {name:26s}{rho:+.4f}   best member {best:+.4f}")
    return alone


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--results", default="results")
    args = parser.parse_args(argv)
    results = NB / args.results

    per_library: dict[str, dict[str, float]] = {}
    for name, column in LIBRARIES:
        path = results / f"{name}.csv"
        if not path.exists():
            print(f"  no {path.name}, skipping")
            continue
        rows = read_library(path, column)
        if not rows:
            print(f"  {name}: no switch carried every term")
            continue
        per_library[name] = report(name, rows)

    if len(per_library) < 2:
        return 0
    print(f"\n{'=' * 78}\n  does any term hold its sign across the libraries?\n{'=' * 78}\n")
    names = list(per_library)
    print(f"    {'term':12s}" + "".join(f"{n:>10s}" for n in names) + "   verdict")
    for term in TERMS:
        values = [per_library[n].get(term) for n in names]
        cells = "".join(f"{v:>+10.3f}" if v is not None else f"{'n/a':>10s}" for v in values)
        got = [v for v in values if v is not None]
        if not got:
            verdict = "never scored"
        elif all(v > 0 for v in got):
            verdict = "positive everywhere"
        elif all(v < 0 for v in got):
            verdict = "negative everywhere"
        else:
            verdict = "FLIPS SIGN"
        print(f"    {term:12s}{cells}   {verdict}")
    print("\n  A term that flips sign has not been shown to measure anything -- it has been shown")
    print("  to measure something that differs between libraries, which is not the same claim.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
