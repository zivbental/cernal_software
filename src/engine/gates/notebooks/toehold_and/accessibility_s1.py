"""Accessibility in VISTA's validated form: full-transcript ensemble, flanked window.

    uv run python src/engine/gates/notebooks/toehold_and/accessibility_s1.py --out accessibility_s1

``l_green`` as the panel computes it is ``1 - sed_w0``, and ``sed_w0`` folds the binding
window as an **isolated slice**. The accessibility term that scored +0.317 against VISTA's
189 measured switches differs in two ways at once: it is read from the pair-probability
matrix of the **whole 711-nt transcript**, and it averages over the window **plus 25 nt of
flank on each side**.

Conflating those two differences is how `mfe_w25` came to be tested as "VISTA's measure" and scored
+0.011. So both are computed here and kept separate:

    l_full_w0    mean P(unpaired) over the exact window, from the FULL-transcript ensemble
    l_full_w10   the same, window plus 10 nt each side
    l_full_w25   the same, plus 25 nt each side  <- the form that scored +0.317
    l_full_w50   plus 50
    l_green      unchanged, the isolated-slice form the panel uses today, for comparison

The transcript is folded **once** -- O(n^3) on 711 nt is the whole cost, and every window is then a
mean over a slice of one profile. That is also the only way the numbers are mutually comparable: a
per-window fold gives each window a different ensemble to be a fraction of.
"""

import argparse
import csv
import sys
from pathlib import Path

NB = Path(__file__).resolve().parent
sys.path.insert(0, str(NB.parents[4] / "src"))
sys.path.insert(0, str(NB))

import objective_panel as op  # noqa: E402
from full_sweep import read_fasta  # noqa: E402

from engine.gates.tools.folding import FoldEngine  # noqa: E402

#: Flank sizes, in nt each side. 25 is the one VISTA reports as significant and that measured
#: +0.317; the others are kept so the flank's effect is visible rather than assumed.
FLANKS = (0, 10, 25, 50)


def unpaired_profile(folder: FoldEngine, transcript: str) -> list[float]:
    """Per-base probability of being unpaired, from ONE fold of the whole transcript.

    ``base_pair_probabilities`` returns the upper-triangular pair matrix; a base's unpaired
    probability is one minus its total pairing probability. Clamped at 0 because the matrix carries
    rounding that can push a fully-paired base marginally past 1.
    """
    matrix = folder.base_pair_probabilities(transcript)
    return [max(0.0, 1.0 - min(1.0, sum(row))) for row in matrix]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default="accessibility_s1")
    args = parser.parse_args(argv)

    results = NB / "results"
    transcript = read_fasta(NB / "mCherry_original.txt")
    folder = FoldEngine(37.0)
    print(f"  folding the {len(transcript)} nt transcript once...", flush=True)
    profile = unpaired_profile(folder, transcript)
    print(f"  {len(profile)} per-base unpaired probabilities\n")

    # Every (window start, role) **the designs use**, not the ones an older table happens to carry.
    #
    # Keyed on (start, role) because that is what ``add_accessibility`` joins on; anything else
    # fails to join silently. But the window LIST comes from the scored designs, with
    # ``accessibility.csv`` only contributing its ``l_green`` where it has one.
    #
    # **Why this matters, measured.** Reading the list off ``accessibility.csv`` gave 2,478 keys and
    # covered **75.8%** of feasible designs. The other 24% carried no accessibility number at all
    # and so passed the accessibility floor unchecked -- the floor only rejects a value it has, and
    # "never measured" is deliberately not "failed". A filter that silently skips a quarter of the
    # population is not a filter.
    #
    # And the fix is free: the transcript is folded **once**, so a window costs a mean over a slice
    # of a profile already in memory. There was never a reason to score only the windows another
    # file knew about.
    known: dict[tuple[int, str], str] = {}
    source = results / "accessibility.csv"
    if source.exists():
        with source.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                start, role = row.get("start"), (row.get("role") or "").strip()
                if start in (None, "") or role not in ("A", "B"):
                    continue
                known[(int(start), role)] = row.get("l_green") or ""
    print(f"  accessibility.csv carries l_green for {len(known):,} (start, role) keys")

    wanted: dict[tuple[int, str], tuple[int, int]] = {}
    for design in op.load(results):
        for role, lo_key, hi_key in (("A", "a_start", "a_end"), ("B", "b_start", "b_end")):
            try:
                lo, hi = int(design[lo_key]), int(design[hi_key])
            except (KeyError, TypeError, ValueError):
                continue
            # The widest form per (start, role): two geometries give the same window start different
            # ends (36/50 nt naive against 35/49 Kim), and one key cannot hold both. The wider span
            # is the conservative choice -- it averages over more of the transcript, so it cannot
            # report a window as more reachable than the narrower form would.
            current = wanted.get((lo, role))
            if current is None or hi > current[1]:
                wanted[(lo, role)] = (lo, hi)
    print(f"  the designs use {len(wanted):,} (start, role) keys")

    rows = []
    for (lo, role), (_, hi) in sorted(wanted.items()):
        entry = {"start": lo, "end": hi, "role": role, "l_green": known.get((lo, role), "")}
        for flank in FLANKS:
            a = max(0, lo - flank)
            b = min(len(profile), hi + flank)
            values = profile[a:b]
            entry[f"l_full_w{flank}"] = round(sum(values) / len(values), 6) if values else None
        rows.append(entry)

    print(f"  {len(rows)} (window, role) keys\n")
    import statistics as st

    for column in ("l_green", *(f"l_full_w{f}" for f in FLANKS)):
        values = [float(r[column]) for r in rows if r.get(column) not in (None, "")]
        if not values:
            continue
        print(
            f"  {column:12s} n={len(values):5d}  min {min(values):.4f}"
            f"  median {st.median(values):.4f}  max {max(values):.4f}"
        )

    def spearman(xs: list[float], ys: list[float]) -> float | None:
        from metric_correlations import spearman as rho

        return rho(xs, ys)

    print("\n  how far the isolated-slice form is from the full-transcript one:")
    both = [
        (float(r["l_green"]), float(r["l_full_w0"]))
        for r in rows
        if r.get("l_green") not in (None, "") and r.get("l_full_w0") is not None
    ]
    if both:
        rho = spearman([p[0] for p in both], [p[1] for p in both])
        print(f"    rho(l_green, l_full_w0) = {rho:+.4f}   n={len(both)}")
        print("    Both are the exact window; the only difference is whether the ensemble is the")
        print("    whole transcript or the slice. A low rho means the context, not the window,")
        print("    is what the panel has been measuring.")
    for flank in FLANKS[1:]:
        pairs = [
            (float(r["l_full_w0"]), float(r[f"l_full_w{flank}"]))
            for r in rows
            if r.get("l_full_w0") is not None and r.get(f"l_full_w{flank}") is not None
        ]
        if pairs:
            rho = spearman([p[0] for p in pairs], [p[1] for p in pairs])
            print(f"    rho(l_full_w0, l_full_w{flank}) = {rho:+.4f}")

    path = results / f"{args.out}.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        names = ["start", "end", "role", "l_green", *(f"l_full_w{f}" for f in FLANKS)]
        writer = csv.DictWriter(handle, fieldnames=names, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n  wrote {path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
