"""The full design sweep, staged so the expensive half only ever sees survivors.

    # stage 1 -- no folding of switches at all, millions of rows are fine
    uv run python src/engine/gates/notebooks/toehold_and/full_sweep.py \\
        --fasta "path/to/mCherry original.txt" --stage cheap --pairs 0 --out sweep

    # stage 2 -- folds the selection stage 1 wrote
    uv run python src/engine/gates/notebooks/toehold_and/full_sweep.py \\
        --fasta "path/to/mCherry original.txt" --stage fold --out sweep --fold 5000

**Why it is staged, with the costs measured rather than guessed.** An earlier version of
this docstring claimed a four-tube evaluation costs ~25 s and that the sweep would otherwise
take weeks. **Both were wrong.** Measured on a 161-nt switch with its two triggers:

| operation | cost | scales with |
|---|---|---|
| four-tube evaluation, all observables | **1.2 s** | one design |
| secondary-stem enumeration (3ⁿ, n = 7 to 10 conflicts) | **2.1 s** | one trigger **pair** |
| the axis grid itself | free | — |

So the bottleneck is **stem enumeration per pair**, not folding per design, and it is paid
once per pair however many designs are built on it. The practical consequences:

* stage 1 over all 1036 pairs is **~36 minutes**, almost all of it stem enumeration;
* stage 2 folding 5,000 designs is **~1.7 hours**;
* folding the *entire* grid — 1036 pairs x 4 stems x 360 combinations, 1.5 M designs — is
  about **21 days**, which is the only case the "weeks" claim ever applied to and is not
  something anyone would run.

Staging is still right, but for a much less dramatic reason than first stated: it turns a
21-day job into a 2-hour one, and it lets the cheap metrics choose *which* designs are worth
the 1.2 s. The default ``--fold`` is set accordingly — we can afford thousands, not hundreds.

**Output is tidy, one row per design, and re-analysable.** Every axis value is its own
column beside every metric, and the switch sequence is written out, so any row can be rebuilt
and any pair of columns can be plotted against each other afterwards without re-running
anything. That is deliberate: the interesting relationships in this project have all turned
out to be ones nobody thought to tabulate in advance, and a table of a few hand-picked
examples cannot show a biological signal that only appears across hundreds of designs.

**The axes.**

1. ``toehold_trim`` — trigger B's toehold ``r2*``, full length or trimmed. Reported with the
   pairing probability of its **3' end**, the part adjacent to the inhibitory hairpin, since
   that is where structure blocks the transition from binding into invasion.
2. ``secondary_arm`` — 18, 19 or 20 nt. **Not yet implemented**: it changes ``ARM_LEN`` and
   therefore ``assemble``'s domain map, which is a change to the gate rather than a patch to a
   built switch. Flagged here so it is not silently dropped.
3. ``scheme`` — the scheme C front, as built, now including its fourth per-position option as
   a reported variant.
4. ``lower3`` — the 3 bp at the stem base: 2 strong + 1 weak, and the alternatives, because
   Green found 2 of 3 G·C optimal and that is a target rather than a maximum.
5. ``upper3`` — the 3 bp nearest the loop: 3 weak, or 2 weak + 1 strong.
6. ``closure`` — AUG sequestration, by depth **and** identity, since ``UAU`` and ``CAU`` close
   to the same depth and do not perform the same.
7. ``rbs_loop`` — 15 or 18 nt.

**Three of those seven are not in the grid yet** — ``toehold_trim``, ``rbs_loop`` and
``secondary_arm`` each change a domain *length*, so they need a change to ``assemble``'s
layout rather than a patch to a built switch. They are recorded at their current fixed value
and named in ``PENDING_LENGTH_AXES``, rather than being emitted as columns that vary in the
output but not in the molecule — which would let every downstream analysis treat them as
tested.

**And one axis the review list omitted:** the **3-nt island**. ``k1*`` is 6 nt and the upper-3
modification changes only its top half, so ``k1*[0:3]`` — between the changed top and the
bulge — stays trigger-derived. Combine upper-3 with an AUG closure and trigger A is left
holding a 3-nt island flanked by mismatches on both sides. It is swept here as ``island``,
because leaving it trigger-derived is a choice and not a default.
"""

import argparse
import csv
import itertools
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[4]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from engine import sequences as sq  # noqa: E402
from engine.domain import Host  # noqa: E402
from engine.gates.toehold import ProkaryoticToeholdAndGate, _mean_unpaired  # noqa: E402
from engine.gates.tools.codons import CodonOptimizer  # noqa: E402
from engine.gates.tools.folding import FoldEngine  # noqa: E402
from engine.gates.tools.translation import TranslationScorer  # noqa: E402

