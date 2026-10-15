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
        out.append(_text(x, y + 32, "two genes, one shared run", "fl-note"))
        return "\n    ".join(out)
    if kind == "choice":
        out = []
        for i in range(6):
            cx = x + 18 + i * 30
            clash = i in (1, 3, 4)
            out.append(
                f'<rect class="fl-base{" fl-base--clash" if clash else ""}" '
                f'x="{cx}" y="{y - 26}" width="22" height="20" rx="2" />'
            )
            out.append(
                f'<rect class="fl-base{" fl-base--clash" if clash else ""}" '
                f'x="{cx}" y="{y - 2}" width="22" height="20" rx="2" />'
            )
            if clash:
                out.append(_text(cx + 11, y + 32, "?", "fl-mark", "middle"))
        out.append(_text(x, y + 48, "three disagree; each is a choice", "fl-note"))
        return "\n    ".join(out)
    if kind == "switch":
        out = [
            _hairpin(x + 10, y, 70, 46, True, "fl-stem"),
            _hairpin(x + 80, y, 70, 46, True, "fl-stem"),
            f'<path class="fl-gene" d="M {x} {y} L {x + 10} {y}" />',
            f'<path class="fl-gene" d="M {x + 150} {y} L {x + ART_W} {y}" />',
            f'<circle class="fl-aug" cx="{x + 115}" cy="{y - 20}" r="7" />',
            _text(x + 155, y - 24, "AUG", "fl-note"),
            _text(x, y + 20, "no gap between the two hairpins", "fl-note"),
        ]
        return "\n    ".join(out)
    if kind == "funnel":
        out = []
        for i, frac in enumerate((1.0, 0.62, 0.30, 0.09)):
            out.append(
                f'<rect class="fl-funnel" x="{x}" y="{y - 30 + i * 17}" '
                f'width="{ART_W * frac:.1f}" height="13" rx="2" />'
            )
        out.append(_text(x, y + 32, "most are cut before any folding", "fl-note"))
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
