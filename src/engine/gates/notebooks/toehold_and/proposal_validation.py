"""Measure the proposed six-component objective function against VISTA's 189 measured switches.

    uv run python src/engine/gates/notebooks/toehold_and/proposal_validation.py
    # with the supplementary tables somewhere else
    uv run python .../proposal_validation.py --data "<Green 2026 dir>"

**What is being tested, and what the claim was.** A proposal (``cernal_scoring_pipeline-v2.py``)
defines a weighted sum of six logistic-mapped sub-scores and its docstring states
``Pearson r = 0.7267 | Spearman r_s = 0.7507 | R^2 = 0.5281`` against 189 full-length RNA targets.
The accompanying analysis says plainly that the script itself was only ever run on two synthetic
candidates, and that the r² = 0.53 belongs to **VISTA's own PLS-DA model** -- a fitted
latent-variable classifier, not a hand-weighted sum. So the number has never been measured for
this function. This measures it.

**Why it is now possible.** Green 2026's supplementary tables close the two gaps:

    Table 4   189 rows: Switch Sequence (141 nt), Target Sequence (36 nt), and the measured
              OFF / ON-truncated / ON-full, so both ON/OFF ratios are available.
    Table 5   VISTA's own Switch Off MFE and RBS-Linker MFE per switch -- used directly rather
              than refolded, so S2 and S6 carry their numbers and not ours.
    Table 7   the 711-nt transcript's pair-probability matrix, including 711 per-base unpaired
              probabilities. All 189 target sequences are exact substrings of our mCherry, so
              S1's +/-25 nt window accessibility is computable from VISTA's own ensemble.

Every sub-score follows the proposal's formulas and midpoints exactly. The one deliberate
adaptation is noted where it happens: the codon scan is **3 codons, not 8**, because VISTA's designs
carry engineered refolding sequence between the hairpin and the linker while ours go straight to a
fixed linker -- scanning 8 would scan constant sequence. Both are reported.
"""

import argparse
import csv
import math
import statistics as st
import sys
from pathlib import Path

NB = Path(__file__).resolve().parent
sys.path.insert(0, str(NB.parents[4] / "src"))
sys.path.insert(0, str(NB))

from full_sweep import read_fasta  # noqa: E402
from metric_correlations import pearson, ranks, spearman  # noqa: E402

from engine import sequences as sq  # noqa: E402
from engine.gates.tools.folding import FoldEngine  # noqa: E402

DEFAULT_DATA = Path(r"C:\Users\Dell\OneDrive - mail.tau.ac.il\IGEM\Toehold\Green 2026")

#: The proposal's weights, verbatim.
WEIGHTS = {
    "S1_target_access": 0.25,
    "S2_off_mfe": 0.20,
    "S3_joint_open_ON": 0.20,
    "S4_stem_architecture": 0.15,
    "S5_logic_occlusion": 0.12,
    "S6_translation": 0.08,
}

#: The proposal's rare-codon set, in DNA as it writes them.
RARE_CODONS = {"AGG", "AGA", "CGA", "CGG", "CTA", "ATA", "CCC", "TCG"}

RBS = "AACAGAGGAGA"


def logistic(value: float, midpoint: float, steepness: float, higher_is_better: bool) -> float:
    x = steepness * (value - midpoint) if higher_is_better else steepness * (midpoint - value)
    try:
        return 1.0 / (1.0 + math.exp(-x))
    except OverflowError:
        return 1.0 if x > 0 else 0.0


def unpaired_profile(path: Path) -> dict[int, float]:
    """Per-base unpaired probability from Table 7, converted to 0-based indices.

    Table 7 is 1-based and marks an unpaired probability by putting -1 in the partner column.
    Converted here once, because every coordinate crossing in this project has been an off-by-one
    until asserted -- and the assertion is that all 189 target sequences are exact substrings of
    the transcript, which only holds if the frame is right.
    """
    out: dict[int, float] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.reader(handle):
            if len(row) < 5 or row[2] != "-1":
                continue
            try:
                out[int(row[1]) - 1] = float(row[4])
            except ValueError:
                continue
    return out


