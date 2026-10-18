"""Rescue designs the rare-codon screen drops, without letting go of trigger A.

    uv run python src/engine/gates/notebooks/toehold_and/rare_codon_rescue.py --table
    uv run python src/engine/gates/notebooks/toehold_and/rare_codon_rescue.py \
        --scan results/sweep_cheap_0.csv

**What the screen does.** ``objective_energy.RARE_CODONS`` drops any design carrying one of eight
rare E. coli codons in the first three codons after the AUG. That span is exactly ``main_pre``
-- the main stem's descending arm, 9 nt -- so the screen reaches the whole lower 9, not just the
``lower3`` axis sets. Measured on 43,378 scored designs, **46.1% carry one**, and 41.6% carry one
without also being excluded by scheme. Those designs are folded for nothing and then deleted.

**They are already on disk.** The screen lives in the SCORER, not in stage 1, so ``full_sweep``
wrote every design including the ones scoring deletes -- the ``k1_cheap_*`` and ``wob_cheap_*``
shards. No ``--keep-rare`` run is needed, and those files are the default scan.

**Why they are deletable and also rescuable.** The reason for a hard screen is sound and stays: rare
codons are *enriched* among the designs the folding model likes, because AGG and CGG are G-rich and
so strengthen pairing, and the score rewards what the ribosome punishes. But a rare codon is a
property of the SEQUENCE, not of the design's logic, and every one of the eight has a synonymous
replacement that is not rare.

**What it yields, measured, and it is not much.** Over 3,501,120 cheap-stage designs, 44.7% carry a
rare codon in the first three and **5.9% of those can be rescued** -- 92,640 designs. Of a
200-design sample of those, only **3.0% pass the ON ceiling**, against 19.2% for the original
population, and their ``open_11`` runs min 1.59, median **13.82**, max 32.26 against a ceiling of
4.0, with 125 of 200 above 12 kcal/mol.

There is a mechanism for that, not just a statistic: the rescue repairs ``main_pre_star`` to keep
the switch's own stem Watson-Crick, which STRENGTHENS the stem wherever that pair was weak, and a
stronger stem is harder to open in the ON state. The constraint that preserves trigger A's grip is
what costs the ON state.

So expect roughly 2,780 of the 92,640 to clear the ceiling. Worth folding once -- 1.5 h on six cores
at a measured 0.35 s per design -- and worth reading with low expectations.

**The constraint that shapes the fix.** ``main_pre`` pairs with ``main_pre_star``, and trigger A
invades ``main_pre_star``. So:

* changing ``main_pre`` alone breaks the switch's own stem and leaves trigger A untouched;
* changing ``main_pre_star`` to match breaks **trigger A's grip**, unless the new pair is a G-U.

That is the ``wobble_GU`` trick, applied at a different position: pick the star base so the switch
stem stays Watson-Crick **and** trigger A keeps a Watson-Crick or G-U pair. Where no base satisfies
both, the design is not rescued and says so -- a fixed substitution that sacrifices the trigger is
exactly the class measured to lose (against trigger A, ``SSW`` carries a real mismatch in 483 of 514
gating designs, ``SWS`` in 446 of 484, while ``wobble_GU`` has **0** in 368).

**Abundance.** The default keeps the supervisor's rule -- replace a codon with one of *similar* E.
coli abundance -- and picks the closest non-rare synonym. That rule was set for the trigger-knockout
recoding, where the point is to leave expression comparable; here the point is to stop the ribosome
stalling, and the closest synonym is still far more abundant than the rare one it replaces (AGG
0.040 -> CGU 0.360). ``--most-abundant`` picks the highest instead, which is the translational
argument rather than the comparability one. Neither is fitted to anything.
"""

import argparse
import csv
import glob
import sys
from pathlib import Path

NB = Path(__file__).resolve().parent
sys.path.insert(0, str(NB.parents[4] / "src"))
sys.path.insert(0, str(NB))

import codon_variants as cv  # noqa: E402
import objective_energy as oe  # noqa: E402

from engine import sequences as sq  # noqa: E402

#: Pairs that hold a duplex: Watson-Crick, plus the G-U wobble that lets the trigger keep its grip.
WC = frozenset({("A", "U"), ("U", "A"), ("G", "C"), ("C", "G")})
WOBBLE = frozenset({("G", "U"), ("U", "G")})
HOLDS = WC | WOBBLE


def star_base_for(new_base: str, trigger_base: str) -> str | None:
    """A ``main_pre_star`` base that pairs with BOTH the new codon base and trigger A's base.

    Returns ``None`` when no nucleotide satisfies both -- which is the honest outcome and not a
    failure to search: there are only four to try.

    The switch's own stem is required to be Watson-Crick rather than merely holding, because a G-U
    inside the stem weakens the OFF state, which is the thing the stem exists to maintain. The
    trigger side is allowed a G-U, because that is the grip we are trying not to lose.
    """
    for base in "ACGU":
        if (new_base, base) in WC and (base, trigger_base) in HOLDS:
            return base
    return None


