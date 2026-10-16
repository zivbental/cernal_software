"""The proposed function on Green's two libraries, and a check of its S4 against Green's own claim.

    uv run --with openpyxl python \\
        src/engine/gates/notebooks/toehold_and/proposal_on_green.py

``proposal_validation.py`` measured the proposal on VISTA's 189, where its composite came out at
rho +0.234 against a claimed 0.751, and where its S4 stem-architecture term read **-0.078**. That
last number deserved challenging: Green 2014 reports the stem's base-pair composition as a clear
discriminator, so a near-zero or wrong-signed S4 looks more like my implementation than like his
result.

**It is neither, and the distinction is the point.** Green's S13 does not claim the composition
predicts performance. It says correlations *emerged when the library was split by* top-of-stem
composition -- "significant correlations began to emerge as we began to analyze subsets of the
library that satisfied different sequence criteria... Correlations are particularly strong for those
subsets in which there is a weak base pair at the top of the stem, with dG_RBS-linker consistently
providing better R2 values". So composition is a **conditioning variable**: it says which switches
dG_RBS-linker predicts well, not which switches work. Scoring it directly, as S4 does, asks a
question Green never answered in the affirmative.

This script tests both readings on the same data: S4 as a direct score, and Green's actual claim
that dG_RBS-linker correlates better inside the weak-top subsets.
"""

import argparse
import glob
import os
import sys
from pathlib import Path

NB = Path(__file__).resolve().parent
sys.path.insert(0, str(NB.parents[4] / "src"))
sys.path.insert(0, str(NB))

from green_calibration import load_switches  # noqa: E402
from metric_correlations import pearson, spearman  # noqa: E402
from proposal_validation import WEIGHTS, score_s2, score_s6  # noqa: E402

from engine.gates.tools.folding import FoldEngine  # noqa: E402

GREEN_2014 = Path(r"C:\Users\Dell\OneDrive - mail.tau.ac.il\IGEM\Toehold\Green 2014")

#: Green's 11-nt prokaryotic RBS, which locates the loop and therefore the stem arms.
RBS = "AACAGAGGAGA"

#: Nucleotides after the AUG that the linker occupies, so the codon scan knows where to stop.
LINKER_AFTER_AUG = 9


def find_table(directory: Path, prefix: str) -> Path | None:
    hits = [
        p
        for p in glob.glob(os.path.join(str(directory), "*.xlsx"))
        if os.path.basename(p).startswith(prefix)
    ]
    return Path(hits[0]) if hits else None


def stem_pairs(switch: str) -> tuple[int, int] | None:
    """``(strong pairs in the bottom 3, strong pairs in the top 3)`` of the RBS hairpin's stem.

    The ascending arm is the 18 nt immediately 5' of the loop that holds the RBS. "Top" is the end
    nearest the loop and "bottom" the end furthest from it, which is the convention Green's
    2S/1W-at-the-bottom and 3-WWW-at-the-top rules use.

    A pair is strong when the ascending base is G or C -- its partner on the descending arm is the
    complement by construction, so G pairs with C either way round and no second lookup is needed.
    Returning ``None`` rather than guessing when the RBS is absent: a switch whose loop cannot be
    located has no identifiable stem and must not be scored as though it did.
    """
    at = switch.find(RBS)
    if at < 0:
        return None
    loop_start = at - 3
    if loop_start - 18 < 0:
        return None
    arm = switch[loop_start - 18 : loop_start]
    strong = [1 if base in ("G", "C") else 0 for base in arm]
    return sum(strong[:3]), sum(strong[-3:])


def score_s4_from(bottom: int, top: int) -> float:
    bottom_score = {2: 1.0, 1: 0.6, 3: 0.2}.get(bottom, 0.0)
    top_score = {0: 1.0, 1: 0.8}.get(top, 0.3)
    return 0.6 * bottom_score + 0.4 * top_score


