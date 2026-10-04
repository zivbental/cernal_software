"""Can the rest of the transcript fire the gate, or block it?

    uv run python src/engine/gates/notebooks/toehold_and/off_target_scan.py \
        --fasta src/engine/gates/notebooks/toehold_and/mCherry_original.txt --out offtarget

Two failure modes the four tubes never show, because they only ever contain the two
triggers we chose. Nothing stops ViennaRNA folding a third or fourth molecule -- it does,
and the second pass below does exactly that -- so this is a gap in what we simulate, not in
what the tool can simulate.

**Q_false — a false ON.** Some other window of mCherry mimics a trigger closely enough to
bind the switch's binding site and fire the gate on its own. A decoy that is to bind the
site trigger A occupies must carry trigger A's own sequence there, so this reduces to:
how long a stretch of the trigger's binding portion recurs elsewhere in the transcript?

**Q_fail — a failed ON.** Some other window occupies a nucleation site on the switch, so
the real trigger has nowhere to start. The sites are `r2*`, which trigger B must find free,
and `x*`, which trigger A nucleates on once B has unlocked it. A blocker must be
complementary to the site, which is the same as carrying the trigger's sequence there, so
the reduction is identical.

**Both are properties of the PAIR, not of a design.** `r2*`, `x*` and the A-binding site are
all fixed once the trigger pair is chosen, so one row per pair joins to every design built
on it -- 1,243 rows rather than 400,000.

**Two passes, cheap then decisive.** The first is a pure sequence screen over every pair:
it finds a decoy that COULD bind, which is fast but blunt, and it reports the run length so
the threshold stays arguable instead of buried. The second folds only what the first
flagged, four strands at a time, and answers the question the screen cannot:

    switch + decoy           against switch alone     -- does it FIRE the gate?
    switch + A + B + decoy   against switch + A + B   -- does it BLOCK the real triggers?

A long repeat is a candidate for a problem, not a problem. On the first pair we checked by
hand, an 11-nt mimic bound the switch at about -14 kcal/mol and moved A_M by 0.000 in
either direction: real binding, no consequence. ``--no-fold`` keeps the cheap pass alone.

**Not the same as orthogonality.** That term, in the design guide, is gate-against-gate
crosstalk between two switches in one cell. This is transcript-against-switch: the target
molecule interfering with its own sensor.
"""

import argparse
import csv
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[4]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from full_sweep import PAIR_KEY_COLUMNS, read_fasta  # noqa: E402
from narrate import Progress, banner, conclude  # noqa: E402

from engine.domain import Host  # noqa: E402
from engine.gates.toehold import ProkaryoticToeholdAndGate, _mean_unpaired  # noqa: E402
from engine.gates.tools.codons import CodonOptimizer  # noqa: E402
from engine.gates.tools.folding import FoldEngine  # noqa: E402
from engine.gates.tools.translation import TranslationScorer  # noqa: E402

#: A run at or above this is worth folding before the pair is ordered. Reported, never
#: applied: the whole point of printing the run length is that the cut stays arguable.
NOTABLE = 10

#: Decoy context taken either side of the matching stretch, so the fold sees a real
#: transcript window rather than a bare repeat.
FLANK = 6

#: How much the decoy must move A_M before it counts as firing or blocking the gate. The
#: four-tube numbers move by ~0.007 between tubes that should be identical, so anything
#: under this is noise rather than an effect.
MOVED = 0.05


