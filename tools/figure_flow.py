"""The method as six steps, each with a small drawing of what it does.

Run::

    uv run python tools/figure_flow.py --out methods-flow.svg

This figure belongs with the summary at the top of the page rather than inside Methods:
it is the picture a reader needs *before* the sections, and by the time they reach them
they are past needing it.

**Every drawing is confined to a declared box, and that is checked rather than
eyeballed.** ``art()`` returns its elements, ``_extent`` reads every path, circle, rect
and label back out of them, and ``main`` refuses to write a file where anything escapes
its row. A drawing that does not fit is a drawing to simplify, not a box to enlarge.

Two things that check has to get right, because both have hidden a real overflow:
an SVG arc's ``0 1 1`` flags are not coordinates, so the stems here are cubics; and a
label's width is nowhere in the markup, so it is estimated rather than counted as zero.

**What the drawings are for.** Each is the smallest picture that tells its step apart
from the one above it: no sequence, nothing to scale, no notation to carry. Figures 3.1
and 3.2 hold the real geometry and this one does not compete with them.
"""

from __future__ import annotations

import argparse
import pathlib
import re

WIDTH = 900
MARGIN = 10
ROW_H = 118
ROW_GAP = 8
ART_X = 470
ART_W = WIDTH - ART_X - MARGIN - 4

#: Title, the one line that says what the step does, the count it leaves behind, and
#: which drawing goes beside it. The counts are what make this a funnel rather than six
#: labelled boxes, and they are the numbers of section 4.5.
STEPS: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "1",
        "Scan each gene",
        "A window could begin at any base.",
        "4 genes, every window a candidate",
        "windows",
    ),
    (
        "2",
        "Pair two genes",
        "Keep the pairs whose windows are complementary.",
        "53,530 candidate pairs \u2192 210 carried",
        "pair",
    ),
    (
        "3",
        "Build the secondary hairpin",
        "Some positions already pair; the rest force a choice.",
        "median 82 on the front, about 9 sampled",
        "choice",
    ),
    (
        "4",
        "Assemble the switch",
        "Two hairpins touching, the start codon inside the second.",
        "one switch, 161 or 165 nt",
        "switch",
    ),
    (
        "5",
        "Vary, then cut",
        "Three parts can be rewritten. Most candidates are cut.",
        "301,440 built \u2192 219,808 folded in four states",
        "levers",
    ),
    (
        "6",
        "Fold four states",
        "Only both triggers together should open it.",
        "4,762 pass every gate of the feasible set",
        "tubes",
    ),
)


def _text(x: float, y: float, s: str, cls: str, anchor: str = "start") -> str:
    extra = f' text-anchor="{anchor}"' if anchor != "start" else ""
    return f'<text class="{cls}" x="{x:.1f}" y="{y:.1f}"{extra}>{s}</text>'


def _bar(x: float, y: float, w: float, h: float, cls: str) -> str:
    return (
        f'<rect class="{cls}" x="{x:.1f}" y="{y:.1f}" '
        f'width="{w:.1f}" height="{h:.1f}" rx="{h / 2:.1f}" />'
    )


def _line(x1: float, y1: float, x2: float, y2: float, cls: str) -> str:
    return f'<path class="{cls}" d="M {x1:.1f} {y1:.1f} L {x2:.1f} {y2:.1f}" />'


def _stem(x: float, top: float, bottom: float, w: float, cls: str = "fl-stem") -> str:
    """A hairpin standing on its arms: two uprights closed by a loop over the top.

    The loop is a cubic rather than an SVG arc. An arc carries three flag digits in the
    middle of its coordinates, and any bounds check that reads a path back as x,y pairs
    is silently thrown off by them -- which is how a stem taller than its row got into
    the first version of this figure unseen.
    """
    r = w / 2
    return (
        f'<path class="{cls}" d="M {x:.1f} {bottom:.1f} L {x:.1f} {top + r:.1f} '
        f"C {x:.1f} {top - 0.35 * r:.1f} {x + w:.1f} {top - 0.35 * r:.1f} "
        f"{x + w:.1f} {top + r:.1f} "
        f'L {x + w:.1f} {bottom:.1f}" />'
    )