def score_s1(profile: dict[int, float], start: int, end: int, flank: int, rt: float) -> tuple:
    """S1: target accessibility over the site plus ``flank`` nt each side.

    The proposal computes ``P_target_open`` as a constrained partition ratio and
    ``dG_access = -RT ln P``, then scores ``exp(-dG_access / RT)`` -- which is algebraically just
    ``P_target_open`` again, so the two steps cancel. What is implemented here is the mean per-base
    unpaired probability over the window, which is the quantity Table 7 supplies and the same form
    Green 2014 S14.3 uses. The proposal's second term, a logistic on ``dG_access``, is kept.
    """
    lo, hi = max(0, start - flank), end + flank
    values = [profile[i] for i in range(lo, hi) if i in profile]
    if not values:
        return None, None
    p_open = st.fmean(values)
    # dG = -RT ln P over the window, from the same profile, so both terms share one source.
    joint = max(min(p_open, 1.0 - 1e-12), 1e-12)
    dg_access = -rt * math.log(joint)
    energy = logistic(dg_access, midpoint=3.0, steepness=0.8, higher_is_better=False)
    return 0.6 * p_open + 0.4 * energy, p_open


def score_s2(off_mfe: float, ned: float) -> float:
    """S2: OFF-state closure. Midpoint -35 for an AND gate, -30 otherwise; VISTA is single-input."""
    mfe = logistic(off_mfe, midpoint=-30.0, steepness=0.2, higher_is_better=False)
    return 0.5 * mfe + 0.5 * max(0.0, 1.0 - ned)


def score_s4(switch: str, rbs_at: int) -> tuple[float, str]:
    """S4: the 2S/1W bottom and 3-WWW top rules, read off the switch sequence.

    The stem is the hairpin whose loop holds the RBS, so its arms are the 18 nt before the loop and
    their reverse complement after it. "Bottom" is the base of the hairpin -- the outermost 3 pairs,
    furthest from the loop -- and "top" the 3 nearest it. A toehold switch's ascending arm sits
    immediately 5' of the loop, so the bottom pairs are at the 5' end of that arm.
    """
    loop_start = rbs_at - 3
    arm = switch[max(0, loop_start - 18) : loop_start]
    if len(arm) < 18:
        return 0.0, "arm too short"
    # Ascending arm 5'->3'; its partner is the descending arm read 3'->5', which is the
    # reverse complement. Pairs are (arm[i], revcomp(arm)[len-1-i]) == (arm[i], complement).
    strong = [sq.reverse_complement(base) in ("G", "C") and base in ("G", "C") for base in arm]
    bottom = sum(strong[:3])
    top = sum(strong[-3:])
    bottom_score = {2: 1.0, 1: 0.6, 3: 0.2}.get(bottom, 0.0)
    top_score = {0: 1.0, 1: 0.8}.get(top, 0.3)
    return 0.6 * bottom_score + 0.4 * top_score, f"bottom {bottom}S top {top}S"


def score_s6(linker_mfe: float, downstream: str, codons: int) -> float:
    """S6: linker energy and a rare-codon scan over ``codons`` codons downstream of the site."""
    linker = logistic(linker_mfe, midpoint=-5.0, steepness=0.5, higher_is_better=True)
    seq = downstream.upper().replace("U", "T")
    need = 3 * codons
    rare = 0
    if len(seq) >= need:
        rare = sum(1 for i in range(0, need, 3) if seq[i : i + 3] in RARE_CODONS)
    codon_score = {0: 1.0, 1: 0.5}.get(rare, 0.0)
    return 0.5 * linker + 0.5 * codon_score


