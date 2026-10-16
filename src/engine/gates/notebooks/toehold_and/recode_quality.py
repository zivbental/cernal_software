"""How well does each eligible trigger pair's window actually recode?

    uv run python src/engine/gates/notebooks/toehold_and/recode_quality.py
    uv run python src/engine/gates/notebooks/toehold_and/recode_quality.py --out recode_quality

A pair whose window cannot be recoded into a knockout is a pair whose 01 or 10 state cannot be
built, however well its switches score. That is a wet-lab constraint and it belongs in the pair
choice rather than being discovered by ``order_check`` after the panel is already published --
which is what happened with ``A@625``: its A window breaks only 5 of 11 substitutions, 45%, under
the 50% bar.

The measure is the recoder's own, run on the real window: of the substitutions
``codon_variants.recode_windows`` would make, how many land on a base that no longer pairs with
what the switch presents. ``effective`` is that fraction; ``breaks`` is the count, which matters
separately because 5 of 5 and 15 of 15 are both 100% and only one of them breaks a duplex.
"""

import argparse
import csv
import sys
from pathlib import Path

NB = Path(__file__).resolve().parent
sys.path.insert(0, str(NB.parents[4] / "src"))
sys.path.insert(0, str(NB))

import codon_variants as cv  # noqa: E402
import objective_panel as op  # noqa: E402
from full_sweep import read_fasta  # noqa: E402

from engine import sequences as sq  # noqa: E402

FIELDS = (
    "pair",
    "pair_label",
    "len_x",
    "a_start",
    "a_end",
    "b_start",
    "b_end",
    "a_subs",
    "a_breaks",
    "a_effective",
    "b_subs",
    "b_breaks",
    "b_effective",
    "worst_effective",
    "n_designs",
    "best_combined",
    "best_f2",
    "best_f2_gain",
    "best_engarm",
)


def recode_window(
    transcript: str, lo: int, hi: int, amino: dict, fraction: dict, groups: dict
) -> tuple[int, int]:
    """``(substitutions, substitutions that break a pair)`` for one window.

    Mirrors ``recode_windows``'s per-codon choice -- break the most pairs, then match abundance,
    then shift GC least -- without the homopolymer and untouched-run repair passes, which can
    trade a break away. So this is the ceiling the recoder aims at, and `order_check` measures what
    it achieved; a gap between them is the repair's cost.
    """
    subs = breaks = 0
    for start in cv.codon_starts(lo, hi):
        codon = transcript[start : start + 3]
        acid = amino.get(codon)
        options = [c for c in groups.get(acid, ()) if c != codon] if acid else []
        if not options:
            continue

        def score(option: str, codon: str = codon, start: int = start) -> tuple:
            broken = sum(
                1
                for k in range(3)
                if option[k] != codon[k]
                and lo <= start + k < hi
                and (option[k], sq.reverse_complement(codon[k])) not in cv._PAIRED
            )
            gc_now = sum(1 for c in codon if c in "GC")
            return (
                -broken,
                abs(fraction.get(option, 0.0) - fraction.get(codon, 0.0)),
                abs(sum(1 for c in option if c in "GC") - gc_now),
            )

        best = min(options, key=score)
        for k in range(3):
            if best[k] == codon[k] or not (lo <= start + k < hi):
                continue
            subs += 1
            if (best[k], sq.reverse_complement(codon[k])) not in cv._PAIRED:
                breaks += 1
    return subs, breaks


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--per-cell", type=int, default=3)
    parser.add_argument("--floor", type=float, default=0.5, help="the order_check bar")
    parser.add_argument("--out", default="", help="write to results/<name>.csv")
    args = parser.parse_args(argv)

    results = NB / "results"
    transcript = read_fasta(NB / "mCherry_original.txt")
    amino, fraction = cv.load_codon_table(NB / "data" / "ecoli_codon_usage_table.csv")
    groups = cv.synonyms(amino)

    rank = op.gating(op.population(results))
    by_pair: dict[str, dict[str, list[dict]]] = {}
    for row in rank:
        by_pair.setdefault(row["pair"], {}).setdefault(row["geom"], []).append(row)

    rows = []
    for pair, geoms in by_pair.items():
        if len(geoms) < 2 or min(len(v) for v in geoms.values()) < args.per_cell:
            continue
        flat = [r for cells in geoms.values() for r in cells]
        # The WIDEST window set across both geometries, which is what codon_variants recodes.
        a_lo = min(int(r["a_start"]) for r in flat)
        a_hi = max(int(r["a_end"]) for r in flat)
        b_lo = min(int(r["b_start"]) for r in flat)
        b_hi = max(int(r["b_end"]) for r in flat)
        a_subs, a_breaks = recode_window(transcript, a_lo, a_hi, amino, fraction, groups)
        b_subs, b_breaks = recode_window(transcript, b_lo, b_hi, amino, fraction, groups)

        def best_of(column: str, lower: bool = False, source=flat):
            values = [r[column] for r in source if r.get(column) is not None]
            if not values:
                return None
            return min(values) if lower else max(values)

        a_eff = a_breaks / a_subs if a_subs else 0.0
        b_eff = b_breaks / b_subs if b_subs else 0.0
        rows.append(
            {
                "pair": pair,
                "pair_label": flat[0]["pair_label"],
                "len_x": int(flat[0]["len_x"]),
                "a_start": a_lo,
                "a_end": a_hi,
                "b_start": b_lo,
                "b_end": b_hi,
                "a_subs": a_subs,
                "a_breaks": a_breaks,
                "a_effective": round(a_eff, 4),
                "b_subs": b_subs,
                "b_breaks": b_breaks,
                "b_effective": round(b_eff, 4),
                "worst_effective": round(min(a_eff, b_eff), 4),
                "n_designs": len(flat),
                "best_combined": best_of("f5"),
                "best_f2": best_of("f2"),
                "best_f2_gain": best_of("f2_gain"),
                "best_engarm": best_of("engaged_arm_11"),
            }
        )

    rows.sort(key=lambda r: (-r["worst_effective"], -(r["best_combined"] or 0)))
    print(f"  {len(rows)} eligible pairs, worst-window recoding effectiveness first")
    print(
        f"  the order_check bar is {args.floor:.0%} on EACH window\n\n"
        f"  {'pair':14s}{'x':>2s}{'A subs':>7s}{'A brk':>6s}{'A eff':>7s}"
        f"{'B subs':>7s}{'B brk':>6s}{'B eff':>7s}{'worst':>7s}"
        f"{'comb':>7s}{'A_M':>8s}{'gain':>7s}{'arm':>6s}"
    )
    passing = 0
    for row in rows:
        ok = min(row["a_effective"], row["b_effective"]) >= args.floor
        passing += ok
        print(
            f"  {row['pair']:14s}{row['len_x']:2d}{row['a_subs']:7d}{row['a_breaks']:6d}"
            f"{row['a_effective']:7.2f}{row['b_subs']:7d}{row['b_breaks']:6d}"
            f"{row['b_effective']:7.2f}{row['worst_effective']:7.2f}"
            f"{row['best_combined'] or 0:7.1f}{row['best_f2'] or 0:8.1f}"
            f"{row['best_f2_gain'] or 0:7.3f}{row['best_engarm'] or 0:6.2f}"
            + ("" if ok else "   <-- below the bar")
        )
    print(f"\n  pairs clearing {args.floor:.0%} on both windows: {passing} of {len(rows)}")

    if args.out:
        path = results / f"{args.out}.csv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(FIELDS), extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        print(f"  wrote {path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