def report(label: str, xs: list[float], ys: list[float]) -> None:
    if len(xs) < 4 or len(set(xs)) < 2:
        print(f"    {label:34s} n={len(xs):3d}  not measurable")
        return
    rho, lin = spearman(xs, ys), pearson(xs, ys)
    print(f"    {label:34s} n={len(xs):3d}  rho {rho:+.4f}  r {lin:+.4f}  R^2 {lin * lin:.4f}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", default=str(GREEN_2014))
    parser.add_argument("--codons", type=int, default=3)
    args = parser.parse_args(argv)

    directory = Path(args.data)
    folder = FoldEngine(37.0)

    for prefix, label in (
        ("Table S1", "G168 first-generation"),
        ("Table S3", "G13 forward-engineered"),
    ):
        path = find_table(directory, prefix)
        if path is None:
            print(f"  {prefix} not found in {directory}")
            continue
        rows = load_switches(str(path))
        print(f"\n{'=' * 78}\n=== {label}: {len(rows)} switches with a sequence pair and a ratio")

        scored = []
        for row in rows:
            switch, trigger = row["switch"], row["trigger"]
            pairs = stem_pairs(switch)
            at = switch.find(RBS)
            if pairs is None or at < 0:
                continue
            bottom, top = pairs
            aug = switch.find("AUG", at + len(RBS))
            if aug < 0:
                continue

            folded = folder.mfe(switch)
            ned = folder.ensemble_defect(switch, folded.structure) / len(switch)
            # S2 wants the OFF-state MFE: the switch alone, as folded.
            s2 = score_s2(folded.energy, ned)
            # S3: the joint probability that the RBS through the start codon is open in the ON
            # complex. Green's switch and trigger are both given, so no reverse complement is
            # invented here.
            s3 = folder.p_open(f"{switch}&{trigger}", (at, min(len(switch), aug + 3)))
            s4 = score_s4_from(bottom, top)
            # S6 needs dG_RBS-linker: the MFE of the RBS loop through the end of the linker,
            # folded as a subsequence, which is how Green computes it.
            piece = switch[max(0, at - 3) : min(len(switch), aug + 3 + LINKER_AFTER_AUG + 21)]
            linker_mfe = folder.mfe(piece).energy
            downstream = switch[aug + 3 :].replace("U", "T")
            s6 = score_s6(linker_mfe, downstream, args.codons)
            scored.append(
                {
                    "on_off": row["on_off"],
                    "S2": s2,
                    "S3": 0.0 if s3 is None else s3,
                    "S4": s4,
                    "S6": s6,
                    "bottom": bottom,
                    "top": top,
                    "linker_mfe": linker_mfe,
                    "ned": ned,
                    "dG_off": folded.energy,
                }
            )

        if len(scored) < 5:
            print(f"  only {len(scored)} scored -- skipping")
            continue
        ys = [r["on_off"] for r in scored]
        print(f"  {len(scored)} scored\n")
        print("  THE PROPOSAL (S1 absent: Green's triggers are truncated, no endogenous context)")
        # Renormalised over the components that exist here, so the composite is not diluted by a
        # term that is structurally unavailable rather than merely zero.
        weights = {
            k: WEIGHTS[k]
            for k in ("S2_off_mfe", "S3_joint_open_ON", "S4_stem_architecture", "S6_translation")
        }
        total = sum(weights.values())
        composite = [sum(weights[k] * r["S" + k[1]] for k in weights) / total for r in scored]
        report("composite S2+S3+S4+S6", composite, ys)
        print("    --- components alone ---")
        for short, name in (
            ("S2", "S2 OFF closure"),
            ("S3", "S3 joint open ON"),
            ("S4", "S4 stem architecture"),
            ("S6", "S6 translation"),
        ):
            report(name, [r[short] for r in scored], ys)

        print("\n  GREEN'S ACTUAL S13 CLAIM: dG_RBS-linker, split by top-of-stem composition")
        print("    (his finding is that the SPLIT reveals the correlation, not that")
        print("     composition predicts performance on its own)")
        for top_count, name in (
            (0, "top 3 all weak  (WWW)"),
            (1, "top 3 one strong"),
            (2, "top 3 two strong"),
            (3, "top 3 all strong (SSS)"),
        ):
            subset = [r for r in scored if r["top"] == top_count]
            if len(subset) < 4:
                print(f"    {name:34s} n={len(subset):3d}  too few")
                continue
            # Green's sign: a LESS negative dG_RBS-linker is better, so negate for the report.
            report(
                name,
                [-r["linker_mfe"] for r in subset],
                [r["on_off"] for r in subset],
            )
        print("    whole library, unsplit:")
        report("dG_RBS-linker, all switches", [-r["linker_mfe"] for r in scored], ys)

        print("\n  and the composition itself, as a direct predictor:")
        for field, name in (
            ("bottom", "strong pairs at the bottom 3"),
            ("top", "strong pairs at the top 3"),
        ):
            report(name, [float(r[field]) for r in scored], ys)
    return 0


if __name__ == "__main__":
    sys.exit(main())
