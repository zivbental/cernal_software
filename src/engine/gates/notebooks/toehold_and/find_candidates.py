"""Stage 1 for the A0 two-input AND gate: find usable trigger pairs in one transcript.

Run it::

    uv run python src/engine/gates/notebooks/toehold_and/find_candidates.py \\
        --fasta "path/to/mCherry original.txt" --csv candidates.csv

**Nothing scientific lives here.** The geometry, the motif restrictions and the
negative-control feasibility check are all on ``ToeholdAndGate``, so the pipeline gets the
same answers this script prints. This file only reads a FASTA, calls those methods in
order, and reports the count at each step — which is what makes the three numbers below
comparable with the validated reference.

On mCherry the ladder is 1,443 pairs whose windows fit and are disjoint, 1,036 also
motif-clean and 50 nt apart, and 867 that can additionally have either trigger disabled by
synonymous substitution. The 169 dropped at the last step are the point of checking it
here: discovering after choosing a pair that its negative control cannot be built wastes a
design cycle.
"""

import argparse
import csv
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[4]


def bootstrap() -> Path:
    """Put ``<repo>/src`` on ``sys.path``, as the notebooks beside this one do.

    The package is not installed into the environment — ``pythonpath = ["src"]`` in
    ``pyproject.toml`` is a pytest setting and does nothing for a plain script run — so
    without this the script would only be runnable through the test harness. It has to
    work from a VS Code Run button too.
    """
    if str(_SRC) not in sys.path:
        sys.path.insert(0, str(_SRC))
    return _SRC


bootstrap()

from engine import sequences as sq  # noqa: E402  (path set up just above)
from engine.domain import Host  # noqa: E402
from engine.gates.toehold import ProkaryoticToeholdAndGate  # noqa: E402
from engine.gates.tools.codons import CodonOptimizer  # noqa: E402
from engine.gates.tools.folding import FoldEngine  # noqa: E402
from engine.gates.tools.translation import TranslationScorer  # noqa: E402


def read_fasta(path: str) -> str:
    """The first record of a FASTA, as RNA. Accepts a bare sequence file too."""
    lines = Path(path).read_text().splitlines()
    return sq.to_rna("".join(line.strip() for line in lines if not line.startswith(">")))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fasta", required=True, help="the transcript both triggers come from")
    parser.add_argument("--min-gap", type=int, default=None, help="default: the gate's own 50")
    parser.add_argument("--csv", help="write every surviving candidate here")
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument(
        "--constructs",
        metavar="PREFIX",
        help="write the four bench-construct FASTAs for the best candidate, as "
        "PREFIX_state{11,10,01,00}.fa - all four on one background, with 00 carrying "
        "both triggers disabled rather than the transcript withheld",
    )
    args = parser.parse_args(argv)

    transcript = read_fasta(args.fasta)
    gate = ProkaryoticToeholdAndGate(
        Host.ECOLI,
        FoldEngine(temperature=37.0),
        TranslationScorer(Host.ECOLI),
        CodonOptimizer(Host.ECOLI),
    )
    kept = args.min_gap if args.min_gap is not None else gate.MIN_WINDOW_GAP
    print(f"transcript: {len(transcript)} nt, {len(transcript) // 3} codons")

    rows = []
    for pair in gate.find_trigger_pairs(transcript, min_window_gap=0):
        a_start, a_end = pair.window_a()
        b_start, b_end = pair.window_b()
        motifs = gate.screen_trigger_window(
            transcript[a_start:a_end], transcript[pair.x_start - 9 : pair.x_start]
        )
        ko_a, ko_b = gate.controls_constructible(transcript, pair)
        rows.append(
            {
                "len_x": pair.len_x,
                "x": transcript[pair.x_start : pair.x_start + pair.len_x],
                "x_start": pair.x_start,
                "xstar_start": pair.xstar_start,
                "window_a": f"{a_start}..{a_end - 1}",
                "window_b": f"{b_start}..{b_end - 1}",
                "gap": pair.gap(),
                "motif_fail": ";".join(motifs) or "-",
                "ko_A": ko_a,
                "ko_B": ko_b,
            }
        )

    passes = [r for r in rows if r["motif_fail"] == "-" and r["gap"] >= kept]
    clean = [r for r in passes if r["ko_A"] and r["ko_B"]]

    print(f"windows fit and are disjoint ................. {len(rows)}")
    print(f"  motif-clean and gap >= {kept} ................. {len(passes)}")
    print(
        f"  and both negative controls constructible ... {len(clean)}"
        f"   ({len(passes) - len(clean)} dropped: no synonymous knockout)"
    )

    clean.sort(key=lambda r: (-r["len_x"], -r["gap"]))
    print(f"\n  {'len_x':>5} {'x':<10} {'x@':>5} {'x*@':>5} {'gap':>5}  window_A       window_B")
    for row in clean[: args.top]:
        print(
            f"  {row['len_x']:>5} {row['x']:<10} {row['x_start']:>5} "
            f"{row['xstar_start']:>5} {row['gap']:>5}  {row['window_a']:<14} {row['window_b']}"
        )
    if len(clean) > args.top:
        print(f"  ... {len(clean) - args.top} more")

    if args.constructs and clean:
        best = clean[0]
        pair = next(
            p
            for p in gate.find_trigger_pairs(transcript, min_window_gap=0)
            if p.x_start == best["x_start"] and p.xstar_start == best["xstar_start"]
        )
        constructs = gate.bench_constructs(transcript, pair)
        print(f"\nbench constructs for x@{pair.x_start} x*@{pair.xstar_start} len_x={pair.len_x}:")
        for state in ("11", "10", "01", "00"):
            sequence = constructs[state]
            if sequence is None:
                print(f"  state {state}: no synonymous knockout - pick another candidate")
                continue
            edits = [
                (i, a, b)
                for i, (a, b) in enumerate(zip(transcript, sequence, strict=True))
                if a != b
            ]
            path = f"{args.constructs}_state{state}.fa"
            with open(path, "w") as handle:
                handle.write(
                    f">state{state} x@{pair.x_start} xstar@{pair.xstar_start} "
                    f"len_x={pair.len_x} edits={len(edits)}\n"
                )
                dna = sq.to_dna(sequence)
                for i in range(0, len(dna), 60):
                    handle.write(dna[i : i + 60] + "\n")
            described = ", ".join(f"{i}:{a}>{b}" for i, a, b in edits) or "unmodified"
            print(f"  state {state}: {path}   {described}")

    if args.csv and clean:
        with open(args.csv, "w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(clean[0]))
            writer.writeheader()
            writer.writerows(clean)
        print(f"\n{len(clean)} candidates written to {args.csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
