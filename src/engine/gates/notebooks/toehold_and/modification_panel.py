"""Measure every proposed architecture modification side by side, on the same candidates.

    uv run python src/engine/gates/notebooks/toehold_and/modification_panel.py \\
        --fasta "path/to/mCherry original.txt" --pairs 4 --out modifications

**Why this exists.** Five modifications are on the table, drawn from Kim 2019 and Green
2014/2026. Arguing them from the literature is not enough — the papers disagree with each
other, and none of them built our architecture. This builds each modification as an actual
switch, folds all four tubes, and reports every observable, so the decision rests on our own
numbers rather than on analogy.

**Every variant is applied to the same base candidate**, so differences between rows are the
modification and nothing else. And every modification is measured on **several trigger
pairs**, because a single pair has twice now produced a result that did not replicate.

**The variants.**

``baseline``
    The design as it stands. Trigger A is the exact reverse complement of all 18 nt of the
    ascending arm (R1), and the AUG faces ``bulge*``.

``upper3``
    Green's forward-engineered change. The 3 bp nearest the RBS loop stop being
    trigger-derived and become a weak A-U ladder. Trigger A then covers 15 of 18 nt, which
    is what Kim's constructs do too. Green's own first generation used our rule and reached
    a mean ON/OFF of 43; this change was one of four that took the next generation to 406.

``upper6``
    The same idea taken to the whole 6-bp upper stem. **No published design does this** --
    Green and Kim both stop at 3 nt -- so unlike ``upper3`` it has no comparability argument
    behind it, only the hypothesis that more is better.

    An earlier description called it a negative control "with no effect on ``separation``".
    That was measured on a **lock-free** stem and is wrong on a locked one: with the
    strongest lock it reaches ``separation`` 2.11 and the best start-codon accessibility of
    any variant, 0.825. What it does **not** do is fix the leak -- ``A_M(10)`` stays at 0.425,
    twice tau4a's threshold, and ``A_M(11) - A_M(10)`` is only 0.016. So it moves the
    metrics without gating, which is a third category distinct from both "no effect" and
    "works".

    A second correction, on attribution: an earlier note here said no published design
    decouples more than 3 nt. Green 2014's forward-engineered switches and Kim both stop at
    3, but **VISTA goes much further** -- its trigger invades only 6 bp of the stem in total,
    leaving the inner lower stem, the whole bulge and the entire upper stem as invariant
    conserved sequence. Decoupling beyond 3 nt is therefore the VISTA direction, with
    ``stop_before_bulge`` (9 of 18 nt trigger-derived) our closest approach and VISTA
    further still.

``aug_paired``
    Give the bulge bonus to the switch: the 3 nt facing the ``AUG`` become its complement,
    so the switch's own arm pairs the start codon and trigger A mismatches there.

``stop_before_bulge``
    Trigger A's invasion stops at the bulge — both ``bulge*`` and ``k1*`` cease to be
    trigger-derived, leaving trigger A complementary to ``main_pre*`` only (9 of 18 nt).
    This is closest to VISTA, which leaves everything above 6 bp invariant.

``stabiliser``
    Kim's 26-nt 5' hairpin prepended to the switch. Nothing else changes. It is a stability
    element, not a logic element, so the question here is only whether it perturbs the
    folding of what follows.

**The AUG bulge size is a separate experiment**, run by ``--bulge-survey``: the loop size is
not a design knob but a property of the trigger window, since ``bulge*`` is
``revcomp(trigger_A[6:9])`` and the ``AUG`` faces it. Across 1036 surviving pairs only 20.7%
give the 3x3 loop R7 specifies; 27.0% give Kim's 1x1. The survey groups candidates by that
class and folds them, so the classes can be compared directly.

**No threshold is applied and no variant is filtered out.** Every row is reported with every
observable, including the ones that fail, because which gates a variant fails is the
informative part.
"""

import argparse
import csv
import math
import sys
from dataclasses import replace
from pathlib import Path

_SRC = Path(__file__).resolve().parents[4]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from engine import sequences as sq  # noqa: E402
from engine.domain import Host  # noqa: E402
from engine.gates.toehold import ProkaryoticToeholdAndGate, _mean_unpaired  # noqa: E402
from engine.gates.tools.binding import can_pair  # noqa: E402
from engine.gates.tools.codons import CodonOptimizer  # noqa: E402
from engine.gates.tools.folding import FoldEngine  # noqa: E402
from engine.gates.tools.translation import TranslationScorer  # noqa: E402

