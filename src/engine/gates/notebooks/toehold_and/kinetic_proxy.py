"""A kinetic proxy, reported beside the equilibrium numbers and never scored.

    uv run python src/engine/gates/notebooks/toehold_and/kinetic_proxy.py \\
        --fasta "path/to/mCherry original.txt" --pairs 3 --out kinetic

**Why this exists, and why it is not a metric.** Every number this project ranks on is an
equilibrium end state. Kim 2019 attribute their working AND gate to *binding probability* and
enforced *sequential binding* — rate quantities that an end-state model cannot represent, and
the reason their bench-validated gate fails our tau4a with the same numbers as a switch that
does not gate at all. Section 4.5 of the design document predicted exactly this. So the
honest thing is to compute a rate proxy, print it next to the equilibrium result, and let a
human see whether the two disagree — **not** to fold it into an objective function and start
optimising against a quantity this crude.

**The proxy.** Toehold-mediated strand displacement nucleates on whatever single-stranded
foothold the invader can find, and its rate rises steeply with the length of that foothold
before saturating. Trigger A's only foothold is ``x*``. So:

* ``free(s)`` — the probability that a base of ``x*`` is unpaired in state ``s``, from the
  same pooled matrix as everything else;
* ``toehold_eff(s) = len_x * free(s)`` — the expected number of free nucleotides there;
* the rate advantage of the ON state over the leak state, in decades, taking roughly one
  order of magnitude per nucleotide up to saturation.

**Every one of those steps is an approximation, and the constants are borrowed.** The
one-decade-per-nucleotide slope and the ~6-nt saturation come from Zhang & Winfree 2009,
which measured **DNA** at 25 °C in a different buffer; we are folding **RNA** at 37 °C.
Treat the output as an order-of-magnitude argument about *whether kinetics could rescue a
design our equilibrium model rejects*, not as a prediction of a rate. It is reported to two
significant figures at most, and never enters a score, a threshold or a ranking.

**What it is for.** If a design shows no equilibrium separation but a large kinetic
advantage, then the equilibrium model is the thing that is wrong about it, and the bench will
say so. If a design shows neither, it is dead on both readings. Distinguishing those two
cases is the whole point, and no equilibrium observable can do it.
"""

import argparse
import csv
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

#: Zhang & Winfree 2009, JACS 131:17303 -- displacement rate spans ~6 orders of magnitude as
#: the toehold grows 0 to 6 nt, then saturates. DNA, 25 C, 1 M Na+. Borrowed, not measured
#: here, and the single largest source of error in this file.
DECADES_PER_NT = 1.0
SATURATION_NT = 6.0


def read_fasta(path: str) -> str:
    lines = Path(path).read_text().splitlines()
    return sq.to_rna("".join(line.strip() for line in lines if not line.startswith(">")))


def free_fraction(matrix, span) -> float:
    """Mean probability that a base of ``span`` is unpaired."""
    width = span[1] - span[0]
    return sum(max(0.0, 1.0 - sum(matrix[i])) for i in range(*span)) / width


def decades(toehold_nt: float) -> float:
    """Rate contribution of a foothold of this length, in orders of magnitude."""
    return DECADES_PER_NT * min(SATURATION_NT, max(0.0, toehold_nt))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fasta", required=True)
    parser.add_argument("--pairs", type=int, default=3)
    parser.add_argument("--stem", default="strongest")
    parser.add_argument("--out", default="kinetic")
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
    print(
        f"  {'design':<22}{'len_x':>6}{'free(10)':>10}{'free(11)':>10}"
        f"{'toehold 10':>12}{'toehold 11':>12}{'rate 11/10':>13}{'equil sep':>11}"
    )
    for pair in kept[: args.pairs]:
        trigger_a = transcript[slice(*pair.window_a())]
        trigger_b = transcript[slice(*pair.window_b())]
        stems = gate.secondary_stems(trigger_a, trigger_b, pair.len_x)
        stem = (
            min(stems, key=lambda s: s.lock_energy)
            if args.stem == "strongest"
            else stems[int(args.stem)]
        )
        base = gate.assemble(trigger_a, trigger_b, pair.len_x, stem)
        built = mp.variants(gate, base, trigger_a)
        for name in ("baseline", "aug_paired"):
            switch = built[name]
            site = switch.domains["sw_xs"]
            tubes = {
                "10": f"{switch.sequence}&{trigger_a}",
                "11": f"{switch.sequence}&{trigger_a}&{trigger_b}",
            }
            free = {
                state: free_fraction(gate.folder.pooled_pair_probabilities(strands), site)
                for state, strands in tubes.items()
            }
            toehold = {state: pair.len_x * value for state, value in free.items()}
            advantage = decades(toehold["11"]) - decades(toehold["10"])
            observed = mp.observe(gate, switch, trigger_a, trigger_b)
            label = f"x@{pair.x_start} {name}"
            rows.append(
                {
                    "x_start": pair.x_start,
                    "len_x": pair.len_x,
                    "variant": name,
                    "lock_energy": stem.lock_energy,
                    "free_10": free["10"],
                    "free_11": free["11"],
                    "toehold_eff_10": toehold["10"],
                    "toehold_eff_11": toehold["11"],
                    "log10_rate_advantage": advantage,
                    "separation": observed["separation"],
                    "A_M_10": observed["A_M_10"],
                    "A_M_11": observed["A_M_11"],
                }
            )
            print(
                f"  {label:<22}{pair.len_x:>6}{free['10']:>10.4f}{free['11']:>10.4f}"
                f"{toehold['10']:>12.2f}{toehold['11']:>12.2f}"
                f"{'10^' + format(advantage, '.1f'):>13}{observed['separation']:>11.2f}",
                flush=True,
            )

    path = output_dir / f"{args.out}.csv"
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n{len(rows)} rows -> {path}")

    print("\nRead the last two columns against each other. A design with no equilibrium")
    print("separation but a large rate advantage is one our model rejects and the bench")
    print("might not. A design with neither is dead on both readings.")
    print("\nThe slope and saturation are borrowed from a DNA study at 25 C. This is an")
    print("order-of-magnitude argument, not a rate, and it is in no score anywhere.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
