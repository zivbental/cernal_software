"""Does the main_z + aug window beat f1 on Green's 168 measured switches?

    uv run python src/engine/gates/notebooks/toehold_and/window_vs_green.py

**The question, and why only this set can answer it.** The new column ``aug_z_sep`` is the worst
OFF tube's joint opening cost over 9 nt -- the 6 nt between the Shine-Dalgarno and the AUG, plus
the AUG -- minus the ON tube's. It has the same SHAPE as ``f1``, a difference of opening energies
between states, and ``f1`` scores **-0.107** against this set: it is the arm that was demoted to a
floor because it got the sign wrong. A new separation resembling our own metrics is therefore not
evidence of anything. Either it beats -0.107 here or it ranks nothing.

**The analogue, and the direction it errs in.** Green's library is two-state -- switch alone
against switch plus its cognate trigger -- where ours has four tubes, so "worst of three OFF
states" has no counterpart and the OFF term is the switch alone. That difference FLATTERS the new
column: our version has to beat the worst of three leaks where this one faces a single OFF state,
so whatever it scores here is an upper bound on what it would do in an AND gate.

The window is located the same way in both libraries: the 6 nt immediately 5' of the AUG, plus the
AUG's own 3. On our switches that is ``main_z + aug`` by construction; on Green's it is
``switch[aug - 6 : aug + 3]`` with ``aug`` the measured ``aug_index``. One definition, two
libraries.

**What is compared**, against each switch's measured ON/OFF, signed so **positive means the metric
is right**: the new separation and each of its two terms alone; ``f1`` as
``dG_open_on - dG_open_off`` from ``g168.csv``, the arm it would replace; and ``A_M_ratio`` and
``A_M_gain`` from the same file for scale. Carried rather than recomputed wherever the column
already exists, so a disagreement cannot come from two definitions of one quantity.
"""

import csv
import statistics as st
import sys
from pathlib import Path

NB = Path(__file__).resolve().parent
sys.path.insert(0, str(NB.parents[4] / "src"))
sys.path.insert(0, str(NB))

import green_calibration as gc  # noqa: E402
from metric_correlations import spearman  # noqa: E402

from engine.gates.tools.folding import FoldEngine  # noqa: E402

#: Nucleotides 5' of the AUG the window covers. Six, because that is ``main_z`` -- the stretch
#: between the Shine-Dalgarno and the start codon in our architecture -- and the window has to mean
#: the same thing on both libraries or the comparison is between two different metrics.
BEFORE_AUG = 6

#: The 2014 Table S1 workbook, taken from ``green_calibration`` rather than spelled again
#: here: ``load_switches`` wants the FILE, and pointing it at the containing directory fails
#: inside openpyxl with a format error that reads like a corrupt file.
WORKBOOK = gc.TABLE_S1


def window_separation(
    folder: FoldEngine, switch: str, trigger: str, aug: int
) -> tuple[float | None, float | None, float | None]:
    """``(off, on, off - on)`` for the window's joint opening cost, in kcal/mol.

    ``open_penalty`` is ``-RT ln P_open`` over the whole span at once, so a region already open
    contributes almost nothing and a closed one dominates -- which is what "the ribosome needs all
    of it at the same time" means. Lower is better for each term, and the separation is
    ``off - on``, so **positive means the ON state opens more cheaply**: the gate working.

    ``None`` for a term that could not be measured, and then ``None`` for the separation. Never
    0.0 -- a zero separation is a measured tie, and a failed measurement written as one would rank
    above designs that were actually measured.
    """
    lo = aug - BEFORE_AUG
    if lo < 0 or aug + 3 > len(switch):
        return (None, None, None)
    window = (lo, aug + 3)
    off = folder.open_penalty(switch, (window,))
    on = folder.open_penalty(f"{switch}&{trigger}", (window,))
    if off is None or on is None:
        return (off, on, None)
    return (off, on, off - on)


