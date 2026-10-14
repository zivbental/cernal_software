"""Three follow-up probes on the characterisation run, each answering one specific question.

    uv run python tools/probe_axes.py --out axes_c8

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
from analyse_axes import CONTRASTS, cells_of, derive, read_rows, sign_test_p, spearman, value_of

#: The contrast probes 2 and 3 are written around -- the main-stem openness ratio. Named once
#: rather than inline, and asserted against `analyse_axes`' own declaration, so renaming a
#: contrast fails here at import instead of leaving this file matching no rows in silence.
A_M_CONTRAST = "sep_a_m"
assert A_M_CONTRAST in {name for name, *_ in CONTRASTS}, A_M_CONTRAST


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
    parser.add_argument("--out", default="axes_c8")
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
    arms = tuple(name for name, *_ in CONTRASTS)
    print("\n  arm to arm")
    for i, a in enumerate(arms):
        for b in arms[i + 1 :]:
            rhos = []
            for group in cells.values():
                usable = [
                    r for r in group if value_of(r, a) is not None and value_of(r, b) is not None
                ]
                if len(usable) < 5:
                    continue
                rho = spearman([value_of(r, a) for r in usable], [value_of(r, b) for r in usable])
                if rho is not None:
                    rhos.append(rho)
            spread(f"{a} vs {b}", rhos)
    print("\n  arm to stem energy")
    for arm in arms:
        for axis in ("a_site_energy", "lock_energy", "lock_minus_a_site"):
            rhos = []
            for group in cells.values():
                usable = [
                    r for r in group if value_of(r, arm) is not None and r.get(axis) is not None
                ]
                if len(usable) < 5:
                    continue
                rho = spearman([r[axis] for r in usable], [value_of(r, arm) for r in usable])
                if rho is not None:
                    rhos.append(rho)
            spread(f"{arm} vs {axis}", rhos)

    # ---- 2. the interaction, with a_site_energy held nearly fixed ------------------------
    print(f"\n{'=' * 92}\n2. closure x scheme, INSIDE narrow a_site_energy strata")
    print("  B-anchored and mixed have different a_site_energy distributions by construction, so")
    print("  the raw interaction could be the energy wearing a label. Strata are quartiles of")
    print("  a_site_energy over the fully measured designs; the interaction is recomputed in each.")
    measured = [
        r
        for r in full
        if r.get("a_site_energy") is not None and value_of(r, A_M_CONTRAST) is not None
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
            vals = [value_of(r, A_M_CONTRAST) for r in here]
            mean, sd = st.fmean(vals), (st.stdev(vals) if len(vals) > 1 else 0.0)
            if sd == 0:
                print("    no variance in this stratum")
                continue
            for r in here:
                by_combo[(str(r.get("closure")), str(r.get("scheme")))].append(
                    (value_of(r, A_M_CONTRAST) - mean) / sd
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

    # ---- 4. Kim's extended secondary arm against the naive one -------------------------
    print(f"\n{'=' * 92}\n4. KIM'S GEOMETRY AGAINST THE NAIVE ONE, PAIRED BY DESIGN")
    print("  `geom` is part of the CELL key, so a within-cell z-score can never compare the two")
    print("  geometries -- every cell holds exactly one. That is a property of the cell key and")
    print("  not of the data: one trigger pair contributes TWO cells, one per geometry, built on")
    print("  the same two windows. So the comparison is available, it just has to be made one")
    print("  level up: match each design in the naive cell to the design in the Kim cell that")
    print("  shares its whole axis tuple -- same stem, closure, upper3 and lower3 -- and compare")
    print("  the matched values. Only `geom` then differs, which is what a paired test needs.")
    print("\n  The pair is the unit: a trigger pair is won by the geometry with the better median")
    print("  over its matched designs, and the sign test is over pairs, never over designs.")

    #: A design's identity with the GEOMETRY removed, so its counterpart in the other
    #: geometry of the same trigger pair is the row with the same key.
    def without_geom(row: dict) -> tuple:
        return (
            row.get("gene_a"),
            row.get("gene_b"),
            row.get("x_start"),
            row.get("xstar_start"),
            row.get("len_x"),
            row.get("stem_index"),
            row.get("closure"),
            row.get("upper3"),
            row.get("lower3"),
        )

    def trigger_pair(row: dict) -> tuple:
        return (row.get("gene_a"), row.get("gene_b"), row.get("x_start"), row.get("xstar_start"))

    geoms = sorted({str(r.get("geom")) for r in rows if r.get("geom")})
    if len(geoms) != 2:
        print(f"\n  needs exactly two geometries, found {len(geoms)}: {geoms}")
        return 0
    naive, kim = geoms[0], geoms[1]
    print(f"\n  comparing {kim}  against  {naive}  (positive = Kim is better)")

    by_key: dict[tuple, dict[str, dict]] = collections.defaultdict(dict)
    for row in rows:
        by_key[without_geom(row)][str(row.get("geom"))] = row

    matched = [v for v in by_key.values() if naive in v and kim in v]
    print(f"  {len(matched):,} matched design pairs, from {len(by_key):,} axis tuples")
    if not matched:
        print("  no design has a counterpart in the other geometry -- nothing to compare")
        return 0

    # Survival first, because it is the one outcome every matched pair carries.
    kim_only = sum(1 for v in matched if not v[kim].get("skipped") and v[naive].get("skipped"))
    naive_only = sum(1 for v in matched if not v[naive].get("skipped") and v[kim].get("skipped"))
    both = sum(1 for v in matched if not v[kim].get("skipped") and not v[naive].get("skipped"))
    print(
        f"\n  survival, over all matched pairs: both open {both:,}  "
        f"Kim only {kim_only:,}  naive only {naive_only:,}"
    )

    for contrast, _on, _off, _pick, label in CONTRASTS:
        per_pair: dict[tuple, list[float]] = collections.defaultdict(list)
        for v in matched:
            a, b = value_of(v[kim], contrast), value_of(v[naive], contrast)
            if a is None or b is None:
                continue
            # Lower is better, so naive MINUS Kim is positive when Kim wins.
            per_pair[trigger_pair(v[kim])].append(b - a)
        medians = [st.median(d) for d in per_pair.values() if d]
        if len(medians) < 5:
            print(f"\n  {contrast:14s} only {len(medians)} trigger pairs have matched values")
            continue
        won = sum(1 for m in medians if m > 0)
        lost = sum(1 for m in medians if m < 0)
        n_designs = sum(len(d) for d in per_pair.values())
        print(f"\n  {contrast}   ({label})")
        print(
            f"    pairs: {won} to Kim, {lost} to naive, {len(medians) - won - lost} tied, "
            f"of {len(medians)}   p {sign_test_p(won, lost):.2g}"
        )
        spread(
            "    median paired difference",
            [m for m in medians if m == m],
        )
        print(f"    ({n_designs:,} matched designs behind those pair medians)")
    # ---- 5. how much is the pair, and how much is the design? --------------------------
    print(f"\n{'=' * 92}\n5. HOW MUCH OF THE OUTCOME IS THE TRIGGER PAIR, AND HOW MUCH THE DESIGN?")
    print("  Every other number in this file is a within-cell z-score, which SUBTRACTS the trigger")
    print("  pair on purpose so that a design decision becomes visible. That makes those numbers")
    print("  structurally unable to answer how much the pair itself decides -- the quantity was")
    print("  removed before the comparison started. So this probe uses the RAW oriented values and")
    print("  splits their variance in two: the part that lies BETWEEN trigger pairs, and the part")
    print("  that lies WITHIN one pair, across the designs built on it.")
    print("\n  between-pair share near 100% means the pair decides and the levers only shuffle")
    print("  designs inside a verdict already made; near 0% means the levers decide. Both")
    print("  geometries are pooled, because geometry is a design decision and not a property of")
    print("  the pair.")

    def pair_of(row: dict) -> tuple:
        return (row.get("gene_a"), row.get("gene_b"), row.get("x_start"), row.get("xstar_start"))

    def decompose(population: list[dict], objective: str) -> tuple[int, int, float] | None:
        """Share of the variance lying between trigger pairs. ``None`` when too little data."""
        by_pair: dict[tuple, list[float]] = collections.defaultdict(list)
        for row in population:
            value = value_of(row, objective)
            if value is not None:
                by_pair[pair_of(row)].append(value)
        by_pair = {k: v for k, v in by_pair.items() if len(v) >= 2}
        values = [v for group in by_pair.values() for v in group]
        if len(by_pair) < 5 or len(values) < 50:
            return None
        grand = st.fmean(values)
        total = sum((v - grand) ** 2 for v in values)
        if total <= 0:
            return None
        between = sum(len(g) * (st.fmean(g) - grand) ** 2 for g in by_pair.values())
        return len(values), len(by_pair), between / total

    print(
        f"\n  {'objective':22s}{'designs':>12s}{'pairs':>8s}"
        f"{'between-pair':>15s}{'within-pair':>14s}"
    )
    print("\n  over designs measured in full (every contrast needs the three OFF tubes):")
    for contrast, _on, _off, _pick, _label in CONTRASTS:
        got = decompose(full, contrast)
        if got is None:
            print(f"    {contrast:22s} too little data")
            continue
        n, pairs, share = got
        print(f"    {contrast:20s}{n:>12,}{pairs:>8,}{share:>14.1%}{1 - share:>14.1%}")

    print("\n  over ALL designs, before the ceiling decides -- no survivorship conditioning:")
    for name in ("xstar_engA_10", "mainpre_engA_10", "dG_open_11", "open_11"):
        got = decompose(rows, name)
        if got is None:
            print(f"    {name:22s} too little data")
            continue
        n, pairs, share = got
        print(f"    {name:20s}{n:>12,}{pairs:>8,}{share:>14.1%}{1 - share:>14.1%}")

    print(
        "\n  Read it beside probe 3: that one asks whether a pair admits ANY working design, this"
    )
    print("  one asks, among the designs that exist, how much of the spread the pair already set.")
    print("  A pair can dominate twice over -- by refusing to yield a design at all, and by fixing")
    print(
        "  most of the quality of the ones it does yield -- and the two are separate measurements."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
