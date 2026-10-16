"""Figure 7.1 -- what the pair settles, and what the design settles.

Eight quantities, each split into the share of its raw variance that lies *between*
trigger pairs and the share that lies *within* one pair across its designs. The job of
this data is part-to-whole, so each row is a 100% stacked bar; the rows are sorted by
the between-pairs share, because the finding is the gap that opens between the top two
and the rest.

That gap is the whole point and it is why the rows are sorted rather than left in table
order: whether a gate can open is two-thirds a property of the two transcripts, while
whether it leaks is nine-tenths a property of the design. Those are different jobs on
different axes, and the shape says so faster than the numbers do.

**Colour.** Gold for the share the trigger pair settles, violet for the share the design
settles, checked with ``tools/validate_palette.py``: the pair separates by 25.2 Delta E
under protanopia, the widest of the combinations tried, and both clear the chroma floor
that teal, blue and kraft all miss. Every segment is also labelled with its percentage,
so nothing rests on hue.

Run::

    uv run python tools/figure_variance.py --out variance-split.svg
"""

from __future__ import annotations

import argparse
import pathlib

WIDTH = 900
LABEL_X = 10
BAR_X = 392
BAR_W = 430
BAR_H = 20
ROW_GAP = 11
GAP = 2.0  # the surface gap between the two segments

#: Variance split, from the table in section 7.2. Both geometries pooled. The leak rows
#: are over all 301,440 designs, before the ON-state ceiling decides, so there is no
#: survivorship conditioning in them.
ROWS: tuple[tuple[str, int, float], ...] = (
    ("ON-state opening cost, main stem", 301_440, 67.1),
    ("ON-state opening cost, ribosome window", 219_808, 63.5),
    ("contrast, ensemble defect", 219_808, 14.4),
    ("contrast, ribosome-window opening", 219_808, 12.2),
    ("contrast, main-stem opening", 219_808, 11.5),
    ("state-10 leak, main stem's ascending arm", 301_440, 10.1),
    ("state-10 leak, trigger A on x*", 301_440, 7.3),
    ("contrast, main-stem openness ratio", 219_808, 2.1),
)

#: The two ON-state rows sit far above the rest; the rule is drawn in that gap.
SPLIT_AFTER = 2


def _text(x: float, y: float, body: str, cls: str, anchor: str = "start") -> str:
    extra = f' text-anchor="{anchor}"' if anchor != "start" else ""
    return f'<text class="{cls}" x="{x:.1f}" y="{y:.1f}"{extra}>{body}</text>'


def _row(name: str, n: int, between: float, y: float) -> list[str]:
    within = 100.0 - between
    left = BAR_W * between / 100.0
    out = [
        _text(LABEL_X, y + 14, name, "vs-name"),
        _text(BAR_X - 10, y + 14, f"n = {n:,}", "vs-n", "end"),
        f'<rect class="vs-seg vs-seg--pair" x="{BAR_X:.1f}" y="{y:.1f}" '
        f'width="{max(left - GAP / 2, 0):.1f}" height="{BAR_H}" rx="2" />',
        f'<rect class="vs-seg vs-seg--design" x="{BAR_X + left + GAP / 2:.1f}" y="{y:.1f}" '
        f'width="{max(BAR_W - left - GAP / 2, 0):.1f}" height="{BAR_H}" rx="2" />',
    ]
    # Each percentage sits inside its own segment where it fits, outside where it does
    # not, so a 2.1% sliver still carries its number.
    if left > 46:
        out.append(_text(BAR_X + 7, y + 14, f"{between:.1f}%", "vs-pct vs-pct--in"))
    else:
        out.append(_text(BAR_X + left + 6, y + 14, f"{between:.1f}%", "vs-pct vs-pct--pair"))
    if BAR_W - left > 46:
        anchor_x = BAR_X + BAR_W - 7
        out.append(_text(anchor_x, y + 14, f"{within:.1f}%", "vs-pct vs-pct--in", "end"))
    return out


def figure() -> str:
    out = [
        _text(
            LABEL_X,
            26,
            "Where the variation lies: input pair or sequence design",
            "vs-title",
        ),
        _text(
            LABEL_X,
            46,
            "Each bar divides the variance in one calculated quantity into "
            "between-pair and within-pair shares.",
            "vs-caption",
        ),
    ]
    y = 74
    for index, (name, n, between) in enumerate(ROWS):
        if index == SPLIT_AFTER:
            rule = y + 1
            out.append(
                f'<path class="vs-rule" d="M {LABEL_X} {rule:.1f} L {BAR_X + BAR_W} {rule:.1f}" />'
            )
            out.append(
                _text(
                    LABEL_X,
                    rule + 16,
                    "Below: most variance occurs among designs of the same pair",
                    "vs-divider",
                )
            )
            y += 26
        out += _row(name, n, between, y)
        y += BAR_H + ROW_GAP

    legend_y = y + 10
    for index, (tone, label) in enumerate(
        (
            ("pair", "between sampled trigger-window pairs"),
            ("design", "within a pair, across sequence variants"),
        )
    ):
        x = LABEL_X + index * 430
        out.append(
            f'<rect class="vs-seg vs-seg--{tone}" x="{x}" y="{legend_y - 10}" '
            f'width="20" height="12" rx="2" />'
        )
        out.append(_text(x + 27, legend_y, label, "vs-legend"))

    height = legend_y + 16
    body = "\n    ".join(out)
    return (
        f'<svg viewBox="0 0 {WIDTH} {height:.0f}" role="img" aria-label="Eight '
        f"100-percent stacked bars showing the variance share between sampled trigger "
        f"pairs versus within each pair across sequence designs. Two ON-state opening "
        f"costs show 63.5 to 67.1 percent between-pair variance, while other modeled "
        f'quantities show 2.1 to 14.4 percent between-pair variance.">\n    {body}\n</svg>'
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Draw the variance split.")
    parser.add_argument("--out", default="variance-split.svg", type=pathlib.Path)
    args = parser.parse_args(argv)
    svg = figure()
    args.out.write_text(svg, encoding="utf-8")
    print(f"  {args.out.name}: {len(svg):,} characters")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
