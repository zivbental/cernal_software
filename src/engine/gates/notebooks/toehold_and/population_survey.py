"""The four tubes across many trigger pairs, for a distribution instead of an anecdote.

    uv run python src/engine/gates/notebooks/toehold_and/population_survey.py \\
        --fasta "path/to/mCherry original.txt" --start 0 --count 40 --out survey

**Why this exists.** Every earlier conclusion in this directory was drawn from one or two
trigger pairs, and one of them was drawn from a sweep that varied the *wrong* thing. The
secondary stem's Pareto front has 55 builds for pair x@260 and **all 55 carry a byte-identical
main hairpin** — scheme C designs ``k2_star`` and ``secondary_z``, and every domain of the
main hairpin is derived from trigger A instead. So "the window does not move across 55
builds" says only that the *secondary* stem does not reach the window once trigger A is
bound. It says nothing about main hairpins in general, because there was only ever one.

The thing that actually changes the main hairpin is the **trigger pair**: 40 pairs give 38
distinct main hairpins, and 1036 pairs survive stage 1. This walks that population.

**What it measures per pair**, all of it raw and none of it thresholded:

* ``dG_open`` and ``A_M`` in all four tubes, so the OFF states and the ON state can be
  compared per design rather than per anecdote;
* ``separation``, and separation with state 10 excluded, since those answer different
  questions and conflating them has caused trouble here before;
* ``d10_11 = dG_open(10) - dG_open(11)`` in units of the measurement floor, because the
  claim under test is that this is zero, and "zero" for a single-precision instrument means
  "smaller than about 3e-05 kcal/mol". Reported in ulps so a reader can see at a glance
  whether a design is genuinely different or merely unresolved;
* ``aug_*``, the unpaired probability of the three start-codon bases alone. R7 places the
  ``AUG`` in a 3x3 internal loop, so on the one design examined so far it is 96% exposed
  with the hairpin **closed** and 34% once trigger A binds. Whether that inversion is
  general or particular to that design is exactly the sort of question one design cannot
  answer.

**Sharding.** Folding dominates the cost, so ``--start``/``--count`` cut the deterministic
pair list into slices that can run as separate processes and be concatenated afterwards.
The ordering is fixed (longest overlap first, then widest gap), so slices never overlap and
a re-run reproduces the same rows.

**The stem choice is an argument, not a default.** ``--stem`` selects the build on the
front; 0 is the all-``both`` "unlocked" build, which has no inhibitory lock at any contested
position and is therefore the most leak-prone build available. Earlier scripts took it
silently, which is how a whole line of reasoning came to rest on an undeclared pick.
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
from engine.gates.toehold import ProkaryoticToeholdAndGate, _mean_unpaired  # noqa: E402
from engine.gates.tools.codons import CodonOptimizer  # noqa: E402
from engine.gates.tools.folding import _FLOAT32_ENERGY_ULP, FoldEngine  # noqa: E402
from engine.gates.tools.translation import TranslationScorer  # noqa: E402

STATES = ("00", "01", "10", "11")


def read_fasta(path: str) -> str:
    lines = Path(path).read_text().splitlines()
    return sq.to_rna("".join(line.strip() for line in lines if not line.startswith(">")))


def surviving_pairs(gate, transcript: str) -> list:
    """Stage 1, in a fixed order, so a slice means the same thing on every run."""
    kept = []
    for pair in gate.find_trigger_pairs(transcript):
        start, end = pair.window_a()
        if gate.screen_trigger_window(transcript[start:end], transcript[pair.x_start - 9 :][:9]):
            continue
        kept.append(pair)
    kept.sort(key=lambda p: (-p.len_x, -p.gap(), p.x_start, p.xstar_start))
    return kept


def survey_one(gate, transcript: str, pair, stem_index: int) -> dict | None:
    """One trigger pair, one build, every raw number. ``None`` if it will not assemble."""
    trigger_a = transcript[slice(*pair.window_a())]
    trigger_b = transcript[slice(*pair.window_b())]
    stems = gate.secondary_stems(trigger_a, trigger_b, pair.len_x)
    if not stems:
        return None
    stem = stems[min(stem_index, len(stems) - 1)]
    switch = gate.assemble(trigger_a, trigger_b, pair.len_x, stem)
    faults = gate.assembly_violations(switch)

    observables = gate.four_tube_observables(switch, trigger_a, trigger_b)
    tubes = {
        "00": switch.sequence,
        "01": f"{switch.sequence}&{trigger_b}",
        "10": f"{switch.sequence}&{trigger_a}",
        "11": f"{switch.sequence}&{trigger_a}&{trigger_b}",
    }
    row = {
        "x_start": pair.x_start,
        "xstar_start": pair.xstar_start,
        "len_x": pair.len_x,
        "stems_on_front": len(stems),
        "scheme": stem.scheme,
        "lock_energy": stem.lock_energy,
        "ddg_pref": stem.ddg_pref,
        "assembly_faults": ";".join(faults) or "-",
        "main_hairpin": "".join(
            switch.sequence[slice(*switch.domains[name])]
            for name in (
                "main_pre_star",
                "bulge_star",
                "k1_star",
                "rbs_loop",
                "main_z",
                "aug",
                "main_pre",
            )
        ),
    }
    for state in STATES:
        row[f"dG_open_{state}"] = observables[f"dG_open_{state}"]
        row[f"A_M_{state}"] = observables[f"A_M_{state}"]
        matrix = gate.folder.pooled_pair_probabilities(tubes[state])
        row[f"aug_{state}"] = _mean_unpaired(matrix, *switch.domains["aug"])
    row["separation"] = observables["separation"]
    row["dG_bind_B"] = observables["dG_bind_B"]

    off = [row[f"dG_open_{s}"] for s in ("00", "01")]
    on = row["dG_open_11"]
    row["separation_no_state_10"] = (
        min(v - on for v in off) if on is not None and all(v is not None for v in off) else None
    )
    ten, eleven = row["dG_open_10"], row["dG_open_11"]
    row["d10_11"] = None if ten is None or eleven is None else ten - eleven
    row["d10_11_in_ulps"] = None if row["d10_11"] is None else row["d10_11"] / _FLOAT32_ENERGY_ULP
    return row


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fasta", required=True)
    parser.add_argument("--start", type=int, default=0, help="first pair in the slice")
    parser.add_argument("--count", type=int, default=40, help="pairs in this slice, 0 for all")
    parser.add_argument("--stem", type=int, default=0, help="build on the Pareto front")
    parser.add_argument("--out", default="survey", help="CSV prefix, written into results/")
    args = parser.parse_args(argv)

    output_dir = Path(__file__).resolve().parent / "results"
    output_dir.mkdir(parents=True, exist_ok=True)

    gate = ProkaryoticToeholdAndGate(
        Host.ECOLI, FoldEngine(37.0), TranslationScorer(Host.ECOLI), CodonOptimizer(Host.ECOLI)
    )
    transcript = read_fasta(args.fasta)
    pairs = surviving_pairs(gate, transcript)
    window = pairs[args.start :] if args.count == 0 else pairs[args.start : args.start + args.count]
    print(
        f"{len(pairs)} pairs survive stage 1; this slice is [{args.start}, "
        f"{args.start + len(window)}), stem {args.stem}",
        flush=True,
    )

    rows = []
    for offset, pair in enumerate(window):
        row = survey_one(gate, transcript, pair, args.stem)
        if row is None:
            print(f"  {args.start + offset:>4} x@{pair.x_start}: no stem on the front", flush=True)
            continue
        rows.append(row)
        print(
            f"  {args.start + offset:>4} x@{row['x_start']:<4} len_x={row['len_x']} "
            f"{row['scheme']:<11} sep {row['separation']:>6.2f} "
            f"sep(no10) {row['separation_no_state_10']:>6.2f} "
            f"d10_11 {row['d10_11_in_ulps']:>+7.2f} ulp  "
            f"A_M 10/11 {row['A_M_10']:.3f}/{row['A_M_11']:.3f}  "
            f"AUG 00/11 {row['aug_00']:.3f}/{row['aug_11']:.3f}",
            flush=True,
        )

    if not rows:
        print("no rows")
        return 0
    path = output_dir / f"{args.out}_{args.start:04d}.csv"
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    resolved = [r for r in rows if r["d10_11"] is not None]
    unresolved = [r for r in resolved if abs(r["d10_11"]) <= _FLOAT32_ENERGY_ULP]
    seps = [r["separation"] for r in rows if r["separation"] is not None]
    print(f"\n{len(rows)} rows -> {path}")
    print(
        f"  d10_11 within the measurement floor: {len(unresolved)}/{len(resolved)}; "
        f"largest |d10_11| "
        f"{max((abs(r['d10_11']) for r in resolved), default=math.nan):.2e} kcal/mol"
    )
    print(f"  separation: min {min(seps):.3f}  max {max(seps):.3f}  over {len(seps)} designs")
    print(f"  distinct main hairpins in this slice: {len({r['main_hairpin'] for r in rows})}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
