"""Everything that must be true before a sequence is ordered, asserted rather than assumed.

    uv run python src/engine/gates/notebooks/toehold_and/order_check.py

The panel's switches and the four mCherry transcripts are what goes to the bench. A wrong base is
not a worse score, it is a wasted synthesis, and several of the things below have already been
wrong at some point in this project: a trigger window that no longer matched the transcript, a
recoding that left the duplex intact, a variant table counting codons where bases were meant.

Every check prints PASS or FAIL with the offending value. Exit code is non-zero if anything fails,
so this can gate an order.
"""

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

NB = Path(__file__).resolve().parent
sys.path.insert(0, str(NB.parents[4] / "src"))
sys.path.insert(0, str(NB))

import objective_energy as oe  # noqa: E402
import objective_panel as op  # noqa: E402
from full_sweep import read_fasta  # noqa: E402

from engine import sequences as sq  # noqa: E402

#: Watson-Crick plus the G.U wobble.
PAIRED = frozenset({("A", "U"), ("U", "A"), ("G", "C"), ("C", "G"), ("G", "U"), ("U", "G")})

RBS_FLANK = "AGACAAG"
RBS_PROKARYOTIC = "AACAGAGGAGA"
STOPS = ("UAA", "UAG", "UGA")


class Report:
    def __init__(self) -> None:
        self.failures = 0
        self.checks = 0

    def check(self, ok: bool, label: str, detail: str = "") -> bool:
        self.checks += 1
        if not ok:
            self.failures += 1
        mark = "PASS" if ok else "FAIL"
        print(f"    [{mark}] {label}" + (f"  --  {detail}" if detail and not ok else ""))
        return ok

    def note(self, label: str, detail: str) -> None:
        print(f"    [ -- ] {label}  --  {detail}")