def longest_elsewhere(motif: str, transcript: str, exclude: tuple[int, int]) -> tuple[int, int]:
    """The longest stretch of ``motif`` that also occurs OUTSIDE ``exclude``.

    Returns ``(length, position)``, position being where the copy sits in the transcript.
    Occurrences inside the trigger's own window are skipped -- a trigger matching itself is
    not an off-target, and not excluding it would report every pair as maximally hazardous.
    """
    best = (0, -1)
    for start in range(len(motif)):
        # Only lengths that could beat the incumbent are worth testing.
        for end in range(start + best[0] + 1, len(motif) + 1):
            piece = motif[start:end]
            at = transcript.find(piece)
            found = -1
            while at >= 0:
                if not (exclude[0] <= at and at + len(piece) <= exclude[1]):
                    found = at
                    break
                at = transcript.find(piece, at + 1)
            if found < 0:
                break
            best = (end - start, found)
    return best


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fasta", required=True)
    parser.add_argument("--out", default="offtarget")
    parser.add_argument(
        "--no-fold",
        action="store_true",
        help="skip the thermodynamic second pass and report the sequence screen alone",
    )
    args = parser.parse_args(argv)

    output_dir = Path(__file__).resolve().parent / "results"
    output_dir.mkdir(parents=True, exist_ok=True)
    gate = ProkaryoticToeholdAndGate(
        Host.ECOLI, FoldEngine(37.0), TranslationScorer(Host.ECOLI), CodonOptimizer(Host.ECOLI)
    )
    transcript = read_fasta(args.fasta)
    pairs = list(gate.find_trigger_pairs(transcript))

    banner(
        "OFF-TARGET SCAN - can mCherry fire its own gate, or block it?",
        [
            f"{len(pairs)} trigger pairs, no folding -- both quantities are pair-level",
            "Q_false: another window mimics a trigger and fires the gate alone",
            "Q_fail: another window occupies a nucleation site and blocks the real trigger",
            f"a run of {NOTABLE} nt or more is reported as notable, never filtered on",
        ],
        estimate=len(pairs) * 0.02,
    )
    bar = Progress(len(pairs), "pairs")

    rows = []
    for pair in pairs:
        rna_a = transcript[slice(*pair.window_a())]
        rna_b = transcript[slice(*pair.window_b())]
        # The portion of each trigger that actually touches the switch. A is k1+bulge+
        # main_pre, the 18 nt it invades; B is r2, its 32-nt toehold grip. x is the overlap
        # both share, and the site trigger A nucleates on once B has freed it.
        a_site = rna_a[: gate.ARM_LEN]
        len_k2 = gate.SECONDARY_INVASION_LEN - pair.len_x
        r2 = rna_b[len_k2 + pair.len_x :]
        x = rna_a[gate.ARM_LEN : gate.ARM_LEN + pair.len_x]

        fa_len, fa_at = longest_elsewhere(a_site, transcript, pair.window_a())
        fb_len, fb_at = longest_elsewhere(r2, transcript, pair.window_b())
        # A blocker of x* only has to present x, which is 4-8 nt and recurs by chance in a
        # 711-nt transcript, so this column is reported for completeness and is expected to
        # saturate. It is the A-site and r2 columns that carry information.
        fx_len, fx_at = longest_elsewhere(x, transcript, pair.window_a())

        row = dict(
            zip(
                PAIR_KEY_COLUMNS,
                (pair.x_start, pair.xstar_start, *pair.window_a(), *pair.window_b()),
                strict=True,
            )
        )
        row.update(
            len_x=pair.len_x,
            q_false_a=fa_len,
            q_false_a_at=fa_at,
            q_false_b=fb_len,
            q_false_b_at=fb_at,
            q_fail_x=fx_len,
            q_fail_x_at=fx_at,
            q_worst=max(fa_len, fb_len),
            notable=max(fa_len, fb_len) >= NOTABLE,
        )
        rows.append(row)
        bar.step(f"x@{pair.x_start}  worst run {row['q_worst']}")
    bar.finish()

    # ---- second pass: fold what the sequence screen flagged -------------------------
    #
    # The screen is cheap and blunt: it finds a decoy that COULD bind, not one that does
    # anything. ViennaRNA folds four strands perfectly well -- switch, both triggers and a
    # decoy -- so each flag gets decided rather than left as a worry:
    #
    #   Q_false  switch + decoy        against switch alone      -- does it fire the gate?
    #   Q_fail   switch + A + B + decoy against switch + A + B    -- does it block it?
    #
    # The switch here is `assemble`'s BASE molecule, before any axis patch. That is the
    # right level for this question: r2*, x* and the main stem are all trigger-derived, and
    # the closure and stem-composition axes do not move them.
    flagged = [r for r in rows if r["notable"]]
    if flagged and not args.no_fold:
        print()
        banner(
            "SECOND PASS - folding the flagged pairs",
            [
                f"{len(flagged)} pairs carry a run of {NOTABLE} nt or more",
                "switch + decoy asks whether it FIRES the gate on its own",
                "switch + A + B + decoy asks whether it BLOCKS the real triggers",
                f"a shift in A_M below {MOVED} is read as noise, not an effect",
            ],
            estimate=len(flagged) * 6.0,
        )
        bar2 = Progress(len(flagged), "flagged pairs")
        by_key = {(r["x_start"], r["xstar_start"]): r for r in rows}
        for pair in pairs:
            row = by_key.get((pair.x_start, pair.xstar_start))
            if row is None or not row["notable"]:
                continue
            rna_a = transcript[slice(*pair.window_a())]
            rna_b = transcript[slice(*pair.window_b())]
            stems = list(gate.secondary_stems(rna_a, rna_b, pair.len_x))
            if not stems:
                bar2.step(f"x@{pair.x_start}  no stem")
                continue
            switch = gate.assemble(rna_a, rna_b, pair.len_x, stems[0]).sequence
            at, run = row["q_false_a_at"], row["q_false_a"]
            if row["q_false_b"] > run:
                at, run = row["q_false_b_at"], row["q_false_b"]
            decoy = transcript[max(0, at - FLANK) : at + run + FLANK]
            n = len(switch)
            span = (n - 75 + 36, n - 75 + 54)  # main_z through main_pre: the A_M window

            def a_m(tube, window=span, folder=gate.folder):
                return _mean_unpaired(folder.pooled_pair_probabilities(tube), *window)

            base_off = a_m(switch)
            with_decoy = a_m(f"{switch}&{decoy}")
            base_on = a_m(f"{switch}&{rna_a}&{rna_b}")
            on_decoy = a_m(f"{switch}&{rna_a}&{rna_b}&{decoy}")
            row.update(
                decoy=decoy,
                a_m_off=round(base_off, 4),
                a_m_off_decoy=round(with_decoy, 4),
                a_m_on=round(base_on, 4),
                a_m_on_decoy=round(on_decoy, 4),
                fires=with_decoy - base_off > MOVED,
                blocks=base_on - on_decoy > MOVED,
            )
            row["verdict"] = "FIRES" if row["fires"] else ("BLOCKS" if row["blocks"] else "inert")
            bar2.step(f"x@{pair.x_start}  {row['verdict']}")
        bar2.finish()

    # Every row carries the same columns, whether or not it was folded: a missing key would
    # make DictWriter raise on the first unflagged row.
    blank = dict.fromkeys(
        (
            "decoy",
            "a_m_off",
            "a_m_off_decoy",
            "a_m_on",
            "a_m_on_decoy",
            "fires",
            "blocks",
            "verdict",
        )
    )
    rows = [{**blank, **r} for r in rows]

    path = output_dir / f"{args.out}.csv"
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    worst = sorted(r["q_worst"] for r in rows)
    flagged = [r for r in rows if r["notable"]]
    findings = [
        f"{len(rows):,} trigger pairs scanned against the whole {len(transcript)}-nt "
        f"transcript, with each trigger's own window excluded.",
        f"Longest decoy run: median {worst[len(worst) // 2]}, "
        f"p90 {worst[int(len(worst) * 0.9)]}, max {worst[-1]} nt.",
        f"{len(flagged):,} pairs ({100 * len(flagged) / len(rows):.1f}%) carry a run of "
        f"{NOTABLE} nt or more somewhere else in mCherry that could bind a site the gate "
        f"needs. Nothing is filtered here -- join on the six pair-key columns and decide.",
    ]
    if flagged:
        top = sorted(flagged, key=lambda r: -r["q_worst"])[:5]
        findings.append(
            "Worst by run length: "
            + ", ".join(f"x@{r['x_start']}/x*{r['xstar_start']} ({r['q_worst']} nt)" for r in top)
        )
    judged = [r for r in rows if r.get("verdict")]
    if judged:
        fires = [r for r in judged if r["fires"]]
        blocks = [r for r in judged if r["blocks"]]
        findings.append(
            f"Folded {len(judged):,} of them: {len(fires):,} FIRE the gate on their own, "
            f"{len(blocks):,} BLOCK the real triggers, and "
            f"{len(judged) - len(fires) - len(blocks):,} bind and do nothing. A long repeat "
            f"is a candidate for a problem, not a problem -- only the fold decides."
        )
        for r in sorted(fires + blocks, key=lambda r: -r["q_worst"])[:5]:
            findings.append(
                f"  {r['verdict']}: x@{r['x_start']}/x*{r['xstar_start']}, {r['q_worst']} nt, "
                f"A_M {r['a_m_off']} -> {r['a_m_off_decoy']} off, "
                f"{r['a_m_on']} -> {r['a_m_on_decoy']} on"
            )
    conclude(findings, wrote=[str(path)])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
