"""How many secondary stems a trigger pair actually offers, and what capping at 2 throws away.

`stems_per_pair = 2` takes the two lowest `lock_energy` stems and discards the rest. The question
is what the rest are: how many there are, how they split by scheme, and how much of the lock-energy
range sits outside the cap. Measured on a sample of the real PFAS pairs rather than on one.

`secondary_stems` is pure geometry plus fixed-alignment energies, so this costs no folding of a
switch -- which is why the census is affordable even though building on every stem is not.
"""

import statistics as st
import sys
from pathlib import Path

ROOT = Path(r"C:\Users\Dell\source\repos\cernal_software")
sys.path.insert(0, str(ROOT / "src"))

from engine import sequences as sq  # noqa: E402
from engine.domain import Host  # noqa: E402
from engine.gates.toehold import ProkaryoticToeholdAndGate  # noqa: E402
from engine.gates.tools.codons import CodonOptimizer  # noqa: E402
from engine.gates.tools.folding import FoldEngine  # noqa: E402
from engine.gates.tools.translation import TranslationScorer  # noqa: E402
from engine.transcriptome import load_transcriptome  # noqa: E402

book = load_transcriptome(Host.ECOLI)
gate = ProkaryoticToeholdAndGate(
    host=Host.ECOLI,
    folder=FoldEngine(),
    translation=TranslationScorer(Host.ECOLI),
    codons=CodonOptimizer(Host.ECOLI),
)

ta, tb = sq.to_rna(book["b3447"]), sq.to_rna(book["b3846"])  # ggt x fadB
src = {"ggt": ta, "fadB": tb}
pairs = list(gate.find_cross_gene_pairs("ggt", ta, "fadB", tb))

# A deterministic sample: every Nth pair of the length-sorted list, so the sample spans the whole
# len_x range instead of the head. The first items of a sorted list are not representative.
ordered = sorted(pairs, key=lambda p: (-p.len_x, p.x_start, p.xstar_start))
step = max(1, len(ordered) // 400)
sample = ordered[::step]
print(f"{len(pairs):,} pairs on ggt x fadB; sampling every {step}th -> {len(sample)} pairs")

offered, usable_counts, by_scheme = [], [], {}
outside_best, outside_second = [], []
for p in sample:
    a0, a1 = p.window_a()
    b0, b1 = p.window_b()
    wa, wb = src[p.gene_a][a0:a1], src[p.gene_b][b0:b1]
    stems = gate.secondary_stems(wa, wb, p.len_x)
    offered.append(len(stems))
    live = [
        s for s in stems if s.scheme in ("B-anchored", "mixed") and (s.lock_energy or 0.0) <= 0.0
    ]
    usable_counts.append(len(live))
    for s in stems:
        by_scheme[s.scheme] = by_scheme.get(s.scheme, 0) + 1
    if len(live) >= 2:
        live.sort(key=lambda s: s.lock_energy)
        # How much stronger-locking stem the cap discards: the gap from the 2nd kept to the best
        # DROPPED one, in kcal/mol. Negative means a dropped stem locks harder than one kept.
        dropped = live[2:]
        if dropped:
            outside_second.append(min(s.lock_energy for s in dropped) - live[1].lock_energy)
        outside_best.append(live[1].lock_energy - live[0].lock_energy)


def spread(label, values):
    if not values:
        print(f"  {label}: none")
        return
    print(
        f"  {label:34s} n {len(values):>4}  min {min(values):>7.2f}  median "
        f"{st.median(values):>7.2f}  mean {st.fmean(values):>7.2f}  sd "
        f"{st.stdev(values) if len(values) > 1 else 0.0:>6.2f}  max {max(values):>7.2f}"
    )


print("\nstems OFFERED per pair, before any filter")
spread("count", [float(v) for v in offered])
print("\nstems USABLE per pair (B-anchored or mixed, lock_energy <= 0)")
spread("count", [float(v) for v in usable_counts])
total = sum(by_scheme.values())
print("\nby scheme, over every stem offered")
for name, n in sorted(by_scheme.items(), key=lambda kv: -kv[1]):
    print(f"  {name:16s}{n:>7,}  {100.0 * n / total:>5.1f}%")

print("\nwhat the cap at 2 discards, in lock_energy kcal/mol")
spread("2nd kept minus best kept", outside_best)
spread("best DROPPED minus 2nd kept", outside_second)
over = [c for c in usable_counts if c > 2]
print(
    f"\n  pairs with more than 2 usable stems: {len(over)} of {len(usable_counts)} "
    f"({100.0 * len(over) / len(usable_counts):.1f}%)"
)
print(f"  mean usable stems where there are more than 2: {st.fmean(over) if over else 0:.2f}")
print("\n  carrying EVERY usable stem instead of 2 multiplies the run by")
print(f"    {st.fmean([float(c) for c in usable_counts]) / 2.0:.2f}x  (mean usable / 2)")