def _rungs(x: float, w: float, levels: list[tuple[float, str]]) -> list[str]:
    """The base pairs inside a stem: a full rung pairs, a broken one does not."""
    out = []
    for y, kind in levels:
        if kind == "clash":
            out.append(
                f'<path class="fl-rung fl-rung--clash" d="M {x:.1f} {y:.1f} '
                f"L {x + 11:.1f} {y:.1f} M {x + w - 11:.1f} {y:.1f} "
                f'L {x + w:.1f} {y:.1f}" />'
            )
        else:
            out.append(
                f'<path class="fl-rung{" fl-rung--lever" if kind == "lever" else ""}" '
                f'd="M {x:.1f} {y:.1f} L {x + w:.1f} {y:.1f}" />'
            )
    return out


def _windows(cy: float) -> list[str]:
    """One gene, and the many windows that could be cut out of it."""
    out = [_bar(ART_X, cy - 36, ART_W, 12, "fl-genebar")]
    for i in range(6):
        out.append(_bar(ART_X + i * 52, cy - 6 + (i % 3) * 9, 120, 7, "fl-win"))
    out.append(_text(ART_X, cy + 42, "one could begin at every base", "fl-note"))
    return out


def _pair(cy: float) -> list[str]:
    """Two genes, and the one window in each that matches the other."""
    out = []
    for y, at in ((cy - 40, 44), (cy + 2, 214)):
        out.append(_bar(ART_X, y, ART_W, 11, "fl-genebar"))
        out.append(_bar(ART_X + at, y - 2, 74, 15, "fl-win fl-win--hit"))
    out.append(_line(ART_X + 81, cy - 25, ART_X + 251, cy + 9, "fl-link"))
    out.append(_text(ART_X, cy + 40, "complementary, 4 nt or more", "fl-note"))
    return out


def _choice(cy: float) -> list[str]:
    """A stem where only some of the positions are settled by the two triggers."""
    x, w = ART_X + 18, 46
    out = [_stem(x, cy - 34, cy + 24, w)]
    out += _rungs(
        x, w, [(cy + 18, "pair"), (cy + 7, "clash"), (cy - 4, "pair"), (cy - 15, "clash")]
    )
    out += [
        _text(ART_X + 96, cy - 22, "Several positions already pair", "fl-note"),
        _text(ART_X + 96, cy - 4, "the rest are a three-way choice", "fl-note"),
        _text(ART_X + 96, cy + 14, "matching one of the two triggers and the stem,", "fl-note"),
        _text(ART_X + 96, cy + 32, "or matching both and bulging the hairpin", "fl-note"),
    ]
    return out


def _switch(cy: float) -> list[str]:
    """The two hairpins, touching, with the start codon buried in the second."""
    first, second, w = ART_X + 40, ART_X + 84, 44
    out = [_stem(first, cy - 30, cy + 22, w), _stem(second, cy - 30, cy + 22, w)]
    out += _rungs(first, w, [(cy + 16, "pair"), (cy + 5, "pair"), (cy - 6, "pair")])
    out += _rungs(second, w, [(cy + 16, "pair"), (cy - 6, "pair")])
    out += [
        _line(ART_X, cy + 22, first, cy + 22, "fl-gene"),
        _line(second + w, cy + 22, ART_X + 180, cy + 22, "fl-gene"),
        f'<circle class="fl-aug" cx="{second + w - 2:.1f}" cy="{cy + 5:.1f}" r="6.5" />',
        _line(second + w - 2, cy + 5, ART_X + 186, cy + 5, "fl-lead"),
        _text(ART_X + 192, cy + 9, "start codon, buried", "fl-note"),
        _text(first + w / 2, cy + 42, "secondary", "fl-note", "middle"),
        _text(second + w / 2, cy + 42, "main", "fl-note", "middle"),
    ]
    return out


