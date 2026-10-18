"""Can two trigger pairs with overlapping windows still be addressed by four transcripts?

    uv run python src/engine/gates/notebooks/toehold_and/role_swap.py
    uv run python src/engine/gates/notebooks/toehold_and/role_swap.py --pairs 591/256/5 645/251/4
    uv run python src/engine/gates/notebooks/toehold_and/role_swap.py --out role_swap

**The constraint this relaxes.** The wet lab builds four mCherry transcripts shared across the whole
panel, and the scheme names each by the ROLE it recodes -- "A-recoded" means every pair's A
window. That breaks when one pair's A overlaps another pair's B: recoding A damages that B as
collateral, so the transcript meant to leave B intact destroys it. ``pick`` therefore rejects any
pair whose windows clash cross-role with an already-chosen pair, which costs candidate pairs.

**The relaxation.** Name a transcript by the SET of windows it recodes instead, and let the state it
realises differ per pair. The overlap then stops being damage and becomes the mechanism:

    T0 = {}              pair1 11   pair2 11
    T1 = {A1}            pair1 01   pair2 10    <- B2 removed as collateral, deliberately
    T2 = {B1, A2}        pair1 10   pair2 01
    T3 = {A1, B1, A2}    pair1 00   pair2 00

Four transcripts, all four states for both pairs. What moves is where the state label lives: it is a
property of the (transcript, pair) cell rather than of the transcript, so "A-recoded" stops being a
meaningful name and the set has to be solved per pair-set.

**What it cannot do.** A pair whose A *and* B both collide with the other pair's windows generally
cannot be separated -- every transcript that removes one removes the other -- and the solver says so
rather than returning a set that silently conflates two states. Collateral damage is also only real
where the recoder would actually substitute a base inside the overlap, so the solver asks
``codon_variants`` which positions it would change rather than assuming the whole window.
"""

import argparse
import csv
import itertools
import sys
from pathlib import Path

NB = Path(__file__).resolve().parent
sys.path.insert(0, str(NB.parents[4] / "src"))
sys.path.insert(0, str(NB))

import codon_variants as cv  # noqa: E402
import objective_panel as op  # noqa: E402
from full_sweep import read_fasta  # noqa: E402

from engine import sequences as sq  # noqa: E402

#: The four logic states, as (A present, B present). Left digit is trigger A, as everywhere here.
STATES = {(True, True): "11", (False, True): "01", (True, False): "10", (False, False): "00"}


def changed_positions(
    transcript: str, lo: int, hi: int, amino: dict, fraction: dict, groups: dict
) -> set[int]:
    """Transcript positions the recoder would actually substitute inside ``[lo, hi)``.

    Asked of the recoder's own per-codon rule rather than assumed to be the whole window: it
    substitutes roughly a quarter to a third of a window, so an overlap containing none of its
    substitutions is not collateral damage at all.
    """
    changed: set[int] = set()
    for start in cv.codon_starts(lo, hi):
        codon = transcript[start : start + 3]
        acid = amino.get(codon)
        options = [c for c in groups.get(acid, ()) if c != codon] if acid else []
        if not options:
            continue

        def score(option: str, codon: str = codon, start: int = start) -> tuple:
            broken = sum(
                1
                for k in range(3)
                if option[k] != codon[k]
                and lo <= start + k < hi
                and (option[k], sq.reverse_complement(codon[k])) not in cv._PAIRED
            )
            gc_now = sum(1 for c in codon if c in "GC")
            return (
                -broken,
                abs(fraction.get(option, 0.0) - fraction.get(codon, 0.0)),
                abs(sum(1 for c in option if c in "GC") - gc_now),
            )

        best = min(options, key=score)
        changed.update(start + k for k in range(3) if best[k] != codon[k] and lo <= start + k < hi)
    return changed