STATES = ("00", "01", "10", "11")
#: Kim's 5' stabilising hairpin for the switch transcript, folded here to
#: ...(((((((......)))))))... at -15.2 kcal/mol.
STABILISER = sq.to_rna("AACGGGCTGCAATAACGCAGCCCAAT")
#: A weak A-U ladder for the 3 bp nearest the loop. All 13 of Green's forward-engineered
#: switches hard-code AUA there; UAU is its reverse complement for the descending side.
WEAK_TOP = "AUA"


def read_fasta(path: str) -> str:
    lines = Path(path).read_text().splitlines()
    return sq.to_rna("".join(line.strip() for line in lines if not line.startswith(">")))


def patch(switch, **pieces):
    """Replace whole domains by name, lengths unchanged."""
    sequence = list(switch.sequence)
    for name, piece in pieces.items():
        start, end = switch.domains[name]
        if end - start != len(piece):
            raise ValueError(f"{name} is {end - start} nt, got {len(piece)}")
        sequence[start:end] = list(piece)
    return replace(switch, sequence="".join(sequence))


def bulge_class(trigger_a: str) -> int:
    """How many of the AUG's three bases the ascending arm can pair (wobbles counted).

    ``ascending[i]`` pairs ``descending[17-i]``, so ``bulge*`` positions 0,1,2 face G, U, A
    of the start codon. 0 paired is the 3x3 loop R7 specifies, 2 is Kim's 1x1.
    """
    ascending = sq.reverse_complement(trigger_a[6:9])
    return sum(can_pair(ascending[i], "GUA"[i]) for i in range(3))


def variants(gate, switch, trigger_a: str) -> dict:
    """Every modification, built on one base switch."""
    k1_star = switch.sequence[slice(*switch.domains["k1_star"])]
    main_z = switch.sequence[slice(*switch.domains["main_z"])]

    # The 3 bp nearest the loop are ascending[15:18] = k1*[3:6] against descending[0:3]
    # = main_z[0:3], read in reverse. Replacing both keeps the helix closed but takes the
    # sequence out of trigger A's reach.
    upper3_k1 = k1_star[:3] + WEAK_TOP
    upper3_z = sq.reverse_complement(WEAK_TOP) + main_z[3:]
    # upper6 as first written used GC-rich GCCGAC while upper3 used the weak A-U ladder,
    # so it compared length AND strength at once and could not separate them. Both are kept:
    # upper6_gc is the original, upper6_au matches upper3's composition so the pair of them
    # isolates length.
    upper6_k1 = sq.reverse_complement("GCCGAC")
    upper6_z = "GCCGAC"
    upper6_au_z = "AUAUAU"
    upper6_au_k1 = sq.reverse_complement(upper6_au_z)

    # The same idea applied to the INHIBITORY hairpin. Its upper helix is k2* against
    # secondary_z, adjacent to the secondary loop; trigger B binds k2* and trigger A never
    # touches it. Decoupling the top from trigger B should therefore cost B its grip while
    # leaving A unaffected -- the opposite of what the main hairpin's version does, which is
    # why it is worth measuring rather than assuming.
    k2_star = switch.sequence[slice(*switch.domains["k2_star"])]
    secondary_z = switch.sequence[slice(*switch.domains["secondary_z"])]

    # Give the AUG a partner: the ascending 3 nt become its complement.
    aug_partner = sq.reverse_complement("AUG")

    # Designed PARTIAL closure. bulge* faces G, U, A across the helix, so pairing position
    # 0 needs C or U, position 1 needs A or G, position 2 needs U. "CAU" pairs all three and
    # removes the loop; "CCU" leaves the middle unpaired (a designed 1x1 mid-helix); "CCC"
    # leaves two unpaired (a designed 2x2). Testing only the extreme would have left the
    # question "or design something else for the AUG?" unanswered.
    aug_pair_two = "CCU"
    aug_pair_one = "CCC"

    # DEPTH and GC CONTENT were confounded in the first pass: every closure tested happened
    # to be C-rich. Four 3-mers close the bulge completely -- CAU, CGU, UAU, UGU -- spanning
    # 0 to 2 G+C. Testing the two extremes at the SAME depth separates "how many positions
    # pair" from "how strong those pairs are", which are different design knobs.
    aug_closed_au = "UAU"  # depth 3, zero G+C -- the weakest full closure
    aug_closed_gc = "CGU"  # depth 3, two G+C -- the strongest

    out = {
        "baseline": switch,
        "upper3": patch(switch, k1_star=upper3_k1, main_z=upper3_z),
        "upper6": patch(switch, k1_star=upper6_k1, main_z=upper6_z),
        "upper6_au": patch(switch, k1_star=upper6_au_k1, main_z=upper6_au_z),
        "aug_paired": patch(switch, bulge_star=aug_partner),
        "aug_closed_au": patch(switch, bulge_star=aug_closed_au),
        "aug_closed_gc": patch(switch, bulge_star=aug_closed_gc),
        "aug_pair2": patch(switch, bulge_star=aug_pair_two),
        "aug_pair1": patch(switch, bulge_star=aug_pair_one),
        "stop_before_bulge": patch(
            switch, bulge_star=aug_partner, k1_star=upper6_k1, main_z=upper6_z
        ),
    }
    # The secondary hairpin's upper helix, decoupled from trigger B by 3 and by 6 nt. The
    # 3 nt nearest the secondary loop are the LAST of k2* against the FIRST of secondary_z,
    # mirroring the main hairpin's geometry one domain over.
    if len(k2_star) >= 3:
        out["sec_upper3"] = patch(
            switch,
            k2_star=k2_star[:-3] + "AUA",
            secondary_z=sq.reverse_complement("AUA") + secondary_z[3:],
        )
    if len(k2_star) >= 6:
        out["sec_upper6"] = patch(
            switch,
            k2_star=k2_star[:-6] + "AUAUAU",
            secondary_z=sq.reverse_complement("AUAUAU") + secondary_z[6:],
        )

    # The stabiliser changes the length, so it cannot go through `patch`: the domain map
    # would silently shift. Rebuilt with every domain offset instead.
    shifted = {
        name: (s + len(STABILISER), e + len(STABILISER)) for name, (s, e) in switch.domains.items()
    }
    out["stabiliser"] = replace(
        switch,
        sequence=STABILISER + switch.sequence,
        domains=shifted,
        dot_bracket="." * len(STABILISER) + switch.dot_bracket,
    )
    del trigger_a
    return out