def _levers(cy: float) -> list[str]:
    """The three parts a design may rewrite, and how little survives the screen."""
    x, w = ART_X + 24, 46
    out = [_stem(x, cy - 32, cy + 24, w)]
    out += _rungs(x, w, [(cy + 18, "lever"), (cy + 2, "lever"), (cy - 14, "lever")])
    for y, name in ((cy + 22, "bottom"), (cy + 6, "middle"), (cy - 10, "top")):
        out.append(_text(x + w + 8, y, name, "fl-note"))
    funnel = ART_X + 206
    for i, width in enumerate((174, 96, 42, 13)):
        out.append(
            f'<rect class="fl-funnel" x="{funnel:.1f}" y="{cy - 28 + i * 14:.1f}" '
            f'width="{width}" height="10" rx="2" />'
        )
    out.append(_text(funnel, cy + 42, "most are cut before folding", "fl-note"))
    return out


def _tubes(cy: float) -> list[str]:
    """The four tubes, with what each one should look like when it settles."""
    out = []
    for i, (label, opens) in enumerate((("00", False), ("10", False), ("01", False), ("11", True))):
        bx = ART_X + i * 104
        out.append(
            f'<rect class="fl-tube{" fl-tube--on" if opens else ""}" x="{bx}" '
            f'y="{cy - 40:.1f}" width="78" height="62" rx="6" />'
        )
        mid = bx + 39
        if opens:
            out.append(
                f'<path class="fl-open" d="M {mid - 22:.1f} {cy - 10:.1f} '
                f"C {mid - 10:.1f} {cy - 24:.1f} {mid + 10:.1f} {cy + 2:.1f} "
                f'{mid + 22:.1f} {cy - 12:.1f}" />'
            )
        else:
            out.append(_stem(mid - 10, cy - 26, cy - 2, 20, "fl-stem fl-stem--small"))
        out.append(_text(mid, cy + 14, label, "fl-state", "middle"))
    out.append(_text(ART_X, cy + 42, "left digit is the main trigger", "fl-note"))
    return out


_ART = {
    "windows": _windows,
    "pair": _pair,
    "choice": _choice,
    "switch": _switch,
    "levers": _levers,
    "tubes": _tubes,
}


def _extent(elements: list[str]) -> tuple[float, float, float, float]:
    """The box the drawn elements actually occupy: paths, circles and labels included."""
    xs: list[float] = []
    ys: list[float] = []
    for element in elements:
        for m in re.finditer(r'\sd="([^"]+)"', element):
            numbers = [float(t) for t in re.findall(r"-?\d+\.?\d*", m.group(1))]
            xs += numbers[0::2]
            ys += numbers[1::2]
        for m in re.finditer(r'\sx="(-?[\d.]+)"\s+y="(-?[\d.]+)"', element):
            px, py = float(m.group(1)), float(m.group(2))
            width = re.search(r'width="([\d.]+)"', element)
            if width:
                height = re.search(r'height="([\d.]+)"', element)
                xs += [px, px + float(width.group(1))]
                ys += [py, py + (float(height.group(1)) if height else 0.0)]
                continue
            # A label. Its width is nowhere in the markup, so estimate it: a label that
            # runs off the panel is exactly what this check exists to catch, and
            # counting text as a zero-width point lets every one of them through.
            body = re.search(r">([^<]*)<", element)
            span = len(re.sub(r"&[a-z]+;|&#\d+;", "x", body.group(1) if body else "")) * 6.2
            anchor = re.search(r'text-anchor="(\w+)"', element)
            shift = {"middle": span / 2, "end": span}.get(
                anchor.group(1) if anchor else "start", 0.0
            )
            xs += [px - shift, px - shift + span]
            ys += [py - 10, py + 4]
        for m in re.finditer(r'cx="(-?[\d.]+)" cy="(-?[\d.]+)" r="([\d.]+)"', element):
            cx, cy, r = (float(m.group(i)) for i in (1, 2, 3))
            xs += [cx - r, cx + r]
            ys += [cy - r, cy + r]
    return min(xs), max(xs), min(ys), max(ys)


