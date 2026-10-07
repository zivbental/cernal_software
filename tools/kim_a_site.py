"""Where do Kim 2019's four built constructs fall on the `a_site_energy` axis?

    uv run python tools/kim_a_site.py

**Why this is the test worth running.** `a_site_energy` -- trigger A's binding to the secondary
hairpin's arm -- is the strongest predictor in our characterisation run (within-cell Spearman -0.60
to -0.77 against all three arms, p ~1e-50) and nothing in the pipeline ranks on it. It has no
external calibration at all. Kim's constructs are the only built-and-measured two-input gates of
this architecture in the literature, and they vary **exactly this quantity**:

    Kim's name   their `a`   nt of A's toehold INSIDE the secondary hairpin   measured behaviour
    G5-G3n5      10          5                                               one-input switch
    G5-G3n8       7          8                                               intermediate
    G5-G3n11      4         11                                               TWO-INPUT AND GATE
    G3n5         --         -- (no inhibitory hairpin)                       plain toehold switch
    ours          0         15

Their `a` is the primary hairpin's exposed toehold and the total is 15, so `15 - a` is how much of
trigger A's nucleation site is sequestered in the secondary hairpin -- which is what their names
`n5`/`n8`/`n11` count. The one that works as an AND gate is `n11`.

**What our data predicts.** Our objectives improve as A's grip on the secondary arm gets WEAKER,
sharply so in the weakest quintile. If that is right, the construct with the most of A's site buried
(`n11`, and ours at 15) should NOT be the best-gripping one -- more buried site means more of A
pairing inside the hairpin, so a stronger grip, so by our data a worse gate. Kim measured the
opposite: `n11` is the one that gates. **So this either calibrates the axis or refutes our sign.**

Either answer is worth having, and this script reports the numbers without choosing.

**What it cannot do.** Kim's two triggers are unrelated sequences binding separate hairpins, while
ours share the overlap `x`, so their trigger B carries no copy of A's nucleation site. The
architectures are cousins, not instances, and `kim2019_comparison.md` records that our four-tube
observables return the SAME `A_M(10)` for all three spacings and for the no-hairpin control -- an
equilibrium model cannot see what Kim varied. This measures one energy, not a ranking.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NB = ROOT / "src/engine/gates/notebooks/toehold_and"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(NB))

# ruff: noqa: E402 - the engine and notebook imports must follow the sys.path inserts.
import statistics as st

from kim2019_benchmark import PRIMARY_TRIGGER, REPORTED, SWITCHES

from engine import sequences as sq
from engine.gates.tools.binding import fixed_alignment_energy
from engine.gates.tools.folding import FoldEngine


def longest_shared(needle: str, haystack: str) -> tuple[int, int, int]:
    """Longest run of `needle` that appears in `haystack`, as (length, start in needle, in hay).

    Used on `revcomp(trigger)` against the switch, so it finds the trigger's longest contiguous
    complementary footprint -- the stretch it can actually zip up.
    """
    best = (0, 0, 0)
    for i in range(len(needle)):
        for j in range(i + best[0] + 1, len(needle) + 1):
            at = haystack.find(needle[i:j])
            if at < 0:
                break
            if j - i > best[0]:
                best = (j - i, i, at)
    return best


def main() -> int:
    folder = FoldEngine()
    # Each construct has its OWN primary trigger. They share the 5' 22 nt and differ at the 3'
    # end, which is exactly the part sequestered in the secondary hairpin -- so the buried segment
    # is the 3'-most 15-a nucleotides of that construct's own trigger, not of a shared one.
    print("  trigger A per construct (TrG3n*), 3' end differs = the buried part:")
    for name, trigger in PRIMARY_TRIGGER.items():
        print(f"    {name:12s}{sq.to_rna(trigger)}")
    print("\n  Kim's constructs, and how much of A's site each buries in the secondary hairpin:")
    print(
        f"  {'construct':12s}{'a':>4s}{'buried':>8s}{'footprint':>11s}"
        f"{'a_site(buried)':>16s}{'per nt':>9s}  measured behaviour"
    )

    rows = []
    for name, (label, behaviour) in REPORTED.items():
        switch = sq.to_rna(SWITCHES[name])
        primary = sq.to_rna(PRIMARY_TRIGGER[name])
        length, _in_trigger, _in_switch = longest_shared(sq.reverse_complement(primary), switch)
        # `a` from Kim's own label, and the buried part is 15 - a: their total toehold is 15 nt and
        # `a` is the portion left exposed on the primary hairpin.
        a = int(label.split("=")[1]) if "=" in label else None
        buried = None if a is None else 15 - a
        energy = per_nt = None
        if buried:
            # The 3'-most `buried` nucleotides of trigger A are the ones sequestered in the
            # secondary hairpin, so that segment against its own complement is the comparable
            # quantity -- the same construction `a_site_energy` uses on our designs.
            segment = primary[-buried:]
            energy = fixed_alignment_energy(segment, sq.reverse_complement(segment), folder)
            if energy is not None:
                per_nt = energy / buried
        rows.append((name, a, buried, length, energy, per_nt, behaviour))
        print(
            f"  {name:12s}{(a if a is not None else '--'):>4}"
            f"{(buried if buried is not None else '--'):>8}{length:>11}"
            f"{(f'{energy:.2f}' if energy is not None else '--'):>16}"
            f"{(f'{per_nt:.3f}' if per_nt is not None else '--'):>9}  {behaviour}"
        )

    # Ours, for the same quantity on the same scale: 15 nt buried, a = 0.
    # Ours uses the n11 trigger's 3' end extended to 15, as the closest available stand-in: we
    # have no built a=0 construct, so this is the SCALE of 15 buried nt, not a real design.
    ours = sq.to_rna(PRIMARY_TRIGGER["G5-G3n11"])[-15:]
    ours_energy = fixed_alignment_energy(ours, sq.reverse_complement(ours), folder)
    print(
        f"  {'ours (a=0)':12s}{0:>4}{15:>8}{'--':>11}"
        f"{(f'{ours_energy:.2f}' if ours_energy is not None else '--'):>16}"
        f"{(f'{ours_energy / 15:.3f}' if ours_energy is not None else '--'):>9}  not yet built"
    )

    print("\n  NOTE on the comparison: this is the energy of the BURIED SEGMENT against its own")
    print("  complement, which isolates length and sequence from the rest of the hairpin. It is")
    print("  comparable ACROSS Kim's four constructs, which is what the question needs, but it is")
    print("  not numerically the same construction as our `a_site_energy` (which pairs x+ext")
    print("  against secondary_z+revcomp(x) in our own domain layout). Sign and ordering transfer;")
    print("  the absolute value does not.")

    # Our own distribution, for the comparison the question is really about.
    import csv

    path = NB / "results"
    values = []
    for i in range(6):
        f = path / f"axes_pfas_{i}.csv"
        if not f.exists():
            continue
        with f.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                text = (row.get("a_site_energy") or "").strip()
                if text:
                    values.append(float(text))
    if values:
        values.sort()
        print(f"\n  our run's a_site_energy over {len(values):,} designs:")
        print(
            f"    min {values[0]:.1f}  Q1 {values[len(values) // 4]:.1f}  "
            f"median {st.median(values):.1f}  Q3 {values[3 * len(values) // 4]:.1f}  "
            f"max {values[-1]:.1f}  kcal/mol"
        )
        print(f"    mean {st.fmean(values):.2f}  sd {st.stdev(values):.2f}")
        print("    Per nucleotide, over 15 buried nt, that is", end=" ")
        print(f"{st.median(values) / 15:.3f} kcal/mol/nt at the median.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
