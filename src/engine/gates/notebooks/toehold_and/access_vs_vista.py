"""Do Green 2014's local single-strandedness and VISTA's flanked MFE pick the same trigger pairs?

    uv run python src/engine/gates/notebooks/toehold_and/access_vs_vista.py

Two different accessibility measures are already computed for every trigger window, and the panel
uses one of them without the other ever having been compared to it:

    l_green     mean per-base unpaired probability over the binding site, read from the pair matrix
                of the WHOLE 711-nt transcript. Green 2014 S14.3, his equation (4), over a 30- or
                36-nt site. HIGHER is better.
    mfe_wL      MFE of the site plus L nt of flank on each side, folded as an isolated slice.
                VISTA 2026's form, at L = 0, 10, 25, 50, 100. LESS NEGATIVE is better -- a stiffer
                local structure is a site the trigger has to open.

**Why this matters beyond tidiness.** VISTA reports that only the SHORT flanks (±10 and ±25) gave
statistically significant differences between truncated and full-length triggers. Our ``access``
term folds the entire transcript, which is the widest context available and the opposite end of
that scale. If the two measures disagree about which pairs are reachable, the panel is selecting on
a quantity one published library says is the wrong one.

This is a pure join and comparison -- nothing is folded here. Both columns were written by
``trigger_accessibility.py``.
"""

import argparse
import csv
import statistics as st
import sys
from pathlib import Path

NB = Path(__file__).resolve().parent
sys.path.insert(0, str(NB.parents[4] / "src"))
sys.path.insert(0, str(NB))

import objective_panel as op  # noqa: E402

#: Flank sizes `trigger_accessibility.py` wrote.
FLANKS = (0, 10, 25, 50, 100)

#: The accessibility measures being compared, as column names on a pair.
MEASURES = ("l_green", "mfe_w0", "mfe_w10", "mfe_w25", "mfe_w50", "mfe_w100")

#: Everything the panel scores: (label, pair column, lower_is_better).
#:
#: "Best in pair" is the best value any design in either geometry reaches, because that is what the
#: panel actually takes -- a pair is used for its best design, never its median one. Correlating a
#: pair-level quantity against a pair's MEDIAN design would be asking a question nobody acts on.
METRICS = (
    ("combined", "best_combined", False),
    ("A_M ratio", "best_f2", False),
    ("A_M gain", "best_f2_gain", False),
    ("opening SEP", "best_f1", True),
    ("Barrier", "best_barrier", True),
    ("ON cost open_11", "best_open11", True),
    ("IED rbs-linker", "best_ied", True),
    ("dG rbs-linker", "best_dgrbs", False),
    ("dG arm (ON)", "best_dgarm", True),
    ("A opens stem", "best_engarm", False),
    ("hairpin worst", "best_hairpin", False),
    ("AUG(11) open", "best_aug11", False),
    ("x* lock", "best_lock", False),
    ("B toehold open", "best_r2", False),
    ("designs in the pair", "n_designs", False),
)


def ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [0.0] * len(values)
    index = 0
    while index < len(order):
        stop = index
        while stop + 1 < len(order) and values[order[stop + 1]] == values[order[index]]:
            stop += 1
        average = (index + stop) / 2.0 + 1.0
        for position in range(index, stop + 1):
            out[order[position]] = average
        index = stop + 1
    return out


def spearman(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 4:
        return None
    rx, ry = ranks(xs), ranks(ys)
    mx, my = st.fmean(rx), st.fmean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry, strict=True))
    den = sum((a - mx) ** 2 for a in rx) ** 0.5 * sum((b - my) ** 2 for b in ry) ** 0.5
    return num / den if den else None


def window_table(results: Path) -> dict[tuple[int, str], dict]:
    """``(window start, role) -> every accessibility column``, the key the panel already uses.

    The two geometries' windows differ by one nucleotide at the 3' end but start at the same
    place, so keying on the start lets a value computed once serve both -- which is exactly why
    ``add_accessibility`` keys it that way.
    """
    out: dict[tuple[int, str], dict] = {}
    path = results / "accessibility.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            start, role = row.get("start"), (row.get("role") or "").strip()
            if start in (None, "") or role not in ("A", "B"):
                continue
            out[(int(start), role)] = row
    return out