#: Closure of the AUG bulge: (label, bulge* sequence). Depth is how many of the start
#: codon's three bases pair; identity is the G+C count at that depth. Both matter -- UAU and
#: CAU close to the same depth and score differently -- so they are separate axis values.
CLOSURES: tuple[tuple[str, str], ...] = (
    ("open_3x3", None),  # leave bulge* trigger-derived, whatever the window gave
    ("closed_UAU", "UAU"),  # depth 3, zero G+C
    ("closed_CAU", "CAU"),  # depth 3, one G+C
    ("closed_CGU", "CGU"),  # depth 3, two G+C
    ("pair2_CCU", "CCU"),  # depth 2, designed 1x1
    ("pair1_CCC", "CCC"),  # depth 1, designed 2x2
)

#: Top 3 bp of the main stem. "W" is a weak A-U pair, "S" a strong G-C.
UPPER3: tuple[tuple[str, str], ...] = (
    ("trigger_derived", None),
    ("WWW_AUA", "AUA"),
    ("WWW_UAU", "UAU"),
    ("WWS_AUG", "AUG"),
    ("WSW_AGA", "AGA"),
)

#: Bottom 3 bp. Green: 2 of 3 G-C is best, so 2S1W leads and the neighbours bracket it.
LOWER3: tuple[tuple[str, str], ...] = (
    ("trigger_derived", None),
    ("SSW", "GGA"),
    ("SWS", "GAG"),
    ("WSS", "AGG"),
    ("SSS", "GGG"),
    ("SWW", "GAA"),
)

#: The 3 nt of k1* between the modified top and the bulge.
ISLAND: tuple[tuple[str, str], ...] = (("trigger_derived", None), ("WWW", "AUA"))

#: Axes that change a DOMAIN LENGTH rather than a domain's sequence, and so need a change to
#: `assemble`'s layout rather than a patch to a built switch. They are deliberately NOT in
#: the grid below: an axis recorded in the output but never applied to the sequence is worse
#: than a missing one, because every downstream analysis would treat it as tested.
#:
#:   toehold_trim   -- trigger B's r2* toehold, trimmed from the 5' end (0 / 4 / 8 nt)
#:   rbs_loop_len   -- 18 (ours) or 15 (Green forward-engineered, and Kim)
#:   secondary_arm  -- 18 / 19 / 20 nt, Kim's verified geometry
#:
#: All three are real axes and all three are pending the same piece of work.
PENDING_LENGTH_AXES = ("toehold_trim", "rbs_loop_len", "secondary_arm")


def read_fasta(path: str) -> str:
    lines = Path(path).read_text().splitlines()
    return sq.to_rna("".join(line.strip() for line in lines if not line.startswith(">")))


def gc_fraction(sequence: str) -> float:
    return sum(1 for base in sequence if base in "GC") / len(sequence) if sequence else 0.0


def cheap_metrics(gate, trigger_a: str, trigger_b: str, pair) -> dict:
    """Everything about a trigger PAIR that needs no switch folding.

    Constant across every design built on that pair, so computed once and joined on, rather
    than recomputed per row -- which is where a sweep of this size would otherwise spend
    most of its time.
    """
    arm = gate.ARM_LEN
    main_pre = trigger_a[9:arm]
    bottom3 = main_pre[-3:]
    top3 = trigger_a[:3]
    return {
        "gc_bottom3": gc_fraction(bottom3),
        "gc_top3": gc_fraction(top3),
        "gc_gradient": gc_fraction(bottom3) - gc_fraction(top3),
        "gc_balance": abs(gc_fraction(trigger_a[:6]) - 0.5),
        "trigger_a_gc": gc_fraction(trigger_a),
        "trigger_b_gc": gc_fraction(trigger_b),
        "len_x": pair.len_x,
        "gap": pair.gap(),
    }


