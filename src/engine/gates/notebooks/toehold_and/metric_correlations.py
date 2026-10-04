"""Every metric against every measured library, Spearman and Pearson, with its window.

    uv run python src/engine/gates/notebooks/toehold_and/metric_correlations.py

``objective_vs_green.py`` ranks the five **objectives**. This ranks the individual
**measurements** they are built from, which is a different and more basic question: before asking
which aggregate is best, ask which raw quantity carries any signal at all.

Every number is read out of ``results/g168.csv``, ``results/g13.csv`` and ``results/vista.csv``,
which ``green_calibration.py`` wrote by folding each published switch through ``FoldEngine``. The
window each metric is taken over is printed beside it, because two metrics over the same span are
comparing statistics while two over different spans are not comparable at all.

**Kim 2019 is absent and that is deliberate.** His four constructs are a null test for a
two-input gate: trigger B moves ``A_M`` by 1e-13, so the AND axis has no variance to correlate
against. ``results/obj_k1_kim.csv`` holds 3,000 of *our* designs scored on his geometry and
carries no measured ON/OFF at all. A correlation over four points would be noise even if the
variance were there.

**Why Pearson is printed next to Spearman.** Measured ON/OFF spans three orders of magnitude, so
Pearson on the raw values is dominated by a handful of high-ON/OFF switches and a metric can look
strong there while ranking badly -- which is exactly the pattern worth seeing rather than hiding.
Read Spearman; read Pearson only to see where the two disagree.
"""

import argparse
import csv
import math
import statistics as st
import sys
from pathlib import Path

NB = Path(__file__).resolve().parent

#: Metric -> (lower_is_better, the window it is taken over, what it is).
#:
#: ``aug`` is the start codon's index in the switch, so every window is stated relative to it.
#: The A0 equivalents are named where one exists -- that is the point of the table, since a
#: metric with no single-input analogue cannot be calibrated here at all.
METRICS: dict[str, tuple[bool, str, str]] = {
    # --- the opening-energy cluster: W_rank, 31 nt, aug-17 .. aug+14 -----------------------
    "dG_open_off": (False, "W_rank, 31 nt", "cost to force W_rank open, OFF state"),
    "dG_open_on": (True, "W_rank, 31 nt", "same, ON state -- our ON cost"),
    "separation": (False, "W_rank, 31 nt", "dG_open_off - dG_open_on -- the SEP analogue"),
    "narrow_sep": (False, "AUG, 3 nt", "the same difference over the start codon alone"),
    "p_open_off": (True, "W_rank, 31 nt", "joint probability all 31 nt open, OFF"),
    "p_open_on": (False, "W_rank, 31 nt", "joint probability all 31 nt open, ON"),
    # --- the accessibility cluster: the arm, 18 nt, aug-6 .. aug+12 ------------------------
    "A_M_off": (True, "arm, 18 nt", "mean per-base unpaired over the arm, OFF"),
    "A_M_on": (False, "arm, 18 nt", "the same, ON -- our A_M(11)"),
    "A_M_gain": (False, "arm, 18 nt", "A_M_on - A_M_off, the DIFFERENCE"),
    "A_M_ratio": (False, "arm, 18 nt", "A_M_on / A_M_off, the RATIO -- our f2"),
    "mean_wrank_off": (True, "W_rank, 31 nt", "mean unpaired over W_rank, OFF"),
    "mean_wrank_on": (False, "W_rank, 31 nt", "the same, ON"),
    "mean_wrank_gain": (False, "W_rank, 31 nt", "the difference"),
    "aug_off": (True, "AUG, 3 nt", "AUG unpaired probability, OFF"),
    "aug_on": (False, "AUG, 3 nt", "the same, ON -- our aug_11"),
    "aug_gain": (False, "AUG, 3 nt", "the difference"),
    # --- the RBS-to-linker cluster: rbs-3 .. aug+33 ----------------------------------------
    "dG_rbs_linker": (False, "RBS loop..linker", "Green's own predictor: MFE of the stretch"),
    "ied_rbs_linker_off": (True, "RBS loop..linker", "VISTA's IED over the same span, OFF"),
    "ied_rbs_linker_on": (True, "RBS loop..linker", "the same, ON"),
    "ied_rbs_linker_gain": (True, "RBS loop..linker", "the difference"),
    # --- the toehold cluster: the first L nt -----------------------------------------------
    "k_analogue12": (False, "toehold, first 12 nt", "mean unpaired over the toehold, OFF"),
    "k_analogue15": (False, "toehold, first 15 nt", "the same, 15 nt"),
    "k_analogue18": (False, "toehold, first 18 nt", "the same, 18 nt"),
    "ied_toehold12_off": (True, "toehold, first 12 nt", "1 - the above"),
    # --- whole-switch ----------------------------------------------------------------------
    "dG_OFF": (True, "whole switch", "the closed switch's own MFE"),
    "d_OFF": (True, "whole switch", "ensemble defect vs its own MFE, length-normalised"),
}