def solve(windows: dict[str, tuple[int, int]], changes: dict[str, set[int]]) -> list[dict] | None:
    """Four window-sets giving both pairs all four states, or ``None`` if none exists.

    ``windows`` maps a label like ``"1A"`` to its span and ``changes`` to the positions the recoder
    would substitute there. A window counts as REMOVED by a transcript when the transcript recodes
    it directly, or when it recodes some other window whose substitutions land inside this one --
    which is the collateral the role swap exploits.

    All 16 subsets are enumerated and every 4-subset combination checked -- 1,820 cases, small
    enough to be exhaustive, so a "no solution" is a proof rather than a search that gave up.
    """
    labels = sorted(windows)

    def removed_by(subset: frozenset[str]) -> dict[str, bool] | None:
        """Which windows this subset removes, or ``None`` if it damages one it must not.

        **A window counts as removed only if it is RECODED, never by collateral damage.** The
        first version of this counted a window as removed when *any* changed base fell inside it,
        and that is false: recoding pair 1's A window changes bases only in the 30 nt it shares
        with pair 2's B window, leaving the other 20 nt of that 50-nt trigger untouched. Measured
        on panel_assign built that way, the transcript meant to put 414/361/4 in state 10 left its
        arm at 0.97 kcal/mol against the ON state's 0.78 -- bench AND-ness -0.19, no gate, on all
        three arms. The trigger was damaged and still worked.

        The same overlap makes the converse a hard constraint: a window that is meant to stay
        INTACT must receive no changed base at all, or the transcript does not realise the state
        it is labelled with. A subset that damages such a window is rejected here rather than
        counted as a solution, which is why this returns ``None``.

        For two pairs the sound solution is then forced and is the obvious one: recode
        ``{1A, 2B}`` together for one cross state and ``{1B, 2A}`` for the other, so every removal
        is direct and the shared region is recoded by whichever window claims it.
        """
        hit: dict[str, bool] = {}
        for label in labels:
            lo, hi = windows[label]
            span = set(range(lo, hi))
            if label in subset:
                hit[label] = True
                continue
            if any(changes[other] & span for other in subset):
                return None
            hit[label] = False
        return hit

    def state_of(subset: frozenset[str], pair: str) -> str | None:
        hit = removed_by(subset)
        if hit is None:
            return None
        return STATES[(not hit[f"{pair}A"], not hit[f"{pair}B"])]

    # Only the subsets that damage nothing they must keep. With overlapping windows this is what
    # removes the unsound options before any combination is considered.
    subsets = [
        frozenset(c)
        for n in range(5)
        for c in itertools.combinations(labels, n)
        if removed_by(frozenset(c)) is not None
    ]
    pairs = sorted({label[0] for label in labels})
    want = {"11", "01", "10", "00"}
    for combo in itertools.combinations(subsets, 4):
        if all({state_of(s, p) for s in combo} == want for p in pairs):
            return [
                {
                    "recoded": sorted(subset),
                    **{f"pair{p}_state": state_of(subset, p) for p in pairs},
                }
                for subset in sorted(combo, key=lambda s: (len(s), sorted(s)))
            ]
    return None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--pairs", nargs="*", default=[], help="two pair ids, else the clashing ones"
    )
    parser.add_argument("--per-cell", type=int, default=3)
    parser.add_argument("--out", default="", help="write solvable pair-sets to results/<name>.csv")
    args = parser.parse_args(argv)

    results = NB / "results"
    transcript = read_fasta(NB / "mCherry_original.txt")
    amino, fraction = cv.load_codon_table(NB / "data" / "ecoli_codon_usage_table.csv")
    groups = cv.synonyms(amino)

    rank = op.gating(op.population(results))
    by_pair: dict[str, dict[str, list[dict]]] = {}
    for row in rank:
        by_pair.setdefault(row["pair"], {}).setdefault(row["geom"], []).append(row)
    eligible = [
        p
        for p, geoms in by_pair.items()
        if len(geoms) >= 2 and min(len(v) for v in geoms.values()) >= args.per_cell
    ]
    print(f"  {len(eligible)} eligible pairs")

    def spans(pair: str) -> dict[str, tuple[int, int]]:
        flat = [r for cells in by_pair[pair].values() for r in cells]
        return {
            "A": (min(int(r["a_start"]) for r in flat), max(int(r["a_end"]) for r in flat)),
            "B": (min(int(r["b_start"]) for r in flat), max(int(r["b_end"]) for r in flat)),
        }

    span_cache = {p: spans(p) for p in eligible}
    change_cache: dict[tuple[str, str], set[int]] = {}
    for pair in eligible:
        for role in ("A", "B"):
            lo, hi = span_cache[pair][role]
            change_cache[(pair, role)] = changed_positions(
                transcript, lo, hi, amino, fraction, groups
            )

    if args.pairs:
        combos = [tuple(args.pairs[:2])]
    else:
        combos = [
            (a, b)
            for a, b in itertools.combinations(eligible, 2)
            if op.cross_role_clash(by_pair, a, b) > 0
        ]
        print(f"  {len(combos)} pair-sets have a cross-role clash and are rejected today\n")

    solved, unsolved, rows = 0, 0, []
    for first, second in combos:
        windows = {f"1{r}": span_cache[first][r] for r in ("A", "B")} | {
            f"2{r}": span_cache[second][r] for r in ("A", "B")
        }
        changes = {f"1{r}": change_cache[(first, r)] for r in ("A", "B")} | {
            f"2{r}": change_cache[(second, r)] for r in ("A", "B")
        }
        clash = op.cross_role_clash(by_pair, first, second)
        answer = solve(windows, changes)
        if answer is None:
            unsolved += 1
            if args.pairs:
                print(f"  {first} + {second}: NO SOLUTION ({clash} nt cross-role clash)")
            continue
        solved += 1
        rows.append(
            {
                "pair_1": first,
                "pair_2": second,
                "clash_nt": clash,
                **{
                    f"T{i}_{k}": v
                    for i, entry in enumerate(answer)
                    for k, v in (
                        ("recoded", " ".join(entry["recoded"]) or "(none)"),
                        ("pair1", entry["pair1_state"]),
                        ("pair2", entry["pair2_state"]),
                    )
                },
            }
        )
        if args.pairs or solved <= 3:
            print(f"  {first} + {second}: SOLVED, {clash} nt cross-role clash")
            print(f"    {'transcript':28s}{'pair 1':>8s}{'pair 2':>8s}")
            for index, entry in enumerate(answer):
                names = " ".join(entry["recoded"]) or "(nothing recoded)"
                print(
                    f"    T{index}: {names:24s}{entry['pair1_state']:>8s}{entry['pair2_state']:>8s}"
                )
            print()

    if not args.pairs:
        total = solved + unsolved
        print(f"  of {total} clashing pair-sets: {solved} SOLVABLE by role swap, {unsolved} not")
        if total:
            print(
                f"  so the role swap recovers {100.0 * solved / total:.0f}% of what the clash costs"
            )

    if args.out and rows:
        path = results / f"{args.out}.csv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        print(f"  wrote {len(rows)} solvable pair-sets to {path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