def flow() -> tuple[str, list[str]]:
    top = 86
    out = [
        _text(MARGIN + 4, 30, "From two genes to a characterised design space", "fl-title"),
        _text(
            MARGIN + 4,
            52,
            "Six steps. Each drawing says what that step changes, not what the molecule measures.",
            "fl-caption",
        ),
    ]
    problems: list[str] = []
    for index, (number, title, line, count, kind) in enumerate(STEPS):
        y = top + index * (ROW_H + ROW_GAP)
        cy = y + ROW_H / 2
        out += [
            f'<rect class="fl-row" x="{MARGIN}" y="{y}" '
            f'width="{WIDTH - 2 * MARGIN}" height="{ROW_H}" rx="6" />',
            f'<circle class="fl-num" cx="{MARGIN + 36}" cy="{cy:.1f}" r="17" />',
            _text(MARGIN + 36, cy + 5, number, "fl-num-text", "middle"),
            _text(MARGIN + 70, cy - 14, title, "fl-step"),
            _text(MARGIN + 70, cy + 8, line, "fl-line"),
            _text(MARGIN + 70, cy + 30, count, "fl-count"),
        ]
        # The row's own text gets the same treatment as the drawing. It was left out
        # when this check was written, and it is the other half of the figure that can
        # run into something: the column is only as wide as the gap between the number
        # and the drawing panel.
        text_box = (MARGIN + 70, ART_X - 12)
        for label, size in ((title, 15), (line, 13), (count, 11)):
            span = len(re.sub(r"&[a-z]+;|&#\d+;", "x", label)) * size * 0.48
            if MARGIN + 70 + span > text_box[1]:
                problems.append(
                    f"step {number}: text runs to {MARGIN + 70 + span:.0f}, past the "
                    f"drawing panel at {text_box[1]} -- {label[:42]}..."
                )

        drawing = _ART[kind](cy)
        x0, x1, y0, y1 = _extent(drawing)
        if y0 < y + 4 or y1 > y + ROW_H - 4:
            problems.append(
                f"step {number}: y {y0:.0f}..{y1:.0f} against row {y + 4:.0f}..{y + ROW_H - 4:.0f}"
            )
        if x0 < ART_X - 2 or x1 > WIDTH - MARGIN - 4:
            problems.append(
                f"step {number}: x {x0:.0f}..{x1:.0f} against panel {ART_X}..{WIDTH - MARGIN - 4}"
            )
        out += drawing
    height = top + len(STEPS) * (ROW_H + ROW_GAP) + 4
    body = "\n    ".join(out)
    svg = (
        f'<svg viewBox="0 0 {WIDTH} {height}" role="img" aria-label="Six steps from two '
        f"genes to a characterised design space: scan each gene for windows, pair two "
        f"genes on "
        f"complementary windows, build the secondary hairpin, assemble the switch, vary and "
        f'cut, and fold all four trigger states.">\n    {body}\n</svg>'
    )
    return svg, problems


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Draw the method flow.")
    parser.add_argument("--out", default="methods-flow.svg", type=pathlib.Path)
    args = parser.parse_args(argv)
    svg, problems = flow()
    if problems:
        print("  REFUSING to write; a drawing escapes its row:")
        for problem in problems:
            print(f"    {problem}")
        return 1
    args.out.write_text(svg, encoding="utf-8")
    print(f"  {args.out.name}: {len(svg):,} characters, every drawing inside its row")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
