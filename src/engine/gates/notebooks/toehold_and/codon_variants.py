"""Four mCherry transcripts that realise the four logic states with one switch.

    uv run python src/engine/gates/notebooks/toehold_and/codon_variants.py

**The idea the wet lab asked for.** A trigger is a window of the mCherry transcript, so recoding
that window synonymously removes the trigger without touching the protein. Four transcripts then
give the four tubes with a single switch and no synthetic oligos:

    original          both trigger windows intact
    A-recoded         every trigger-A window recoded
    B-recoded         every trigger-B window recoded
    AB-recoded        both

**Four transcripts, not four per pair.** The panel's two trigger pairs have A windows that sit
close together, so one recode covers both, and the same for B. That keeps the count at four
however many pairs the panel carries -- each variant recodes *every* window of its role.

**Which tube each transcript belongs in.** The left digit is trigger A, so recoding window A
removes trigger A and leaves only B -- state **01**. Recoding window B leaves only A: state **10**.
Each row carries ``removes`` as well as the state name, because the removal is the fact and the
state name is a convention applied to it; a convention change is then a relabel, not a rebuild.

**Codon choice: closest abundance, GC as the tie-breaker.** Every codon that has a synonym is
replaced by the synonym whose *E. coli* usage fraction is nearest its own, so translation speed
moves as little as the genetic code allows. Where two are equally close, the one shifting the
window's GC least wins; where those tie too, the more different sequence wins, since it removes the
trigger more thoroughly and costs nothing. Met and Trp have one codon each and cannot be changed.

This replaces a scheme that maximised sequence difference and held GC exactly. That answered a
different question -- how far can a window be pushed -- and it fought the constraint that matters
here: the recoded transcript must still translate at the rate of the one it stands in for.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[3]))

import objective_energy as oe  # noqa: E402

from engine import sequences as sq  # noqa: E402
from engine.gates.toehold import _mean_unpaired  # noqa: E402
from engine.gates.tools.folding import FoldEngine  # noqa: E402

#: Longest single-base run a recoded window may contain. Above about five nucleotides a
#: homopolymer causes synthesis and sequencing trouble, so a recode that introduces one has traded
#: a biology problem for an ordering problem.
#: Watson-Crick plus the G.U wobble. A substitution landing on one of these opposite the
#: switch's base has not broken the duplex, which is the whole job of a knockout.
_PAIRED = frozenset({("A", "U"), ("U", "A"), ("G", "C"), ("C", "G"), ("G", "U"), ("U", "G")})

MAX_HOMOPOLYMER = 4

#: Longest stretch of bases a recoded window may leave identical to the original.
#:
#: 6 is declared, not derived: two untouched codons' worth. It cannot always be met -- a codon
#: with no synonym is unchangeable, and three of those in a row force a 9-nt run whatever the
#: rule says -- so this is a target the repair pass works towards and `longest_untouched` in the
#: stats reports what was actually achieved. A promise the code cannot keep is worse than a
#: number beside the result.
MAX_UNTOUCHED = 6

#: mCherry's ORF frame, verified rather than assumed by ``verify_frame``.
ORF_FRAME = 0

_OVER_LONG = re.compile(r"(.)\1{" + str(MAX_HOMOPOLYMER) + ",}")


def load_codon_table(path: Path) -> tuple[dict[str, str], dict[str, float]]:
    """codon -> amino acid, and codon -> E. coli usage fraction."""
    amino: dict[str, str] = {}
    fraction: dict[str, float] = {}
    with path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            codon = (row.get("Codon") or "").strip().upper().replace("T", "U")
            if len(codon) != 3:
                continue
            amino[codon] = (row.get("Amino acid") or "").strip()
            try:
                fraction[codon] = float(row["Fraction"])
            except (KeyError, ValueError):
                fraction[codon] = 0.0
    return amino, fraction


def synonyms(amino: dict[str, str]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = defaultdict(list)
    for codon, acid in amino.items():
        groups[acid].append(codon)
    return groups


def verify_frame(rna: str, amino: dict[str, str]) -> int:
    """Confirm the ORF is in frame 0 and return its codon count.

    An ORF begins with AUG and carries no internal stop. Checking only that the first triplet is a
    codon proves nothing -- 61 of 64 triplets are. Measured here: frame 0 gives 237 codons and no
    internal stop, frame 1 gives 15 and frame 2 gives 2, and frame 0 translates to
    ``MVSKGEEDNMAIIKEFMRFKVHME...``, mCherry's own N-terminus.

    Raises rather than warns: if it is ever wrong, no substitution in this file is synonymous.
    """
    stops = {"UAA", "UAG", "UGA"}
    codons = [rna[i : i + 3] for i in range(ORF_FRAME, len(rna) - 2, 3)]
    if codons[0] != "AUG":
        raise AssertionError(f"frame {ORF_FRAME} starts {codons[0]}, not AUG -- not the ORF")
    internal = [i for i, c in enumerate(codons[:-1]) if c in stops]
    if internal:
        raise AssertionError(
            f"frame {ORF_FRAME} has {len(internal)} internal stop(s), first at codon "
            f"{internal[0]} -- not the ORF, so no substitution here is synonymous"
        )
    missing = [c for c in codons if c not in amino]
    if missing:
        raise AssertionError(f"{len(missing)} codon(s) absent from the table, e.g. {missing[0]}")
    return len(codons)


def codon_starts(lo: int, hi: int) -> list[int]:
    """Starts of the codons lying entirely inside ``[lo, hi)``, in frame 0.

    A codon straddling the boundary cannot be changed without altering a neighbouring window's
    amino acid, so it is left alone.
    """
    first = lo + (-lo) % 3
    return [s for s in range(first, hi - 2, 3) if s + 3 <= hi]


def recode_windows(
    rna: str,
    windows: list[tuple[int, int]],
    amino: dict[str, str],
    fraction: dict[str, float],
    groups: dict[str, list[str]],
) -> tuple[str, dict]:
    """Recode every codon in every window to its nearest-abundance synonym."""
    out = list(rna)
    stats = {
        "codons": 0,
        "changed": 0,
        "no_synonym": 0,
        "homopolymer_fixes": 0,
        "untouched_fixes": 0,
    }

    def breaks_pairing(option: str, codon: str) -> int:
        """How many substituted positions actually stop pairing with the switch.

        **The bug this exists to fix.** The switch was built to pair with the ORIGINAL window, so
        opposite transcript base ``b`` it presents ``revcomp(b)``. Ranking only on codon abundance
        made ``C -> U`` the dominant substitution (104 of 198), and opposite a ``G`` that is
        ``G.C -> G.U`` -- **still a base pair**, the wobble pair. A knockout that leaves a wobble
        pair has knocked nothing out.

        Measured on the panel's own variants before this term existed: of 732 substitutions,
        **424 (57.9%) left a G.U wobble** and only 308 broke anything, with per-window
        effectiveness as low as 36.4%. The symptom was that all six B-recoded transcripts of one
        trigger pair moved the ON cost by at most 0.098 kcal/mol -- the recoding ran, reported 15
        substitutions, and the gate did not notice.

        Opposite ``G`` only ``A`` and ``G`` break the pair; opposite ``C`` only ``C`` and ``U``;
        and so on. Returned as a COUNT so a codon breaking two pairs beats one breaking one.
        """
        return sum(
            1
            for x, y in zip(option, codon, strict=True)
            if x != y and (x, sq.reverse_complement(y)) not in _PAIRED
        )

    def rank(option: str, codon: str) -> tuple[int, float, int, int]:
        gc_now = sum(1 for c in codon if c in "GC")
        return (
            # FIRST: does it actually knock the trigger out. Abundance matching was the
            # supervisor's requirement and it stays, but it is a constraint on HOW to break the
            # pairing, not a reason to leave it intact.
            -breaks_pairing(option, codon),
            abs(fraction.get(option, 0.0) - fraction.get(codon, 0.0)),
            abs(sum(1 for c in option if c in "GC") - gc_now),
            -sum(1 for x, y in zip(option, codon, strict=True) if x != y),
        )

    for start in sorted({s for lo, hi in windows for s in codon_starts(lo, hi)}):
        codon = "".join(out[start : start + 3])
        acid = amino.get(codon)
        if acid is None:
            continue
        stats["codons"] += 1
        options = [c for c in groups.get(acid, ()) if c != codon]
        if not options:
            stats["no_synonym"] += 1
            continue
        out[start : start + 3] = list(min(options, key=lambda o: rank(o, codon)))
        stats["changed"] += 1

    # Homopolymers, scored by TOTAL nucleotides inside over-long runs and not by the longest one:
    # with two runs of five, fixing one leaves the longest at five, so a longest-run test rejects
    # every repair and nothing moves. That happened.
    def violation(seq: str) -> int:
        return sum(len(m.group(0)) for m in _OVER_LONG.finditer(seq))

    for lo, hi in windows:
        for _attempt in range(len(codon_starts(lo, hi)) * 3):
            before = violation("".join(out[lo:hi]))
            if not before:
                break
            best = None
            for start in codon_starts(lo, hi):
                codon = "".join(out[start : start + 3])
                acid = amino.get(codon)
                for option in groups.get(acid, ()) if acid else ():
                    if option == codon:
                        continue
                    trial = list(out)
                    trial[start : start + 3] = list(option)
                    if violation("".join(trial[lo:hi])) >= before:
                        continue
                    score = (*rank(option, codon), start)
                    if best is None or score < best[0]:
                        best = (score, start, option)
            if best is None:
                break
            _score, start, option = best
            out[start : start + 3] = list(option)
            stats["homopolymer_fixes"] += 1

    # Untouched RUNS, in bases. The earlier rule counted consecutive unchanged CODONS and did not
    # survive the rewrite to four transcripts; worse, it was the wrong unit. A codon whose only
    # synonym differs at position 3 contributes two unchanged bases on each side, so a window can
    # have every codon "changed" and still show a long unchanged stretch -- measured here at 11 nt
    # in window B with 12 of 49 bases changed. What a reviewer looks at is the base run, so that is
    # what this bounds.
    #
    # Repaired the same way as homopolymers, by TOTAL bases inside over-long runs rather than by
    # the longest one: with two long runs, fixing one leaves the longest unchanged and a
    # longest-run test then rejects every repair.
    def untouched(seq: list[str], lo: int, hi: int) -> int:
        total = run = 0
        for index in range(lo, hi):
            run = run + 1 if seq[index] == rna[index] else 0
            if run > MAX_UNTOUCHED:
                total += 1
        return total

    for lo, hi in windows:
        for _attempt in range(len(codon_starts(lo, hi)) * 3):
            before = untouched(out, lo, hi)
            if not before:
                break
            best = None
            for start in codon_starts(lo, hi):
                codon = "".join(out[start : start + 3])
                acid = amino.get(codon)
                for option in groups.get(acid, ()) if acid else ():
                    if option == codon:
                        continue
                    trial = list(out)
                    trial[start : start + 3] = list(option)
                    # Never trade an untouched run for a homopolymer: the homopolymer pass has
                    # already run and this must not undo it.
                    if violation("".join(trial[lo:hi])):
                        continue
                    after = untouched(trial, lo, hi)
                    if after >= before:
                        continue
                    score = (after, *rank(option, codon), start)
                    if best is None or score < best[0]:
                        best = (score, start, option)
            if best is None:
                break
            _score, start, option = best
            out[start : start + 3] = list(option)
            stats["untouched_fixes"] += 1

    stats["longest_untouched"] = max(
        (
            max(
                (
                    len(run)
                    for lo, hi in windows
                    for run in "".join(
                        "=" if out[i] == rna[i] else " " for i in range(lo, hi)
                    ).split()
                ),
                default=0,
            ),
        ),
        default=0,
    )
    return "".join(out), stats


def a_m_terms(
    folder: FoldEngine, switch: str, trig_a: str, trig_b: str
) -> tuple[float | None, float | None, float | None]:
    """``(ratio, gain)``: ``A_M(11)/max(A_M OFF)`` and ``A_M(11) - max(A_M OFF)``, on this
    transcript's triggers.

    ``A_M`` is the mean per-base unpaired probability over ``main_z + AUG + main_pre`` -- the gate's
    own span from ``four_tube_observables``, 18 nt and identical in both geometries. A mean and not
    a joint probability: over 18 nt a joint is ~1e-22 for any arm.

    **Both from the same four folds, which is the point of returning a tuple.** The four tubes are
    the whole cost here; computing the gain in a second function would double it and, worse, would
    leave two code paths able to disagree about ``A_M(11)`` for one design.

    **Why the gain is the one the panel ranks on.** The ratio's +0.698 against Green's 13
    forward-engineered switches belongs to its DENOMINATOR -- ``A_M_off`` alone scores +0.648 there,
    against the ON term's +0.528 -- and that denominator gives -0.046 on Green's 168 and +0.021 on
    VISTA. The gain tracks the ON state instead (rho 0.995 with ``A_M_on``, against the ratio's
    0.930), is bounded in [-1, 1] rather than running to 383, and is architecture-neutral: 5 of the
    top 100 by gain come from one geometry where 89 of the top 100 by ratio do.

    The ratio is kept beside it, not replaced. It is the number the earlier panels were read with,
    so dropping it would make this table incomparable with those.
    """
    d = oe.domains(switch)
    span = (d["main_z"][0], d["main_pre"][1])
    values = {}
    for state, strands in (
        ("00", switch),
        ("01", f"{switch}&{trig_b}"),
        ("10", f"{switch}&{trig_a}"),
        ("11", f"{switch}&{trig_a}&{trig_b}"),
    ):
        values[state] = _mean_unpaired(folder.pooled_pair_probabilities(strands), *span)
    worst_off = max(values[s] for s in ("00", "01", "10"))
    # The gain needs no non-zero denominator, so it survives a transcript the ratio cannot score.
    gain = round(values["11"] - worst_off, 4)
    # ``worst_off`` is returned rather than left implicit because the gain cannot see it: over 2,052
    # gating designs rho(gain, worst A_M) = -0.019 against rho(gain, A_M(11)) = +0.940. A variant
    # whose ratio rises while its gain holds has lost its OFF state, and only this column says so.
    return (
        round(values["11"] / worst_off, 3) if worst_off else None,
        gain,
        round(worst_off, 4),
    )


def parse_swap(recipe: str) -> tuple[list[str], list[tuple[str, list[str]]]] | None:
    """``pairs=P1;P2|T0=|T1=1A|T2=1B,2A`` -> the two pair labels and each transcript's windows.

    ``None`` when the panel carries no swap, which is the ordinary case and keeps the four
    role-named transcripts.
    """
    if not recipe:
        return None
    head, *rest = recipe.split("|")
    if not head.startswith("pairs=") or not rest:
        return None
    pairs = head[len("pairs=") :].split(";")
    steps = []
    for part in rest:
        name, _, windows = part.partition("=")
        steps.append((name, [w for w in windows.split(",") if w]))
    return pairs, steps


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--panel", default="panel_three", help="results/<name>.csv")
    parser.add_argument("--out", default="variants", help="results/<name>.csv")
    parser.add_argument("--fasta", default="mCherry_original.txt")
    parser.add_argument("--table", default="data/ecoli_codon_usage_table.csv")
    parser.add_argument(
        "--no-score", action="store_true", help="skip the four-tube scoring, the slow part"
    )
    args = parser.parse_args(argv)

    results = HERE / "results"
    raw = (HERE / args.fasta).read_text()
    rna = sq.to_rna(
        "".join(line.strip() for line in raw.splitlines() if not line.startswith(">")).upper()
    )
    amino, fraction = load_codon_table(HERE / args.table)
    groups = synonyms(amino)
    folder = FoldEngine(37.0)
    print(f"  transcript {len(rna):,} nt   {len(amino)} codons in the usage table")
    print(f"  frame {ORF_FRAME} verified: {verify_frame(rna, amino)} codons, no internal stop")

    rows = list(csv.DictReader((results / f"{args.panel}.csv").open(encoding="utf-8")))
    # Every window of each role across the whole panel: one A-recode covers both pairs.
    a_windows = sorted({(int(r["a_start"]), int(r["a_end"])) for r in rows})
    b_windows = sorted({(int(r["b_start"]), int(r["b_end"])) for r in rows})
    print(f"  {len(rows)} panel rows -> {len(a_windows)} A window(s), {len(b_windows)} B window(s)")
    for label, spans in (("A", a_windows), ("B", b_windows)):
        print(f"    {label}: " + ", ".join(f"{lo}-{hi}" for lo, hi in spans))

    recoded_a, stats_a = recode_windows(rna, a_windows, amino, fraction, groups)
    recoded_b, stats_b = recode_windows(rna, b_windows, amino, fraction, groups)
    recoded_ab, stats_ab = recode_windows(recoded_a, b_windows, amino, fraction, groups)
    both = {k: stats_a.get(k, 0) + stats_ab.get(k, 0) for k in stats_a}

    # Named by what each REMOVES as well as by its state: the removal is the fact and the
    # state name is a convention applied to it.
    # The four transcripts the panel actually needs.
    #
    # Without a role swap they are the role-named four: every A window recoded, every B window,
    # both. With one they are NOT -- the swap exists because the two pairs' windows cross, so
    # "recode every A window" would damage a B window another pair must keep. The plan says which
    # single windows each transcript recodes (``1A`` = pair 1's A window alone), and each pair
    # reads a DIFFERENT state off the same transcript. Building the role-named four for such a
    # panel produces transcripts that realise no state for either pair.
    swap = parse_swap(next((r.get("swap_recipe") or "" for r in rows), ""))
    if swap is None:
        variants = [
            ("original", rna, "nothing removed", "11", {}),
            ("A-recoded", recoded_a, "trigger A removed", "01", stats_a),
            ("B-recoded", recoded_b, "trigger B removed", "10", stats_b),
            ("AB-recoded", recoded_ab, "both removed", "00", both),
        ]
    else:
        swap_pairs, steps = swap
        print(f"\n  role swap: {len(steps)} transcripts over pairs {', '.join(swap_pairs)}")
        # Which window each `<index><role>` token names, from the panel's own rows rather than
        # from an assumption about order: pair 1 is the first label in the recipe.
        window_of: dict[str, tuple[int, int]] = {}
        for position, label in enumerate(swap_pairs, start=1):
            mine = [r for r in rows if r.get("pair") == label or r.get("pair_label") == label]
            if not mine:
                print(f"    {label} has no rows in this panel -- cannot build its transcripts")
                return 1
            window_of[f"{position}A"] = (
                min(int(r["a_start"]) for r in mine),
                max(int(r["a_end"]) for r in mine),
            )
            window_of[f"{position}B"] = (
                min(int(r["b_start"]) for r in mine),
                max(int(r["b_end"]) for r in mine),
            )
        variants = []
        for name, tokens in steps:
            unknown = [t for t in tokens if t not in window_of]
            if unknown:
                print(f"    {name}: unknown window {', '.join(unknown)}")
                return 1
            spans = sorted({window_of[t] for t in tokens})
            built, stats = (
                (rna, {}) if not spans else recode_windows(rna, spans, amino, fraction, groups)
            )
            # The state label belongs to a PAIR, not to the transcript, so it is resolved per
            # design below. Here the transcript is named by what it recodes.
            variants.append(
                (name, built, " ".join(tokens) if tokens else "nothing removed", "", stats)
            )
        print(
            "    "
            + "  ".join(f"{name}:{' '.join(t for t in tokens) or 'none'}" for name, tokens in steps)
        )
    print("\n  four transcripts:")
    for name, transcript, removes, states, stats in variants:
        changed = sum(1 for x, y in zip(rna, transcript, strict=True) if x != y)
        print(
            f"    {name:12s}{removes:20s}state {states:10s}{changed:>4d} nt changed, "
            f"{stats.get('changed', 0)} codons recoded, "
            f"{stats.get('no_synonym', 0)} unchangeable, "
            f"{stats.get('homopolymer_fixes', 0)} homopolymer fix(es)"
        )

    # The four transcripts themselves, beside the per-design table. They existed only as locals
    # here, so the only way to get the sequence that will actually be ORDERED was to re-run this
    # script and read the console -- and the ordering sheet needs the whole 711 nt with the changed
    # positions marked, not a per-design summary of them.
    #
    # `changed` is a run list, not a position list: the recoder moves whole codons, so the changes
    # arrive in short runs and a run list is what a reader can check against the window bounds.
    def runs_of(original: str, variant: str) -> str:
        spans, start = [], None
        for index, (one, two) in enumerate(zip(original, variant, strict=True)):
            if one != two and start is None:
                start = index
            elif one == two and start is not None:
                spans.append((start, index))
                start = None
        if start is not None:
            spans.append((start, len(variant)))
        return " ".join(f"{lo}-{hi}" for lo, hi in spans)

    tpath = results / f"{args.out}_transcripts.csv"
    with tpath.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["variant", "removes", "states", "length", "changed_nt", "changed", "seq"])
        for name, transcript, removes, states, _stats in variants:
            changed = sum(1 for x, y in zip(rna, transcript, strict=True) if x != y)
            writer.writerow(
                [
                    name,
                    removes,
                    states,
                    len(transcript),
                    changed,
                    runs_of(rna, transcript),
                    transcript,
                ]
            )
    print(f"\n  written: {tpath.name}  (the four transcripts, full length)")

    out_rows = []
    for row in rows:
        switch = row["switch"]
        a_lo, a_hi = int(row["a_start"]), int(row["a_end"])
        b_lo, b_hi = int(row["b_start"]), int(row["b_end"])
        base_a, base_b = rna[a_lo:a_hi], rna[b_lo:b_hi]
        for name, transcript, removes, states, stats in variants:
            trig_a, trig_b = transcript[a_lo:a_hi], transcript[b_lo:b_hi]
            record = {
                "pair": row.get("pair_label", ""),
                "geom": row.get("geom", ""),
                "arm": row.get("arm", ""),
                "variant": name,
                "removes": removes,
                # With a swap the state is read off THIS pair's own plan, because the same
                # transcript is 01 for one pair and 10 for the other. `swap_states` carries it as
                # `T0=11 T1=10 ...` on every row of the pair.
                "states": states
                or dict(
                    part.split("=", 1)
                    for part in (row.get("swap_states") or "").split()
                    if "=" in part
                ).get(name, "?"),
                "len_x": row["len_x"],
                "a_start": a_lo,
                "a_end": a_hi,
                "b_start": b_lo,
                "b_end": b_hi,
                "codons_recoded": stats.get("changed", 0),
                "codons_unchangeable": stats.get("no_synonym", 0),
                "homopolymer_fixes": stats.get("homopolymer_fixes", 0),
                "gc_a": round(sq.gc_content(trig_a), 2),
                "gc_b": round(sq.gc_content(trig_b), 2),
                "gc_a_shift": round(sq.gc_content(trig_a) - sq.gc_content(base_a), 2),
                "gc_b_shift": round(sq.gc_content(trig_b) - sq.gc_content(base_b), 2),
                "identity_a": round(
                    sum(1 for x, y in zip(base_a, trig_a, strict=True) if x == y) / len(base_a), 3
                ),
                "identity_b": round(
                    sum(1 for x, y in zip(base_b, trig_b, strict=True) if x == y) / len(base_b), 3
                ),
                "trigger_a": trig_a,
                "trigger_b": trig_b,
            }
            if not args.no_score:
                # The ORIGINAL switch against these triggers -- the switch never changes.
                scored = oe.score_design(folder, switch, trig_a, trig_b)
                for key in ("open_00", "open_01", "open_10", "open_11", "andness", "barrier"):
                    record[key] = scored.get(key)
                (
                    record["a_m_ratio"],
                    record["a_m_gain"],
                    record["a_m_worst"],
                ) = a_m_terms(folder, switch, trig_a, trig_b)
            out_rows.append(record)

    path = results / f"{args.out}.csv"
    fields: list[str] = []
    for record in out_rows:
        for key in record:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(out_rows)

    def show(value, places: int = 2) -> str:
        # The gain lives in [-1, 1] and the ratio runs past 100, so one shared precision would print
        # the gain as 0.76 against a ratio of 56.79 and lose the half of it that discriminates.
        return "n/a" if value in (None, "") else f"{float(value):.{places}f}"

    print(
        f"\n  {'pair':17s}{'chosen by':14s}{'variant':12s}{'ON cost':>8s}{'AND-ness':>10s}"
        f"{'Barrier':>9s}{'A_M ratio':>11s}{'A_M gain':>10s}{'worst A_M':>11s}"
        f"{'GC A':>8s}{'GC B':>8s}"
    )
    last = None
    for record in out_rows:
        if last and (record["pair"], record["arm"]) != last:
            print()
        last = (record["pair"], record["arm"])
        print(
            f"  {record['pair'][:16]:17s}{record['arm'][:12]:14s}{record['variant']:12s}"
            f"{show(record.get('open_11')):>8s}{show(record.get('andness')):>10s}"
            f"{show(record.get('barrier')):>9s}{show(record.get('a_m_ratio')):>11s}"
            f"{show(record.get('a_m_gain'), 3):>10s}"
            f"{show(record.get('a_m_worst'), 4):>11s}"
            f"{record['gc_a']:>6.1f}{record['gc_a_shift']:>+5.1f}"
            f"{record['gc_b']:>6.1f}{record['gc_b_shift']:>+5.1f}"
        )
    print(f"\n  written: {path.name}")
    print("")
    print("  Every row is the SAME switch; only the transcript changes. A variant that removes a")
    print("  trigger should push ON cost UP and AND-ness towards 0. Barrier depends on the switch")
    print("  alone, so it is constant across a design's four rows -- a sanity check, not a result.")
    print("  GC is the tie-breaker in the codon choice, and its shift is printed so a variant that")
    print("  failed for its folding energy is not mistaken for one that failed for its sequence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