def main(argv=None) -> int:
    results = NB / "results"
    g168 = results / "g168.csv"
    if not g168.exists():
        print(f"  no {g168.name} -- run green_calibration.py first")
        return 1

    measured: dict[str, dict] = {}
    for row in csv.DictReader(g168.open(encoding="utf-8")):
        try:
            measured[str(row["switch_number"])] = {
                "on_off": float(row["on_off"]),
                "aug_index": int(row["aug_index"]),
                "f1": float(row["dG_open_on"]) - float(row["dG_open_off"]),
                "A_M_ratio": float(row["A_M_ratio"]),
                "A_M_gain": float(row["A_M_gain"]),
            }
        except (KeyError, TypeError, ValueError):
            continue
    print(f"  {len(measured)} switches with a measured ON/OFF and an AUG index")

    sequences: dict[str, tuple[str, str]] = {}
    try:
        for record in gc.load_switches(str(WORKBOOK)):
            # `switch_number`, which is what load_switches returns. `number` is always
            # absent, so every lookup missed and the comparison would have had no rows.
            key = str(record.get("switch_number"))
            sequences[key] = (record["switch"], record["trigger"])
    except Exception as error:
        print(f"  could not load the workbook ({type(error).__name__}: {error})")
        print(f"  expected it at {WORKBOOK}")
        return 1
    print(f"  {len(sequences)} switch/trigger pairs from the workbook\n")

    folder = FoldEngine(37.0)
    rows: list[dict] = []
    for position, (number, fields) in enumerate(sorted(measured.items())):
        pair = sequences.get(number)
        if not pair:
            continue
        switch, trigger = pair
        off, on, sep = window_separation(folder, switch, trigger, fields["aug_index"])
        if sep is None:
            continue
        rows.append(
            {**fields, "number": number, "aug_z_off": off, "aug_z_on": on, "aug_z_sep": sep}
        )
        if position % 25 == 0:
            print(f"    {position + 1}/{len(measured)}", flush=True)

    if not rows:
        print("\n  nothing measurable -- no switch had both a sequence and a usable window")
        return 1

    print(f"\n  measured the window on {len(rows)} of Green's switches\n")
    for column in ("aug_z_off", "aug_z_on", "aug_z_sep"):
        values = [r[column] for r in rows]
        print(
            f"    {column:12s}min {min(values):>8.2f}  median {st.median(values):>8.2f}"
            f"  mean {st.fmean(values):>8.2f}  sd {st.stdev(values):>7.2f}"
            f"  max {max(values):>8.2f}"
        )

    print("\n  against the measured ON/OFF, signed so POSITIVE means the metric is right:\n")
    # Each row carries its own sign. f1 and the two bare opening terms are lower-is-better, so
    # their correlations are negated to put every line on one scale; the separation is
    # higher-is-better and is not. Getting that backwards is how a failed metric reads as a winner.
    on_off = [r["on_off"] for r in rows]
    verdicts = [
        ("aug_z_sep   new window, higher better", "aug_z_sep", +1),
        ("aug_z_on    its ON term alone, lower better", "aug_z_on", -1),
        ("aug_z_off   its OFF term alone, lower better", "aug_z_off", -1),
        ("f1          the arm it replaces, lower better", "f1", -1),
        ("A_M_ratio   higher better", "A_M_ratio", +1),
        ("A_M_gain    higher better", "A_M_gain", +1),
    ]
    scored: dict[str, float] = {}
    for label, column, sign in verdicts:
        rho = spearman([r[column] for r in rows], on_off)
        if rho is None:
            print(f"    {label:46s}   n/a")
            continue
        scored[column] = sign * rho
        print(f"    {label:46s}{sign * rho:+.4f}")

    new, old = scored.get("aug_z_sep"), scored.get("f1")
    print()
    if new is None or old is None:
        print("  one of the two could not be scored, so there is no verdict")
    elif new > old:
        print(f"  the new window beats f1 here: {new:+.4f} against {old:+.4f}.")
        print("  One external set, and a two-state analogue that flatters it -- the AND-gate")
        print("  version faces the worst of three OFF states. That earns it a place as an arm; it")
        print("  does not earn believing this magnitude.")
    else:
        print(f"  the new window does NOT beat f1: {new:+.4f} against {old:+.4f}.")
        print("  It stays reported and ranks nothing. The window was the better-founded guess and")
        print("  the measurement declined it, which is the entire reason for measuring first.")
    if scored:
        best = max(scored.items(), key=lambda kv: kv[1])
        print(f"\n  strongest of everything compared: {best[0]} at {best[1]:+.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
