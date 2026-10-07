"""The ribosome window as probabilities, base by base, in all four tubes.

    uv run python src/engine/gates/notebooks/toehold_and/window_probabilities.py \\
        --fasta "path/to/mCherry original.txt"

**Why probabilities and not energies.** Everything the gate is scored on is reported as a
free energy, and a free energy is a logarithm — it compresses a factor of 10⁹ into the
width of a table column. ``dG_open`` of 21.58 against 7.59 kcal/mol sounds like a factor of
three; it is a factor of **7.2 x 10⁹**. Asking to see the probabilities is asking to see
the number before the logarithm hid its scale, and it is the right thing to look at.

**Two things to read carefully.**

*The joint number is severe.* ``P_open`` is the probability that **all thirty** nucleotides
of ``W_rank`` are unpaired *at the same instant*. That is a hard condition, so the number
is tiny even when the gate is fully ON — around 4 x 10⁻⁶ here. It is therefore **not** "the
fraction of transcripts a ribosome can load", and quoting it as one will mislead. Only
ratios between tubes mean anything.

*The per-base numbers are gentle.* ``P_unpaired(i)`` is the probability that one base is
unpaired, ignoring the others, and runs 0 to 1 in a readable way. It is what to plot. Its
mean over the **main stem** — ``mainZ+AUG+main_pre``, 18 of these 30 nt — is ``A_M``; its
mean over the whole 30-nt window is a different number (0.66 against 0.46 here), and the
two are easy to confuse, so both are printed. The joint and per-base views disagree in feel
and agree in fact: the gap is the correlation between neighbouring bases, since a stem
closes a whole block at once.

**The thing this view shows that the averages hide.** Read the ``AUG only`` column. In the
OFF state the start codon is **96% unpaired** — R7 puts it in a 3x3 internal loop, so the
closed hairpin leaves it exposed — and when trigger A binds it drops to **34%**. Every
average over the window moves the other way (``A_M`` 0.17 -> 0.46), because trigger A does
open the stem around it. So the aggregate says the gate turned on while the start codon
itself became less accessible than it was in the OFF state. Whether that matters is a
question about initiation, not about this number, but no averaged metric we score can see
it.

**The measurement floor is printed with the numbers, deliberately.** ViennaRNA's partition
function returns single precision, so every energy lands on a grid about 1.5 x 10⁻⁵
kcal/mol wide and a difference of two on a grid about 3 x 10⁻⁵ wide. Differences smaller
than that are unresolved, not zero, and this script says so rather than printing a clean
0.00 and letting a reader believe it was proven.

**What it shows on the current design.** States 10 and 11 agree at every base to ~10⁻¹⁵,
while the same comparison over trigger B's own binding site differs by up to 0.999. Trigger
B is doing a great deal to the molecule and none of it to the ribosome window.
"""

import argparse
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[4]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from engine import sequences as sq  # noqa: E402
from engine.domain import Host  # noqa: E402
from engine.gates.toehold import ProkaryoticToeholdAndGate, _mean_unpaired  # noqa: E402
from engine.gates.tools.codons import CodonOptimizer  # noqa: E402
from engine.gates.tools.folding import _FLOAT32_ENERGY_ULP, FoldEngine  # noqa: E402
from engine.gates.tools.translation import TranslationScorer  # noqa: E402

STATES = ("00", "01", "10", "11")


def read_fasta(path: str) -> str:
    lines = Path(path).read_text().splitlines()
    return sq.to_rna("".join(line.strip() for line in lines if not line.startswith(">")))


def unpaired_profile(matrix: list[list[float]], start: int, end: int) -> list[float]:
    """``P(unpaired)`` per position over ``[start, end)``."""
    return [max(0.0, 1.0 - sum(matrix[i])) for i in range(start, end)]


