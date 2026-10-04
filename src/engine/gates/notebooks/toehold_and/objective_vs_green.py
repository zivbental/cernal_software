"""Rank the five objective functions against every measured toehold library we have.

    uv run python src/engine/gates/notebooks/toehold_and/objective_vs_green.py
    # the 13 forward-engineered switches (Green Table S3)
    ... --g168 results/g13.csv --table-s1 "<...>/Table S3. ....xlsx" --label "G13"
    # the VISTA library (Robson/Green 2026 Supplementary Table 4)
    ... --g168 results/vista.csv --csv "<...>/Supplementary_Table4.csv" --label "VISTA"
    # and the matched-band comparison that asks whether two libraries disagree for a reason
    ... --band results/vista_objectives.csv

**The question this answers.** Four objectives were competing for three panel slots, and the
argument for each was theoretical. Green 2014 measured ON/OFF for 168 switches, so the argument
is decidable: compute every objective on his switches and correlate with what the bench saw.

**The result.** Spearman against measured ON/OFF, signed so that **positive means the objective
points the right way**, with the leave-one-out range beside it:

    f5   pct(f2, Barrier, access)   +0.366   [+0.355, +0.384]
    f2   A_M ratio                  +0.306   [+0.294, +0.323]
    f4   pct(f1, Barrier, access)   +0.213   [+0.200, +0.231]
    Barrier                         +0.179   [+0.165, +0.195]
    f1   open-energy difference      -0.107   [-0.125, -0.093]

No leave-one-out range straddles zero, so the ordering is not one influential switch.

Three consequences, all acted on in ``objective_panel.py``:

* **f1's sign is wrong.** On Green's data a larger open-energy difference goes with a *worse*
  measured ON/OFF. f1 is therefore demoted from a ranking arm to the gating floor (``GATING``):
  the measurement says f1 ranks badly *among designs that already gate*, not that AND-ness is
  meaningless, and the floor is the job it survives.
* **f5 replaces f4.** Same three-term percentile aggregate with f2 where f1 stood, and it is the
  best of the five. f4 is not worthless at +0.213, but it is the same construction carrying the
  one term that points backwards, and keeping both would be keeping a known-worse copy.
* **The barrier earns its slot.** f2 alone is +0.306 and f2 with the barrier and access is
  +0.366, so the barrier is not redundant with f2; it lifts it.

**A correction worth keeping.** An earlier, ad-hoc version of this measurement built f4 and f5
from **two** terms instead of three -- it dropped ``access`` -- and reported f5 at +0.345 and f4
at **+0.074**, which supported a much stronger claim ("f4 is nothing") than the data does. The
third term is not a rounding detail: it moves f4 by +0.139 and reorders it above the barrier.
That is why this measurement lives in a script with the aggregate built the way the panel builds
it, rather than in a one-off.

**All three libraries, same five objectives.**

    objective   G168 (n=168)   G13 (n=13)   VISTA (n=189)
    f5             +0.366        +0.591        -0.097
    f2             +0.306        +0.698        -0.016
    f4             +0.213        +0.526        -0.144
    Barrier        +0.179        +0.280        -0.130
    f1             -0.107        -0.033        -0.070

Green's two libraries **agree on everything that matters**: f1 at or below zero, f2 and f5 on
top, the barrier weakest of the positive ones. They **disagree on f2 against f5** -- f5 wins on
the 168, f2 wins on the 13 -- so the data cannot separate those two, which is the measured reason
both stay in the panel rather than one being dropped. Two caveats: n=13 gives f1 a leave-one-out
range of [-0.315, +0.147] that straddles zero, and the two libraries are **not independent**
(same lab, same design rules, same reporter), so their agreement is weaker than two datasets
sounds.

**VISTA cannot arbitrate, and not for the reason we assumed.** All five objectives are at or
below zero there. Two mechanistic explanations were tested and **both failed**:

1. *The OFF state is not really shut.* It is: ``dG_open_off`` is distributed almost identically
   in the two libraries -- median 17.76 against Green's 17.77, mean 17.71 against 17.69. Every
   VISTA switch costs at least 10.4 kcal/mol to open with no trigger.
2. *VISTA's toeholds are occluded, so no trigger can nucleate.* They are twice as occluded --
   toehold-18 ensemble defect median **0.568** against Green's 0.303 and the 13's 0.245 -- but
   **matching on it does not rescue the correlation**. In the band both libraries occupy
   (0.229-0.601) f5 is +0.347 on Green's switches and -0.081 on VISTA's; in the tightest
   sub-band, 0.23-0.40, it is **+0.484 against -0.509** on switches with the same toehold
   accessibility (VISTA n=11 there, so read that pair as a direction and not a magnitude).

So VISTA's ON/OFF is driven by something none of these five objectives models, and we do not
know what. Until that is identified, VISTA is a **warning about generalisation**, not a vote.
See ``docs`` and the memory note on metrics not holding their sign across datasets.

**Green's endogenous sensors are not a dataset at all.** Tables S4 and S5 carry sensor sequences,
target subsequences and plasmid names -- there is **no measured ratio column**, so there is
nothing to correlate against. The Figure 4 numbers are in the figures only.

**What this is not.** Green's switches are **single-input**, so AND-ness does not exist there.
f1 is evaluated as its two-state analogue ``dG_open(ON) - dG_open(OFF)`` and f2 as the A_M ratio
between the two states -- the same quantities one trigger short. A fair analogue is not the same
function, which is why f1 keeps a floor rather than being deleted outright.

The barrier is computed here for the first time on Green's switches: fold the switch, unpair the
AUG neighbourhood in the target structure, and take ``find_saddle`` between the two.
"""