#: Repairs for the A_M ratio, tested here because the ratio's denominator is what makes it
#: extreme: on our own gating population the worst-OFF A_M reaches 0.001, and designs with a
#: deliberately closed AUG bulge are 4.7% of the population but 89 of the top 100 by ratio --
#: while having a LOWER median A_M(11). So the ratio can reward a design for a shut OFF state
#: even as its ON state gets worse, and these ask whether Green's data sees that too.
def repairs(row: dict[str, float | None]) -> dict[str, float | None]:
    on, off = row.get("A_M_on"), row.get("A_M_off")
    if on is None or off is None:
        return {}
    out: dict[str, float | None] = {}
    for floor in (0.01, 0.05, 0.10):
        out[f"A_M_ratio_floor{floor:g}"] = on / max(off, floor)
    out["A_M_ratio_log"] = math.log10(on / off) if on > 0 and off > 0 else None
    # The ratio capped at the point where it stops discriminating rather than floored.
    out["A_M_ratio_cap20"] = min(on / off, 20.0) if off > 0 else None
    return out


REPAIR_META = {
    "A_M_ratio_floor0.01": (False, "arm, 18 nt", "A_M_on / max(A_M_off, 0.01)"),
    "A_M_ratio_floor0.05": (False, "arm, 18 nt", "A_M_on / max(A_M_off, 0.05)"),
    "A_M_ratio_floor0.1": (False, "arm, 18 nt", "A_M_on / max(A_M_off, 0.10)"),
    "A_M_ratio_log": (False, "arm, 18 nt", "log10 of the ratio -- rank-identical, for scale"),
    "A_M_ratio_cap20": (False, "arm, 18 nt", "the ratio capped at 20x"),
}


def _num(value: str | None) -> float | None:
    """A blank cell is ``None``, never ``0.0`` -- zero is a real value for most of these."""
    if value is None or value == "":
        return None
    try:
        result = float(value)
    except ValueError:
        return None
    return None if math.isnan(result) or math.isinf(result) else result


def ranks(values: list[float]) -> list[float]:
    """Average ranks, so ties do not fabricate an ordering."""
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


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3:
        return None
    mx, my = st.fmean(xs), st.fmean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    den = math.sqrt(sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys))
    return num / den if den else None


def spearman(xs: list[float], ys: list[float]) -> float | None:
    return pearson(ranks(xs), ranks(ys))


def load(path: Path, measured: str = "on_off") -> list[dict[str, float | None]]:
    rows = []
    for raw in csv.DictReader(path.open(encoding="utf-8", newline="")):
        row = {key: _num(value) for key, value in raw.items()}
        if row.get(measured) is None:
            continue
        row.update(repairs(row))
        rows.append(row)
    return rows


def correlate(rows: list[dict], key: str, lower: bool, measured: str = "on_off"):
    """Signed Spearman and Pearson, plus the leave-one-out range of the Spearman."""
    pairs = [
        (r[key], r[measured])
        for r in rows
        if r.get(key) is not None and r.get(measured) is not None
    ]
    if len(pairs) < 4:
        return None
    sign = -1.0 if lower else 1.0
    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]
    rho, lin = spearman(xs, ys), pearson(xs, ys)
    if rho is None:
        return None
    loo = []
    for index in range(len(pairs)):
        kept_x = xs[:index] + xs[index + 1 :]
        kept_y = ys[:index] + ys[index + 1 :]
        one = spearman(kept_x, kept_y)
        if one is not None:
            loo.append(sign * one)
    return {
        "n": len(pairs),
        "rho": sign * rho,
        "pearson": sign * lin if lin is not None else None,
        "loo_low": min(loo) if loo else None,
        "loo_high": max(loo) if loo else None,
        "spread": (min(xs), max(xs)),
        "sd": st.pstdev(xs) if len(xs) > 1 else 0.0,
    }


