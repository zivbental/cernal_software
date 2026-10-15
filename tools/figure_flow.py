"""The method as a flow, with a small drawing beside every step.

Run::

    uv run python tools/figure_flow.py --out methods-flow.svg

Six steps from two genes to a ranked design, each a row: a number, a title, one line of
plain text, and a **small drawing of what that step does to the molecule**. The drawing
is the point. A reader who meets "the inhibitory hairpin's ascending arm is built from
three-way choices" has to hold a structure in their head to follow it; a reader who sees
two short strands disagreeing at four positions does not.

**The drawings are schematic and say so.** They are not to scale and carry no sequence --
each is the smallest picture that distinguishes this step from the one above it. The real
geometry is in Figures 3.1 and 3.2, which this figure deliberately does not duplicate.

Layout rule carried over from the other figures: declared bands, nothing inside a drawing
longer than a symbol or two words, and a programmatic width check rather than judging
overflow in a browser.
"""

from __future__ import annotations

import argparse
import pathlib

WIDTH = 900
ROW_H = 96
ART_X = 560  # where each row's drawing starts
ART_W = 320

#: (section, title, one line, which drawing). The line is what a reader who stops here
#: should come away with, so it states the outcome and not the mechanism.
STEPS: tuple[tuple[str, str, str, str], ...] = (
    (
        "4.1",
        "Find candidate windows",
        "Scan each gene for stretches a trigger could be cut from.",
        "windows",
    ),
    (
        "4.2",
        "Pair them across two genes",
        "Keep pairs whose two windows share a run of sequence.",
        "pair",
    ),
    (
        "4.3",
        "Build the inhibitory hairpin",
        "At each disagreeing position, serve A, serve B, or hold the stem shut.",
        "choice",
    ),
    (
        "4.4",
        "Assemble the switch",
        "Two hairpins, nothing between them, the start codon buried in the second.",
        "switch",
    ),
    (
        "4.5",
        "Vary the design and cut the space",
        "Three levers per design; most candidates are rejected before folding.",
        "funnel",
    ),
    (
        "4.6",
        "Fold all four input states",
        "Only both-triggers should open. The other three are the test.",
        "tubes",
    ),
)


def _text(x, y, s, cls, anchor="start") -> str:
    extra = f' text-anchor="{anchor}"' if anchor != "start" else ""
    return f'<text class="{cls}" x="{x:.1f}" y="{y:.1f}"{extra}>{s}</text>'


def _hairpin(x: float, y: float, w: float, h: float, shut: bool, cls: str) -> str:
    """A tiny hairpin: a loop over two arms, or a flat line when it has opened."""
    if not shut:
        return f'<path class="{cls}" d="M {x:.1f} {y:.1f} L {x + w:.1f} {y:.1f}" />'
    half = w / 2
    return (
        f'<path class="{cls}" d="M {x:.1f} {y:.1f} L {x:.1f} {y - h + half:.1f} '
        f"A {half} {half} 0 1 1 {x + w:.1f} {y - h + half:.1f} "
        f'L {x + w:.1f} {y:.1f}" />'
    )


