"""`open_penalty` over `x*` on our own designs, so the Kim margin becomes like for like.

    uv run python tools/xstar_competition.py --pairs 20 --stems 2

The Kim comparison was not comparable. His margin is ``|grip| - hold`` where ``hold`` is
``open_penalty`` on the **folded switch** -- what the whole fold charges to free trigger A's landing
region -- while ours used ``lock_energy``, a fixed-alignment energy of the secondary stem alone.
Ours therefore ignores everything else the switch could fold into and understates the hold. This
computes the missing term on our designs, with the same function Kim's side used.

**The region is `sw_xs`.** Reading the domain map 5'->3'::

    cap  r2_star  sw_x  k2_star  secondary_loop  secondary_z  sw_xs  main_pre_star ...

the secondary hairpin closes ``sw_x`` against ``sw_xs`` and ``k2_star`` against ``secondary_z``. So
``sw_xs`` is ``x*``: the segment trigger A must nucleate on, and the one the hairpin holds shut.

**And this exposes something about the architecture that Kim's does not share.** The switch's own
``sw_x`` is sequence-identical to trigger A's ``x`` -- it is the same gene window, copied forward --
so **A and the hairpin's own arm offer the same duplex to the same site.** A cannot win that
competition on binding energy; whatever tips it has to come from the rest of the fold, from the
entropy of an intermolecular pairing, or from kinetics. Kim's buried segment and his hairpin arm are
different sequences, so his margin can be positive on energy alone. Measured below rather than
asserted.

Runs through ``generate_designs`` on a sample of real PFAS pairs, so every design is the production
article. Deliberately small by default: the characterisation run may still be using the cores.
"""

from __future__ import annotations

import argparse
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# ruff: noqa: E402 - the engine imports must follow the sys.path insert.
from engine import sequences as sq
from engine.domain import Constraints, Host, TriggerCandidate, TriggerSet
from engine.gates.toehold import (
    KimSecondaryArmToeholdAndGate,
    ProkaryoticToeholdAndGate,
)
from engine.gates.tools.binding import fixed_alignment_energy
from engine.gates.tools.codons import CodonOptimizer
from engine.gates.tools.folding import FoldEngine
from engine.gates.tools.translation import TranslationScorer
from engine.stages.folding import FoldProfiler
from engine.transcriptome import load_transcriptome

GENE_PAIRS = (
    ("ggt", "b3447", "fadB", "b3846"),
    ("ggt", "b3447", "astC", "b1748"),
    ("ggt", "b3447", "aldA", "b1415"),
)


