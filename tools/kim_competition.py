"""Trigger A's grip on the secondary hairpin AGAINST what holds it — length cancelled.

    uv run python tools/kim_competition.py

**This corrects `tools/kim_a_site.py`, which measured length.** That script took the energy of
Kim's buried segment against its own complement at 5, 8 and 11 nucleotides and found -3.80, -9.20
and -14.40 kcal/mol. More base pairs give more energy, so the ordering it reported was a
restatement of the lengths Kim chose, not a property of the grip. Per nucleotide it still rose
(-0.760, -1.150, -1.309) but longer duplexes also stack better per base, so even that is partly
mechanical. The figure built on it overstates what was measured.

Two things fix it, both of them the objection that prompted this file.

**1. The quantity that decides displacement is a difference, not a binding energy.** Trigger A does
not bind free RNA; it competes with whatever already pairs that region. So the measurement is

    hold = open_penalty(switch, [R])           kcal/mol to free region R from the switch's own fold
    grip = |fixed_alignment_energy(A_seg, R)|   kcal/mol A offers for the same R
    margin = grip - hold                        positive means A can pay for it

Both terms scale with |R|, so the **difference cancels length** and the margin is comparable across
constructs with different burial. `open_penalty` is the same function our own `open_00`/`open_11`
call, so the hold term is on the same scale as everything else in this project.

**2. What is OUTSIDE the hairpin is not nothing.** Kim's `a` nucleotides are A's free toehold on the
PRIMARY hairpin: A nucleates there and then invades. Our design has `a = 0`, so A has no free
toehold at all and must nucleate on `x*` while it is still inside the secondary hairpin. That is an
architectural difference, not a parameter difference, and it is the reason this comparison is
strained however the energies are computed. It is reported beside the numbers rather than buried.
"""

from __future__ import annotations

import csv
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NB = ROOT / "src/engine/gates/notebooks/toehold_and"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(NB))

# ruff: noqa: E402 - the engine and notebook imports must follow the sys.path inserts.
from kim2019_benchmark import PRIMARY_TRIGGER, REPORTED, SWITCHES

from engine import sequences as sq
from engine.gates.toehold import ToeholdAndGate
from engine.gates.tools.binding import fixed_alignment_energy
from engine.gates.tools.folding import FoldEngine


def footprint_start(primary: str, switch: str) -> tuple[int, int]:
    """Where trigger A's complement sits in the switch, and how long the run is.

    Searched on ``revcomp(primary)``, which read 5'->3' IS the switch region A binds, in switch
    order. So index 0 of that needle is the complement of A's 3'-terminal base, and A's 3'-most
    ``k`` nucleotides map to the needle's first ``k`` -- which is what makes the buried region
    ``[at, at + buried)`` below.
    """
    needle = sq.reverse_complement(primary)
    best = (0, -1)
    for i in range(len(needle)):
        for j in range(i + best[0] + 1, len(needle) + 1):
            at = switch.find(needle[i:j])
            if at < 0:
                break
            if j - i > best[0]:
                best = (j - i, at)
    return best


def main() -> int:
    folder = FoldEngine()
    print(
        "  Kim 2019, Supplementary Table S2, with the 21-nt linker appended as the benchmark does"
    )
    print(
        f"\n  {'construct':11s}{'a':>3s}{'buried':>7s}{'hold':>8s}{'grip':>8s}"
        f"{'margin':>9s}{'hold/nt':>9s}{'grip/nt':>9s}{'margin/nt':>11s}  measured"
    )

    rows = []
    for name, (label, behaviour) in REPORTED.items():
        if "=" not in label:
            print(f"  {name:11s}{'--':>3s}{'--':>7s}  no inhibitory hairpin -- nothing to displace")
            continue
        a = int(label.split("=")[1])
        buried = 15 - a
        switch = sq.to_rna(SWITCHES[name]) + sq.to_rna(ToeholdAndGate.LINKER_SEQUENCE)
        primary = sq.to_rna(PRIMARY_TRIGGER[name])
        run, at = footprint_start(primary, switch)
        if at < 0 or run < buried:
            print(f"  {name:11s}  footprint not located ({run} nt) -- skipped rather than guessed")
            continue
        region = (at, at + buried)
        r_seq = switch[region[0] : region[1]]
        hold = folder.open_penalty(switch, (region,))
        grip = fixed_alignment_energy(primary[-buried:], r_seq, folder)
        if hold is None or grip is None:
            print(f"  {name:11s}  unevaluable -- reported as None, never as zero")
            continue
        margin = abs(grip) - hold
        rows.append((name, a, buried, hold, grip, margin, behaviour))
        print(
            f"  {name:11s}{a:>3d}{buried:>7d}{hold:>8.2f}{grip:>8.2f}{margin:>9.2f}"
            f"{hold / buried:>9.3f}{grip / buried:>9.3f}{margin / buried:>11.3f}  {behaviour}"
        )

    print("\n  hold   = open_penalty(switch, [R]): kcal/mol to free A's landing region from the")
    print("           switch's own fold. Positive, a cost. Same function as our open_00/open_11.")
    print("  grip   = fixed_alignment_energy(A's buried segment, R): negative, a duplex.")
    print("  margin = |grip| - hold. POSITIVE means A offers more than the fold charges, so A can")
    print("           displace it; negative means it cannot. Both terms scale with the number of")
    print("           nucleotides, so the margin is the length-cancelled quantity.")

    # The same margin on our own designs, from the run, so the two are on one scale.
    ours = []
    for i in range(6):
        path = NB / "results" / f"axes_pfas_{i}.csv"
        if not path.exists():
            continue
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                lock = (row.get("lock_energy") or "").strip()
                site = (row.get("a_site_energy") or "").strip()
                if lock and site:
                    # `lock_energy` is the secondary hairpin's own stem, `a_site_energy` is A's
                    # binding to that arm -- both negative, both over the same 15 nt. So
                    # |a_site| - |lock| is our margin in the same sense as Kim's above.
                    ours.append(abs(float(site)) - abs(float(lock)))
    if ours:
        ours.sort()
        print(f"\n  our designs, |a_site_energy| - |lock_energy| over {len(ours):,} designs:")
        print(
            f"    min {ours[0]:.2f}  Q1 {ours[len(ours) // 4]:.2f}  median {st.median(ours):.2f}  "
            f"Q3 {ours[3 * len(ours) // 4]:.2f}  max {ours[-1]:.2f}  kcal/mol"
        )
        above = sum(1 for v in ours if v > 0)
        print(
            f"    A offers more than the stem holds in {above:,} of {len(ours):,} "
            f"({100.0 * above / len(ours):.1f}%)"
        )
        print("    NOTE: our margin uses `lock_energy`, a fixed-alignment stem energy, where Kim's")
        print("    uses `open_penalty` on the folded switch. The two are not the same measurement;")
        print("    ours ignores what else the switch could fold into and so understates the hold.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