def number(row: dict, key: str) -> float | None:
    value = row.get(key)
    if value in (None, ""):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--per-cell", type=int, default=3)
    args = parser.parse_args(argv)

    results = NB / "results"
    table = window_table(results)
    print(f"  {len(table):,} (window start, role) keys in accessibility.csv\n")

    live = op.population(results)
    rank_rows = op.gating(live)
    by_pair: dict[str, dict[str, list[dict]]] = {}
    for row in rank_rows:
        by_pair.setdefault(row["pair"], {}).setdefault(row["geom"], []).append(row)

    pairs = []
    for pair, geoms in by_pair.items():
        if len(geoms) < 2 or min(len(v) for v in geoms.values()) < args.per_cell:
            continue
        sample = next(iter(next(iter(geoms.values()))))
        a_key = (int(sample["a_start"]), "A")
        b_key = (int(sample["b_start"]), "B")
        if a_key not in table or b_key not in table:
            continue
        entry: dict[str, object] = {"pair": pair, "len_x": int(sample["len_x"])}
        # Both measures reduce the two windows to one number the same way the panel does, by
        # taking the WORSE of A and B -- a pair is only as reachable as its harder window.
        for flank in FLANKS:
            a = number(table[a_key], f"mfe_w{flank}")
            b = number(table[b_key], f"mfe_w{flank}")
            # Less negative is better, so the worse window is the MORE negative one.
            entry[f"mfe_w{flank}"] = None if a is None or b is None else min(a, b)
        a_l, b_l = number(table[a_key], "l_green"), number(table[b_key], "l_green")
        entry["l_green"] = None if a_l is None or b_l is None else min(a_l, b_l)
        flat = [r for cells in geoms.values() for r in cells]
        entry["n_designs"] = len(flat)

        def best_of(column: str, lower: bool, rows=flat):
            values = [r[column] for r in rows if r.get(column) is not None]
            if not values:
                return None
            return min(values) if lower else max(values)

        for column, label, lower in (
            ("f5", "best_combined", False),
            ("f2", "best_f2", False),
            ("f2_gain", "best_f2_gain", False),
            ("f1", "best_f1", True),
            ("barrier", "best_barrier", True),
            ("open_11f", "best_open11", True),
            ("ied_rbs_linker_11", "best_ied", True),
            ("dG_rbs_linker", "best_dgrbs", False),
            ("dG_arm_11", "best_dgarm", True),
            ("engaged_arm_11", "best_engarm", False),
            ("hairpin_worst", "best_hairpin", False),
            ("aug_11", "best_aug11", False),
            ("lock", "best_lock", False),
            ("r2_star_00", "best_r2", False),
        ):
            entry[label] = best_of(column, lower)
        pairs.append(entry)

    print(f"  {len(pairs)} eligible trigger pairs carry both measures\n")
    if len(pairs) < 4:
        print("  too few to compare.")
        return 0

    print("=== 1. do the two measures agree with each other? ===")
    good = [p for p in pairs if p["l_green"] is not None]
    for flank in FLANKS:
        subset = [p for p in good if p[f"mfe_w{flank}"] is not None]
        if len(subset) < 4:
            continue
        rho = spearman([p["l_green"] for p in subset], [p[f"mfe_w{flank}"] for p in subset])
        # Both are "higher is better" after the sign flip above, so a POSITIVE rho means they
        # agree about which pairs are reachable.
        print(
            f"    rho(l_green, mfe_w{flank:<3d}) = {rho:+.3f}   n={len(subset)}"
            + ("   <-- VISTA's significant flanks" if flank in (10, 25) else "")
        )

    print("\n=== 2. does either predict anything we measure? ===")
    print(
        "    Best-in-pair for every metric, against every accessibility measure. Signed so\n"
        "    POSITIVE means 'more reachable pairs carry better designs' -- each metric's own\n"
        "    direction is applied first.\n"
        f"    n = {len(pairs)} pairs. |rho| below about 0.33 is not distinguishable from noise\n"
        "    at p=0.05 here, and this grid is 6 measures x 15 metrics = 90 cells, so a handful\n"
        "    will clear 0.33 by chance alone. Read the table, not its largest entry."
    )
    header = f"    {'metric':20s}" + "".join(f"{k:>10s}" for k in MEASURES)
    print("\n" + header)
    print("    " + "-" * (len(header) - 4))
    for label, key, lower_better in METRICS:
        cells = []
        for measure in MEASURES:
            subset = [p for p in pairs if p.get(measure) is not None and p.get(key) is not None]
            if len(subset) < 4:
                cells.append(f"{'--':>10s}")
                continue
            sign = -1.0 if lower_better else 1.0
            rho = spearman([p[measure] for p in subset], [p[key] for p in subset])
            cells.append(f"{'--':>10s}" if rho is None else f"{sign * rho:+10.3f}")
        print(f"    {label:20s}" + "".join(cells))
    print(
        "\n    Every cell correlates an accessibility measure against OUR OWN scores, not bench\n"
        "    data -- there is no measured ON/OFF for our trigger pairs. So this is internal\n"
        "    consistency, not correctness: a measure could be right about reachability and read\n"
        "    zero here, because reachability and switch quality are different axes."
    )

    print("\n=== 3. which pairs would each measure choose? ===")
    for key in ("l_green", "mfe_w25", "mfe_w10"):
        ordered = sorted((p for p in pairs if p[key] is not None), key=lambda p: -p[key])
        names = [p["pair"] for p in ordered]
        print(f"\n    by {key}, most reachable first:")
        for p in ordered[:6]:
            print(
                f"      {p['pair']:13s} x{p['len_x']}  {key}={p[key]:8.2f}  "
                f"best combined {p['best_combined'] or float('nan'):6.1f}  "
                f"best A_M ratio {p['best_f2'] or float('nan'):8.1f}"
            )
        if key != "l_green":
            base = [
                p["pair"]
                for p in sorted(
                    (q for q in pairs if q["l_green"] is not None), key=lambda q: -q["l_green"]
                )
            ]
            shared = len(set(names[:10]) & set(base[:10]))
            print(f"      top 10 shared with l_green's top 10: {shared} of 10")

    print("\n=== 4. what the current l_green FLOOR removes, by each measure ===")
    floor = op.L_GREEN_FLOOR
    kept = [p for p in pairs if p["l_green"] is not None and p["l_green"] > floor]
    dropped = [p for p in pairs if p["l_green"] is not None and p["l_green"] <= floor]
    print(f"    l_green > {floor}: keeps {len(kept)} pairs, drops {len(dropped)}")
    for label, group in (("kept", kept), ("dropped", dropped)):
        if not group:
            continue
        for flank in (10, 25):
            vals = [p[f"mfe_w{flank}"] for p in group if p[f"mfe_w{flank}"] is not None]
            if vals:
                print(
                    f"      {label:7s} n={len(vals):3d}  mfe_w{flank} median {st.median(vals):7.2f}"
                    f"  min {min(vals):7.2f}  max {max(vals):7.2f}"
                )
    return 0


if __name__ == "__main__":
    sys.exit(main())
