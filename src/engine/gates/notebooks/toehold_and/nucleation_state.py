"""Who is holding trigger A's nucleation site: the switch, trigger A, or nobody?

    uv run python src/engine/gates/notebooks/toehold_and/nucleation_state.py \\
        --fasta "path/to/mCherry original.txt" --stems 10 --out nucleation

``A_S`` is an *unpaired* probability over ``sw_xs`` (the ``x*`` site), so it cannot tell
"held shut by the switch's own stem" from "held by trigger A" &mdash; both are paired, and
both read as inaccessible. Those are opposite situations: the first is the lock doing its
job, the second is the leak. This decomposes the same pair-probability matrix three ways:

``locked``
    ``x*`` paired to ``sw_x``, its partner in the inhibitory hairpin. The lock holding.
``engaged``
    ``x*`` paired to trigger A. The nucleation site taken, which in state 10 is the leak and
    in state 11 is the mechanism.
``free``
    ``x*`` unpaired. Available but unused.

The three are read from the pooled matrix, so they include every strand ordering rather than
whichever one the caller happened to type.

**What it is for.** ``lock_energy`` predicts whether closing the AUG produces a working gate,
but it is a *proxy*: a number scheme C computes for a duplex, not a measurement of the
molecule. ``locked(10)`` is the physical quantity it stands in for &mdash; is ``x*`` actually
sequestered when trigger A is present and trigger B is not. This measures both on the same
stems and asks which predicts the outcome better, so the pipeline can select on the right
one. Both are reported per stem; neither is assumed.
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


def read_fasta(path: str) -> str:
    lines = Path(path).read_text().splitlines()
    return sq.to_rna("".join(line.strip() for line in lines if not line.startswith(">")))


def decompose(matrix, site, partner, strands) -> dict[str, float]:
    """Mean probability per base of ``site`` that it is locked, engaged, or free.

    ``partner`` is the ``(start, end)`` of ``sw_x`` inside the switch; ``strands`` maps a
    label to the ``(start, end)`` of each trigger in the concatenation. Everything not
    accounted for is pairing to somewhere else entirely and is reported as ``other``, rather
    than folded into one of the three and hidden.
    """
    width = site[1] - site[0]
    out = {"locked": 0.0, "engaged_A": 0.0, "engaged_B": 0.0, "free": 0.0, "other": 0.0}
    for i in range(*site):
        row = matrix[i]
        paired = sum(row)
        locked = sum(row[j] for j in range(*partner))
        by_strand = {label: sum(row[j] for j in range(*span)) for label, span in strands.items()}
        out["locked"] += locked
        out["engaged_A"] += by_strand.get("A", 0.0)
        out["engaged_B"] += by_strand.get("B", 0.0)
        out["free"] += max(0.0, 1.0 - paired)
        out["other"] += max(0.0, paired - locked - sum(by_strand.values()))
    return {key: value / width for key, value in out.items()}


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
    parser.add_argument("--pairs", type=int, default=2, help="trigger pairs to sample")
    parser.add_argument("--stems", type=int, default=8, help="stems per pair across the front")
    parser.add_argument("--out", default="nucleation")
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

    rows = []
    for pair in kept[: args.pairs]:
        trigger_a = transcript[slice(*pair.window_a())]
        trigger_b = transcript[slice(*pair.window_b())]
        stems = sorted(
            gate.secondary_stems(trigger_a, trigger_b, pair.len_x), key=lambda s: s.lock_energy
        )
        step = max(1, len(stems) // args.stems)
        chosen = stems[::step][: args.stems]
        print(f"\n=== pair x@{pair.x_start} len_x={pair.len_x}, {len(chosen)} stems ===")
        print(
            f"  {'lock':>7} {'scheme':<12}{'locked(10)':>12}{'engagedA(10)':>14}"
            f"{'free(10)':>10}{'locked(00)':>12}{'sep|closed':>12}"
        )
        for stem in chosen:
            switch = gate.assemble(trigger_a, trigger_b, pair.len_x, stem)
            site = switch.domains["sw_xs"]
            partner = switch.domains["sw_x"]
            length = len(switch.sequence)

            tubes = {
                "00": (switch.sequence, {}),
                "10": (
                    f"{switch.sequence}&{trigger_a}",
                    {"A": (length, length + len(trigger_a))},
                ),
                "11": (
                    f"{switch.sequence}&{trigger_a}&{trigger_b}",
                    {
                        "A": (length, length + len(trigger_a)),
                        "B": (
                            length + len(trigger_a),
                            length + len(trigger_a) + len(trigger_b),
                        ),
                    },
                ),
            }
            state = {}
            for label, (strands, spans) in tubes.items():
                matrix = gate.folder.pooled_pair_probabilities(strands)
                state[label] = decompose(matrix, site, partner, spans)

            closed = mp.observe(
                gate, mp.variants(gate, switch, trigger_a)["aug_paired"], trigger_a, trigger_b
            )
            row = {
                "x_start": pair.x_start,
                "len_x": pair.len_x,
                "scheme": stem.scheme,
                "lock_energy": stem.lock_energy,
                "separation_closed": closed["separation"],
                "A_M_11_closed": closed["A_M_11"],
                "aug_11_closed": closed["aug_11"],
            }
            for label, values in state.items():
                for key, value in values.items():
                    row[f"{key}_{label}"] = value
            rows.append(row)
            print(
                f"  {stem.lock_energy:>7.1f} {stem.scheme:<12}"
                f"{state['10']['locked']:>12.3f}{state['10']['engaged_A']:>14.3f}"
                f"{state['10']['free']:>10.3f}{state['00']['locked']:>12.3f}"
                f"{closed['separation']:>12.2f}",
                flush=True,
            )

    path = output_dir / f"{args.out}.csv"
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n{len(rows)} rows -> {path}")

    print("\nWhich predicts whether closing the AUG produces a gate?")
    for field in (
        "lock_energy",
        "locked_10",
        "engaged_A_10",
        "free_10",
        "locked_00",
    ):
        data = [
            (r[field], r["separation_closed"])
            for r in rows
            if r.get(field) is not None and r["separation_closed"] is not None
        ]
        print(f"  {field:<16} vs separation(closed): rho {spearman(data):+.3f}  n {len(data)}")

    print("\nState 11, as a check that the mechanism is what we think:")
    for label in ("locked", "engaged_A", "free"):
        values = [r[f"{label}_11"] for r in rows if r.get(f"{label}_11") is not None]
        if values:
            ordered = sorted(values)
            print(
                f"  {label:<10} median {ordered[len(ordered) // 2]:.3f}  "
                f"min {ordered[0]:.3f}  max {ordered[-1]:.3f}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
