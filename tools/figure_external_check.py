"""Figure 5.1 -- do our measures rank the measured libraries the way the bench did?

The answer is the decisive justification for how designs are scored, and it was sitting
in two tables. Two panels, both diverging from a zero line, because the job of this data
is **polarity**: a measure that ranks a real library the way a real bench did comes out
positive, and one that does not comes out negative.

**Panel A** is the check itself: three state-comparing measures against the measured
ON/OFF ratios of Green's two libraries. One is positive on both; two are negative on
both.

**Panel B** is why. Each failing measure is a difference between an ON term and an OFF
term, and splitting them apart shows the ON terms right-signed and strong while the OFF
terms are wrong-signed. The difference lands next to its OFF term, not between the two.
Drawing the three on one axis is the whole argument.

**Colour.** The diverging pair is violet for right-signed and red for wrong-signed,
checked with ``tools/validate_palette.py`` rather than by eye: green and red, the
obvious choice, separate by only 4.1 Delta E under deuteranopia, below the floor of 6.0.
Violet against the same red reaches 14.5. Every bar is directly labelled as well, so the
sign never rests on colour alone.

Run::

    uv run python tools/figure_external_check.py --out external-check.svg
"""

from __future__ import annotations

import argparse
import pathlib

WIDTH = 900
ZERO_X = 430
SCALE = 430.0  # pixels per unit of rho, so +0.70 lands 301 px right of zero
BAR_H = 17
ROW_GAP = 25
GROUP_GAP = 20

#: Signed Spearman against the measured ON/OFF ratio, our measures applied unchanged to
#: the published sequences. Copied from the tables in section 5.3 of the model page.
CHECK: tuple[tuple[str, str, float, float], ...] = (
    ("the A_M ratio", "ON over worst-OFF arm accessibility", +0.306, +0.698),
    ("the IED gain", "ensemble defect, OFF minus ON", -0.345, -0.495),
    ("the opening separation", "cost to open the window, OFF minus ON", -0.107, -0.033),
)

#: The two failing measures split back into the states they are built from, on G168.
SPLIT: tuple[tuple[str, tuple[tuple[str, float], ...]], ...] = (
    (
        "ensemble defect, binding loop to linker",
        (("ON term", +0.356), ("OFF term", -0.073), ("the difference", -0.345)),
    ),
    (
        "opening cost, ribosome window",
        (("ON term", +0.315), ("OFF term", -0.362), ("the difference", -0.107)),
    ),
)

TICKS = (-0.6, -0.4, -0.2, 0.0, 0.2, 0.4, 0.6, 0.8)


def _text(x: float, y: float, body: str, cls: str, anchor: str = "start") -> str:
    extra = f' text-anchor="{anchor}"' if anchor != "start" else ""
    return f'<text class="{cls}" x="{x:.1f}" y="{y:.1f}"{extra}>{body}</text>'


def _signed(value: float) -> str:
    """A rho with an explicit sign, using the page's minus rather than a hyphen."""
    return f"&minus;{abs(value):.3f}" if value < 0 else f"+{value:.3f}"


def _bar(value: float, y: float, strong: bool) -> list[str]:
    """One diverging bar from the zero line, with its value labelled at the free end."""
    width = abs(value) * SCALE
    x = ZERO_X if value >= 0 else ZERO_X - width
    tone = "pos" if value >= 0 else "neg"
    weight = "" if strong else " xc-bar--soft"
    label_x = (x + width + 8) if value >= 0 else (x - 8)
    anchor = "start" if value >= 0 else "end"
    return [
        f'<rect class="xc-bar xc-bar--{tone}{weight}" x="{x:.1f}" y="{y:.1f}" '
        f'width="{width:.1f}" height="{BAR_H}" rx="3" />',
        _text(label_x, y + BAR_H - 4, _signed(value), f"xc-value xc-value--{tone}", anchor),
    ]


def _axis(top: float, bottom: float) -> list[str]:
    out = []
    for tick in TICKS:
        x = ZERO_X + tick * SCALE
        is_zero = tick == 0.0
        out.append(
            f'<path class="xc-grid{" xc-grid--zero" if is_zero else ""}" '
            f'd="M {x:.1f} {top:.1f} L {x:.1f} {bottom:.1f}" />'
        )
        mark = "0" if is_zero else (f"&minus;{abs(tick):.1f}" if tick < 0 else f"+{tick:.1f}")
        out.append(_text(x, bottom + 16, mark, "xc-tick", "middle"))
    return out


