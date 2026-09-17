"""What the AUG bulge actually is, which side is designable, and what the two hairpins weigh.

    uv run python src/engine/gates/notebooks/toehold_and/bulge_geometry.py \\
        --fasta "path/to/mCherry original.txt" --fold 8 --out bulge_geometry

Three questions came out of the architecture review that the first pass answered loosely or
not at all. Each is settled here by measurement.

**1. Can the loop be asymmetric — 1x2, 0x2?** In the idealised two-arm accounting, no. The
ascending side contributes exactly 3 nt (``bulge*``) and the descending side exactly 3 (the
``AUG``), so if *k* of the three positions pair, ``3-k`` are unpaired on **each** side and the
loop is symmetric by construction. What is *not* fixed is **which** positions pair: an
unpaired middle gives a 1x1 internal loop, an unpaired end gives the same size sitting against
the helix junction, and the two are different structures with different stacking. That
position is reported here as a pattern string, not collapsed into a count. Asymmetric loops
can still appear in the real fold if the helix register shifts, which the idealised accounting
cannot see — so the folded structures are checked against it.

**2. Which side is designable?** Only the ascending one. The descending side *is* the start
codon and cannot change. So every bulge modification is a change to ``bulge*``, and
``bulge*`` is ``revcomp(trigger_A[6:9])`` — trigger-derived, hence today an accident of which
window was picked rather than a choice.

**3. What does ``aug_paired`` actually do?** It sets ``bulge*`` to ``CAU``, the complement of
the start codon. That removes the loop **entirely** — the main stem becomes a continuous
18 bp helix — and it costs trigger A its three pairs there *unless* trigger A's own
``trigger_A[6:9]`` happens to pair ``CAU``. How many of those three trigger A keeps is the
mechanistically correct variable for this design, and it is not the same as the original
bulge class. It is computed here as ``retained_by_A`` and correlated with the outcome.

**And the 19/17 question.** Kim's inhibitory hairpin is 19 bp against a 17-bp primary; ours
are 18 and 18. Changing that needs an assembly change, so it is not built here. What *is*
measured is the quantity the asymmetry exists to produce — whether the inhibitory hairpin
out-holds the main one — reported per design as the two hairpins' folding energies and their
difference, so the question can be answered on our own numbers rather than by analogy.
"""

import argparse
import csv
import math
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[4]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from engine import sequences as sq  # noqa: E402
from engine.domain import Host  # noqa: E402
from engine.gates.toehold import ProkaryoticToeholdAndGate  # noqa: E402
from engine.gates.tools.binding import can_pair  # noqa: E402
from engine.gates.tools.codons import CodonOptimizer  # noqa: E402
from engine.gates.tools.folding import FoldEngine  # noqa: E402
from engine.gates.tools.translation import TranslationScorer  # noqa: E402

AUG_FACES = "GUA"  # what bulge*[0], [1], [2] face across the helix
AUG_PARTNER = "CAU"  # revcomp("AUG") -- what aug_paired writes into bulge*


def read_fasta(path: str) -> str:
    lines = Path(path).read_text().splitlines()
    return sq.to_rna("".join(line.strip() for line in lines if not line.startswith(">")))


def bulge_pattern(trigger_a: str) -> tuple[str, int]:
    """Which of the three AUG positions pair, as a pattern and a count.

    ``"o.o"`` means the outer two pair and the middle does not — a 1x1 internal loop in the
    middle of the helix. ``"oo."`` is the same *size* against the helix junction, which is a
    different structure. Collapsing both to "1x1" is what the first pass did.
    """
    ascending = sq.reverse_complement(trigger_a[6:9])
    flags = [can_pair(ascending[i], AUG_FACES[i]) for i in range(3)]
    return "".join("o" if f else "." for f in flags), sum(flags)


def retained_by_a(trigger_a: str) -> int:
    """How many of its three bulge pairs trigger A keeps once ``bulge*`` becomes ``CAU``.

    Trigger A pairs ``bulge*`` antiparallel, so its nt 6,7,8 face ``CAU`` reversed. Lower is
    better for the gate: it is exactly the advantage the modification is trying to remove.
    """
    facing = AUG_PARTNER[::-1]
    return sum(can_pair(trigger_a[6 + i], facing[i]) for i in range(3))


def hairpin_energies(gate, switch) -> tuple[float, float]:
    """Folding energy of each hairpin alone, main and secondary, in kcal/mol."""
    d = switch.domains
    main = switch.sequence[d["main_pre_star"][0] : d["main_pre"][1]]
    secondary = switch.sequence[d["sw_x"][0] : d["sw_xs"][1]]
    return gate.folder.mfe(main).energy, gate.folder.mfe(secondary).energy


