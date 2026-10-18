"""Is the stored barrier a barrier, or is it the energy difference between two states?

A review pointed out that an activation barrier is the highest point of a path *above*
its starting state and so cannot be negative, while 10 to 12% of ours are. A first look
at eight designs found something sharper than a sign error: in all eight, negative and
positive alike, the returned saddle equalled the energy of the END structure exactly. If
that holds generally, the stored number is ``E(end) - E(start)`` -- a state difference
with no path in it -- and calling it a barrier is wrong whatever its sign.

This settles it on a sample, by checking four things per design:

* whether the start structure is legal for the sequence at all (an illegal pair is
  silently dropped by some entry points and not by others, which would make the path
  start somewhere other than where we think);
* the saddle against E(start) and E(end);
* the energies actually visited along the path, taken from ``path_findpath`` rather than
  from the saddle call, skipping the first element because its energy field is not
  filled by the bindings;
* whether the highest energy visited is above the start, which is the only thing that
  deserves the word barrier.

Run::

    uv run python tools/barrier_validate.py --rows docs/assets/barrier/designs_0.csv -n 12
"""

from __future__ import annotations

import argparse
import csv
import pathlib
import sys

import RNA

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import barrier_designs as bd
import barrier_sign as bs

from engine import sequences as sq
from engine.domain import Host
from engine.gates.tools.folding import FoldEngine
from engine.transcriptome import load_transcriptome

PAIRABLE = {"AU", "UA", "GC", "CG", "GU", "UG"}


def illegal_pairs(sequence: str, structure: str) -> int:
    """How many pairs in the structure are not pairs the sequence can make."""
    plain = sequence.replace("&", "")
    stack: list[int] = []
    bad = 0
    for index, symbol in enumerate(structure):
        if symbol == "(":
            stack.append(index)
        elif symbol == ")":
            if not stack:
                return -1
            opened = stack.pop()
            if plain[opened] + plain[index] not in PAIRABLE:
                bad += 1
    return bad if not stack else -1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Validate what the barrier measures.")
    parser.add_argument("--rows", type=pathlib.Path, required=True)
    parser.add_argument("-n", type=int, default=12)
    args = parser.parse_args(argv)

    rows = list(csv.DictReader(args.rows.open(newline="", encoding="utf-8")))
    stored = [r for r in rows if r["b_10"] not in ("", "None")]
    negative = [r for r in stored if float(r["b_10"]) < 0]
    positive = [r for r in stored if float(r["b_10"]) > 2]
    sample = negative[: args.n // 2] + positive[: args.n // 2]
    print(f"  {args.rows.name}: {len(stored)} measured, {len(negative)} negative")

    folder = FoldEngine(37.0)
    book = load_transcriptome(Host.ECOLI)
    gates = {name: cls(Host.ECOLI, folder, None, None) for name, cls in bd.CLASSES.items()}
    transcripts = {sym: sq.to_rna(book[gid]) for sym, gid, _, _ in bd.GENE_PAIRS}
    transcripts |= {sym: sq.to_rna(book[gid]) for _, _, sym, gid in bd.GENE_PAIRS}

    header = (
        f"  {'stored':>7} {'bad':>4} {'saddle':>8} {'E(start)':>9} {'E(end)':>8} "
        f"{'path max':>9} {'max-start':>10}  verdict"
    )
    print(header)
    same_as_end = 0
    checked = 0
    for row in sample:
        built = bs.rebuild(row, gates, transcripts)
        if built is None:
            continue
        strands, start, end = built
        compound = RNA.fold_compound(strands)
        saddle = compound.path_findpath_saddle(start, end, bd.CEILING) / 100.0
        e_start = compound.eval_structure(start)
        e_end = compound.eval_structure(end)
        bad = illegal_pairs(strands, start)
        # path_findpath leaves the first element's energy field unset, so the energies
        # actually visited are re-evaluated from the structures themselves.
        visited = [
            compound.eval_structure(step.s) for step in compound.path_findpath(start, end, 10)
        ]
        top = max(visited) if visited else float("nan")
        checked += 1
        if abs(saddle - e_end) < 0.005:
            same_as_end += 1
        verdict = "saddle == E(end)" if abs(saddle - e_end) < 0.005 else "saddle is a real max"
        print(
            f"  {float(row['b_10']):7.2f} {bad:4d} {saddle:8.2f} {e_start:9.2f} {e_end:8.2f} "
            f"{top:9.2f} {top - e_start:+10.2f}  {verdict}"
        )

    conclusion = (
        "The stored number is a state difference, not a barrier."
        if same_as_end == checked
        else "Mixed -- inspect individually."
    )
    print(f"\n  saddle equalled E(end) in {same_as_end} of {checked} designs. {conclusion}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
