"""Figure 7.3 -- the start-codon closure improves the leak and costs the ON state.

Two panels, because a closure cannot be judged from one of them.

**Left**, each closed bulge against the open control, paired inside cells, as cells won
to the right and cells lost to the left. Three measures of the leak run almost entirely
to the right; the ON state runs entirely to the left, 0 wins in every comparison. The
two directions on one axis are the trade.

**Right**, the share of each level's designs that clear the ON-state ceiling at all.
This is the part a ranking over survivors cannot see: the tighter the closure, the
smaller the population its ranking was computed on, from 82.9% down to 40.7%.

Reading only the left panel says the closed bulges are better. Reading only the right
says they are worse. Both are drawn because a design decision needs both, which is the
section's point and the reason the ON-state ceiling is reported rather than applied
quietly.

Run::

    uv run python tools/figure_closure.py --out closure-tradeoff.svg
"""

from __future__ import annotations

import argparse
import pathlib

WIDTH = 900
LEFT_X = 150
LEFT_W = 400
ZERO = LEFT_X + LEFT_W * 0.22  # lost side is narrower; nothing loses by much
RIGHT_X = 648
RIGHT_W = 232
BAR_H = 15
ROW_GAP = 5
GROUP_GAP = 20

#: Cells won and lost against the open 3x3 control, paired inside cells, from the table
#: in section 7.4. The ON-state row is the one that runs the other way.
CLOSURES: tuple[tuple[str, float, tuple[tuple[str, int, int], ...]], ...] = (
    (
        "closed UAU",
        55.4,
        (
            ("leak: A on x*", 294, 2),
            ("leak: A on the arm", 296, 0),
            ("separation", 281, 7),
            ("ON state", 0, 296),
        ),
    ),
    (
        "closed CGU",
        53.7,
        (
            ("leak: A on x*", 278, 2),
            ("leak: A on the arm", 278, 2),
            ("separation", 265, 9),
            ("ON state", 0, 280),
        ),
    ),
    (
        "closed CAU",
        40.7,
        (
            ("leak: A on x*", 252, 0),
            ("leak: A on the arm", 252, 0),
            ("separation", 244, 6),
            ("ON state", 0, 252),
        ),
    ),
)

OPEN_SURVIVAL = 82.9


def _text(x: float, y: float, body: str, cls: str, anchor: str = "start") -> str:
    extra = f' text-anchor="{anchor}"' if anchor != "start" else ""
    return f'<text class="{cls}" x="{x:.1f}" y="{y:.1f}"{extra}>{body}</text>'


def _share(won: int, lost: int) -> float:
    total = won + lost
    return won / total if total else 0.0


def left_panel(top: float) -> tuple[list[str], float, dict[str, float]]:
    """Cells won to the right of the line, cells lost to the left."""
    out = [
        _text(10, top, "Each closed bulge against the open loop, paired inside cells", "cl-panel"),
        _text(10, top + 16, "Bar length is the share of cells that went each way.", "cl-note"),
    ]
    y = top + 34
    survival_at: dict[str, float] = {}
    for name, survival, rows in CLOSURES:
        survival_at[name] = y
        out.append(_text(10, y + 11, name, "cl-closure"))
        out.append(_text(10, y + 26, f"survival {survival:.1f}%", "cl-sub"))
        for label, won, lost in rows:
            share = _share(won, lost)
            right = (LEFT_X + LEFT_W - ZERO) * share
            left = (ZERO - LEFT_X) * (1 - share)
            out.append(_text(LEFT_X - 8, y + 11, label, "cl-measure", "end"))
            if left > 0.5:
                out.append(
                    f'<rect class="cl-bar cl-bar--lost" x="{ZERO - left:.1f}" y="{y:.1f}" '
                    f'width="{left:.1f}" height="{BAR_H}" rx="2" />'
                )
            if right > 0.5:
                out.append(
                    f'<rect class="cl-bar cl-bar--won" x="{ZERO:.1f}" y="{y:.1f}" '
                    f'width="{right:.1f}" height="{BAR_H}" rx="2" />'
                )
            out.append(
                _text(
                    LEFT_X + LEFT_W + 8,
                    y + 11,
                    f"{won} won &middot; {lost} lost",
                    "cl-count",
                )
            )
            y += BAR_H + ROW_GAP
        y += GROUP_GAP
    bottom = y - GROUP_GAP
    out.insert(
        2,
        f'<path class="cl-zero" d="M {ZERO:.1f} {top + 28:.1f} L {ZERO:.1f} {bottom + 2:.1f}" />',
    )
    out.append(_text(ZERO - 6, bottom + 18, "lost", "cl-axis", "end"))
    out.append(_text(ZERO + 6, bottom + 18, "won", "cl-axis"))
    return out, bottom + 24, survival_at