def art(kind: str, y: float) -> str:
    """One row's drawing, baseline at y."""
    x = ART_X
    if kind == "windows":
        out = [f'<path class="fl-gene" d="M {x} {y} L {x + ART_W} {y}" />']
        for at in (0.18, 0.46, 0.78):
            out.append(
                f'<rect class="fl-window" x="{x + ART_W * at:.1f}" y="{y - 7}" '
                f'width="34" height="14" rx="2" />'
            )
        out.append(_text(x, y + 20, "one gene, three candidate windows", "fl-note"))
        return "\n    ".join(out)
    if kind == "pair":
        out = []
        for row, at in ((y - 14, 0.20), (y + 10, 0.52)):
            out.append(f'<path class="fl-gene" d="M {x} {row} L {x + ART_W} {row}" />')
            out.append(
                f'<rect class="fl-window" x="{x + ART_W * at:.1f}" y="{row - 7}" '
                f'width="46" height="14" rx="2" />'
            )
        out.append(
            f'<path class="fl-share" d="M {x + ART_W * 0.20 + 23:.1f} {y - 7} '
            f'L {x + ART_W * 0.52 + 23:.1f} {y + 3}" />'
        )
        out.append(_text(x + 150, y - 2, "revcomp, &#8805; 4 nt", "fl-note"))
        out.append(_text(x, y + 32, "the two runs are each other's complement", "fl-note"))
        return "\n    ".join(out)
    if kind == "choice":
        # A STANDING stem, because that is what it is: two arms facing each other, not a
        # sequence read left to right. Some positions already pair -- the run copied from
        # trigger A's own complement, and others that happen to match -- and the figure
        # has to show that those are the majority before it shows the dilemma.
        left, right = x + 86, x + 150
        pattern = ("pair", "pair", "clash", "pair", "clash", "pair")
        out = [
            f'<path class="fl-stem" d="M {left} {y - 86} '
            f"A 32 32 0 1 1 {right} {y - 86} "
            f'M {left} {y - 86} L {left} {y + 6} M {right} {y - 86} L {right} {y + 6}" />'
        ]
        for i, kindp in enumerate(pattern):
            ry = y - 76 + i * 14
            if kindp == "pair":
                out.append(f'<path class="fl-rung" d="M {left} {ry} L {right} {ry}" />')
            else:
                out.append(
                    f'<path class="fl-rung fl-rung--clash" d="M {left} {ry} '
                    f'L {left + 16} {ry} M {right - 16} {ry} L {right} {ry}" />'
                )
                out.append(_text((left + right) / 2, ry + 4, "?", "fl-mark", "middle"))
        out.append(_text(x, y - 92, "the two arms, facing", "fl-note"))
        out.append(_text(x + 176, y - 62, "most positions pair:", "fl-note"))
        out.append(_text(x + 176, y - 48, "the run from trigger A,", "fl-note"))
        out.append(_text(x + 176, y - 34, "plus chance matches", "fl-note"))
        out.append(_text(x + 176, y - 10, "where they disagree,", "fl-note"))
        out.append(_text(x + 176, y + 4, "three ways: match A,", "fl-note"))
        out.append(_text(x + 176, y + 18, "match B, or stay shut", "fl-note"))
        out.append(_text(x + 176, y + 32, "&mdash; any two, never all", "fl-note"))
        return "\n    ".join(out)

    if kind == "switch":
        # The same shape as Figure 3.1's state 00, without its notations: two hairpins
        # standing side by side on one backbone with nothing between them, the start
        # codon inside the second. A reader who has seen 3.1 should recognise this.
        out = []
        for hx in (x + 30, x + 118):
            out.append(
                f'<path class="fl-stem" d="M {hx} {y} L {hx} {y - 52} '
                f"A 22 22 0 1 1 {hx + 44} {y - 52} "
                f'L {hx + 44} {y}" />'
            )
            for k in range(4):
                ry = y - 10 - k * 11
                out.append(f'<path class="fl-rung" d="M {hx} {ry} L {hx + 44} {ry}" />')
        out += [
            f'<path class="fl-gene" d="M {x} {y} L {x + 30} {y}" />',
            f'<path class="fl-gene" d="M {x + 162} {y} L {x + ART_W} {y}" />',
            f'<circle class="fl-aug" cx="{x + 140}" cy="{y - 32}" r="7" />',
            _text(x + 152, y - 56, "AUG", "fl-note"),
            _text(x + 230, y - 30, "the ribosome&#8217;s", "fl-note"),
            _text(x + 230, y - 16, "signals, buried", "fl-note"),
            _text(x, y + 20, "nothing between the two hairpins", "fl-note"),
        ]
        return "\n    ".join(out)

    if kind == "funnel":
        # The funnel alone says how much is cut and nothing about what varies, which is
        # the half a reader needs here. The switch beside it marks the three parts a
        # lever rewrites, so "three levers" is a place on the molecule and not a word.
        out = []
        for i, frac in enumerate((1.0, 0.58, 0.26, 0.07)):
            out.append(
                f'<rect class="fl-funnel" x="{x}" y="{y - 34 + i * 15}" '
                f'width="{150 * frac:.1f}" height="11" rx="2" />'
            )
        out.append(_text(x, y + 22, "most are cut before folding", "fl-note"))
        hx = x + 190
        out.append(
            f'<path class="fl-stem" d="M {hx} {y} L {hx} {y - 52} '
            f"A 22 22 0 1 1 {hx + 44} {y - 52} "
            f'L {hx + 44} {y}" />'
        )
        for k, lever in enumerate(("top", "bulge", "foot")):
            ry = y - 14 - k * 16
            out.append(f'<path class="fl-rung fl-rung--lever" d="M {hx} {ry} L {hx + 44} {ry}" />')
            out.append(_text(hx + 54, ry + 4, lever, "fl-note"))
        out.append(_text(x + 180, y + 22, "what a lever rewrites", "fl-note"))
        return "\n    ".join(out)

    # tubes
    out = []
    for i, (label, open_) in enumerate((("00", False), ("10", False), ("01", False), ("11", True))):
        cx = x + i * 78
        out.append(
            f'<rect class="fl-tube{" fl-tube--on" if open_ else ""}" x="{cx}" '
            f'y="{y - 30}" width="62" height="34" rx="4" />'
        )
        out.append(_text(cx + 31, y - 8, label, "fl-state", "middle"))
    out.append(_text(x, y + 20, "only 11 should translate", "fl-note"))
    return "\n    ".join(out)


def flow() -> str:
    top = 86
    out = [
        _text(8, 28, "The method, one step at a time", "fl-title"),
        _text(
            8,
            50,
            "Each row is a section below. The drawing is schematic: it says "
            "what the step changes, not what the molecule measures.",
            "fl-caption",
        ),
    ]
    for index, (section, title, line, kind) in enumerate(STEPS):
        y = top + index * ROW_H
        base = y + 54
        out.append(
            f'<rect class="fl-row" x="8" y="{y}" width="{WIDTH - 16}" '
            f'height="{ROW_H - 10}" rx="4" />'
        )
        out.append(f'<circle class="fl-num" cx="42" cy="{y + 36}" r="16" />')
        out.append(_text(42, y + 41, section, "fl-num-text", "middle"))
        out.append(_text(74, y + 30, title, "fl-step"))
        out.append(_text(74, y + 52, line, "fl-line"))
        out.append(art(kind, base))
        if index < len(STEPS) - 1:
            out.append(f'<path class="fl-arrow" d="M 42 {y + ROW_H - 10} L 42 {y + ROW_H}" />')
    base = top + len(STEPS) * ROW_H
    out.append(
        _text(
            8,
            base + 14,
            "What comes out is a ranked list of designs, each "
            "with the measurements behind its rank.",
            "fl-note",
        )
    )
    body = "\n    ".join(out)
    return (
        f'<svg viewBox="0 0 {WIDTH} {base + 34}" role="img" aria-label="Six steps from '
        f"two genes to a ranked design, each with a small schematic drawing of what that "
        f'step does.">\n    {body}\n</svg>'
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Draw the method flow.")
    parser.add_argument("--out", default="methods-flow.svg", type=pathlib.Path)
    args = parser.parse_args(argv)
    svg = flow()
    args.out.write_text(svg, encoding="utf-8")
    print(f"  {args.out.name}: {len(svg):,} characters")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
