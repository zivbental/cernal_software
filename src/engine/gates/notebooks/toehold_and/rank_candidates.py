"""Stages 3-5 for the A0 AND gate: assemble, fold four tubes, gate, and rank.

Run it after ``find_candidates.py``::

    uv run python src/engine/gates/notebooks/toehold_and/rank_candidates.py \\
        --fasta "path/to/mCherry original.txt" --limit 50 --csv pass1.csv

**The pipeline is two-pass, and that is an architecture requirement rather than a
preference.** ``lambda`` is a property of the candidate *population* and every ``Q`` term
is normalised within that same population, so neither exists until every candidate has
been evaluated. Nothing can be scored inside the generation loop. Pass 1 therefore
persists one row per survivor — **raw, unnormalised, no ranks and no scores** — so pass 2
can re-run with a different ``w`` or a different weighting without re-folding anything.
Folding is the expensive step and it happens exactly once.

The run is funnelled, because folding every build is not affordable. Scheme C emits 3^n
builds per candidate, and the four-tube evaluation costs a few seconds each:

1. **Screen the pair.** The main hairpin's four accessibilities and the toehold's depend
   on the trigger pair alone — scheme C designs only the *secondary* hairpin — so one fold
   per candidate decides whether any stem could work. A pair that opens on trigger A alone
   cannot be rescued by a better stem, and a rejection here is final. Note what this does
   **not** cover: trigger B binds the secondary stem, so ``dG_bind_B``, ``dG_open(01)``,
   ``ddG_AND`` and ``separation`` all move with the build and are gated per build.
2. **Enumerate stems** only for survivors, keeping the Pareto front over lock, A-site and
   B-site. That is roughly 120 builds where 3^n would be tens of thousands, and it
   discards only builds another build beats on all three claims at once.
3. **Fold and gate** each surviving build in full.

What is **not** here: ``Q_pair``. Its eight factors are the six trigger-accessibility
sub-measures plus the two cross-talk margins, and none of them is built yet anywhere — so
``Phi = Q_pair * J`` cannot be computed and this script ranks on ``J`` alone. That is a
gap, not a simplification, and it is reported in the output rather than hidden.
"""

import argparse
import csv
import statistics
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

#: Weight between trigger capture and ribosome accessibility inside ``J_M``. Equal by
#: default: that asserts no evidence either matters more, rather than inventing a
#: preference. Sweep it at 0.25/0.5/0.75 and report how far the top-k moves — the check is
#: cheaper than the weight is defensible, and more informative.
DEFAULT_W = 0.5


def read_fasta(path: str) -> str:
    lines = Path(path).read_text().splitlines()
    return sq.to_rna("".join(line.strip() for line in lines if not line.startswith(">")))


def build_gate() -> ProkaryoticToeholdAndGate:
    return ProkaryoticToeholdAndGate(
        Host.ECOLI,
        FoldEngine(temperature=37.0),
        TranslationScorer(Host.ECOLI),
        CodonOptimizer(Host.ECOLI),
    )


def stage_one(gate, transcript):
    """Trigger pairs whose windows fit, are motif-clean, and can be knocked out."""
    for pair in gate.find_trigger_pairs(transcript):
        start, end = pair.window_a()
        if gate.screen_trigger_window(transcript[start:end], transcript[pair.x_start - 9 :][:9]):
            continue
        ko_a, ko_b = gate.controls_constructible(transcript, pair)
        if ko_a and ko_b:
            yield pair