def panel_a(top: float) -> tuple[list[str], float]:
    """The check: three measures, two libraries each."""
    out = [
        _text(
            10, top, "Does the measure rank the measured library the way the bench did?", "xc-head"
        ),
        _text(
            10,
            top + 18,
            "Signed Spearman against measured ON/OFF. G168 is Green&#8217;s 168 measured "
            "switches, G13 his 13 forward-engineered ones.",
            "xc-sub",
        ),
    ]
    y = top + 40
    rows_top = y
    for name, window, g168, g13 in CHECK:
        out.append(_text(10, y + BAR_H - 4, name, "xc-measure"))
        out.append(_text(10, y + BAR_H + 13, window, "xc-window"))
        # The library is named on its own bar, so which series a bar belongs to never
        # rests on its fill weight alone.
        for label, value, strong in (("G168", g168, True), ("G13", g13, False)):
            side = ZERO_X - 6 if value >= 0 else ZERO_X + 6
            anchor = "end" if value >= 0 else "start"
            out.append(_text(side, y + BAR_H - 4, label, "xc-series", anchor))
            out += _bar(value, y, strong=strong)
            y += BAR_H + 4
        y += ROW_GAP - 4
    out += _axis(rows_top - 8, y - ROW_GAP + 6)
    return out, y - ROW_GAP + 30


def panel_b(top: float) -> tuple[list[str], float]:
    """Why: each failing difference beside the two terms it is built from."""
    out = [
        _text(10, top, "Where the wrong sign comes from", "xc-head"),
        _text(
            10,
            top + 18,
            "The same two measures split into the states they are built from, on G168. "
            "The difference lands beside its OFF term rather than between the two.",
            "xc-sub",
        ),
    ]
    y = top + 40
    rows_top = y
    for name, terms in SPLIT:
        out.append(_text(10, y + BAR_H - 4, name, "xc-measure"))
        y += BAR_H + 2
        for label, value in terms:
            out.append(_text(28, y + BAR_H - 4, label, "xc-term"))
            out += _bar(value, y, strong=label == "the difference")
            y += BAR_H + 4
        y += GROUP_GAP
    out += _axis(rows_top - 8, y - GROUP_GAP + 2)
    return out, y - GROUP_GAP + 26


def legend(y: float) -> list[str]:
    """Identity never rests on colour: the swatches are labelled and so is every bar."""
    out = []
    for index, (tone, label) in enumerate(
        (("pos", "ranks it the way the bench did"), ("neg", "ranks it the wrong way"))
    ):
        x = 10 + index * 300
        out.append(
            f'<rect class="xc-bar xc-bar--{tone}" x="{x}" y="{y - 9}" '
            f'width="20" height="11" rx="2" />'
        )
        out.append(_text(x + 27, y, label, "xc-legend"))
    out.append(
        _text(
            10 + 2 * 300,
            y,
            "each bar names its library",
            "xc-legend",
        )
    )
    return out


def figure() -> str:
    body: list[str] = []
    elements, next_top = panel_a(30)
    body += elements
    body += legend(next_top + 4)
    elements, bottom = panel_b(next_top + 34)
    body += elements
    height = bottom + 8
    joined = "\n    ".join(body)
    return (
        f'<svg viewBox="0 0 {WIDTH} {height:.0f}" role="img" aria-label="Two panels of '
        f"diverging bars. Above, three of our measures correlated against the measured "
        f"ON/OFF ratios of two published switch libraries: the A_M ratio is positive on "
        f"both, the ensemble-defect gain and the opening separation are negative on "
        f"both. Below, the two negative measures split into their ON and OFF terms, "
        f'showing the ON terms positive and the OFF terms negative.">'
        f"\n    {joined}\n</svg>"
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Draw the external-check figure.")
    parser.add_argument("--out", default="external-check.svg", type=pathlib.Path)
    args = parser.parse_args(argv)
    svg = figure()
    args.out.write_text(svg, encoding="utf-8")
    print(f"  {args.out.name}: {len(svg):,} characters")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
