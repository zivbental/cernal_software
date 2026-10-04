"""Does replacing every MFE with the ensemble free energy improve the correlations?

    uv run --with openpyxl python \\
        src/engine/gates/notebooks/toehold_and/ensemble_vs_mfe.py

CLAUDE.md and the A0 spec both say a scored observable should be an **ensemble** quantity, and two
of the metrics in play are not: ``dG_rbs_linker`` is the MFE of a subsequence and ``dG_OFF`` the MFE
of the switch. The obvious repair is to use ``-RT ln Q`` over the same span instead -- the ensemble
free energy, which ``FoldEngine.partition`` returns.

That is an argument from principle, and principle has lost to measurement repeatedly in this
project, so this measures it. For each of Green's two libraries, both forms of both quantities are
computed over identical spans and correlated against the measured ON/OFF.

**What the two forms are.** The MFE is the single most stable structure's energy. The ensemble free
energy is ``G = -RT ln(sum over all structures of exp(-E/RT))``, which is always at least as
negative and carries the whole Boltzmann sum. They answer "how stable is the best fold" versus "how
stable is the molecule", and for a region with several competing folds those are different numbers.

Also reported: the cross-correlation between ``dG_rbs_linker`` and ``A_M_gain`` on our own gating
population, which decides whether they can be two arms of a panel or are one arm twice.
"""

import argparse
import glob
import os
import statistics as st
import sys
from pathlib import Path

NB = Path(__file__).resolve().parent
sys.path.insert(0, str(NB.parents[4] / "src"))
sys.path.insert(0, str(NB))

from green_calibration import load_switches  # noqa: E402
from metric_correlations import pearson, spearman  # noqa: E402

from engine.gates.tools.folding import FoldEngine  # noqa: E402

GREEN_2014 = Path(r"C:\Users\Dell\OneDrive - mail.tau.ac.il\IGEM\Toehold\Green 2014")
RBS = "AACAGAGGAGA"
LINKER_AFTER_AUG = 9


def find_table(directory: Path, prefix: str) -> Path | None:
    hits = [
        p
        for p in glob.glob(os.path.join(str(directory), "*.xlsx"))
        if os.path.basename(p).startswith(prefix)
    ]
    return Path(hits[0]) if hits else None