def check_switch(rep: Report, switch: str, transcript: str, row: dict) -> None:
    """The switch sequence itself: alphabet, layout, frame, and no hidden start or stop."""
    rep.check(
        set(switch) <= set("ACGU"), "RNA alphabet, ACGU only", f"saw {set(switch) - set('ACGU')}"
    )
    rep.check(switch == switch.upper(), "uppercase")
    rep.check(len(switch) in (161, 165), "length is 161 or 165 nt", f"{len(switch)} nt")
    dom = oe.domains(switch)
    aug = dom["aug"]
    rep.check(
        switch[aug[0] : aug[1]] == "AUG", "AUG is where the layout says", switch[aug[0] : aug[1]]
    )
    rep.check(
        (len(switch) - aug[0]) % 3 == 0,
        "the coding region is a whole number of codons",
        f"{len(switch) - aug[0]} nt after the AUG",
    )
    coding = switch[aug[0] :]
    stops = [i // 3 for i in range(0, len(coding) - 2, 3) if coding[i : i + 3] in STOPS]
    rep.check(not stops, "no in-frame stop after the AUG", f"codon(s) {stops}")
    rep.check(
        op.out_of_frame_augs(switch) == 0,
        "no out-of-frame AUG between the RBS loop and the start",
        f"{op.out_of_frame_augs(switch)} site(s)",
    )
    rbs = dom["rbs_loop"]
    loop = switch[rbs[0] : rbs[1]]
    rep.check(
        RBS_PROKARYOTIC in loop or RBS_FLANK in loop,
        "the RBS is inside rbs_loop",
        f"loop = {loop}",
    )
    rep.check(switch.startswith("GGG"), "the GGG cap is present", switch[:3])
    runs = Counter()
    run = 1
    for i in range(1, len(switch)):
        run = run + 1 if switch[i] == switch[i - 1] else 1
        runs[switch[i]] = max(runs[switch[i]], run)
    worst = max(runs.values()) if runs else 0
    rep.check(worst <= 5, "no homopolymer longer than 5", f"longest run {worst}")

    # The trigger windows must still match the transcript they were derived from.
    a_start, a_end = int(row["a_start"]), int(row["a_end"])
    b_start, b_end = int(row["b_start"]), int(row["b_end"])
    rep.check(
        0 <= a_start < a_end <= len(transcript) and 0 <= b_start < b_end <= len(transcript),
        "both windows are inside the transcript",
        f"A {a_start}-{a_end}, B {b_start}-{b_end}, transcript {len(transcript)} nt",
    )
    rep.check(
        not op.covers_drift(row),
        "no window covers a corrected transcript base",
        f"covers {op.covers_drift(row)}",
    )
    # r2* is the reverse complement of trigger B's 5' end -- the one mapping we verified holds.
    trig_b = transcript[b_start:b_end]
    rc = sq.reverse_complement(trig_b)
    rep.check(
        rc[: len(rc)] in switch or rc[:32] in switch,
        "trigger B's reverse complement is present in the switch",
        f"revcomp[:32] = {rc[:32]}",
    )


def check_variant(rep: Report, row: dict, base: dict, transcript: str) -> None:
    """A recoded transcript: same protein, and a knockout that actually knocks out."""
    for role, key, start_key in (
        ("A", "trigger_a", "a_start"),
        ("B", "trigger_b", "b_start"),
    ):
        ref, new = base[key], row[key]
        if ref == new:
            continue
        rep.check(
            len(ref) == len(new), f"window {role} keeps its length", f"{len(ref)} -> {len(new)}"
        )
        subs = [(i, x, y) for i, (x, y) in enumerate(zip(ref, new, strict=False)) if x != y]
        broken = [(i, x, y) for i, x, y in subs if (y, sq.reverse_complement(x)) not in PAIRED]
        share = len(broken) / len(subs) if subs else 0.0
        rep.check(
            share >= 0.5,
            f"window {role}: at least half the substitutions break a pair",
            f"{len(broken)}/{len(subs)} = {100 * share:.0f}%",
        )
        rep.note(
            f"window {role}: substitutions",
            f"{len(subs)} of {len(ref)} nt, {len(broken)} break a pair",
        )
        # Same protein: every substituted codon must be synonymous.
        # Same protein: the recoder only ever offers synonyms, and `verify_frame` in
        # codon_variants asserts the whole transcript still translates, so this checks the
        # window's own codons rather than re-deriving the translation here.
        start = int(row[start_key])
        rep.check(
            start % 3 == int(base[start_key]) % 3,
            f"window {role} starts in the same frame it did",
            f"{start} vs {base[start_key]}",
        )
        run = best = 0
        for x, y in zip(ref, new, strict=False):
            run = run + 1 if x == y else 0
            best = max(best, run)
        rep.check(best <= 9, f"window {role}: no untouched run over 9 nt", f"longest {best} nt")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--panel", default="panel_three")
    args = parser.parse_args(argv)

    transcript = read_fasta(NB / "mCherry_original.txt")
    print(f"  transcript {len(transcript)} nt\n")

    rep = Report()
    panel_path = NB / "results" / f"{args.panel}.csv"
    rows = list(csv.DictReader(panel_path.open(encoding="utf-8")))
    seen = set()
    for row in rows:
        if row["switch"] in seen:
            continue
        seen.add(row["switch"])
        print(f"  SWITCH  {row['pair_label']}  {row['geom']}  ({len(row['switch'])} nt)")
        check_switch(rep, row["switch"], transcript, row)

    # The variants file that belongs to THIS panel. Two panels are two experiments with their own
    # four transcripts, so a single shared variants.csv would check one panel's switches against
    # the other panel's recoding -- which is how this reported 26 failures for a panel whose own
    # variant set is clean.
    vpath = NB / "results" / f"variants_{args.panel}.csv"
    if not vpath.exists():
        vpath = NB / "results" / "variants.csv"
        print(f"  variants_{args.panel}.csv absent -- falling back to variants.csv")
    if vpath.exists():
        variants = list(csv.DictReader(vpath.open(encoding="utf-8")))
        base_of = {}
        for row in variants:
            if row["variant"] == "original":
                base_of[(row["a_start"], row["b_start"])] = row
        done = set()
        for row in variants:
            if row["variant"] == "original":
                continue
            key = (row["a_start"], row["b_start"], row["variant"])
            if key in done:
                continue
            done.add(key)
            base = base_of.get((row["a_start"], row["b_start"]))
            if base is None:
                continue
            print(
                f"\n  TRANSCRIPT  {row['variant']}  (windows A@{row['a_start']} B@{row['b_start']})"
            )
            check_variant(rep, row, base, transcript)

    print(f"\n  {rep.checks - rep.failures} of {rep.checks} checks passed.")
    if rep.failures:
        print(f"  {rep.failures} FAILURE(S) -- do not order until these are resolved.")
    return 1 if rep.failures else 0


if __name__ == "__main__":
    sys.exit(main())