LIBRARIES = (
    ("G168", "g168.csv", "Green 2014 Table S1, 168 measured switches", "on_off"),
    ("G13", "g13.csv", "Green 2014 Table S3, 13 forward-engineered", "on_off"),
    ("VISTA", "vista.csv", "Robson/Green 2026 Table 4, 189 switches", "on_off"),
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default="", help="write the table to results/<name>.csv")
    args = parser.parse_args(argv)

    loaded = {}
    for label, filename, note, measured in LIBRARIES:
        path = NB / "results" / filename
        if not path.exists():
            print(f"  {label}: {filename} missing, skipped")
            continue
        loaded[label] = (load(path, measured), note, measured)
        print(f"  {label}: {len(loaded[label][0]):3d} switches -- {note}")

    every = {**METRICS, **REPAIR_META}
    print(
        "\n  Signed Spearman: POSITIVE means the metric points the right way, after applying its\n"
        "  own direction. Pearson in brackets. An empty cell means the column is absent or had\n"
        "  fewer than four usable values -- never a zero.\n"
    )
    header = f"  {'metric':24s}{'window':22s}"
    for label in loaded:
        header += f"{label:>20s}"
    print(header)
    print("  " + "-" * (46 + 20 * len(loaded)))

    table = []
    for key, (lower, window, what) in every.items():
        cells = {}
        for label, (rows, _note, measured) in loaded.items():
            cells[label] = correlate(rows, key, lower, measured)
        if not any(cells.values()):
            continue
        line = f"  {key:24s}{window:22s}"
        for label in loaded:
            cell = cells[label]
            line += (
                f"{cell['rho']:+7.3f} [{cell['pearson']:+6.3f}]"
                if cell and cell["pearson"] is not None
                else f"{'--':>20s}"
            )
        order = cells.get("G168") or next((c for c in cells.values() if c), None)
        table.append((order["rho"] if order else -9, line, key, what, cells))
    for _, line, _key, _what, _cells in sorted(table, reverse=True):
        print(line)

    print("\n  What each one is:")
    for _, _line, key, what, _cells in sorted(table, reverse=True):
        print(f"    {key:24s}{what}")

    # Where Spearman and Pearson disagree most -- the question that prompted this table.
    print(
        "\n  Where Pearson and Spearman disagree on G168 (|Pearson| - |Spearman|, largest first).\n"
        "  A large positive gap is a metric that tracks the few highest-ON/OFF switches while\n"
        "  ranking the rest badly, which is what makes Pearson the wrong read here:"
    )
    gaps = []
    for _, _line, key, _what, cells in table:
        cell = cells.get("G168")
        if cell and cell["pearson"] is not None:
            gaps.append((abs(cell["pearson"]) - abs(cell["rho"]), key, cell))
    for gap, key, cell in sorted(gaps, reverse=True)[:8]:
        print(f"    {key:24s}gap {gap:+.3f}   rho {cell['rho']:+.3f}  r {cell['pearson']:+.3f}")

    # The SEP collapse, stated as a measurement rather than as a memory.
    print(
        "\n  The subtraction collapse. Each OFF/ON pair is a strong single-state metric; their\n"
        "  difference is weaker than both, on every library that has them:"
    )
    for off_key, on_key, diff_key in (
        ("dG_open_off", "dG_open_on", "separation"),
        ("A_M_off", "A_M_on", "A_M_gain"),
        ("mean_wrank_off", "mean_wrank_on", "mean_wrank_gain"),
        ("aug_off", "aug_on", "aug_gain"),
    ):
        parts = []
        for label, (rows, _n, measured) in loaded.items():
            trio = [correlate(rows, k, every[k][0], measured) for k in (off_key, on_key, diff_key)]
            if all(trio):
                parts.append(
                    f"{label} off {trio[0]['rho']:+.3f} on {trio[1]['rho']:+.3f} "
                    f"diff {trio[2]['rho']:+.3f}"
                )
        if parts:
            print(f"    {diff_key:22s}" + " | ".join(parts))

    if args.out:
        path = NB / "results" / f"{args.out}.csv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            names = ["metric", "window", "what"]
            for label in loaded:
                names += [f"{label}_n", f"{label}_rho", f"{label}_pearson"]
            writer = csv.DictWriter(handle, fieldnames=names)
            writer.writeheader()
            for _, _line, key, what, cells in sorted(table, reverse=True):
                out = {"metric": key, "window": every[key][1], "what": what}
                for label in loaded:
                    cell = cells.get(label)
                    out[f"{label}_n"] = cell["n"] if cell else None
                    out[f"{label}_rho"] = round(cell["rho"], 4) if cell else None
                    out[f"{label}_pearson"] = (
                        round(cell["pearson"], 4) if cell and cell["pearson"] is not None else None
                    )
                writer.writerow(out)
        print(f"\n  wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