def right_panel(top: float, bottom: float) -> list[str]:
    """How much of each level survives the ON-state ceiling in the first place."""
    out = [
        _text(RIGHT_X, top, "Share clearing the ON-state ceiling", "cl-panel"),
        _text(RIGHT_X, top + 16, "The population each ranking is computed on.", "cl-note"),
    ]
    levels = [("open 3&times;3 loop", OPEN_SURVIVAL)] + [
        (name, survival) for name, survival, _rows in CLOSURES
    ]
    y = top + 38
    for name, survival in levels:
        width = RIGHT_W * survival / 100.0
        tone = "open" if survival == OPEN_SURVIVAL else "closed"
        out.append(_text(RIGHT_X, y - 4, name, "cl-level"))
        out.append(
            f'<rect class="cl-track" x="{RIGHT_X}" y="{y:.1f}" '
            f'width="{RIGHT_W}" height="{BAR_H + 3}" rx="2" />'
        )
        out.append(
            f'<rect class="cl-bar cl-bar--{tone}" x="{RIGHT_X}" y="{y:.1f}" '
            f'width="{width:.1f}" height="{BAR_H + 3}" rx="2" />'
        )
        out.append(_text(RIGHT_X + width + 7, y + 13, f"{survival:.1f}%", "cl-pct"))
        y += BAR_H + 30
    out.append(
        _text(
            RIGHT_X,
            min(y + 4, bottom + 18),
            "the tighter the closure, the fewer designs its",
            "cl-axis",
        )
    )
    out.append(_text(RIGHT_X, min(y + 18, bottom + 32), "ranking had to choose from", "cl-axis"))
    return out


def figure() -> str:
    out = [
        _text(10, 26, "Closing the bulge buys the leak and spends the ON state", "cl-title"),
        _text(
            10,
            46,
            "Three closed bulges against the open 3&times;3 loop. Left: which way each "
            "cell went. Right: how many designs were there to compare in the first place.",
            "cl-caption",
        ),
    ]
    body, bottom, _at = left_panel(80)
    out += body
    out += right_panel(80, bottom)

    legend_y = bottom + 42
    for index, (tone, label) in enumerate(
        (("won", "the closed bulge wins the cell"), ("lost", "the open loop wins it"))
    ):
        x = 10 + index * 270
        out.append(
            f'<rect class="cl-bar cl-bar--{tone}" x="{x}" y="{legend_y - 10}" '
            f'width="20" height="12" rx="2" />'
        )
        out.append(_text(x + 27, legend_y, label, "cl-legend"))

    height = legend_y + 18
    joined = "\n    ".join(out)
    return (
        f'<svg viewBox="0 0 {WIDTH} {height:.0f}" role="img" aria-label="Left, three '
        f"closed start-codon bulges compared cell by cell against the open loop: three "
        f"leak measures win almost every cell while the ON state loses every one. "
        f"Right, the share of each level's designs that clear the ON-state ceiling, "
        f'falling from 82.9 percent for the open loop to 40.7 for the tightest.">'
        f"\n    {joined}\n</svg>"
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Draw the closure trade-off.")
    parser.add_argument("--out", default="closure-tradeoff.svg", type=pathlib.Path)
    args = parser.parse_args(argv)
    svg = figure()
    args.out.write_text(svg, encoding="utf-8")
    print(f"  {args.out.name}: {len(svg):,} characters")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