def pass_one(gate, transcript, limit, verbose=True):
    """Generate, fold and gate. Returns survivors and a census of what killed the rest."""
    survivors, census = [], {"pair_screened_out": 0, "assembly": 0, "gated_out": 0}
    pair_failures: dict[str, int] = {}
    build_failures: dict[str, int] = {}

    candidates = list(stage_one(gate, transcript))
    if limit:
        step = max(1, len(candidates) // limit)
        candidates = candidates[::step][:limit]
    if verbose:
        print(f"stage 1 candidates to evaluate: {len(candidates)}", flush=True)

    for index, pair in enumerate(candidates, 1):
        a_start, a_end = pair.window_a()
        b_start, b_end = pair.window_b()
        trigger_a, trigger_b = transcript[a_start:a_end], transcript[b_start:b_end]

        probe = gate.probe_switch(trigger_a, trigger_b, pair.len_x)
        if gate.assembly_violations(probe):
            census["assembly"] += 1
            continue

        # (1) one fold decides the pair, before any stem is enumerated
        pair_view = gate.screen_pair(trigger_a, trigger_b, pair.len_x)
        failed = gate.pair_gate_violations(pair_view)
        if failed:
            census["pair_screened_out"] += 1
            for name in failed:
                pair_failures[name] = pair_failures.get(name, 0) + 1
            continue

        # (2) stems only for survivors, (3) folded and gated in full
        for stem in gate.secondary_stems(trigger_a, trigger_b, pair.len_x):
            switch = gate.assemble(trigger_a, trigger_b, pair.len_x, stem)
            if gate.assembly_violations(switch):
                census["assembly"] += 1
                continue
            observables = gate.four_tube_observables(switch, trigger_a, trigger_b)
            violations = gate.gate_violations(observables)
            if violations:
                census["gated_out"] += 1
                for name in violations:
                    build_failures[name] = build_failures.get(name, 0) + 1
                continue
            survivors.append(
                {
                    "x_start": pair.x_start,
                    "xstar_start": pair.xstar_start,
                    "len_x": pair.len_x,
                    "k2_star": stem.k2_star,
                    "secondary_z": stem.secondary_z,
                    "ddg_pref": stem.ddg_pref,
                    "lock_energy": stem.lock_energy,
                    "a_site_energy": stem.a_site_energy,
                    "b_site_energy": stem.b_site_energy,
                    "sequence": switch.sequence,
                    **observables,
                }
            )
        if verbose and index % 10 == 0:
            print(f"  {index}/{len(candidates)}  survivors so far: {len(survivors)}", flush=True)

    return survivors, census, pair_failures, build_failures


def score(survivors, w=DEFAULT_W):
    """The population boundary, then pass 2.

    ``lambda`` rescales accessibility onto the energy component's numeric range, by the
    **spread** of each and not their means. Normalising by means over-corrects badly: on a
    plausible population it hands `separation` almost all of the score variance while the
    sensitivity sweep still reports stability, so the error leaves no trace.

    Read ``J_A`` as *accessibility*, not as *trigger A*. Inverting the ratio makes
    `separation` dominate more, not less.
    """
    energy = [-row["dG_bind_A_given_B"] for row in survivors]  # J_E
    access = [row["separation"] for row in survivors]  # J_A
    if len(survivors) < 2 or statistics.pstdev(access) == 0:
        lam = 1.0
    else:
        lam = statistics.pstdev(energy) / statistics.pstdev(access)

    for row in survivors:
        j_s = -row["dG_bind_B"]
        j_m = w * (-row["dG_bind_A_given_B"]) + (1 - w) * lam * row["separation"]
        row["J_S"], row["J_M"] = j_s, j_m
        row["J"] = (max(0.0, j_s) * max(0.0, j_m)) ** 0.5
    survivors.sort(key=lambda r: -r["J"])
    return lam


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fasta", required=True)
    parser.add_argument("--limit", type=int, default=25, help="candidates to evaluate (0 = all)")
    parser.add_argument("--w", type=float, default=DEFAULT_W)
    parser.add_argument("--csv", help="pass-1 output: raw, unnormalised, one row per survivor")
    parser.add_argument("--top", type=int, default=10)
    args = parser.parse_args(argv)

    gate = build_gate()
    transcript = read_fasta(args.fasta)
    survivors, census, pair_failures, build_failures = pass_one(gate, transcript, args.limit)

    print("\n--- pass 1 ---")
    print(f"  rejected at assembly ......... {census['assembly']}")
    print(f"  pair screened out ............ {census['pair_screened_out']}")
    print(f"  builds gated out ............. {census['gated_out']}")
    print(f"  survivors .................... {len(survivors)}")
    for label, failures in (("pair screen", pair_failures), ("per build", build_failures)):
        if failures:
            print(f"\n  what failed, {label}:")
            for name, count in sorted(failures.items(), key=lambda kv: -kv[1]):
                print(f"     {name:<22} {count}")

    if not survivors:
        print("\nNothing survived, so there is no population to normalise against and no")
        print("ranking to report. The failure census above is the result: it says which")
        print("gate is binding, which is what decides whether the design rules, the")
        print("thresholds or the assumptions behind them need revisiting.")
        return 0

    lam = score(survivors, args.w)
    print("\n--- population boundary ---")
    print(f"  survivors (the population) ... {len(survivors)}")
    print(f"  realised lambda .............. {lam:.4f}   [sd(J_E)/sd(J_A)]")
    print(f"  w ............................ {args.w}")
    print("  Q_pair ....................... NOT COMPUTED - its eight factors are unbuilt,")
    print("                                 so this ranks on J, not on Phi = Q_pair * J.")
    print("\n  A score is meaningful only with the population it was computed against.")
    print("  Never compare these numbers across runs with different candidate sets.")

    print(f"\n--- top {args.top} by J ---")
    print(f"  {'J':>8}{'sep':>8}{'dG_bind_B':>11}{'dG_A|B':>9}{'ddG_pref':>10}  x@    x*@   len_x")
    for row in survivors[: args.top]:
        print(
            f"  {row['J']:>8.2f}{row['separation']:>8.2f}{row['dG_bind_B']:>11.2f}"
            f"{row['dG_bind_A_given_B']:>9.2f}{row['ddg_pref']:>10.2f}"
            f"{row['x_start']:>6}{row['xstar_start']:>6}{row['len_x']:>6}"
        )

    if args.csv:
        with open(args.csv, "w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(survivors[0]))
            writer.writeheader()
            writer.writerows(survivors)
        print(f"\npass-1 rows written to {args.csv}  ({len(survivors)} survivors, raw values)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
