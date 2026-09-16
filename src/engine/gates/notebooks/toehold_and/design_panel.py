"""The whole A0 pipeline, end to end, for a wet-lab panel. One command, no hand-holding.

Quick run (minutes) — start here::

    uv run python src/engine/gates/notebooks/toehold_and/design_panel.py \\
        --fasta "path/to/mCherry original.txt" --quick --out panel

Full run (hours)::

    uv run python src/engine/gates/notebooks/toehold_and/design_panel.py \\
        --fasta "path/to/mCherry original.txt" --out panel

**What it produces.** Two trigger pairs, taken at the longest available overlap, and for
each of them two designs from every secondary-stem family — A-anchored, B-anchored and
mixed (the builds only scheme C can express). Twelve switches, each with its four-tube
observables, plus the four negative-control transcripts per pair.

**The funnel, because folding is what costs.** A four-tube evaluation is a few seconds and
scheme C emits ``3^n`` builds per pair, so nothing can fold everything:

1. Stage 1 selects trigger pairs on geometry and motifs. Negative-control feasibility is a
   ``[lab]`` filter — both inputs coming from one recoded gene is a property of *this*
   validation, not of the framework — so ``--no-lab-filter`` turns it off for a production
   run where the triggers are endogenous and cannot be recoded.
2. Pairs are ranked by overlap length, and only the top few go further.
3. Scheme C enumerates, R6 and the invasion-stall cap filter, and the Pareto front over
   (lock, A-site, B-site) keeps only builds no other build beats on all three at once.
4. Two builds per family are folded in full. ``--quick`` narrows steps 2 and 4.

**Gates are reported, not enforced, and that is deliberate.** ``A_M(10) < τ4a`` is currently
unsatisfiable for this architecture: trigger A's first 18 nt are the exact reverse
complement of the main hairpin's arm, so it opens the hairpin at equilibrium whether or not
trigger B has acted, which makes ``A_M(10)`` equal to ``A_M(11)`` on every candidate
measured. Kim 2019's bench-validated AND gate fails the same gate with the same numbers.
Enforcing it would return an empty panel and hide the designs; printing every gate outcome
lets a human see which failures are the architecture's and which are the candidate's.
``separation`` is therefore reported twice — over all three OFF states, and excluding state
10 — with the second being the informative one until that decision is settled.
"""

import argparse
import csv
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[4]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from engine import sequences as sq  # noqa: E402  (path set up just above)
from engine.domain import Host  # noqa: E402
from engine.gates.toehold import ProkaryoticToeholdAndGate  # noqa: E402
from engine.gates.tools.codons import CodonOptimizer  # noqa: E402
from engine.gates.tools.folding import FoldEngine  # noqa: E402
from engine.gates.tools.translation import TranslationScorer  # noqa: E402

FAMILIES = ("A-anchored", "B-anchored", "mixed")


def read_fasta(path: str) -> str:
    lines = Path(path).read_text().splitlines()
    return sq.to_rna("".join(line.strip() for line in lines if not line.startswith(">")))


def select_pairs(gate, transcript, *, lab_filter: bool, wanted: int, verbose: bool):
    """Stage 1, then the longest overlaps. Long overlaps come first because `x*` is the one
    domain scheme C cannot design, so its length is the only lever on how firmly trigger A's
    nucleation site is held shut."""
    kept = []
    for pair in gate.find_trigger_pairs(transcript):
        start, end = pair.window_a()
        if gate.screen_trigger_window(transcript[start:end], transcript[pair.x_start - 9 :][:9]):
            continue
        if lab_filter:
            ko_a, ko_b = gate.controls_constructible(transcript, pair)
            if not (ko_a and ko_b):
                continue
        kept.append(pair)
    kept.sort(key=lambda p: (-p.len_x, -p.gap()))
    if verbose:
        print(f"stage 1: {len(kept)} pairs survive; longest overlap is {kept[0].len_x} nt")
    return kept[:wanted]