def report(label: str, xs: list[float], ys: list[float]) -> None:
    rho, lin = spearman(xs, ys), pearson(xs, ys)
    r2 = lin * lin if lin is not None else None
    # R^2 of the rank fit too, because the proposal reports R^2 beside a Spearman and those are
    # different quantities; printing one labelled as the other is how 0.53 travelled.
    rank_r = pearson(ranks(xs), ranks(ys))
    print(
        f"    {label:30s} rho {rho:+.4f}   r {lin:+.4f}   R^2(linear) {r2:.4f}"
        f"   R^2(rank) {rank_r * rank_r:.4f}"
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", default=str(DEFAULT_DATA))
    parser.add_argument("--flank", type=int, default=25, help="S1 flank, nt each side")
    parser.add_argument("--codons", type=int, default=3, help="S6 codon scan length")
    args = parser.parse_args(argv)

    data = Path(args.data)
    folder = FoldEngine(37.0)
    transcript = read_fasta(NB / "mCherry_original.txt")
    dna = transcript.replace("U", "T")

    t4 = {
        r["Index"]: r
        for r in csv.DictReader((data / "Supplementary_Table4.csv").open(encoding="utf-8-sig"))
        if r.get("Index")
    }
    t5 = {
        r["Index"]: r
        for r in csv.DictReader((data / "Supplementary_Table5.csv").open(encoding="utf-8-sig"))
        if r.get("Index")
    }
    profile = unpaired_profile(data / "Supplementary_Table7.csv")
    print(f"  Table 4 {len(t4)} switches, Table 5 {len(t5)}, Table 7 {len(profile)} positions\n")

    def number(row: dict, key: str) -> float | None:
        value = (row.get(key) or "").strip()
        if not value:
            return None
        try:
            result = float(value)
        except ValueError:
            return None
        return None if math.isnan(result) or math.isinf(result) else result

    rows = []
    skipped: dict[str, int] = {}
    for index, row4 in t4.items():
        row5 = t5.get(index)
        if row5 is None:
            skipped["no Table 5 row"] = skipped.get("no Table 5 row", 0) + 1
            continue
        switch = (row4.get("Switch Sequence") or "").strip().upper().replace("T", "U")
        target = (row4.get("Target Sequence") or "").strip().upper().replace("U", "T")
        at = dna.find(target)
        if not switch or at < 0:
            skipped["target not in the transcript"] = (
                skipped.get("target not in the transcript", 0) + 1
            )
            continue
        rbs_at = switch.find(RBS)
        if rbs_at < 0:
            skipped["RBS not found in the switch"] = (
                skipped.get("RBS not found in the switch", 0) + 1
            )
            continue

        off_mfe = number(row5, "Switch Off MFE")
        linker_mfe = number(row5, "RBS-Linker MFE")
        on_full = number(row4, "ON OFF Full")
        on_trunc = number(row4, "ON OFF Truncated")
        if None in (off_mfe, linker_mfe, on_full):
            skipped["a measured value is blank"] = skipped.get("a measured value is blank", 0) + 1
            continue

        s1, p_open = score_s1(profile, at, at + len(target), args.flank, folder.rt)
        # NED of the OFF state against its own MFE structure, length-normalised: the same stand-in
        # `green_calibration` uses, because the published switches carry no intended dot-bracket.
        folded = folder.mfe(switch)
        ned = folder.ensemble_defect(switch, folded.structure) / len(switch)
        s2 = score_s2(off_mfe, ned)
        # S3: the joint probability that RBS through AUG is open, in the ON complex. The trigger is
        # the target's reverse complement, which is what the switch was designed against.
        trigger = sq.reverse_complement(transcript[at : at + len(target)])
        window = (rbs_at, min(len(switch), rbs_at + len(RBS) + 12))
        s3 = folder.p_open(f"{switch}&{trigger}", window)
        s4, s4_note = score_s4(switch, rbs_at)
        downstream = dna[at + len(target) : at + len(target) + 3 * max(args.codons, 8)]
        s6 = score_s6(linker_mfe, downstream, args.codons)
        rows.append(
            {
                "index": index,
                "on_full": on_full,
                "on_trunc": on_trunc,
                "S1": s1,
                "S2": s2,
                "S3": 0.0 if s3 is None else s3,
                "S4": s4,
                "S5": 1.0,
                "S6": s6,
                "p_open_25": p_open,
                "s4_note": s4_note,
            }
        )

    print(f"  {len(rows)} switches scored" + (f", skipped {skipped}" if skipped else ""))
    if len(rows) < 10:
        print("  too few to measure.")
        return 1

    composite = []
    for row in rows:
        total = 0.0
        for key, weight in WEIGHTS.items():
            short = "S" + key[1]
            value = row.get(short)
            total += weight * (0.0 if value is None else value)
        composite.append(total)

    for measured, name in (
        ("on_full", "ON/OFF, FULL-LENGTH target"),
        ("on_trunc", "ON/OFF, TRUNCATED trigger"),
    ):
        ys = [r[measured] for r in rows if r[measured] is not None]
        keep = [i for i, r in enumerate(rows) if r[measured] is not None]
        if len(ys) < 10:
            continue
        print(f"\n=== against {name}  (n={len(ys)}) ===")
        report("THE PROPOSED COMPOSITE", [composite[i] for i in keep], ys)
        print("    --- its components, each alone ---")
        for short, label in (
            ("S1", "S1 target access +/-25nt"),
            ("S2", "S2 OFF closure"),
            ("S3", "S3 joint open ON"),
            ("S4", "S4 stem architecture"),
            ("S6", "S6 translation"),
        ):
            xs = [rows[i][short] for i in keep]
            if any(x is None for x in xs):
                print(f"    {label:30s} not computable")
                continue
            if len(set(xs)) < 2:
                print(f"    {label:30s} constant at {xs[0]:.4f} -- carries no information")
                continue
            report(label, xs, ys)

    print("\n  S5 is constant at 1.0: it is the AND-gate occlusion rule and VISTA is single-input.")
    print(f"  S1 flank is +/-{args.flank} nt; S6 scans {args.codons} codons.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
