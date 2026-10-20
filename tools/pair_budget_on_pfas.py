"""What selecting trigger pairs by accessibility does to the run, on the real PFAS genes.

    uv run python tools/pair_budget_on_pfas.py

**Why this lives in ``tools/`` and not beside the notebook.** It uses ``FoldProfiler``, a stage-2
tool, and ``tests/engine/test_house_rules.py`` forbids any file under ``gates/`` from referencing
it -- both as an upward import (layer 4 from layer 3) and as a gate family reaching for a
stage tool. The notebook's exemption covers the shared-tool rule only; every other house rule still
applies to it. ``accessibility_local.py`` is here for exactly the same reason.

This is a research budget analysis, not an application entry point. See
``docs/prokaryotic-and-reproducibility.md`` for runtime and research responsibilities.

The question is whether every pair can be carried. The answer has to come from the pair count at
each accessibility threshold, because the grid behind each pair is fixed and the pair count is the
only free factor.

Accessibility is `FoldProfiler.openness` -- RNAplfold W=200 L=150 u=20, the measure CERNAL uses --
on the pair's WEAKER window, `min(l_local_A, l_local_B)`, which is the same quantity and the same
form the mCherry panel filters on. One fold per transcript, cached, so scoring all pairs is free
next to folding a single design.
"""

import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from engine import sequences as sq  # noqa: E402
from engine.domain import Constraints, Host  # noqa: E402
from engine.gates.toehold import (  # noqa: E402
    KimSecondaryArmToeholdAndGate,
    ProkaryoticToeholdAndGate,
)
from engine.gates.tools.codons import CodonOptimizer  # noqa: E402
from engine.gates.tools.folding import FoldEngine  # noqa: E402
from engine.gates.tools.translation import TranslationScorer  # noqa: E402
from engine.stages.folding import FoldProfiler  # noqa: E402
from engine.transcriptome import load_transcriptome  # noqa: E402

PAIRS = [
    ("ggt", "b3447", "fadB", "b3846"),
    ("ggt", "b3447", "astC", "b1748"),
    ("ggt", "b3447", "aldA", "b1415"),
]

book = load_transcriptome(Host.ECOLI)
profiler = FoldProfiler()
folder = FoldEngine()
limits = Constraints()

gates = {}
for cls in (ProkaryoticToeholdAndGate, KimSecondaryArmToeholdAndGate):
    g = cls(
        host=Host.ECOLI,
        folder=folder,
        translation=TranslationScorer(Host.ECOLI),
        codons=CodonOptimizer(Host.ECOLI),
    )
    gates[g.geometry_name] = g

print("the two geometries the engine registers, and the switch each builds:")
for name, g in gates.items():
    print(
        f"  {name:22s} ARM_LEN {g.ARM_LEN} (main hairpin)  "
        f"SECONDARY_ARM_LEN {g.SECONDARY_ARM_LEN}  SECONDARY_INVASION_LEN "
        f"{g.SECONDARY_INVASION_LEN}  footprints {g.role_footprints()}"
    )

grid = {}
for name, g in gates.items():
    grid[name] = len(g.CLOSURES) * len(g.UPPER3) * len(g.LOWER3)
    print(
        f"  {name:22s} grid = {len(g.CLOSURES)} closures x {len(g.UPPER3)} upper3 "
        f"x {len(g.LOWER3)} lower3 = {grid[name]}"
    )
per_pair = sum(grid.values()) * limits.stems_per_pair
print(
    f"\n  designs per trigger pair, both geometries, stems_per_pair={limits.stems_per_pair}: "
    f"{per_pair}"
)

# The overlap scan keys on MIN_OVERLAP and SECONDARY_INVASION_LEN only, so either geometry
# enumerates the same runs; the footprints differ by 1 nt and `fits` is checked per geometry.
scan = next(iter(gates.values()))
GRID_TOTAL = sum(grid.values()) * limits.stems_per_pair

print(f"\n{'=' * 92}")
all_access: list[float] = []
per_gene_pair: dict[str, list[float]] = {}
for a_sym, a_id, b_sym, b_id in PAIRS:
    ta, tb = sq.to_rna(book[a_id]), sq.to_rna(book[b_id])
    src = {a_sym: ta, b_sym: tb}
    pairs = list(scan.find_cross_gene_pairs(a_sym, ta, b_sym, tb))
    access = []
    for p in pairs:
        a0, a1 = p.window_a()
        b0, b1 = p.window_b()
        la = profiler.openness(src[p.gene_a], a0, a1)
        lb = profiler.openness(src[p.gene_b], b0, b1)
        access.append(min(la, lb))
    label = f"{a_sym} x {b_sym}"
    per_gene_pair[label] = access
    all_access.extend(access)
    print(
        f"{label:14s} {len(pairs):>7,} pairs   min(l_local) "
        f"min {min(access):.4f}  median {st.median(access):.4f}  mean {st.fmean(access):.4f}  "
        f"sd {st.stdev(access):.4f}  max {max(access):.4f}"
    )

print(f"\nall three gene pairs: {len(all_access):,} trigger pairs")
print(
    f"  min {min(all_access):.4f}  median {st.median(all_access):.4f}  "
    f"mean {st.fmean(all_access):.4f}  sd {st.stdev(all_access):.4f}  max {max(all_access):.4f}"
)

print(
    f"\n{'threshold':>10s}{'pairs kept':>12s}{'share':>8s}{'designs':>14s}{'core-hours':>12s}"
    f"{'6 cores':>10s}"
)
for floor in (0.0, 0.3369, 0.40, 0.4065, 0.45, 0.50, 0.55, 0.60):
    kept = sum(1 for v in all_access if v > floor)
    designs = kept * GRID_TOTAL
    hours = designs * 0.3 / 3600.0
    print(
        f"{floor:>10.4f}{kept:>12,}{100.0 * kept / len(all_access):>7.1f}%{designs:>14,}"
        f"{hours:>12,.0f}{hours / 6:>10,.0f}"
    )
print("\n  0.3 s per design is the measured cost AFTER the ON ceiling rejects ~88%;")
print("  the ceiling runs first, so this is the effective per-enumerated-design cost.")
