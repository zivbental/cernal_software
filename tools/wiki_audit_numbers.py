"""Find quantities the model page states more than once, and disagrees with itself about.

Every factual slip caught in this page so far has been the same shape: one number
written in two places, and one of them left behind when the other changed. Swapped
cross-references to 4.3 and 4.4, a table captioned "The five" over four rows, a barrier
span quoted in six places after the quantity was recomputed, a caption saying a run was
still completing where another section reported it finished. None was subtle, and all
survived several readings.

So this reads the page rather than trusting it. For each quantity it knows how to
recognise it collects every value the page gives, and reports the ones that disagree.
It knows nothing about biology; it is a consistency check, not a review.

**It matches what a reader sees, not the markup.** The page is reduced to plain text
first, because matching the raw HTML means matching SVG path coordinates: a pattern
looking for "210" found "210 258 Q 232 258" inside a drawing and reported it as a
count. Figure labels survive the reduction and are checked, which is the point -- a
figure quoting a number the prose has since changed is exactly the failure here.

Run::

    uv run python tools/wiki_audit_numbers.py
    uv run python tools/wiki_audit_numbers.py --verbose   # every match, not only clashes

Exit status is 1 when a quantity disagrees with itself, so it can gate a publish.
"""

from __future__ import annotations

import argparse
import collections
import pathlib
import re

PAGE = pathlib.Path(r"C:\dev\tau-israel\wiki\pages\and-gate-model.html")

#: A quantity and the pattern that finds it in the reduced text. Each pattern captures
#: exactly one group, the value. A pattern that stops matching is reported rather than
#: passing quietly, because a check that matches nothing always says yes.
QUANTITIES: tuple[tuple[str, str], ...] = (
    # "N designs" alone is too loose: the page legitimately says it of the budget
    # before the grid cuts, of the number folded, and of a measurement's sample.
    # Each is its own quantity and gets its own line.
    ("designs built", r"(?:built|holds|sweep holds) ([\d,]{7,})(?: designs| versions)?"),
    ("budget before the grid cuts", r"([\d,]{7,}) designs, about 202 core-hours"),
    ("span-comparison sample", r"measured on all ([\d,]{6,}) designs"),
    (
        "designs in both barrier readings",
        r"([\d,]{4,}) (?:designs compared with a heuristic|designs drawn from three"
        r"|modeled designs are not the entire|designs, no heuristic path"
        r"|designs showed that equilibrium)",
    ),
    ("designs folded in four states", r"([\d,]{6,}) (?:were folded|folded) in (?:all )?four"),
    ("designs folded, trailing form", r"([\d,]{6,}) designs folded in (?:all )?four"),
    ("candidate trigger pairs", r"([\d,]{6,}) candidate (?:trigger )?pairs"),
    ("feasible designs", r"admits ([\d,]{3,}) designs"),
    # Not a bare "NNN cells": 7.6 legitimately reports a 389-cell matched subset, and a
    # loose pattern would read that as a second value for this quantity.
    (
        "cells",
        r"(?:[Aa]cross all |of the |switches over |two geometries \()(\d{3}) "
        r"(?:cells|trigger-pair-by-geometry|pair-by-geometry)",
    ),
    ("carried trigger pairs", r"take (\d{3}) of the 53,530"),
    ("stems built", r"all ([\d,]{4,}) stems"),
    ("preferred-stem designs", r"(\d{3}) preferred-stem designs"),
    ("path barrier span", r"spans? ([\d.]+) kcal/mol"),
    ("ON-state ceiling", r"ceiling (?:of |is now )?\(?([\d.]+) kcal/mol"),
    ("Green measured switches", r"Green's ([\d,]{3}) measured"),
    ("overlap floor, nt", r"at least ([\d]) nt"),
    ("switch length, naive", r"(\d{3}) nt for the naive"),
    ("barrier minimum", r"\+([\d.]+) to \+25\.2"),
)

ENTITIES = {
    "&nbsp;": " ",
    "&mdash;": "--",
    "&ndash;": "-",
    "&minus;": "-",
    "&times;": "x",
    "&middot;": "-",
    "&rsquo;": "'",
    "&#8217;": "'",
    "&ldquo;": '"',
    "&rdquo;": '"',
    "&sect;": "S",
    "&rho;": "rho",
    "&amp;": "&",
}


def as_read(page: str) -> str:
    """The page as a reader meets it: tags gone, entities resolved, spacing collapsed.

    Reducing before matching is what keeps SVG geometry out of the results. Figure
    labels are kept, because a figure quoting a stale number is the failure this looks
    for.
    """
    text = re.sub(r"<[^>]+>", " ", page)
    for entity, plain in ENTITIES.items():
        text = text.replace(entity, plain)
    text = re.sub(r"&[a-z]+;|&#\d+;", " ", text)
    return re.sub(r"\s+", " ", text)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Check the page against itself.")
    parser.add_argument("--page", default=PAGE, type=pathlib.Path)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    text = as_read(args.page.read_text(encoding="utf-8"))

    found: dict[str, list[str]] = collections.defaultdict(list)
    for name, pattern in QUANTITIES:
        for match in re.finditer(pattern, text):
            found[name].append(match.group(1).replace(",", ""))

    clashes, stale = 0, 0
    for name, _pattern in QUANTITIES:
        hits = found.get(name, [])
        if not hits:
            stale += 1
            print(f"  [STALE] {name}: matches nothing, so it is checking nothing")
            continue
        distinct = sorted(set(hits))
        if len(distinct) > 1:
            clashes += 1
            print(f"  [CLASH] {name}: {distinct} over {len(hits)} mentions")
        elif args.verbose:
            print(f"  [ ok ] {name}: {distinct[0]} in {len(hits)} place(s)")

    print()
    if clashes or stale:
        if clashes:
            print(f"  {clashes} quantity(ies) disagree with themselves.")
        if stale:
            print(f"  {stale} pattern(s) match nothing and need rewriting or removing.")
        return 1
    print(f"  {len(QUANTITIES)} quantities checked, every mention agrees.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
