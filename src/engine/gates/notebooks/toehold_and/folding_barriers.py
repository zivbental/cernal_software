"""Real refolding barriers, from ViennaRNA's findpath, for the step kinetics turns on.

    uv run python src/engine/gates/notebooks/toehold_and/folding_barriers.py \\
        --fasta "path/to/mCherry original.txt" --pairs 4 --out barriers

**Why findpath and not the obvious alternatives.** The textbook way to get RNA kinetics is
``RNAsubopt`` into ``barriers`` into ``treekin`` — enumerate the low-energy ensemble, build
the barrier tree, integrate the master equation. On a 161-nt switch plus two triggers
(247 nt in the three-strand tube) that enumeration is astronomically large; ``barriers`` is
practical to roughly 100 nt and would not return. ``Kinefold`` and ``DrTransformer`` are the
tools built for longer sequences — DrTransformer in particular does **cotranscriptional**
folding, which matters here because our switch is transcribed 5'→3', so ``r2*`` and the
inhibitory hairpin exist before the main hairpin does. **None of those three is installed**,
and each is a separate install rather than part of the ViennaRNA Python package.

What *is* available in ViennaRNA 2.7.2 is ``findpath``: a breadth-limited heuristic search
for the lowest saddle on a direct refolding path between two structures. It gives the one
number the rate depends on — the **barrier height** — at O(n² x width) rather than by
enumerating a landscape, so it runs on our lengths in seconds. It is a heuristic and can only
over-estimate the true saddle, never under-estimate it, which makes it a conservative bound.

**The step being measured.** Trigger A cannot invade until its nucleation site ``x*`` is
single-stranded. So the barrier that gates the whole gate is the work of opening ``x*``:

* from configuration **00** — the switch alone, inhibitory hairpin shut;
* from configuration **01** — trigger B bound, which is supposed to have opened it.

The difference between those two barriers is what trigger B buys trigger A, in kcal/mol, on
a real pathway rather than as an end-state ratio. An end-state model cannot produce it at all.

**Units.** ``path_findpath_saddle`` returns **dekacal/mol** as an integer — 320 means
3.20 kcal/mol. Reporting it unconverted is the exact trap CLAUDE.md warns about for
``subopt``'s energy window, and it is divided by 100 here.

**Not scored.** Reported beside the equilibrium numbers, like every other kinetic quantity in
this project.
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

#: findpath's search width. Higher is a closer bound on the true saddle and costs linearly.
SEARCH_WIDTH = 20


def read_fasta(path: str) -> str:
    lines = Path(path).read_text().splitlines()
    return sq.to_rna("".join(line.strip() for line in lines if not line.startswith(">")))


def barrier_to_open(folder: FoldEngine, strands: str, window: tuple[int, int]) -> dict:
    """Saddle height for refolding from the MFE to a structure with ``window`` open.

    Both endpoints come from the same sequence, so the path is a legitimate refolding
    trajectory. The constrained endpoint is the best structure that keeps the window
    single-stranded, which is where trigger A can nucleate.
    """
    folded = folder.mfe(strands)
    start, start_energy = folded.structure, folded.energy
    target, target_energy = folder.mfe_with_window_open(strands, window)
    saddle = folder.refolding_saddle(strands, start, target, width=SEARCH_WIDTH)
    if saddle is None:
        return {"barrier": None, "start_dG": start_energy, "target_dG": target_energy}
    return {
        "barrier": saddle - start_energy,
        "saddle": saddle,
        "start_dG": start_energy,
        "target_dG": target_energy,
        "cost": target_energy - start_energy,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fasta", required=True)
    parser.add_argument("--pairs", type=int, default=4)
    parser.add_argument("--out", default="barriers")
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
        f"  {'design':<24}{'nucl 00':>12}{'nucl 01':>12}{'B buys':>10}"
        f"{'window 00':>11}{'window 10':>11}{'window 11':>11}"
    )
    for pair in kept[: args.pairs]:
        trigger_a = transcript[slice(*pair.window_a())]
        trigger_b = transcript[slice(*pair.window_b())]
        stems = gate.secondary_stems(trigger_a, trigger_b, pair.len_x)
        stem = min(stems, key=lambda s: s.lock_energy)
        base = gate.assemble(trigger_a, trigger_b, pair.len_x, stem)
        for name, switch in (
            ("baseline", base),
            ("aug_paired", mp.variants(gate, base, trigger_a)["aug_paired"]),
        ):
            site = switch.domains["sw_xs"]
            shut = barrier_to_open(gate.folder, switch.sequence, site)
            with_b = barrier_to_open(gate.folder, f"{switch.sequence}&{trigger_b}", site)
            # The OTHER half of the rate. Nucleation is only the first step: once trigger A
            # has a foothold it still has to open the ribosome window, and that barrier
            # lives in the MAIN hairpin. Rate ~ nucleation x completion, so both are needed
            # and neither alone is the gate.
            rank = switch.span(-17, 13)
            window_00 = barrier_to_open(gate.folder, switch.sequence, rank)
            window_10 = barrier_to_open(gate.folder, f"{switch.sequence}&{trigger_a}", rank)
            window_11 = barrier_to_open(
                gate.folder, f"{switch.sequence}&{trigger_a}&{trigger_b}", rank
            )
            gain = (
                None
                if shut["barrier"] is None or with_b["barrier"] is None
                else shut["barrier"] - with_b["barrier"]
            )
            rows.append(
                {
                    "x_start": pair.x_start,
                    "len_x": pair.len_x,
                    "variant": name,
                    "lock_energy": stem.lock_energy,
                    "barrier_00": shut["barrier"],
                    "barrier_01": with_b["barrier"],
                    "barrier_drop": gain,
                    "cost_00": shut.get("cost"),
                    "cost_01": with_b.get("cost"),
                    "window_barrier_00": window_00["barrier"],
                    "window_barrier_10": window_10["barrier"],
                    "window_barrier_11": window_11["barrier"],
                    "window_drop_A": (
                        None
                        if window_00["barrier"] is None or window_10["barrier"] is None
                        else window_00["barrier"] - window_10["barrier"]
                    ),
                }
            )
            print(
                f"  x@{pair.x_start} {name:<16}{shut['barrier']:>12.2f}"
                f"{with_b['barrier']:>12.2f}{gain:>10.2f}"
                f"{window_00['barrier']:>11.2f}{window_10['barrier']:>11.2f}"
                f"{window_11['barrier']:>11.2f}",
                flush=True,
            )

    path = output_dir / f"{args.out}.csv"
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n{len(rows)} rows -> {path}")
    print(
        "\n'B buys' is how much trigger B lowers the barrier to exposing trigger A's\n"
        "nucleation site, in kcal/mol, on a real refolding path. At 37 C, RT is 0.616,\n"
        "so each 1.4 kcal/mol is roughly a factor of 10 in rate."
    )
    print(
        "\nfindpath is a heuristic and can only over-estimate a saddle, so these are\n"
        "conservative bounds. barriers/treekin would be exact and will not run at this\n"
        "length; DrTransformer is the right tool for cotranscriptional folding and is\n"
        "not installed."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