from __future__ import annotations

import argparse
import csv
import statistics as st
from pathlib import Path

from engine.gates.tools.folding import FoldEngine

#: How far either side of the AUG to open in the target structure. The barrier is the cost of
#: clearing the start codon's neighbourhood, so the target is "this window unpaired" and the
#: partners of those bases are released too -- a half-open pair is not a structure.
AUG_BEFORE = 6
AUG_AFTER = 12


def pairs_of(structure: str) -> dict[int, int]:
    """Index -> partner index, for a dot-bracket string."""
    stack: list[int] = []
    out: dict[int, int] = {}
    for index, char in enumerate(structure):
        if char == "(":
            stack.append(index)
        elif char == ")":
            opened = stack.pop()
            out[index] = opened
            out[opened] = index
    return out


def aug_open_target(structure: str, aug: int) -> str:
    """``structure`` with the AUG neighbourhood, and whatever it pairs with, set unpaired."""
    target = list(structure)
    partners = pairs_of(structure)
    for index in range(max(0, aug - AUG_BEFORE), min(aug + AUG_AFTER, len(target))):
        if index in partners:
            target[partners[index]] = "."
        target[index] = "."
    return "".join(target)


def ranks(values: list[float]) -> list[float]:
    """Average ranks, so ties do not fabricate an ordering."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [0.0] * len(values)
    start = 0
    while start < len(order):
        stop = start
        while stop + 1 < len(order) and values[order[stop + 1]] == values[order[start]]:
            stop += 1
        for position in range(start, stop + 1):
            out[order[position]] = (start + stop) / 2 + 1
        start = stop + 1
    return out


def pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 3:
        return None
    mx, my = st.fmean(xs), st.fmean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    den = (sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys)) ** 0.5
    return None if den == 0 else num / den


def spearman(xs: list[float], ys: list[float]) -> float | None:
    return pearson(ranks(xs), ranks(ys))


def percentiles(values: list[float], lower_is_better: bool) -> list[float]:
    """Percentile inside this population, 100 = best -- the same construction the panel uses."""
    ordered = sorted(values)
    n = len(ordered)
    out = []
    for value in values:
        below = 100.0 * sum(1 for v in ordered if v < value) / n
        out.append(100.0 - below if lower_is_better else below)
    return out


def measure(
    g168: Path, switches: dict[str, str], folder: FoldEngine, verbose: bool = True
) -> list[dict]:
    """One row per switch with all five objectives and the measured ON/OFF."""
    rows = list(csv.DictReader(g168.open(encoding="utf-8")))
    out = []
    for index, row in enumerate(rows):
        sequence = switches.get(str(row["switch_number"]))
        if not sequence:
            continue

        def number(key: str, row: dict = row) -> float | None:
            raw = row.get(key)
            return float(raw) if raw not in (None, "") else None

        on_off = number("on_off")
        open_on, open_off = number("dG_open_on"), number("dG_open_off")
        ratio = number("A_M_ratio")
        if on_off is None or on_off <= 0 or open_on is None or open_off is None or ratio is None:
            continue
        folded = folder.mfe(sequence)
        barrier = folder.saddle(
            sequence, folded.structure, aug_open_target(folded.structure, int(row["aug_index"]))
        )
        if barrier is None:
            continue
        # Carried, not computed: the OFF-state toehold defect comes from green_calibration, so
        # the matched-band comparison cannot silently use a second definition of the same span.
        toehold = row.get("ied_toehold18_off")
        out.append(
            {
                "switch_number": row["switch_number"],
                "on_off": on_off,
                "toehold_defect": float(toehold) if toehold not in (None, "") else None,
                # The two-state analogue of AND-ness: the ON state costs less to open than the
                # OFF state. Lower is better, exactly as f1 is lower-is-better.
                "f1": open_on - open_off,
                "f2": ratio,
                "barrier": barrier,
                # Accessibility's analogue is the ON-state opening energy itself: the third term
                # of the aggregate asks how cheap the productive state is on its own.
                "access": open_on,
            }
        )
        if verbose and index % 50 == 0:
            print(f"    {index + 1}/{len(rows)}", flush=True)

    for row, pct_f1, pct_f2, pct_bar, pct_acc in zip(
        out,
        percentiles([r["f1"] for r in out], True),
        percentiles([r["f2"] for r in out], False),
        percentiles([r["barrier"] for r in out], True),
        percentiles([r["access"] for r in out], True),
        strict=True,
    ):
        row["f4"] = st.fmean([pct_f1, pct_bar, pct_acc])
        row["f5"] = st.fmean([pct_f2, pct_bar, pct_acc])
    return out


#: name -> (key, lower_is_better, label). ``lower_is_better`` flips the correlation's sign so
#: that a positive number always means "this objective points the right way", which is the only
#: form in which five objectives with three different directions can be compared at a glance.
OBJECTIVES = (
    ("f5", "f5", False, "pct(f2, Barrier, access)"),
    ("f2", "f2", False, "A_M ratio"),
    ("Barrier", "barrier", True, "find_saddle, kcal/mol"),
    ("f4", "f4", False, "pct(f1, Barrier, access)"),
    ("f1", "f1", True, "open-energy difference"),
)


def report(rows: list[dict], label: str = "Green's measured switches") -> None:
    print(f"\n  {label}, n = {len(rows)}")
    print("  Spearman with measured ON/OFF, signed so POSITIVE = the objective is right\n")
    print(f"  {'objective':10s}{'what it is':26s}{'rho':>8s}{'Pearson':>9s}   leave-one-out")
    scored = []
    for name, key, lower, label in OBJECTIVES:
        sign = -1.0 if lower else 1.0
        values = [r[key] for r in rows]
        measured = [r["on_off"] for r in rows]
        rho = spearman(values, measured)
        lin = pearson(values, measured)
        loo = []
        for index in range(len(rows)):
            kept = rows[:index] + rows[index + 1 :]
            single = spearman([r[key] for r in kept], [r["on_off"] for r in kept])
            if single is not None:
                loo.append(sign * single)
        scored.append((sign * rho, name, label, sign * lin, min(loo), max(loo)))
    for rho, name, label, lin, low, high in sorted(scored, reverse=True):
        print(f"  {name:10s}{label:26s}{rho:+8.3f}{lin:+9.3f}   [{low:+.3f}, {high:+.3f}]")
    print(
        "\n  Pearson is printed only for comparability: ON/OFF spans three orders of magnitude,\n"
        "  so the rank correlation is the one to read."
    )


#: The band both Green's 168 and the VISTA library occupy on the OFF-state toehold defect. Below
#: 0.229 only Green's switches exist; above 0.601 only VISTA's.
MATCHED_BAND = (0.229, 0.601)


def compare(mine: list[dict], other: list[dict], other_label: str) -> None:
    """Correlate both libraries inside the toehold-accessibility band they share.

    Two libraries can disagree because they are different experiments or because they occupy
    different regions of the same axis. This distinguishes the two: if the disagreement survives
    matching, the axis is not the reason.
    """
    lo, hi = MATCHED_BAND

    def band(rows: list[dict]) -> list[dict]:
        return [
            r
            for r in rows
            if r.get("toehold_defect") is not None and lo <= r["toehold_defect"] <= hi
        ]

    mine_band, other_band = band(mine), band(other)
    if len(mine_band) < 8 or len(other_band) < 8:
        print(f"\n  too few switches in the band {lo}-{hi} to compare")
        return
    print(f"\n  MATCHED BAND -- OFF-state toehold defect {lo}-{hi}, the range both libraries share")
    print(f"    this library  {len(mine_band):4d} of {len(mine):4d}")
    print(f"    {other_label:13s} {len(other_band):4d} of {len(other):4d}\n")
    print(
        f"  {'objective':10s}{'this, band':>12s}{'this, all':>11s}"
        f"{other_label + ', band':>20s}{other_label + ', all':>19s}"
    )
    for name, key, lower, _label in OBJECTIVES:
        sign = -1.0 if lower else 1.0

        def cell(rows: list[dict], key: str = key, sign: float = sign) -> str:
            rho = spearman([r[key] for r in rows], [r["on_off"] for r in rows])
            return f"{sign * rho:+.3f}" if rho is not None else "n/a"

        print(
            f"  {name:10s}{cell(mine_band):>12s}{cell(mine):>11s}"
            f"{cell(other_band):>20s}{cell(other):>19s}"
        )
    print(
        "\n  A sign that survives matching is not explained by the axis matched on. Measured:\n"
        "  f5 is +0.347 on Green's switches and -0.081 on VISTA's inside this band, so toehold\n"
        "  occlusion does NOT explain why VISTA inverts."
    )


def main(argv=None) -> int:
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--g168",
        default=str(here / "results" / "g168.csv"),
        help="the scored switches, from green_calibration.py -- g168.csv, g13.csv or vista.csv",
    )
    parser.add_argument(
        "--table-s1",
        default="",
        help="the xlsx whose 'Table S…' sheet holds the sequences; defaults to Green's Table S1. "
        "Table S3 is the 13 forward-engineered set. Tables S4/S5 carry NO measured ratio column, "
        "so Green's endogenous sensors cannot be correlated at all -- they are sequence tables",
    )
    parser.add_argument(
        "--csv",
        default="",
        help="read the sequences from the VISTA library CSV instead of an xlsx, through "
        "green_calibration.load_vista_csv, which strips the T7 promoter",
    )
    parser.add_argument("--label", default="", help="what to call this dataset in the report")
    parser.add_argument(
        "--band",
        default="",
        help="a per-switch CSV written by an earlier --out run; correlate both libraries inside "
        "the toehold-accessibility band they share, to test whether a disagreement has a cause",
    )
    parser.add_argument("--out", default="", help="write the per-switch rows to results/<name>.csv")
    args = parser.parse_args(argv)

    import green_calibration as green

    if args.csv:
        source = green.load_vista_csv(args.csv)
    else:
        source = green.load_switches(args.table_s1 or green.TABLE_S1)
    switches = {str(r["switch_number"]): r["switch"] for r in source}
    folder = FoldEngine(37.0)
    print(f"  folding and saddling {len(switches)} switches...")
    rows = measure(Path(args.g168), switches, folder)
    if not rows:
        print("  nothing measurable -- run green_calibration.py first, and check that the")
        print("  sequence table and the scored CSV use the same switch numbering")
        return 1
    report(rows, args.label or "Green's measured switches")

    if args.band:
        other = []
        for row in csv.DictReader(Path(args.band).open(encoding="utf-8")):
            try:
                other.append(
                    {k: float(row[k]) for k in ("on_off", "f1", "f2", "barrier", "f4", "f5")}
                    | {
                        "toehold_defect": (
                            float(row["toehold_defect"]) if row.get("toehold_defect") else None
                        )
                    }
                )
            except (ValueError, KeyError):
                continue
        compare(rows, other, Path(args.band).stem.split("_")[0])

    if args.out:
        path = Path(args.g168).parent / f"{args.out}.csv"
        fields = [
            "switch_number",
            "on_off",
            "toehold_defect",
            "f1",
            "f2",
            "barrier",
            "access",
            "f4",
            "f5",
        ]
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        print(f"\n  written: {path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
