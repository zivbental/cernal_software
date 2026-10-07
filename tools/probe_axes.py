"""Three follow-up probes on the characterisation run, each answering one specific question.

    uv run python tools/probe_axes.py --out axes_pfas

**1. Do the arms agree with each other less than they agree with the stem energies?** If a stem
energy predicts an arm better than another arm does, the arms are measuring something the stem
energy already contains. Same within-cell Spearman, so the comparison is like for like.

**2. Is the closure x scheme interaction really about the scheme, or is it `a_site_energy` in
disguise?** B-anchored and mixed build the arms differently, so they have different
`a_site_energy` distributions by construction. The interaction is recomputed inside narrow
`a_site_energy` strata: if it survives with the energy held nearly fixed, the scheme carries
something of its own; if it vanishes, the scheme was a label for the energy.

**3. Why are whole shards at 0% survival?** Checked rather than asserted — the suspicion is that
this is a property of the trigger PAIR and was mislabelled as a property of the shard, because at
the time it was read each shard had processed one or two pairs.
"""

from __future__ import annotations

import argparse
import collections
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

# ruff: noqa: E402 - the sibling tool must be importable from this directory.
from analyse_axes import cells_of, derive, read_rows, sign_test_p, spearman


def spread(label: str, rhos: list[float], width: int = 38) -> None:
    if not rhos:
        print(f"  {label:{width}s} no cell supports it")
        return
    pos = sum(1 for v in rhos if v > 0)
    neg = sum(1 for v in rhos if v < 0)
    p = sign_test_p(pos, neg)
    print(
        f"  {label:{width}s}n {len(rhos):>5}  median {st.median(rhos):>+7.3f}  "
        f"+{pos}/-{neg}  p {(f'{p:.2g}' if p is not None else '--'):>9s}"
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default="axes_pfas")
    parser.add_argument("--shards", type=int, default=6)
    args = parser.parse_args(argv)

    rows = read_rows(args.out, args.shards)
    if not rows:
        print(f"  nothing in results/{args.out}_*.csv")
        return 1
    derive(rows)
    cells = cells_of(rows)
    full = [r for r in rows if not r.get("skipped")]
    print(f"  {len(rows):,} rows, {len(full):,} measured in full, {len(cells):,} cells")

    # ---- 1. the arms against each other, and against the stem energies ------------------
    print(f"\n{'=' * 92}\n1. WITHIN-CELL AGREEMENT -- arm to arm, beside arm to stem energy")
    print("  Same measure throughout: Spearman inside each cell, then the median over cells.")
    print("  |rho| near 1 means the two carry the same ordering of designs.")
    arms = ("f1_opening_sep", "a_m_ratio", "ied_gain")
    print("\n  arm to arm")
    for i, a in enumerate(arms):
        for b in arms[i + 1 :]:
            rhos = []
            for group in cells.values():
                usable = [r for r in group if r.get(a) is not None and r.get(b) is not None]
                if len(usable) < 5:
                    continue
                rho = spearman([r[a] for r in usable], [r[b] for r in usable])
                if rho is not None:
                    rhos.append(rho)
            spread(f"{a} vs {b}", rhos)
    print("\n  arm to stem energy")
    for arm in arms:
        for axis in ("a_site_energy", "lock_energy", "lock_minus_a_site"):
            rhos = []
            for group in cells.values():
                usable = [r for r in group if r.get(arm) is not None and r.get(axis) is not None]
                if len(usable) < 5:
                    continue
                rho = spearman([r[axis] for r in usable], [r[arm] for r in usable])
                if rho is not None:
                    rhos.append(rho)
            spread(f"{arm} vs {axis}", rhos)

    # ---- 2. the interaction, with a_site_energy held nearly fixed ------------------------
    print(f"\n{'=' * 92}\n2. closure x scheme, INSIDE narrow a_site_energy strata")
    print("  B-anchored and mixed have different a_site_energy distributions by construction, so")
    print("  the raw interaction could be the energy wearing a label. Strata are quartiles of")
    print("  a_site_energy over the fully measured designs; the interaction is recomputed in each.")
    measured = [
        r for r in full if r.get("a_site_energy") is not None and r.get("a_m_ratio") is not None
    ]
    if len(measured) < 400:
        print("  too few fully measured designs yet")
    else:
        values = sorted(r["a_site_energy"] for r in measured)
        cuts = [values[int(len(values) * q / 4) - 1] for q in (1, 2, 3)]

        def stratum(row) -> int:
            for i, cut in enumerate(cuts):
                if row["a_site_energy"] <= cut:
                    return i
            return 3

        for s in range(4):
            here = [r for r in measured if stratum(r) == s]
            lo = min(r["a_site_energy"] for r in here)
            hi = max(r["a_site_energy"] for r in here)
            print(f"\n  stratum {s}: a_site {lo:.1f} to {hi:.1f} kcal/mol, {len(here):,} designs")
            # Within-stratum z against the stratum's own mean, so the energy is controlled for.
            by_combo: dict[tuple[str, str], list[float]] = collections.defaultdict(list)
            vals = [r["a_m_ratio"] for r in here]
            mean, sd = st.fmean(vals), (st.stdev(vals) if len(vals) > 1 else 0.0)
            if sd == 0:
                print("    no variance in this stratum")
                continue
            for r in here:
                by_combo[(str(r.get("closure")), str(r.get("scheme")))].append(
                    (r["a_m_ratio"] - mean) / sd
                )
            schemes = sorted({k[1] for k in by_combo})
            print(f"    {'closure':16s}" + "".join(f"{s2[:13]:>17s}" for s2 in schemes))
            for closure in sorted({k[0] for k in by_combo}):
                line = ""
                for s2 in schemes:
                    got = by_combo.get((closure, s2))
                    line += f"{st.fmean(got):>+10.2f}({len(got):>4})" if got else f"{'--':>17s}"
                print(f"    {closure:16s}{line}")

    # ---- 3. the 0% shards --------------------------------------------------------------
    print(f"\n{'=' * 92}\n3. IS 0% SURVIVAL A SHARD OR A TRIGGER PAIR?")
    by_pair: dict[tuple, list] = collections.defaultdict(list)
    for r in rows:
        by_pair[(r.get("gene_a"), r.get("gene_b"), r.get("x_start"), r.get("xstar_start"))].append(
            r
        )
    rates = []
    for group in by_pair.values():
        kept = sum(1 for r in group if not r.get("skipped"))
        rates.append(kept / len(group))
    zero = sum(1 for v in rates if v == 0.0)
    allp = sum(1 for v in rates if v > 0.95)
    print(f"  {len(rates):,} trigger pairs with rows so far")
    print(f"    pairs where NO design opens:        {zero:>5,}  ({100.0 * zero / len(rates):.1f}%)")
    print(f"    pairs where >95% of designs open:   {allp:>5,}  ({100.0 * allp / len(rates):.1f}%)")
    print(
        f"    median pair survival {st.median(rates):.3f}  mean {st.fmean(rates):.3f}  "
        f"sd {st.stdev(rates) if len(rates) > 1 else 0:.3f}"
    )
    buckets = [0] * 10
    for v in rates:
        buckets[min(int(v * 10), 9)] += 1
    print(
        "\n  distribution of per-pair survival -- a U shape means the pair decides, not the design"
    )
    for i, n in enumerate(buckets):
        bar = "#" * max(1, int(60 * n / max(buckets))) if n else ""
        print(f"    {i * 10:>3}-{i * 10 + 10:>3}%  {n:>6,}  {bar}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