def spearman(pairs: list[tuple[float, float]]) -> tuple[float, int]:
    def ranks(values):
        order = sorted(range(len(values)), key=lambda i: values[i])
        out = [0.0] * len(values)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
                j += 1
            shared = (i + j) / 2 + 1
            for k in range(i, j + 1):
                out[order[k]] = shared
            i = j + 1
        return out

    if len(pairs) < 3:
        return math.nan, len(pairs)
    xs, ys = ranks([p[0] for p in pairs]), ranks([p[1] for p in pairs])
    n = len(pairs)
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return (cov / (sx * sy) if sx and sy else math.nan), n


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fasta", required=True)
    parser.add_argument("--fold", type=int, default=8, help="candidates to fold per class")
    parser.add_argument("--out", default="bulge_geometry")
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

    # --- census: no folding, all 1036 pairs -------------------------------------------
    patterns: dict[str, int] = {}
    retained: dict[int, int] = {}
    for pair in kept:
        trigger_a = transcript[slice(*pair.window_a())]
        pattern, _ = bulge_pattern(trigger_a)
        patterns[pattern] = patterns.get(pattern, 0) + 1
        keep = retained_by_a(trigger_a)
        retained[keep] = retained.get(keep, 0) + 1

    print(f"{len(kept)} surviving pairs\n")
    print("AUG bulge pattern (o = that position can pair, . = it cannot):")
    print(f"  {'pattern':<10}{'loop':<8}{'where':<26}{'count':>7}{'share':>8}")
    where = {
        "ooo": "no loop, continuous helix",
        "oo.": "1x1 at the arm base",
        "o.o": "1x1 mid-helix",
        ".oo": "1x1 by the RBS loop",
        "o..": "2x2 at the arm base",
        ".o.": "2x2 split",
        "..o": "2x2 by the RBS loop",
        "...": "3x3, what R7 specifies",
    }
    for pattern in sorted(patterns, key=lambda p: -patterns[p]):
        size = 3 - pattern.count("o")
        print(
            f"  {pattern:<10}{f'{size}x{size}':<8}{where.get(pattern, '?'):<26}"
            f"{patterns[pattern]:>7}{100 * patterns[pattern] / len(kept):>7.1f}%"
        )
    print("\nThe loop is SYMMETRIC in every case: both sides contribute exactly 3 nt, so")
    print("k paired positions always leave 3-k unpaired on each side. 1x2 and 0x2 cannot")
    print("arise from this geometry -- only from a register shift in the real fold.\n")

    print("After aug_paired (bulge* becomes CAU), how many pairs trigger A keeps there:")
    for keep in sorted(retained):
        print(
            f"  keeps {keep} of 3   {retained[keep]:>5} pairs "
            f"({100 * retained[keep] / len(kept):.1f}%)   "
            f"{'<- A loses most, best for the gate' if keep == 0 else ''}"
        )

    # --- fold a stratified sample ------------------------------------------------------
    print("\n\nFolding a sample, stratified by how much trigger A retains...")
    import modification_panel as mp

    by_retained: dict[int, list] = {}
    for pair in kept:
        keep = retained_by_a(transcript[slice(*pair.window_a())])
        by_retained.setdefault(keep, []).append(pair)

    rows = []
    for keep in sorted(by_retained):
        for pair in by_retained[keep][: args.fold]:
            trigger_a = transcript[slice(*pair.window_a())]
            trigger_b = transcript[slice(*pair.window_b())]
            stems = gate.secondary_stems(trigger_a, trigger_b, pair.len_x)
            stem = min(stems, key=lambda s: s.lock_energy)
            base = gate.assemble(trigger_a, trigger_b, pair.len_x, stem)
            built = mp.variants(gate, base, trigger_a)
            main_dg, sec_dg = hairpin_energies(gate, base)
            pattern, paired = bulge_pattern(trigger_a)
            for variant in ("baseline", "aug_paired"):
                o = mp.observe(gate, built[variant], trigger_a, trigger_b)
                o.update(
                    variant=variant,
                    x_start=pair.x_start,
                    len_x=pair.len_x,
                    lock_energy=stem.lock_energy,
                    scheme=stem.scheme,
                    bulge_pattern=pattern,
                    bulge_loop=f"{3 - paired}x{3 - paired}",
                    retained_by_A=keep,
                    main_hairpin_dG=main_dg,
                    secondary_hairpin_dG=sec_dg,
                    hairpin_gap=sec_dg - main_dg,
                )
                rows.append(o)
            print(
                f"  keeps {keep}  x@{pair.x_start:<4} {pattern}  "
                f"main {main_dg:6.1f}  sec {sec_dg:6.1f}  gap {sec_dg - main_dg:+6.1f}  "
                f"sep {rows[-1]['separation']:6.2f}  A_M11 {rows[-1]['A_M_11']:.3f}  "
                f"AUG11 {rows[-1]['aug_11']:.3f}",
                flush=True,
            )

    path = output_dir / f"{args.out}.csv"
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=sorted({k for r in rows for k in r}))
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n{len(rows)} rows -> {path}")

    aug = [r for r in rows if r["variant"] == "aug_paired"]
    print(f"\naug_paired only, n = {len(aug)}. Spearman against the outcome:")
    for field, target in (
        ("retained_by_A", "separation"),
        ("retained_by_A", "A_M_11"),
        ("hairpin_gap", "separation"),
        ("hairpin_gap", "A_M_11"),
        ("lock_energy", "separation"),
        ("secondary_hairpin_dG", "separation"),
        ("main_hairpin_dG", "separation"),
    ):
        data = [
            (r[field], r[target]) for r in aug if r[field] is not None and r[target] is not None
        ]
        rho, n = spearman(data)
        print(f"  {field:<22} vs {target:<12} rho {rho:+.3f}  n {n}")

    print("\nBy how much trigger A retains (medians):")
    print(f"  {'keeps':<8}{'n':>4}{'sep':>9}{'A_M10':>8}{'A_M11':>8}{'AUG11':>8}{'gap':>8}")
    for keep in sorted({r["retained_by_A"] for r in aug}):
        group = [r for r in aug if r["retained_by_A"] == keep]

        def med(key, group=group):
            values = sorted(v for v in (g[key] for g in group) if v is not None)
            return values[len(values) // 2] if values else math.nan

        print(
            f"  {keep:<8}{len(group):>4}{med('separation'):>9.2f}{med('A_M_10'):>8.3f}"
            f"{med('A_M_11'):>8.3f}{med('aug_11'):>8.3f}{med('hairpin_gap'):>8.1f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
