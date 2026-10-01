"""Can the AUG-closure choice be made separately from the secondary-stem choice?

    uv run python src/engine/gates/notebooks/toehold_and/factorisation.py \\
        --fasta "path/to/mCherry original.txt" --stems 10 --out factorisation

**Why it matters for the pipeline, not just for the science.** Scheme C emits a Pareto front
of dozens of secondary stems per trigger pair, and there are now three sensible AUG-closure
depths. Evaluating every combination is ``stems x closures`` four-tube folds per candidate,
which is the difference between an afternoon and a week. If the two choices **factorise** —
if the closure that wins is the same whichever stem it sits on, and the stem that wins is the
same whichever closure it carries — the pipeline can pick the stem first on a cheap scalar and
then fold only the closures, turning a product into a sum.

**But they are known not to be independent.** Closing the AUG does nothing on a lock-free
stem, and a strong lock does nothing without the closure; that interaction is the central
result of the architecture review. So the question is narrower and more useful: **is lock
energy a sufficient statistic for the secondary stem?** If separation under closure is a
function of ``lock_energy`` alone, the scheme label (A-anchored, B-anchored, mixed, unlocked)
carries no extra information and the front can be reduced to its strongest-lock member before
any closure is folded.

**What this measures.** For one trigger pair, stems spanning the whole lock-energy range and
every scheme, each folded at every closure depth. Then two questions, answered with numbers:

1. Does the ranking of closure depths change from stem to stem? If it does not, closure can
   be chosen once.
2. Within a scheme, does separation track lock energy? And at matched lock energy, do
   different schemes differ? If lock energy explains it, the scheme label can be dropped.

Reported as a full stem-by-closure grid rather than a summary, because a factorisation claim
is exactly the kind that a median hides.
"""

import argparse
import csv
import math
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[4]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from engine import sequences as sq  # noqa: E402
from engine.domain import Host  # noqa: E402
from engine.gates.toehold import ProkaryoticToeholdAndGate  # noqa: E402
from engine.gates.tools.codons import CodonOptimizer  # noqa: E402
from engine.gates.tools.folding import FoldEngine  # noqa: E402
from engine.gates.tools.translation import TranslationScorer  # noqa: E402

CLOSURES = ("baseline", "aug_pair1", "aug_pair2", "aug_paired")


def read_fasta(path: str) -> str:
    lines = Path(path).read_text().splitlines()
    return sq.to_rna("".join(line.strip() for line in lines if not line.startswith(">")))