def observe(gate, switch, trigger_a: str, trigger_b: str) -> dict:
    """Four tubes plus the probabilities and the start codon, for one built switch."""
    o = gate.four_tube_observables(switch, trigger_a, trigger_b)
    rank = switch.span(-17, 13)
    tubes = {
        "00": switch.sequence,
        "01": f"{switch.sequence}&{trigger_b}",
        "10": f"{switch.sequence}&{trigger_a}",
        "11": f"{switch.sequence}&{trigger_a}&{trigger_b}",
    }
    row: dict = {}
    for state in STATES:
        row[f"dG_open_{state}"] = o[f"dG_open_{state}"]
        row[f"P_open_{state}"] = gate.folder.p_open(tubes[state], rank)
        row[f"A_M_{state}"] = o[f"A_M_{state}"]
        row[f"A_S_{state}"] = o[f"A_S_{state}"]
        matrix = gate.folder.pooled_pair_probabilities(tubes[state])
        row[f"aug_{state}"] = _mean_unpaired(matrix, *switch.domains["aug"])
        row[f"meanW_{state}"] = _mean_unpaired(matrix, *rank)
    row["separation"] = o["separation"]
    row["ddG_AND"] = o["ddG_AND"]
    row["dG_bind_B"] = o["dG_bind_B"]
    row["dG_bind_A_given_B"] = o["dG_bind_A_given_B"]
    row["d_off"] = o["d_off"]
    off = [row["dG_open_00"], row["dG_open_01"]]
    on = row["dG_open_11"]
    row["separation_no_10"] = (
        min(v - on for v in off) if on is not None and all(v is not None for v in off) else None
    )
    # The averaged analogue of separation, which is the form that actually rank-correlated
    # with Green's 168 measured switches (rho +0.32 against -0.11 for the joint form).
    if row["meanW_11"] is not None and all(row[f"meanW_{s}"] is not None for s in STATES):
        row["mean_separation"] = row["meanW_11"] - max(
            row[f"meanW_{s}"] for s in ("00", "01", "10")
        )
        row["mean_separation_no_10"] = row["meanW_11"] - max(row["meanW_00"], row["meanW_01"])
    else:
        row["mean_separation"] = row["mean_separation_no_10"] = None
    row["gates_failed"] = ";".join(gate.gate_violations(o)) or "-"
    return row


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fasta", required=True)
    parser.add_argument("--pairs", type=int, default=4, help="base candidates to modify")
    parser.add_argument("--stem", default="strongest", help="'strongest' or an index")
    parser.add_argument(
        "--bulge-survey",
        type=int,
        default=0,
        help="also fold N candidates from EACH AUG-bulge class (0,1,2 pairable positions)",
    )
    parser.add_argument("--out", default="modifications")
    args = parser.parse_args(argv)

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
    print(f"{len(kept)} pairs survive stage 1")

    rows = []

    def run(pair, label_extra: str = "") -> None:
        trigger_a = transcript[slice(*pair.window_a())]
        trigger_b = transcript[slice(*pair.window_b())]
        stems = gate.secondary_stems(trigger_a, trigger_b, pair.len_x)
        stem = (
            min(stems, key=lambda s: s.lock_energy)
            if args.stem == "strongest"
            else stems[int(args.stem)]
        )
        base = gate.assemble(trigger_a, trigger_b, pair.len_x, stem)
        klass = bulge_class(trigger_a)
        print(
            f"\n=== x@{pair.x_start} len_x={pair.len_x} {stem.scheme} "
            f"lock {stem.lock_energy:.1f} · AUG bulge {3 - klass}x{3 - klass} {label_extra}==="
        )
        print(
            f"  {'variant':<19}{'sep':>7}{'sep-10':>8}{'meanSep':>9}"
            f"{'A_M11':>7}{'A_M10':>7}{'AUG11':>7}{'dG11':>7}{'P_open11':>11}"
        )
        for name, built in variants(gate, base, trigger_a).items():
            row = observe(gate, built, trigger_a, trigger_b)
            row.update(
                variant=name,
                x_start=pair.x_start,
                len_x=pair.len_x,
                scheme=stem.scheme,
                lock_energy=stem.lock_energy,
                bulge_pairable=klass,
                bulge_loop=f"{3 - klass}x{3 - klass}",
                switch=built.sequence,
            )
            rows.append(row)
            print(
                f"  {name:<19}{row['separation']:>7.2f}{row['separation_no_10']:>8.2f}"
                f"{row['mean_separation']:>9.3f}{row['A_M_11']:>7.3f}{row['A_M_10']:>7.3f}"
                f"{row['aug_11']:>7.3f}{row['dG_open_11']:>7.2f}{row['P_open_11']:>11.2e}"
            )

    for pair in kept[: args.pairs]:
        run(pair)

    if args.bulge_survey:
        print("\n\n########## AUG bulge-class survey ##########")
        by_class: dict[int, list] = {0: [], 1: [], 2: []}
        for pair in kept:
            klass = bulge_class(transcript[slice(*pair.window_a())])
            if klass in by_class:
                by_class[klass].append(pair)
        for klass, members in by_class.items():
            print(f"\nclass {klass} pairable -> {3 - klass}x{3 - klass} loop: {len(members)} pairs")
            for pair in members[: args.bulge_survey]:
                run(pair, label_extra="[survey] ")

    path = output_dir / f"{args.out}.csv"
    fields = sorted({k for r in rows for k in r})
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n{len(rows)} rows -> {path}")

    print("\nPer-variant medians across every base candidate:")
    header = f"  {'variant':<19}{'sep':>8}{'sep-10':>9}{'meanSep':>10}"
    header += f"{'A_M11':>8}{'A_M10':>8}{'AUG11':>8}"
    print(header)
    names = []
    for row in rows:
        if row["variant"] not in names:
            names.append(row["variant"])
    for name in names:
        group = [r for r in rows if r["variant"] == name]

        def med(key, group=group):
            values = sorted(v for v in (r[key] for r in group) if v is not None)
            return values[len(values) // 2] if values else math.nan

        print(
            f"  {name:<19}{med('separation'):>8.2f}{med('separation_no_10'):>9.2f}"
            f"{med('mean_separation'):>10.3f}{med('A_M_11'):>8.3f}{med('A_M_10'):>8.3f}"
            f"{med('aug_11'):>8.3f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