def pick_by_family(stems, per_family: int):
    """Up to ``per_family`` builds from each scheme, strongest lock first.

    Strongest lock first because that is the anti-leak end of the frontier, and because a
    panel wants the best representative of each family rather than a random one. Families
    with no build are reported rather than silently skipped.
    """
    chosen: dict[str, list] = {}
    for family in FAMILIES:
        members = sorted((s for s in stems if s.scheme == family), key=lambda s: s.lock_energy)
        chosen[family] = members[:per_family]
    return chosen


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fasta", required=True)
    parser.add_argument("--out", default="panel", help="prefix for the CSV and the FASTAs")
    parser.add_argument("--pairs", type=int, default=2, help="trigger pairs to design for")
    parser.add_argument("--per-family", type=int, default=2, help="designs per stem family")
    parser.add_argument(
        "--quick",
        action="store_true",
        help="one pair, one design per family, and cap the stem enumeration",
    )
    parser.add_argument(
        "--no-lab-filter",
        action="store_true",
        help="skip negative-control feasibility, which is a [lab] constraint only",
    )
    args = parser.parse_args(argv)

    pairs_wanted = 1 if args.quick else args.pairs
    per_family = 1 if args.quick else args.per_family
    output_dir = Path(__file__).resolve().parent / "results"
    output_dir.mkdir(parents=True, exist_ok=True)

    gate = ProkaryoticToeholdAndGate(
        Host.ECOLI,
        FoldEngine(temperature=37.0),
        TranslationScorer(Host.ECOLI),
        CodonOptimizer(Host.ECOLI),
    )
    transcript = read_fasta(args.fasta)
    print(f"transcript: {len(transcript)} nt, {len(transcript) // 3} codons")
    if args.quick:
        print("quick mode: one pair, one design per family\n")

    pairs = select_pairs(
        gate, transcript, lab_filter=not args.no_lab_filter, wanted=pairs_wanted, verbose=True
    )

    rows = []
    for pair in pairs:
        a_start, a_end = pair.window_a()
        b_start, b_end = pair.window_b()
        trigger_a, trigger_b = transcript[a_start:a_end], transcript[b_start:b_end]
        print(f"\n=== pair x@{pair.x_start} x*@{pair.xstar_start} len_x={pair.len_x} ===")

        stems = gate.secondary_stems(trigger_a, trigger_b, pair.len_x)
        counts = {f: sum(1 for s in stems if s.scheme == f) for f in FAMILIES}
        print(f"  {len(stems)} builds on the Pareto front: {counts}")

        for family, members in pick_by_family(stems, per_family).items():
            if not members:
                print(f"  {family}: no build on the frontier")
                continue
            for stem in members:
                switch = gate.assemble(trigger_a, trigger_b, pair.len_x, stem)
                faults = gate.assembly_violations(switch)
                if faults:
                    print(f"  {family}: rejected at assembly ({', '.join(faults)})")
                    continue
                o = gate.four_tube_observables(switch, trigger_a, trigger_b)
                off = [o[f"dG_open_{s}"] for s in ("00", "01")]
                sep_no_ten = (
                    min(v - o["dG_open_11"] for v in off)
                    if o["dG_open_11"] is not None and all(v is not None for v in off)
                    else None
                )
                failed = gate.gate_violations(o)
                print(
                    f"  {family:<11} lock {stem.lock_energy:>7.1f}  ddG_pref {stem.ddg_pref:>5.2f}"
                    f"  sep {o['separation']:>6.2f}  sep(no 10) {sep_no_ten:>6.2f}"
                    f"  dG_bind_B {o['dG_bind_B']:>7.1f}  fails {len(failed)}"
                )
                rows.append(
                    {
                        "x_start": pair.x_start,
                        "xstar_start": pair.xstar_start,
                        "len_x": pair.len_x,
                        "scheme": family,
                        "k2_star": stem.k2_star,
                        "secondary_z": stem.secondary_z,
                        "ddg_pref": stem.ddg_pref,
                        "lock_energy": stem.lock_energy,
                        "a_site_energy": stem.a_site_energy,
                        "b_site_energy": stem.b_site_energy,
                        "separation_no_state_10": sep_no_ten,
                        "gates_failed": ";".join(failed) or "-",
                        "switch": switch.sequence,
                        "off_structure": switch.dot_bracket,
                        **o,
                    }
                )

        constructs = gate.bench_constructs(transcript, pair)
        for state in ("11", "10", "01", "00"):
            sequence = constructs[state]
            if sequence is None:
                print(f"  control {state}: no synonymous knockout")
                continue
            path = output_dir / f"{args.out}_x{pair.x_start}_state{state}.fa"
            edits = sum(1 for a, b in zip(transcript, sequence, strict=True) if a != b)
            with path.open("w") as handle:
                handle.write(f">state{state} x@{pair.x_start} edits={edits}\n")
                dna = sq.to_dna(sequence)
                for i in range(0, len(dna), 60):
                    handle.write(dna[i : i + 60] + "\n")
            print(f"  control {state}: {path}  ({edits} edits)")

    if rows:
        path = output_dir / f"{args.out}_designs.csv"
        with path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        print(f"\n{len(rows)} designs written to {path}")
        print("\nGate outcomes are in gates_failed. A_M_10<0.2 failing on every design is")
        print("the architecture, not the candidate: trigger A opens the main hairpin at")
        print("equilibrium whether or not B has acted, and Kim 2019's validated AND gate")
        print("fails it identically. Rank on separation_no_state_10 until that is settled.")
    else:
        print("\nNo design survived assembly. Nothing to order.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
