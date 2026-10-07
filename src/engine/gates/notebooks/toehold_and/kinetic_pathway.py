"""The kinetic test done properly: what foothold does trigger A see *before* it binds?

    uv run python src/engine/gates/notebooks/toehold_and/kinetic_pathway.py \\
        --fasta "path/to/mCherry original.txt" --pairs 4 --out kinetic_pathway

**What the first attempt got wrong.** ``kinetic_proxy.py`` read ``free(x*)`` out of tubes 10
and 11 and found no difference. Of course it did: those are *post-binding* equilibria, in
which trigger A is already bound in both. Asking how accessible the nucleation site is after
the invader has taken it is not a kinetic question at all.

**The right question is what trigger A finds on arrival**, which means reading the foothold
off the configuration the switch is in *before* A binds. The two paths differ in exactly that:

* **Path to state 10** — trigger A arrives at a switch with no trigger bound, so its foothold
  is ``free(x*)`` in tube **00**, where the inhibitory hairpin is shut.
* **Path to state 11** — trigger B binds first and opens the inhibitory hairpin, so trigger A
  arrives at a switch in configuration **01** and its foothold is ``free(x*)`` there.

That ordering is not an assumption bolted on: trigger B's own toehold ``r2*`` is 32 nt and
fully exposed in the OFF state, while trigger A's is ``len_x`` nucleotides and sequestered.
B binds first because it is the only one of the two that *can* bind quickly. This is Kim
2019's "sequential binding", made computable — and it is the mechanism an end-state model
structurally cannot see, because at equilibrium both paths terminate in the same place.

**The rate model, and every borrowed constant in it.** Toehold-mediated displacement rises
about **one order of magnitude per nucleotide** of toehold and saturates near **6 nt**
(Zhang & Winfree 2009, JACS 131:17303). Those numbers were measured on **DNA at 25 °C in
1 M Na+**; we fold **RNA at 37 °C**. The slope and the saturation point are therefore
borrowed, not derived, and they are the dominant error in everything below. The *ratio*
between two paths is more defensible than either absolute rate, because the borrowed
constants partly cancel.

**This is reported and never scored.** It does not enter an objective function, a threshold
or a ranking. Its job is to answer one question: is there a design whose equilibrium
separation is zero but whose kinetic advantage is large? If so, our model rejects designs the
bench may well accept, and the whole architecture review needs re-reading in that light.
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
from engine.gates.tools.binding import fixed_alignment_energy  # noqa: E402
from engine.gates.tools.codons import CodonOptimizer  # noqa: E402
from engine.gates.tools.folding import FoldEngine  # noqa: E402
from engine.gates.tools.translation import TranslationScorer  # noqa: E402

#: Zhang & Winfree 2009: displacement rate spans ~6 orders of magnitude as the toehold grows
#: 0 to 6 nt, then saturates. DNA, 25 C, 1 M Na+ -- BORROWED, and the dominant error here.
DECADES_PER_NT = 1.0
SATURATION_NT = 6.0


def read_fasta(path: str) -> str:
    lines = Path(path).read_text().splitlines()
    return sq.to_rna("".join(line.strip() for line in lines if not line.startswith(">")))


def free_fraction(matrix, span) -> float:
    width = span[1] - span[0]
    return sum(max(0.0, 1.0 - sum(matrix[i])) for i in range(*span)) / width


def decades(toehold_nt: float) -> float:
    return DECADES_PER_NT * min(SATURATION_NT, max(0.0, toehold_nt))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fasta", required=True)
    parser.add_argument("--pairs", type=int, default=4)
    parser.add_argument("--stem", default="strongest")
    parser.add_argument("--out", default="kinetic_pathway")
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
        f"  {'design':<23}{'free x*|00':>12}{'free x*|01':>12}"
        f"{'toe 00':>9}{'toe 01':>9}{'rate 01/00':>13}{'equil sep':>11}{'r2* free|00':>13}"
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
        x = trigger_a[gate.ARM_LEN : gate.ARM_LEN + pair.len_x]
        toehold_dg = fixed_alignment_energy(x, sq.reverse_complement(x), gate.folder)

        for name in ("baseline", "aug_paired"):
            switch = built[name]
            site = switch.domains["sw_xs"]
            b_toehold = switch.domains["r2_star"]
            # The two STARTING configurations, not the two end states.
            shut = gate.folder.pooled_pair_probabilities(switch.sequence)
            after_b = gate.folder.pooled_pair_probabilities(f"{switch.sequence}&{trigger_b}")
            free_00 = free_fraction(shut, site)
            free_01 = free_fraction(after_b, site)
            toe_00 = pair.len_x * free_00
            toe_01 = pair.len_x * free_01
            advantage = decades(toe_01) - decades(toe_00)
            observed = mp.observe(gate, switch, trigger_a, trigger_b)
            r2_free = free_fraction(shut, b_toehold)
            rows.append(
                {
                    "x_start": pair.x_start,
                    "len_x": pair.len_x,
                    "variant": name,
                    "lock_energy": stem.lock_energy,
                    "toehold_dG": toehold_dg,
                    "free_xstar_00": free_00,
                    "free_xstar_01": free_01,
                    "toehold_eff_00": toe_00,
                    "toehold_eff_01": toe_01,
                    "log10_rate_advantage": advantage,
                    "r2_star_free_00": r2_free,
                    "separation": observed["separation"],
                    "mean_separation": observed["mean_separation"],
                    "A_M_10": observed["A_M_10"],
                    "A_M_11": observed["A_M_11"],
                }
            )
            print(
                f"  x@{pair.x_start} {name:<15}{free_00:>12.4f}{free_01:>12.4f}"
                f"{toe_00:>9.2f}{toe_01:>9.2f}{'10^' + format(advantage, '.1f'):>13}"
                f"{observed['separation']:>11.2f}{r2_free:>13.3f}",
                flush=True,
            )

    path = output_dir / f"{args.out}.csv"
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n{len(rows)} rows -> {path}")

    base_rows = [r for r in rows if r["variant"] == "baseline"]
    if base_rows:
        best = max(base_rows, key=lambda r: r["log10_rate_advantage"])
        print(
            f"\nBaseline designs -- the ones our equilibrium model rejects outright:\n"
            f"  largest kinetic advantage {10 ** best['log10_rate_advantage']:,.0f}x "
            f"(x@{best['x_start']}), with equilibrium separation "
            f"{best['separation']:.2f} kcal/mol."
        )
    print(
        "\nr2*|00 is trigger B's own toehold in the OFF state. If it is high, B binds first\n"
        "because it is the only trigger that can, which is what makes the ordering above a\n"
        "mechanism rather than an assumption."
    )
    print("\nSlope and saturation borrowed from Zhang & Winfree 2009: DNA, 25 C, 1 M Na+.")
    print("We fold RNA at 37 C. Ratios are more defensible than absolute rates. Not scored.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