def spearman(pairs):
    def ranks(values):
        order = sorted(range(len(values)), key=lambda i: values[i])
        out = [0.0] * len(values)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
                j += 1
            shared = (i + j) / 2 + 1
            for k in range(i, j + 1):
                out[order[k]] = shared
            i = j + 1
        return out

    if len(pairs) < 3:
        return math.nan
    xs, ys = ranks([p[0] for p in pairs]), ranks([p[1] for p in pairs])
    n = len(pairs)
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return cov / (sx * sy) if sx and sy else math.nan


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fasta", required=True)
    parser.add_argument("--pair", type=int, default=0, help="index into the surviving pairs")
    parser.add_argument("--stems", type=int, default=10, help="stems to sample across the front")
    parser.add_argument("--out", default="factorisation")
    args = parser.parse_args(argv)

    import modification_panel as mp

    output_dir = Path(__file__).resolve().parent / "results"
    output_dir.mkdir(parents=True, exist_ok=True)
    gate = ProkaryoticToeholdAndGate(
        Host.ECOLI, FoldEngine(37.0), TranslationScorer(Host.ECOLI), CodonOptimizer(Host.ECOLI)
    )
    transcript = read_fasta(args.fasta)

    kept = []
    for pair in gate.find_trigger_pairs(transcript):
        start, end = pair.window_a()
        if gate.screen_trigger_window(transcript[start:end], transcript[pair.x_start - 9 :][:9]):
            continue
        kept.append(pair)
    kept.sort(key=lambda p: (-p.len_x, -p.gap(), p.x_start))
    pair = kept[args.pair]

    trigger_a = transcript[slice(*pair.window_a())]
    trigger_b = transcript[slice(*pair.window_b())]
    stems = sorted(
        gate.secondary_stems(trigger_a, trigger_b, pair.len_x), key=lambda s: s.lock_energy
    )
    step = max(1, len(stems) // args.stems)
    chosen = stems[::step][: args.stems]
    print(
        f"pair x@{pair.x_start} len_x={pair.len_x}: {len(stems)} stems on the front, "
        f"folding {len(chosen)} across lock {chosen[0].lock_energy:.1f} to "
        f"{chosen[-1].lock_energy:.1f}\n"
    )

    header = f"  {'lock':>7} {'scheme':<12}"
    for closure in CLOSURES:
        header += f"{closure:>12}"
    print(header + "     (separation)")

    rows = []
    for stem in chosen:
        switch = gate.assemble(trigger_a, trigger_b, pair.len_x, stem)
        built = mp.variants(gate, switch, trigger_a)
        line = f"  {stem.lock_energy:>7.1f} {stem.scheme:<12}"
        per_stem = {}
        for closure in CLOSURES:
            o = mp.observe(gate, built[closure], trigger_a, trigger_b)
            per_stem[closure] = o["separation"]
            rows.append(
                {
                    "x_start": pair.x_start,
                    "lock_energy": stem.lock_energy,
                    "scheme": stem.scheme,
                    "ddg_pref": stem.ddg_pref,
                    "closure": closure,
                    "separation": o["separation"],
                    "mean_separation": o["mean_separation"],
                    "A_M_10": o["A_M_10"],
                    "A_M_11": o["A_M_11"],
                    "aug_11": o["aug_11"],
                }
            )
            line += f"{o['separation']:>12.2f}"
        best = max(per_stem, key=lambda c: per_stem[c])
        print(line + f"   best: {best}", flush=True)

    path = output_dir / f"{args.out}.csv"
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n{len(rows)} rows -> {path}")

    # Question 1: does the winning closure change from stem to stem?
    #
    # Asked only of stems where SOMETHING works. On a stem where all four closures return
    # 0.00, "which won" is a tie broken by floating-point noise; counting those manufactures
    # a disagreement out of nothing. An earlier version of this analysis did exactly that and
    # concluded "they do not factorise" from seven stems that were dead at every closure.
    live_threshold = 0.5  # kcal/mol -- below this it is not a working gate on any reading
    winners: dict[str, int] = {}
    dead = 0
    for stem in chosen:
        sub = [
            r for r in rows if r["lock_energy"] == stem.lock_energy and r["scheme"] == stem.scheme
        ]
        best = max(sub, key=lambda r: r["separation"] if r["separation"] is not None else -99)
        if best["separation"] is None or best["separation"] < live_threshold:
            dead += 1
            continue
        winners[best["closure"]] = winners.get(best["closure"], 0) + 1
    print(f"\nQ1. Which closure wins, where any clears {live_threshold} kcal/mol:")
    print(f"  {dead} of {len(chosen)} stems are dead at every closure -- excluded, not counted")
    for closure, count in sorted(winners.items(), key=lambda kv: -kv[1]):
        print(f"  {closure:<14} wins on {count} of {len(chosen) - dead} live stems")
    if not winners:
        print("  -> no stem here supports any closure; nothing can be concluded")
    elif len(winners) == 1:
        print("  -> the same closure wins on every live stem; closure can be chosen once")
    else:
        print("  -> the winning closure depends on the stem")

    # Question 2: is lock energy a sufficient statistic for the stem?
    print("\nQ2. Is lock energy enough, or does the scheme add information?")
    for closure in CLOSURES:
        sub = [r for r in rows if r["closure"] == closure and r["separation"] is not None]
        rho = spearman([(r["lock_energy"], r["separation"]) for r in sub])
        print(f"  {closure:<14} separation vs lock energy: rho {rho:+.3f}  n {len(sub)}")
    print("\n  separation by scheme, at each closure (medians):")
    schemes = sorted({r["scheme"] for r in rows})
    print(f"    {'closure':<14}" + "".join(f"{s:>13}" for s in schemes))
    for closure in CLOSURES:
        line = f"    {closure:<14}"
        for scheme in schemes:
            vals = sorted(
                r["separation"]
                for r in rows
                if r["closure"] == closure and r["scheme"] == scheme and r["separation"] is not None
            )
            line += f"{vals[len(vals) // 2]:>13.2f}" if vals else f"{'-':>13}"
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
