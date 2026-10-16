"""The main_z + aug window -- ON, OFF and GAIN -- on all three measured libraries.

    uv run python src/engine/gates/notebooks/toehold_and/augz_vs_libraries.py

**The window.** The 6 nt between the Shine-Dalgarno and the AUG, plus the AUG: 9 contiguous
nucleotides, as a JOINT opening cost in kcal/mol. On our switches that is ``main_z + aug`` by
construction; here it is ``switch[aug - 6 : aug + 3]`` with ``aug`` the library's own ``aug_index``.
One definition, three libraries.

**Why this window and not a wider one.** ``f1`` spans ``main_z + main_pre`` and deliberately
EXCLUDES the AUG -- the thing the ribosome has to reach. Adding the Shine-Dalgarno instead makes the
window worse, measured: over 40 of our gating designs the SD is already 0.962 unpaired in tube 00
and **closes** by 0.163 going to tube 11, so in the OFF state it contributes a constant and in the
ON state it contributes the wrong sign -- which shows up as ``rbs_aug_open_00`` correlating +0.785
with the barrier and only -0.190 with ``A_M_11``. These 9 nt are the widest span that means the same
thing in every tube.

**Why the GAIN and not either term alone.** An arm that reads one state cannot tell a gate from a
constitutively open switch. ``f1`` is the cautionary case: it is an opening DIFFERENCE and still
fails, so the gain form is not automatically right -- but a single-state term is automatically
incomplete. On our own designs the OFF side is ``min`` over the three OFF tubes; these libraries are
two-state, so the OFF term is the switch alone, and that difference FLATTERS the gain here.

**Joint, not a mean.** ``open_penalty`` is ``-RT ln P`` over the whole span at once, so a region
already open contributes almost nothing while a closed one dominates. Over 9 nt the joint
probability runs about 1e-3 to 1e-6, which is why this is reported as an energy: a ratio of
probabilities that small is all tail, and an energy difference is bounded and reads directly.
"""

import argparse
import csv
import statistics as st
import sys
from pathlib import Path

NB = Path(__file__).resolve().parent
sys.path.insert(0, str(NB.parents[4] / "src"))
sys.path.insert(0, str(NB))

import green_calibration as gc  # noqa: E402
from metric_correlations import spearman  # noqa: E402
from window_vs_green import window_separation  # noqa: E402

from engine.gates.tools.folding import FoldEngine  # noqa: E402

GREEN_2014 = Path(r"C:\Users\Dell\OneDrive - mail.tau.ac.il\IGEM\Toehold\Green 2014")
GREEN_2026 = Path(r"C:\Users\Dell\OneDrive - mail.tau.ac.il\IGEM\Toehold\Green 2026")

#: Each library: its calibration CSV, where its sequences come from, and how to load them.
#:
#: ``g168`` and ``g13`` are xlsx Table S1 and Table S3 read by ``load_switches``; VISTA is the 2026
#: Supplementary Table 4 CSV read by ``load_vista_csv``, which carries two measured ratios per
#: switch (truncated and full-length reporter) and whose full-length one is ``on_off``.
LIBRARIES = (
    (
        "g168",
        "g168.csv",
        gc.TABLE_S1,
        "xlsx",
    ),
    (
        "g13",
        "g13.csv",
        str(
            GREEN_2014
            / "Table S3. Sequence and Performance Information for the Set of Forward-Engineered "
            "Toehold Switches, Endogenous RNA Polymerase Expression Constructs, and Definitions "
            "of Thermodynamic Pa.xlsx"
        ),
        "xlsx",
    ),
    (
        "vista",
        "vista.csv",
        str(GREEN_2026 / "Supplementary_Table4.csv"),
        "csv",
    ),
)