def domain_at(switch, index: int) -> str:
    for name, (start, end) in switch.domains.items():
        if start <= index < end:
            return name
    return "-"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fasta", required=True)
    parser.add_argument("--pairs", type=int, default=1, help="trigger pairs to report")
    parser.add_argument(
        "--stem",
        type=int,
        default=0,
        help="which build on the secondary-stem Pareto front (0 is the all-'both' "
        "'unlocked' build, the one with no inhibitory lock anywhere)",
    )
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
        stems = gate.secondary_stems(trigger_a, trigger_b, pair.len_x)
        stem = stems[args.stem]
        switch = gate.assemble(trigger_a, trigger_b, pair.len_x, stem)
        rank = switch.span(-17, 13)
        tubes = {
            "00": switch.sequence,
            "01": f"{switch.sequence}&{trigger_b}",
            "10": f"{switch.sequence}&{trigger_a}",
            "11": f"{switch.sequence}&{trigger_a}&{trigger_b}",
        }

        print(f"\n=== pair x@{pair.x_start} len_x={pair.len_x} · stem {args.stem} ")
        print(f"    of {len(stems)} on the Pareto front, scheme '{stem.scheme}' ===")
        print(f"    W_rank = offsets -17..+13 = switch[{rank[0]}:{rank[1]}], 30 nt")
        print(f"    resolution floor on any energy difference: {_FLOAT32_ENERGY_ULP:.1e} kcal/mol")

        profiles = {}
        joint = {}
        for state, strands in tubes.items():
            matrix = gate.folder.pooled_pair_probabilities(strands)
            profiles[state] = unpaired_profile(matrix, *rank)
            joint[state] = gate.folder.p_open(strands, rank)

        print("\n  JOINT probability that all 30 bases are open at once (what p_open means):")
        print(f"    {'state':<8}{'P_open':>16}{'relative to state 11':>24}")
        for state in STATES:
            ratio = joint[state] / joint["11"] if joint["11"] else float("nan")
            print(f"    {state:<8}{joint[state]:>16.6e}{ratio:>24.4e}")
        print("    ^ tiny in every tube, ON included. Read the ratios, never the absolutes.")

        print("\n  PER-BASE probability that one base is open (this is what to plot):")
        header = f"    {'off':>4} {'base':>4} {'domain':<14}"
        header += "".join(f"{'P(' + s + ')':>10}" for s in STATES) + f"{'11 - 10':>12}"
        print(header)
        for k in range(rank[1] - rank[0]):
            index = rank[0] + k
            offset = k - 17 if k < 17 else k - 16  # no zero offset: -1 is followed by +1
            values = [profiles[s][k] for s in STATES]
            print(
                f"    {offset:>+4} {switch.sequence[index]:>4} {domain_at(switch, index):<14}"
                + "".join(f"{v:>10.4f}" for v in values)
                + f"{values[3] - values[2]:>12.2e}"
            )

        # A_M is NOT the mean over W_rank: it is the mean over the main stem,
        # mainZ+AUG+main_pre, which is 18 of these 30 nt. Printed side by side because
        # conflating them is an easy and invisible mistake -- they differ by 0.20 here.
        stem_span = (switch.domains["main_z"][0], switch.domains["main_pre"][1])
        aug_span = switch.domains["aug"]
        print("\n  Summary, as probabilities:")
        print(
            f"    {'state':<8}{'mean over W_rank':>18}{'A_M (main stem)':>18}"
            f"{'AUG only':>12}{'minimum':>12}{'>0.5 of 30':>12}{'joint':>13}"
        )
        for state in STATES:
            values = profiles[state]
            matrix = gate.folder.pooled_pair_probabilities(tubes[state])
            print(
                f"    {state:<8}{sum(values) / len(values):>18.6f}"
                f"{_mean_unpaired(matrix, *stem_span):>18.6f}"
                f"{_mean_unpaired(matrix, *aug_span):>12.6f}{min(values):>12.6f}"
                f"{sum(1 for v in values if v > 0.5):>12}{joint[state]:>13.3e}"
            )
        print(
            "    ^ read the AUG column against the others. The averages go UP when\n"
            "      trigger A binds while the start codon itself goes DOWN: in the OFF\n"
            "      state the AUG sits unpaired in R7's 3x3 bulge, and trigger A buries it."
        )

        biggest = max(
            range(len(profiles["10"])), key=lambda k: abs(profiles["11"][k] - profiles["10"][k])
        )
        print(
            f"\n  Largest per-base difference between states 10 and 11 anywhere in the "
            f"window:\n    {abs(profiles['11'][biggest] - profiles['10'][biggest]):.3e} "
            f"at offset {biggest - 17 if biggest < 17 else biggest - 16}"
        )

        # The contrast that makes the number above mean something: trigger B is not inert,
        # it simply acts somewhere the ribosome does not read.
        b_site = (switch.domains["r2_star"][0], switch.domains["sw_x"][1])
        contrast = {}
        for state in ("10", "11"):
            matrix = gate.folder.pooled_pair_probabilities(tubes[state])
            contrast[state] = unpaired_profile(matrix, *b_site)
        gap = max(abs(x - y) for x, y in zip(contrast["11"], contrast["10"], strict=True))
        print(
            f"  Same comparison over trigger B's own site (r2*+sw_x, "
            f"switch[{b_site[0]}:{b_site[1]}]):\n    {gap:.3f}"
        )
        print(
            "\n  So trigger B changes the molecule a great deal and the ribosome window\n"
            "  not at all. That is the state-10 leak, in probabilities."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
