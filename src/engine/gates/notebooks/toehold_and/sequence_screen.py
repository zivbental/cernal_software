"""Green 2014's sequence screens, measured on our population before any of them becomes a filter.

    uv run python src/engine/gates/notebooks/toehold_and/sequence_screen.py

Green 2014 Extended Experimental Procedures S6.2 lists the patterns NUPACK was forbidden to
generate: ``AAAA, CCCC, GGGG, UUUU, KKKKKK, MMMMMM, RRRRRR, SSSSSS, WWWWWW, YYYYYY`` (IUPAC, so
``K`` is G/U, ``M`` A/C, ``R`` A/G, ``S`` G/C, ``W`` A/U, ``Y`` C/U). S6.3 adds the in-frame stop
screen, and an out-of-frame AUG upstream of the real start is the matching hazard: it gives the
ribosome a second place to initiate, in the wrong frame.

**Why this measures before it filters.** Two of our domains are FIXED and not design output -- the
``GGG`` cap and the 21-nt linker, which contains ``CAAAAG``. So ``AAAA`` is present in every design
by construction, and a screen applied to the whole switch would reject the entire population while
reporting nothing about design quality. Green's constraints applied to sequences NUPACK was
generating; ours have to apply to the parts we generate. This script reports the hit rate per
pattern and per region so the line is drawn with the numbers in view.
"""

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

NB = Path(__file__).resolve().parent
sys.path.insert(0, str(NB.parents[4] / "src"))
sys.path.insert(0, str(NB))

import objective_energy as oe  # noqa: E402
import objective_panel as op  # noqa: E402

#: IUPAC degenerate codes over RNA, as character classes.
IUPAC = {
    "K": "[GU]",
    "M": "[AC]",
    "R": "[AG]",
    "S": "[GC]",
    "W": "[AU]",
    "Y": "[CU]",
}

#: Green S6.2 verbatim. A run of one nucleotide at 4, a run of one *pair class* at 6.
GREEN_PATTERNS = (
    "AAAA",
    "CCCC",
    "GGGG",
    "UUUU",
    "KKKKKK",
    "MMMMMM",
    "RRRRRR",
    "SSSSSS",
    "WWWWWW",
    "YYYYYY",
)

STOP_CODONS = ("UAA", "UAG", "UGA")


def compiled() -> dict[str, re.Pattern]:
    out = {}
    for pattern in GREEN_PATTERNS:
        body = "".join(IUPAC.get(char, char) for char in pattern)
        out[pattern] = re.compile(body)
    return out


PATTERNS = compiled()


def designed_spans(switch: str) -> list[tuple[str, int, int]]:
    """The regions we actually choose, excluding every fixed one.

    Fixed and therefore exempt: the ``GGG`` cap, the three constant loops
    (``sec_loop``, ``rbs_loop``), the ``AUG`` itself and the 21-nt ``linker``. What remains is
    the trigger-derived and scheme-chosen sequence, which is the only part a screen can ask us
    to change.
    """
    dom = oe.domains(switch)
    sws_end = len(switch) - 75
    spans = [
        # The secondary hairpin's designed half: everything from the cap to sws_end except
        # sec_loop. Taken as one span up to sec_loop and one after it.
        ("secondary 5'", 3, sws_end),
        ("main stem 5' arm", dom["main_pre_star"][0], dom["k1_star"][1]),
        ("main_z", dom["main_z"][0], dom["main_z"][1]),
        ("main_pre", dom["main_pre"][0], dom["main_pre"][1]),
    ]
    return [(name, lo, hi) for name, lo, hi in spans if 0 <= lo < hi <= len(switch)]


def out_of_frame_augs(switch: str) -> int:
    """AUGs upstream of the real start that are NOT in its frame.

    An in-frame upstream AUG extends the same protein by a few residues; an out-of-frame one
    makes the ribosome translate something else entirely, and the real start is then competing
    with it. Counted from the RBS loop forward, which is where a ribosome can reach.
    """
    dom = oe.domains(switch)
    start, aug = dom["rbs_loop"][0], dom["aug"][0]
    return sum(
        1
        for index in range(start, aug - 2)
        if switch[index : index + 3] == "AUG" and (aug - index) % 3
    )


def screen(switch: str) -> dict[str, list[str]]:
    """Every violation, by category. Never the first one only -- all of them."""
    faults: dict[str, list[str]] = {}
    for name, lo, hi in designed_spans(switch):
        region = switch[lo:hi]
        for pattern, rx in PATTERNS.items():
            if rx.search(region):
                faults.setdefault(f"pattern {pattern}", []).append(name)
    aug = oe.domains(switch)["aug"][0]
    coding = switch[aug:]
    for index in range(0, len(coding) - 2, 3):
        if coding[index : index + 3] in STOP_CODONS:
            faults.setdefault("in-frame stop", []).append(f"codon {index // 3}")
    count = out_of_frame_augs(switch)
    if count:
        faults.setdefault("out-of-frame AUG upstream", []).append(f"{count} site(s)")
    return faults


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scope", default="gating", choices=("gating", "feasible", "all"))
    args = parser.parse_args(argv)

    results = NB / "results"
    if args.scope == "all":
        rows = op.load(results)
    else:
        rows = op.population(results)
        if args.scope == "gating":
            rows = op.gating(rows)
    print(f"  {len(rows):,} designs in scope '{args.scope}'\n")

    # First: the whole-switch rate, to show why the screen is scoped to designed regions.
    whole = Counter()
    for row in rows:
        for pattern, rx in PATTERNS.items():
            if rx.search(row["switch"]):
                whole[pattern] += 1
    print("  If applied to the WHOLE switch (fixed domains included):")
    for pattern in GREEN_PATTERNS:
        hits = whole[pattern]
        note = (
            "  <-- a fixed domain, so this is not a design fault" if hits > 0.95 * len(rows) else ""
        )
        print(f"    {pattern:8s} {hits:7,d}  ({100.0 * hits / len(rows):5.1f}%){note}")

    print("\n  Applied to the DESIGNED regions only:")
    designed = Counter()
    regions = Counter()
    extra = Counter()
    clean = 0
    for row in rows:
        faults = screen(row["switch"])
        if not faults:
            clean += 1
        for key, where in faults.items():
            if key.startswith("pattern "):
                designed[key[8:]] += 1
                for name in where:
                    regions[f"{key[8:]} in {name}"] += 1
            else:
                extra[key] += 1
    for pattern in GREEN_PATTERNS:
        hits = designed[pattern]
        print(f"    {pattern:8s} {hits:7,d}  ({100.0 * hits / len(rows):5.1f}%)")
    print("\n  The frame screens:")
    for key in ("in-frame stop", "out-of-frame AUG upstream"):
        print(f"    {key:28s} {extra[key]:7,d}  ({100.0 * extra[key] / len(rows):5.1f}%)")
    print(
        f"\n  designs passing EVERY screen: {clean:,} of {len(rows):,} "
        f"({100.0 * clean / len(rows):.1f}%)"
    )

    print("\n  Where each pattern lands (top 12):")
    for key, count in regions.most_common(12):
        print(f"    {key:44s} {count:7,d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