def noise_for(n: int) -> float:
    return 1.0 / (n**0.5) if n else 1.0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default="augz_libraries")
    args = parser.parse_args(argv)
    results = NB / "results"
    folder = FoldEngine(37.0)
    everything: list[dict] = []

    for label, table, source, kind in LIBRARIES:
        path = results / table
        if not path.exists():
            print(f"  no {table}, skipping {label}")
            continue
        measured = {}
        for row in csv.DictReader(path.open(encoding="utf-8")):
            try:
                measured[str(row["switch_number"])] = {
                    "on_off": float(row["on_off"]),
                    "aug_index": int(row["aug_index"]),
                }
            except (KeyError, TypeError, ValueError):
                continue
        try:
            records = gc.load_switches(source) if kind == "xlsx" else gc.load_vista_csv(source)
        except Exception as error:
            print(f"  {label}: could not load sequences ({type(error).__name__}: {error})")
            continue
        sequences = {str(r.get("switch_number")): (r["switch"], r["trigger"]) for r in records}
        print(f"\n  {label}: {len(measured)} measured, {len(sequences)} with sequences", flush=True)

        rows = []
        for number, fields in sorted(measured.items()):
            pair = sequences.get(number)
            if not pair:
                continue
            switch, trigger = pair
            off, on, gain = window_separation(folder, switch, trigger, fields["aug_index"])
            if gain is None:
                continue
            rows.append(
                {
                    "library": label,
                    "switch_number": number,
                    "on_off": fields["on_off"],
                    "aug_z_on": round(on, 4),
                    "aug_z_off": round(off, 4),
                    "aug_z_gain": round(gain, 4),
                }
            )
        if not rows:
            print(f"  {label}: no switch had both a sequence and a usable window")
            continue
        everything.extend(rows)

        noise = noise_for(len(rows))
        print(f"  scored {len(rows)}; sampling noise ~{noise:.2f}\n")
        print(
            f"    {'term':12s}{'min':>9s}{'median':>9s}{'mean':>9s}{'sd':>8s}{'max':>9s}"
            f"{'rho vs ON/OFF':>15s}"
        )
        on_off = [r["on_off"] for r in rows]
        for term, sign in (("aug_z_on", -1), ("aug_z_off", -1), ("aug_z_gain", +1)):
            values = [r[term] for r in rows]
            rho = spearman(values, on_off)
            signed = "n/a" if rho is None else f"{sign * rho:+.4f}"
            flag = ""
            if rho is not None and abs(sign * rho) < noise:
                flag = "  (inside noise)"
            print(
                f"    {term:12s}{min(values):>9.2f}{st.median(values):>9.2f}"
                f"{st.fmean(values):>9.2f}{st.stdev(values):>8.2f}{max(values):>9.2f}"
                f"{signed:>15s}{flag}"
            )
        print("    rho is signed so POSITIVE means the term is right; ON and OFF are costs,")
        print("    so lower is better for them and their correlations are negated.")

    if not everything:
        return 1
    out = results / f"{args.out}.csv"
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(everything[0]))
        writer.writeheader()
        writer.writerows(everything)
    print(f"\n  wrote {len(everything):,} rows to {out.name}")

    print(f"\n{'=' * 78}\n  does aug_z hold its sign across the libraries?\n{'=' * 78}\n")
    labels = [label for label, *_ in LIBRARIES if any(r["library"] == label for r in everything)]
    print(f"    {'term':12s}" + "".join(f"{label:>10s}" for label in labels) + "   verdict")
    for term, sign in (("aug_z_on", -1), ("aug_z_off", -1), ("aug_z_gain", +1)):
        cells, got = "", []
        for label in labels:
            pool = [r for r in everything if r["library"] == label]
            rho = spearman([r[term] for r in pool], [r["on_off"] for r in pool])
            value = None if rho is None else sign * rho
            got.append(value)
            cells += f"{value:>+10.3f}" if value is not None else f"{'n/a':>10s}"
        real = [v for v in got if v is not None]
        if not real:
            verdict = "never scored"
        elif all(v > 0 for v in real):
            verdict = "positive everywhere"
        elif all(v < 0 for v in real):
            verdict = "negative everywhere"
        else:
            verdict = "FLIPS SIGN"
        print(f"    {term:12s}{cells}   {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