def build(base, axes: dict):
    """Apply one point of the axis grid to an assembled switch.

    Patches whole domains by name and never changes a length, so the domain map stays valid
    and the sequence can be rebuilt from the row's axis columns alone.
    """
    from dataclasses import replace

    sequence = list(base.sequence)

    def put(domain: str, piece: str, at_end: bool = False) -> None:
        start, end = base.domains[domain]
        offset = end - len(piece) if at_end else start
        sequence[offset : offset + len(piece)] = list(piece)

    if axes["closure"] is not None:
        put("bulge_star", axes["closure"])
    if axes["upper3"] is not None:
        put("k1_star", axes["upper3"], at_end=True)
        put("main_z", sq.reverse_complement(axes["upper3"]))
    if axes["island"] is not None:
        put("k1_star", axes["island"])
        put("main_z", sq.reverse_complement(axes["island"]), at_end=True)
    if axes["lower3"] is not None:
        put("main_pre_star", sq.reverse_complement(axes["lower3"]))
        put("main_pre", axes["lower3"], at_end=True)
    return replace(base, sequence="".join(sequence))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fasta", required=True)
    parser.add_argument("--stage", choices=("cheap", "fold"), required=True)
    parser.add_argument("--pairs", type=int, default=20, help="trigger pairs, 0 for all")
    parser.add_argument("--stems", type=int, default=4, help="stems per pair from the front")
    parser.add_argument(
        "--fold",
        type=int,
        default=5000,
        help="designs to fold in stage 2; at ~1.2 s each, 5000 is under two hours",
    )
    parser.add_argument("--out", default="sweep")
    args = parser.parse_args(argv)

    output_dir = Path(__file__).resolve().parent / "results"
    output_dir.mkdir(parents=True, exist_ok=True)
    gate = ProkaryoticToeholdAndGate(
        Host.ECOLI, FoldEngine(37.0), TranslationScorer(Host.ECOLI), CodonOptimizer(Host.ECOLI)
    )
    transcript = read_fasta(args.fasta)

    if args.stage == "cheap":
        return _cheap(gate, transcript, args, output_dir)
    return _fold(gate, transcript, args, output_dir)


def _cheap(gate, transcript, args, output_dir) -> int:
    kept = []
    for pair in gate.find_trigger_pairs(transcript):
        start, end = pair.window_a()
        if gate.screen_trigger_window(transcript[start:end], transcript[pair.x_start - 9 :][:9]):
            continue
        kept.append(pair)
    kept.sort(key=lambda p: (-p.len_x, -p.gap(), p.x_start))
    if args.pairs:
        kept = kept[: args.pairs]
    print(f"{len(kept)} trigger pairs")

    grid = list(itertools.product(CLOSURES, UPPER3, LOWER3, ISLAND))
    print(f"{len(grid)} axis combinations per stem")
    print(f"pending, needing an assemble change: {', '.join(PENDING_LENGTH_AXES)}")

    rows = []
    for index, pair in enumerate(kept):
        trigger_a = transcript[slice(*pair.window_a())]
        trigger_b = transcript[slice(*pair.window_b())]
        stems = gate.secondary_stems(trigger_a, trigger_b, pair.len_x)
        stems = [s for s in stems if s.lock_energy <= 0.0]  # a positive lock is not a lock
        if not stems:
            continue
        stems = sorted(stems, key=lambda s: s.lock_energy)[: args.stems]
        shared = cheap_metrics(gate, trigger_a, trigger_b, pair)
        for stem_index, stem in enumerate(stems):
            base = gate.assemble(trigger_a, trigger_b, pair.len_x, stem)
            for closure, upper3, lower3, island in grid:
                axes = {
                    "closure": closure[1],
                    "upper3": upper3[1],
                    "lower3": lower3[1],
                    "island": island[1],
                }
                switch = build(base, axes)
                stem_dg = gate.main_stem_energies(
                    trigger_a, pair.len_x, switch.sequence[slice(*switch.domains["main_z"])]
                )
                rows.append(
                    {
                        **shared,
                        "x_start": pair.x_start,
                        "xstar_start": pair.xstar_start,
                        "a_start": pair.window_a()[0],
                        "a_end": pair.window_a()[1],
                        "b_start": pair.window_b()[0],
                        "b_end": pair.window_b()[1],
                        "stem_index": stem_index,
                        "scheme": stem.scheme,
                        "lock_energy": stem.lock_energy,
                        "a_site_energy": stem.a_site_energy,
                        "b_site_energy": stem.b_site_energy,
                        "ddg_pref": stem.ddg_pref,
                        "lock_minus_a_site": stem.lock_energy - stem.a_site_energy,
                        "closure": closure[0],
                        "upper3": upper3[0],
                        "lower3": lower3[0],
                        "island": island[0],
                        "toehold_trim": 0,
                        "rbs_loop_len": len(gate.RBS_FLANK) + len(gate.RBS_PROKARYOTIC),
                        "secondary_arm": gate.ARM_LEN,
                        "stem_dG": stem_dg[0],
                        "grip_alone": stem_dg[1],
                        "grip_with_x": stem_dg[2],
                        "switch": switch.sequence,
                    }
                )
        if index % 5 == 0:
            print(f"  {index + 1}/{len(kept)} pairs, {len(rows)} rows", flush=True)

    path = output_dir / f"{args.out}_cheap.csv"
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n{len(rows)} designs -> {path}")
    print("Tidy: one row per design, every axis its own column, sequence included, so any")
    print("two columns can be plotted against each other without re-running the sweep.")
    return 0