def report(label: str, xs: list[float], ys: list[float], flip: bool) -> float | None:
    """Signed Spearman, with the metric's own direction applied so positive means 'right'."""
    pairs = [(x, y) for x, y in zip(xs, ys, strict=True) if x is not None and y is not None]
    if len(pairs) < 4:
        print(f"    {label:38s} n={len(pairs):3d}  too few")
        return None
    sign = -1.0 if flip else 1.0
    a = [p[0] for p in pairs]
    b = [p[1] for p in pairs]
    rho, lin = spearman(a, b), pearson(a, b)
    print(
        f"    {label:38s} n={len(pairs):3d}  rho {sign * rho:+.4f}  r {sign * lin:+.4f}"
        f"   span {min(a):8.2f}..{max(a):8.2f}"
    )
    return sign * rho


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", default=str(GREEN_2014))
    args = parser.parse_args(argv)

    folder = FoldEngine(37.0)
    directory = Path(args.data)

    for prefix, label in (
        ("Table S1", "G168 first-generation"),
        ("Table S3", "G13 forward-engineered"),
    ):
        path = find_table(directory, prefix)
        if path is None:
            print(f"  {prefix} not found")
            continue
        rows = load_switches(str(path))
        measured, mfe_linker, ens_linker, mfe_off, ens_off = [], [], [], [], []
        for row in rows:
            switch = row["switch"]
            at = switch.find(RBS)
            if at < 0:
                continue
            aug = switch.find("AUG", at + len(RBS))
            if aug < 0:
                continue
            piece = switch[max(0, at - 3) : min(len(switch), aug + 3 + LINKER_AFTER_AUG + 21)]
            measured.append(row["on_off"])
            mfe_linker.append(folder.mfe(piece).energy)
            # Ensemble free energy over the SAME span. `partition` is single-strand, which is what
            # both of these are -- no `&`, so no strand-ordering question arises.
            ens_linker.append(folder.partition(piece))
            mfe_off.append(folder.mfe(switch).energy)
            ens_off.append(folder.partition(switch))

        if len(measured) < 5:
            print(f"\n=== {label}: only {len(measured)} usable -- skipping")
            continue
        print(f"\n{'=' * 78}\n=== {label}: {len(measured)} switches\n")
        print("  dG_RBS-linker, over an identical span. Green's sign: LESS negative is better.")
        rho_m = report("MFE of the subsequence", mfe_linker, measured, flip=True)
        rho_e = report("ensemble free energy of the same span", ens_linker, measured, flip=True)
        print("\n  dG_OFF, the whole switch. LESS negative is worse, so lower is better.")
        rho_om = report("MFE of the switch", mfe_off, measured, flip=False)
        rho_oe = report("ensemble free energy of the switch", ens_off, measured, flip=False)

        print("\n  how far apart the two forms are, on the same molecules:")
        gap_l = [e - m for e, m in zip(ens_linker, mfe_linker, strict=True)]
        gap_o = [e - m for e, m in zip(ens_off, mfe_off, strict=True)]
        print(
            f"    RBS-linker span: ensemble minus MFE  median {st.median(gap_l):+.3f}"
            f"  min {min(gap_l):+.3f}  max {max(gap_l):+.3f} kcal/mol"
        )
        print(
            f"    whole switch:    ensemble minus MFE  median {st.median(gap_o):+.3f}"
            f"  min {min(gap_o):+.3f}  max {max(gap_o):+.3f} kcal/mol"
        )
        rank_rho = spearman(mfe_linker, ens_linker)
        print(f"    rho(MFE, ensemble) on the RBS-linker span: {rank_rho:+.4f}")

        def verdict(mfe: float | None, ensemble: float | None) -> str:
            if mfe is None or ensemble is None:
                return "not comparable"
            if abs(ensemble - mfe) < 0.01:
                return "tie"
            return "ensemble wins" if ensemble > mfe else "MFE wins"

        if rho_m is not None and rho_e is not None:
            print(
                f"\n  VERDICT for dG_RBS-linker: MFE {rho_m:+.4f} vs "
                f"ensemble {rho_e:+.4f}  -> {verdict(rho_m, rho_e)}"
            )
        if rho_om is not None and rho_oe is not None:
            print(
                f"  VERDICT for dG_OFF:        MFE {rho_om:+.4f} vs "
                f"ensemble {rho_oe:+.4f}  -> {verdict(rho_om, rho_oe)}"
            )

    # --- the cross-correlation that decides whether two candidate arms are one arm -------------
    print(
        f"\n{'=' * 78}\n=== our own gating population: can dG_rbs_linker and A_M gain both be arms?"
    )
    import objective_panel as op

    rank = op.gating(op.population(NB / "results"))
    for a, b, flip_a, flip_b in (
        ("dG_rbs_linker", "f2_gain", False, False),
        ("dG_rbs_linker", "barrier", False, True),
        ("dG_rbs_linker", "ied_rbs_linker_11", False, True),
        ("f2_gain", "barrier", False, True),
        ("ied_rbs_linker_11", "f2_gain", True, False),
    ):
        pairs = [(r[a], r[b]) for r in rank if r.get(a) is not None and r.get(b) is not None]
        if len(pairs) < 10:
            print(f"    {a} vs {b}: too few")
            continue
        sign = (-1.0 if flip_a else 1.0) * (-1.0 if flip_b else 1.0)
        rho = spearman([p[0] for p in pairs], [p[1] for p in pairs])
        agree = sign * rho
        verdict = (
            "DUPLICATE -- one arm twice"
            if abs(agree) >= 0.6
            else "related"
            if abs(agree) >= 0.35
            else "independent -- both can be arms"
        )
        print(f"    {a:20s} vs {b:20s} n={len(pairs):5d}  agreement {agree:+.3f}   {verdict}")
    print(
        "\n    'agreement' is the Spearman after each metric's own direction is applied, so"
        "\n    positive means the two rank designs the same way and near zero means they disagree"
        "\n    independently -- which is what makes two arms worth having."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
