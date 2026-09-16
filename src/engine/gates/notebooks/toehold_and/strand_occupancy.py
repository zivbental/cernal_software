"""Where does each strand actually go, in each of the four tubes?

    uv run python src/engine/gates/notebooks/toehold_and/strand_occupancy.py \\
        --fasta "path/to/mCherry original.txt"

**Why this exists.** Three earlier audits established that ``p_open``, ``A_M`` and
``dG_open`` are computed correctly — agreement to 0.01 kcal/mol against independent
re-derivations. None of them explains *why* ``dG_open(10)`` equals ``dG_open(11)`` on every
candidate, under every perturbation of the main hairpin we have tried. That equality has
now survived 40 spacer variants over 10 trigger pairs, a bulge inversion, and Kim 2019's
four published constructs, so it wants an explanation that is not another energy.

This asks a structural question instead: for each tube, how many nucleotides of each strand
are paired, and to what? It sums the pair-probability matrix over strand-by-strand blocks,
so each entry reads directly as an expected number of paired bases. No thresholds, no
single representative structure, nothing to tune.

**The answer it gives.** Trigger A occupies essentially all of its 36 nt on the switch in
state 10 *and* in state 11 — the two differ by ~0.004 nt. Trigger B binds just as
completely in 01 and in 11, and the two triggers do not pair with each other. Adding
trigger B does change the molecule, destroying ~17 bp of the switch's own structure, but
that structure is the secondary hairpin, which lies outside ``W_rank``. So trigger A alone
already reaches the final state inside the ribosome window, and the architecture's premise
— that B unlocks the site A needs — does not constrain the equilibrium end state. That is
the state-10 leak, stated without reference to any threshold.
"""

import argparse
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


def occupancy(folder, strands: str, lengths: list[tuple[str, int]]) -> dict[str, float]:
    """Expected paired bases for every pair of strands in one tube.

    The matrix is indexed over the concatenation with the ``&`` removed, strands in the
    order given, so a block sum is an expected count of paired nucleotides between those
    two strands. Within one strand the block is summed over ``i < j`` only, since the
    matrix is symmetric and a pair would otherwise be counted twice.
    """
    matrix = folder.base_pair_probabilities(strands)
    spans, cursor = {}, 0
    for name, length in lengths:
        spans[name] = (cursor, cursor + length)
        cursor += length
    if len(matrix) < cursor:
        raise ValueError(f"matrix is {len(matrix)} for {cursor} nt of strands")

    names = list(spans)
    out: dict[str, float] = {}
    for index, first in enumerate(names):
        for second in names[index:]:
            start_a, end_a = spans[first]
            start_b, end_b = spans[second]
            if first == second:
                total = sum(
                    matrix[i][j] for i in range(start_a, end_a) for j in range(i + 1, end_a)
                )
            else:
                total = sum(
                    matrix[i][j] for i in range(start_a, end_a) for j in range(start_b, end_b)
                )
            out[f"{first}:{second}"] = total
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fasta", required=True)
    parser.add_argument("--pairs", type=int, default=1, help="trigger pairs to audit")
    args = parser.parse_args(argv)

    gate = ProkaryoticToeholdAndGate(
        Host.ECOLI, FoldEngine(37.0), TranslationScorer(Host.ECOLI), CodonOptimizer(Host.ECOLI)
    )
    transcript = read_fasta(args.fasta)

    pairs = []
    for pair in gate.find_trigger_pairs(transcript):
        start, end = pair.window_a()
        if gate.screen_trigger_window(transcript[start:end], transcript[pair.x_start - 9 :][:9]):
            continue
        pairs.append(pair)
    pairs.sort(key=lambda p: (-p.len_x, -p.gap()))

    for pair in pairs[: args.pairs]:
        trigger_a = transcript[slice(*pair.window_a())]
        trigger_b = transcript[slice(*pair.window_b())]
        stem = gate.secondary_stems(trigger_a, trigger_b, pair.len_x)[0]
        switch = gate.assemble(trigger_a, trigger_b, pair.len_x, stem)
        sizes = (len(switch.sequence), len(trigger_a), len(trigger_b))
        print(
            f"\n=== pair x@{pair.x_start} len_x={pair.len_x} {stem.scheme}: "
            f"switch {sizes[0]} nt, A {sizes[1]} nt, B {sizes[2]} nt ==="
        )
        print(
            f"  {'tube':<12}{'A on switch':>14}{'B on switch':>14}"
            f"{'switch on itself':>18}{'A on B':>9}"
        )
        tubes = {
            "00 (neither)": (switch.sequence, [("S", sizes[0])]),
            "01 (B only)": (f"{switch.sequence}&{trigger_b}", [("S", sizes[0]), ("B", sizes[2])]),
            "10 (A only)": (f"{switch.sequence}&{trigger_a}", [("S", sizes[0]), ("A", sizes[1])]),
            "11 (both)": (
                f"{switch.sequence}&{trigger_a}&{trigger_b}",
                [("S", sizes[0]), ("A", sizes[1]), ("B", sizes[2])],
            ),
        }
        for label, (strands, lengths) in tubes.items():
            got = occupancy(gate.folder, strands, lengths)
            cells = [got.get("S:A"), got.get("S:B"), got.get("S:S"), got.get("A:B")]
            print(
                f"  {label:<12}"
                + "".join(
                    f"{value:>{width}.3f}" if value is not None else " " * (width - 1) + "-"
                    for value, width in zip(cells, (14, 14, 18, 9), strict=True)
                )
            )
        print(
            "\n  Trigger A's occupancy is the same in 10 and 11, so nothing is left for B to\n"
            "  enable inside the ribosome window. What B does change is the switch's own\n"
            "  structure -- the secondary hairpin, outside W_rank."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