def _fold(gate, transcript, args, output_dir) -> int:
    source = output_dir / f"{args.out}_cheap.csv"
    if not source.exists():
        print(f"{source} not found -- run --stage cheap first")
        return 1
    with source.open(newline="") as handle:
        cheap = list(csv.DictReader(handle))
    print(f"{len(cheap)} designs from stage 1")

    # Stratify across the closure axis so no arm is starved, then take the strongest locks
    # within each -- lock_energy being the best single predictor we have (rho -0.938).
    by_closure: dict[str, list] = {}
    for row in cheap:
        by_closure.setdefault(row["closure"], []).append(row)
    quota = max(1, args.fold // max(1, len(by_closure)))
    chosen = []
    for _closure, group in by_closure.items():
        group.sort(key=lambda r: float(r["lock_energy"]))
        chosen.extend(group[:quota])
    print(f"folding {len(chosen)} designs, {quota} per closure arm")

    rows = []
    axis_lookup = {
        "closure": dict(CLOSURES),
        "upper3": dict(UPPER3),
        "lower3": dict(LOWER3),
        "island": dict(ISLAND),
    }
    for index, row in enumerate(chosen):
        # Rebuilt from the axis columns, not from the stored sequence, so stage 2 has the
        # full domain map and any disagreement between the two surfaces as an assertion
        # rather than as a silently wrong span.
        trigger_a = transcript[int(row["a_start"]) : int(row["a_end"])]
        trigger_b = transcript[int(row["b_start"]) : int(row["b_end"])]
        len_x = int(row["len_x"])
        stems = [
            s for s in gate.secondary_stems(trigger_a, trigger_b, len_x) if s.lock_energy <= 0.0
        ]
        stems.sort(key=lambda s: s.lock_energy)
        stem = stems[int(row["stem_index"])]
        base = gate.assemble(trigger_a, trigger_b, len_x, stem)
        switch = build(base, {name: axis_lookup[name][row[name]] for name in axis_lookup})
        if switch.sequence != row["switch"]:
            raise AssertionError(f"rebuild disagrees with stage 1 at row {index}")

        observed = gate.four_tube_observables(switch, trigger_a, trigger_b)
        rank = switch.span(-17, 13)
        out = dict(row)
        for state in ("00", "01", "10", "11"):
            strands = {
                "00": switch.sequence,
                "01": f"{switch.sequence}&{trigger_b}",
                "10": f"{switch.sequence}&{trigger_a}",
                "11": f"{switch.sequence}&{trigger_a}&{trigger_b}",
            }[state]
            matrix = gate.folder.pooled_pair_probabilities(strands)
            out[f"dG_open_{state}"] = observed[f"dG_open_{state}"]
            out[f"P_open_{state}"] = gate.folder.p_open(strands, rank)
            out[f"A_M_{state}"] = observed[f"A_M_{state}"]
            out[f"meanW_{state}"] = _mean_unpaired(matrix, *rank)
            out[f"aug_{state}"] = _mean_unpaired(matrix, *switch.domains["aug"])
            out[f"free_xstar_{state}"] = _mean_unpaired(matrix, *switch.domains["sw_xs"])
        out["separation"] = observed["separation"]
        out["ddG_AND"] = observed["ddG_AND"]
        out["dG_bind_B"] = observed["dG_bind_B"]
        out["d_off"] = observed["d_off"]
        means = [out[f"meanW_{st}"] for st in ("00", "01", "10", "11")]
        out["mean_separation"] = (
            means[3] - max(means[:3]) if all(m is not None for m in means) else None
        )
        # The kinetic arm: what trigger A finds on arrival, before it binds, on each path.
        out["log10_rate_advantage"] = min(6.0, len_x * out["free_xstar_01"]) - min(
            6.0, len_x * out["free_xstar_00"]
        )
        rows.append(out)
        if index % 10 == 0:
            print(f"  {index + 1}/{len(chosen)}", flush=True)

    path = output_dir / f"{args.out}_folded.csv"
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=sorted({k for r in rows for k in r}))
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n{len(rows)} folded -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