def rescue(
    switch: str,
    trigger_a: str,
    amino: dict[str, str],
    fraction: dict[str, float],
    groups: dict[str, list[str]],
    *,
    most_abundant: bool = False,
) -> tuple[str, dict] | None:
    """A switch with no rare codon in its first three codons, or ``None`` with no change possible.

    Returns ``(new_switch, report)``. The report names every substitution and why, so a rescued
    design can be audited against the original rather than appearing from nowhere.
    """
    codons = oe.early_codons(switch)
    rare = [(i, c) for i, c in enumerate(codons) if c in oe.RARE_CODONS]
    if not rare:
        return switch, {"changed": 0, "reason": "no rare codon"}

    domains = oe.domains(switch)
    pre_start, pre_end = domains["main_pre"]
    star_start, star_end = domains["main_pre_star"]
    if pre_end - pre_start != 9 or star_end - star_start != 9:
        return None

    # Trigger A invades main_pre_star antiparallel. Locate it by the best 9-nt match to the star's
    # reverse complement, the same way the audit scripts do, rather than assuming an offset: the
    # lower3 levels break the exact match on purpose, so an exact search would fail on most designs.
    probe = sq.reverse_complement(switch[star_start:star_end])
    best, offset = 10, None
    for start in range(max(1, len(trigger_a) - 9 + 1)):
        window = trigger_a[start : start + 9]
        mismatches = sum(1 for x, y in zip(probe, window, strict=False) if x != y)
        if mismatches < best:
            best, offset = mismatches, start
    if offset is None:
        return None
    segment = trigger_a[offset : offset + 9]

    out = list(switch)
    notes = []
    for index, codon in rare:
        acid = amino.get(codon)
        options = (
            [c for c in groups.get(acid, ()) if c != codon and c not in oe.RARE_CODONS]
            if acid
            else []
        )
        if not options:
            return None
        if most_abundant:
            options.sort(key=lambda c: -fraction.get(c, 0.0))
        else:
            options.sort(key=lambda c: abs(fraction.get(c, 0.0) - fraction.get(codon, 0.0)))

        placed = None
        for option in options:
            # Every base that changes needs a star base holding both duplexes. Try the whole
            # synonym list rather than only the first: one may be unplaceable where the next is not.
            plan = {}
            for k in range(3):
                if option[k] == codon[k]:
                    continue
                # main_pre[index * 3 + k] pairs with main_pre_star[8 - (index * 3 + k)].
                here = index * 3 + k
                star_at = star_start + (8 - here)
                base = star_base_for(option[k], segment[8 - (8 - here)])
                if base is None:
                    plan = None
                    break
                plan[star_at] = base
            if plan is None:
                continue
            for k in range(3):
                out[pre_start + index * 3 + k] = option[k]
            for at, base in plan.items():
                out[at] = base
            placed = option
            notes.append(
                {
                    "codon": index + 1,
                    "was": codon,
                    "now": option,
                    "aa": acid,
                    "fraction_was": round(fraction.get(codon, 0.0), 3),
                    "fraction_now": round(fraction.get(option, 0.0), 3),
                    "star_bases_set": len(plan),
                }
            )
            break
        if placed is None:
            return None

    rescued = "".join(out)
    if any(c in oe.RARE_CODONS for c in oe.early_codons(rescued)):
        # A replacement can create a rare codon at a neighbouring position, because the codons are
        # adjacent in one 9-nt run. Checked rather than assumed.
        return None
    return rescued, {"changed": len(notes), "substitutions": notes, "trigger_mismatches": best}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--table", action="store_true", help="print the synonym table and stop")
    parser.add_argument(
        "--scan",
        default="",
        help="glob of built designs to scan. Defaults to the cheap-stage shards, which is where "
        "the dropped designs already are: the rare-codon screen lives in the SCORER, so stage 1 "
        "wrote every design including the ones scoring deletes",
    )
    parser.add_argument(
        "--shards",
        type=int,
        default=0,
        help="write the rescued designs as N cheap-format shards, so objective_energy can score "
        "them with --from <out> --shard i/N",
    )
    parser.add_argument("--fasta", default="mCherry_original.txt")
    parser.add_argument("--codons", default="data/ecoli_codon_usage_table.csv")
    parser.add_argument("--most-abundant", action="store_true")
    parser.add_argument("--out", default="", help="write rescued designs to results/<name>.csv")
    args = parser.parse_args(argv)

    amino, fraction = cv.load_codon_table(NB / args.codons)
    groups = cv.synonyms(amino)

    # `--table` only. An earlier version printed the table whenever --scan was empty and then
    # RETURNED, which silently skipped the whole rescue in the driver -- the default cheap-shard
    # scan below never ran, and the phase looked like it had worked.
    if args.table:
        print(f"\n  {'rare':6s}{'aa':4s}{'fraction':>10s}   non-rare synonyms, closest first")
        for codon in sorted(oe.RARE_CODONS):
            acid = amino.get(codon)
            if acid is None:
                print(f"  {codon:6s} not in the codon table")
                continue
            options = [
                (c, fraction.get(c, 0.0))
                for c in groups.get(acid, ())
                if c != codon and c not in oe.RARE_CODONS
            ]
            options.sort(key=lambda t: abs(t[1] - fraction.get(codon, 0.0)))
            shown = ", ".join(f"{c} ({f:.3f})" for c, f in options[:4]) or "NONE"
            print(f"  {codon:6s}{acid:4s}{fraction.get(codon, 0.0):>10.3f}   {shown}")
        print("\n  every rare codon has a non-rare synonym, so nothing is lost to the codon table;")
        print("  what decides a rescue is whether a star base can hold both duplexes.")
        return 0

    from full_sweep import read_fasta

    transcript = read_fasta(NB / args.fasta)
    if args.scan:
        pattern = args.scan
        paths = sorted(Path(p) for p in glob.glob(str(NB / pattern))) or (
            [Path(pattern)] if Path(pattern).exists() else []
        )
    else:
        # The cheap shards of the current sweep. Both prefixes, because the two geometries were run
        # separately: `k1` is the Kim arm and `wob` the naive one, six shards each.
        paths = sorted(
            Path(p)
            for prefix in ("k1_cheap_", "wob_cheap_")
            for p in glob.glob(str(NB / "results" / f"{prefix}*.csv"))
        )
    if not paths:
        print(f"  nothing to scan (pattern {args.scan or 'k1_cheap_*/wob_cheap_*'})")
        return 1
    print(
        f"  scanning {len(paths)} file(s): {', '.join(p.name for p in paths[:4])}"
        f"{' ...' if len(paths) > 4 else ''}"
    )

    seen = carried = rescued_n = 0
    by_position = [0, 0, 0]
    failures: dict[str, int] = {}
    out_rows = []
    # One cache per (switch, trigger window): the cheap shards repeat a design across axis points
    # that do not touch main_pre, and rescuing the same sequence twice would be pure waste.
    done: dict[tuple[str, int, int], str | None] = {}
    for path in paths:
        with path.open(encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                switch = row.get("switch")
                if not switch or len(switch) < 75:
                    continue
                seen += 1
                codons = oe.early_codons(switch)
                hits = [i for i, c in enumerate(codons) if c in oe.RARE_CODONS]
                if not hits:
                    continue
                carried += 1
                for i in hits:
                    by_position[i] += 1
                try:
                    a_lo, a_hi = int(row["a_start"]), int(row["a_end"])
                except (KeyError, TypeError, ValueError):
                    failures["no trigger window on the row"] = (
                        failures.get("no trigger window on the row", 0) + 1
                    )
                    continue
                key = (switch, a_lo, a_hi)
                if key in done:
                    answer = done[key]
                else:
                    answer = rescue(
                        switch,
                        transcript[a_lo:a_hi],
                        amino,
                        fraction,
                        groups,
                        most_abundant=args.most_abundant,
                    )
                    done[key] = answer
                if answer is None:
                    failures["no star base holds both duplexes"] = (
                        failures.get("no star base holds both duplexes", 0) + 1
                    )
                    continue
                rescued_n += 1
                new_switch, report = answer
                out_rows.append(
                    {
                        **row,
                        "switch": new_switch,
                        "rescued_from": switch,
                        "substitutions": len(report.get("substitutions", [])),
                    }
                )

    print(f"\n  scanned {seen:,} designs across {len(paths)} file(s)")
    share = 100.0 * carried / max(seen, 1)
    print(f"  carry a rare codon in the first three: {carried:,} ({share:.1f}%)")
    print(f"    by position after the AUG: {by_position}")
    rate = 100.0 * rescued_n / max(carried, 1)
    print(f"  rescued: {rescued_n:,} ({rate:.1f}% of those carrying one)")
    for reason, count in sorted(failures.items(), key=lambda kv: -kv[1]):
        print(f"    not rescued -- {reason}: {count:,}")

    if args.out and out_rows:
        shards = max(1, args.shards)
        fields = list(out_rows[0])
        for index in range(shards):
            name = f"{args.out}_{index}" if args.shards else args.out
            target = NB / "results" / f"{name}.csv"
            mine = out_rows[index::shards] if args.shards else out_rows
            with target.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(mine)
            print(f"  wrote {len(mine):,} rescued designs to {target.name}")
        print("  these are NEW SEQUENCES and carry no folded measurements. Score them with:")
        print(f"    objective_energy.py --from {args.out} --shard i/{shards} --out rescued_folded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