def spread(label: str, values: list[float], unit: str = "kcal/mol") -> None:
    if not values:
        print(f"  {label:36s} nothing measured")
        return
    values = sorted(values)
    print(
        f"  {label:34s}n {len(values):>6,}  min {values[0]:>7.2f}"
        f"  Q1 {values[len(values) // 4]:>7.2f}"
        f"  median {st.median(values):>7.2f}  Q3 {values[3 * len(values) // 4]:>7.2f}"
        f"  max {values[-1]:>7.2f}  mean {st.fmean(values):>7.2f}"
        f"  sd {st.stdev(values) if len(values) > 1 else 0.0:>6.2f}  {unit}"
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pairs", type=int, default=20, help="trigger pairs per gene pair")
    parser.add_argument("--stems", type=int, default=2, help="stems per pair")
    parser.add_argument("--cache", type=int, default=8_000)
    args = parser.parse_args(argv)

    folder = FoldEngine(cache_size=args.cache)
    profiler = FoldProfiler()
    book = load_transcriptome(Host.ECOLI)
    constraints = Constraints(stems_per_pair=args.stems, stem_order="front")

    gates = {}
    for cls in (ProkaryoticToeholdAndGate, KimSecondaryArmToeholdAndGate):
        gate = cls(
            host=Host.ECOLI,
            folder=folder,
            translation=TranslationScorer(Host.ECOLI),
            codons=CodonOptimizer(Host.ECOLI),
        )
        gates[gate.geometry_name] = gate
    scan = next(iter(gates.values()))

    hold_all, grip_all, margin_all, lock_all, identical = [], [], [], [], 0
    by_geom: dict[str, list[float]] = {}
    n_designs = 0

    for a_sym, a_id, b_sym, b_id in GENE_PAIRS:
        ta, tb = sq.to_rna(book[a_id]), sq.to_rna(book[b_id])
        src = {a_sym: ta, b_sym: tb}
        pairs = list(scan.find_cross_gene_pairs(a_sym, ta, b_sym, tb))
        scored = []
        for p in pairs:
            a0, a1 = p.window_a()
            b0, b1 = p.window_b()
            la = profiler.openness(src[p.gene_a], a0, a1)
            lb = profiler.openness(src[p.gene_b], b0, b1)
            scored.append((min(la, lb), p))
        scored.sort(key=lambda t: (-t[0], t[1].x_start))
        step = max(1, len(scored) // max(args.pairs, 1))
        taken = scored[::step][: args.pairs]
        print(
            f"  {a_sym} x {b_sym}: {len(pairs):,} pairs -> {len(taken)} sampled across the range",
            flush=True,
        )

        for worse, pair in taken:
            a0, a1 = pair.window_a()
            b0, b1 = pair.window_b()
            src_a = src[pair.gene_a]
            src_b = src[pair.gene_b]
            for geom, gate in gates.items():
                fa, fb = gate.role_footprints()
                window_a = src_a[a0 : a0 + fa]
                window_b = src_b[b1 - fb : b1]
                if len(window_a) != fa or len(window_b) != fb:
                    continue
                trigger_set = TriggerSet(
                    activators=(
                        TriggerCandidate(
                            trigger_id=f"A@{a0}",
                            gene_id=pair.gene_a,
                            symbol=pair.gene_a,
                            sequence=window_a,
                            start_index=a0,
                            openness=worse,
                            accessibility=worse,
                            mfe=0.0,
                            off_target_penalty=0.0,
                            segment_specificity=0.0,
                            gc_content=sq.gc_content(window_a),
                        ),
                        TriggerCandidate(
                            trigger_id=f"B@{b0}",
                            gene_id=pair.gene_b,
                            symbol=pair.gene_b,
                            sequence=window_b,
                            start_index=b0,
                            openness=worse,
                            accessibility=worse,
                            mfe=0.0,
                            off_target_penalty=0.0,
                            segment_specificity=0.0,
                            gc_content=sq.gc_content(window_b),
                        ),
                    )
                )
                try:
                    designs = list(gate.generate_designs(trigger_set, constraints))
                except Exception:
                    continue
                for design in designs:
                    spans = design.architecture.get("domain_map") or {}
                    region = spans.get("sw_xs")
                    sw_x = spans.get("sw_x")
                    if not region or not sw_x:
                        continue
                    lo, hi = int(region[0]), int(region[1])
                    switch = design.sequence
                    xstar = switch[lo:hi]
                    x_in_switch = switch[int(sw_x[0]) : int(sw_x[1])]
                    # What the WHOLE FOLD charges to free x*, the same function Kim's hold used.
                    hold = folder.open_penalty(switch, ((lo, hi),))
                    # What trigger A offers for the same site: its own `x`, which is the gene window
                    # at the overlap -- and which the switch already carries as `sw_x`.
                    x_of_a = window_a[gate.ARM_LEN : gate.ARM_LEN + pair.len_x]
                    grip = fixed_alignment_energy(x_of_a, xstar, folder)
                    if hold is None or grip is None:
                        continue
                    if x_of_a == x_in_switch:
                        identical += 1
                    hold_all.append(hold)
                    grip_all.append(grip)
                    margin_all.append(abs(grip) - hold)
                    lock = design.architecture.get("lock_energy")
                    if lock is not None:
                        lock_all.append(abs(float(lock)) - hold)
                    by_geom.setdefault(geom, []).append(abs(grip) - hold)
                    n_designs += 1
                    if n_designs % 200 == 0:
                        print(f"    {n_designs:,} designs measured", flush=True)

    print(f"\n  {n_designs:,} designs measured")
    print(
        f"  trigger A's `x` is sequence-identical to the switch's own `sw_x` in "
        f"{identical:,} of {n_designs:,} "
        f"({100.0 * identical / max(n_designs, 1):.1f}%)"
    )
    print("\n  the two terms, and the margin that cancels length:")
    spread("hold = open_penalty over x*", hold_all)
    spread("grip = A's x against x*", grip_all)
    spread("margin = |grip| - hold", margin_all)
    if margin_all:
        positive = sum(1 for v in margin_all if v > 0)
        print(
            f"\n  margin > 0 (A outbids the fold) in {positive:,} of {len(margin_all):,} "
            f"({100.0 * positive / len(margin_all):.1f}%)"
        )
        print(
            "  Kim's working construct sits at +3.86; his two non-gating ones at -1.32 and -5.61."
        )
    if lock_all:
        print("\n  and the term the earlier comparison used instead, on the same designs:")
        spread("|lock_energy| - hold", lock_all)
        print("  If this is far from the margin above, the earlier Kim comparison was reading a")
        print("  different quantity, which is exactly what it was corrected for.")
    for geom, values in sorted(by_geom.items()):
        spread(f"margin, {geom}", values)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
