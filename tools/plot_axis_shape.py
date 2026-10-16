"""One dot per design: the raw shape of an axis against an objective, with nothing binned.

    uv run python tools/plot_axis_shape.py --out axes_c8 --x a_site_energy --y sep_open
    uv run python tools/plot_axis_shape.py --out axes_c8 --x lock_energy --y xstar_engA_10

**Why this exists.** A quintile table already answers "is the relationship monotone", but it
answers it at the resolution the bins impose: five numbers cannot show whether the effect turns on
gradually across the last fifth or snaps at one value inside it, and a reader has to take the
binning on trust. A scatter of every design shows the shape itself and lets the bins be checked
against it rather than believed.

**The one transformation, and why it cannot be avoided.** The y axis is the objective's z-score
*within its own cell*, not its raw value. Cells differ enormously in difficulty -- some trigger
pairs have no working design at all -- so a raw objective plotted across cells draws the spread
between trigger pairs, which is far larger than any design effect and would bury it. The z-score
asks "how far from this design's own cell's average, in that cell's own spread", which is
comparable across cells. The x axis is left RAW, because the axis is a physical energy and its
scale is the thing being looked at.

**Sampling.** Hundreds of thousands of dots neither fit in an SVG nor read as anything but a
block of ink. A seeded sample is drawn instead, and the seed is an argument so the same command
returns the same picture. The binned median is computed on ALL points, not on the sample, so the
line is not a summary of the dots you happen to see.
"""

from __future__ import annotations

import argparse
import math
import random
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

# ruff: noqa: E402 - the sibling tool must be importable from this directory.
from analyse_axes import cells_of, derive, read_rows, zscores

#: Light and dark are both selected rather than one being an automatic flip of the other, and the
#: ink stays in text colours while the dots carry the series colour -- the same rule the page uses.
STYLE = """
  :root {
    --surface: #fcfcfb; --ink: #0b0b0b; --ink-2: #52514e; --ink-3: #77756e;
    --rule: #dcdad4; --dot: #2a78d6; --line: #eb6834;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --surface: #1a1a19; --ink: #f0efec; --ink-2: #c3c2b7; --ink-3: #9b9a90;
      --rule: #3a3a37; --dot: #3987e5; --line: #d95926;
    }
  }
  .bg { fill: var(--surface); }
  .ax { stroke: var(--rule); stroke-width: 1; }
  .gr { stroke: var(--rule); stroke-width: 1; stroke-dasharray: 3 3; }
  .tk { fill: var(--ink-3); font: 11px ui-sans-serif, system-ui, sans-serif; }
  .lb { fill: var(--ink-2); font: 12px ui-sans-serif, system-ui, sans-serif; }
  .ti { fill: var(--ink); font: 13px ui-sans-serif, system-ui, sans-serif; }
  .dot { fill: var(--dot); }
  .med { stroke: var(--line); stroke-width: 2; fill: none; }
"""

W, H = 760, 460
PAD_L, PAD_R, PAD_T, PAD_B = 80, 30, 68, 70


def nice_ticks(lo: float, hi: float, count: int = 5) -> list[float]:
    """Round tick values spanning [lo, hi], so the axis reads in human numbers."""
    if hi <= lo:
        return [lo]
    raw = (hi - lo) / max(1, count)
    mag = 10 ** math.floor(math.log10(raw))
    step = min((m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw), default=raw)
    first = math.ceil(lo / step) * step
    out, value = [], first
    while value <= hi + 1e-9:
        out.append(round(value, 10))
        value += step
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="axes_c8", help="which run to read")
    parser.add_argument("--shards", type=int, default=6)
    parser.add_argument("--x", default="a_site_energy", help="the axis, plotted raw")
    parser.add_argument("--y", default="sep_open", help="the objective, as a within-cell z-score")
    parser.add_argument("--points", type=int, default=6000, help="how many dots to draw")
    parser.add_argument("--bins", type=int, default=24, help="bins for the median line")
    parser.add_argument("--seed", type=int, default=20261014, help="so the picture is repeatable")
    parser.add_argument(
        "--into", default="", help="directory for the SVG; default is beside the run"
    )
    args = parser.parse_args(argv)

    rows = read_rows(args.out, args.shards)
    if not rows:
        print(f"  no rows found for {args.out!r}")
        return 1
    derive(rows)

    points: list[tuple[float, float]] = []
    for group in cells_of(rows).values():
        z = zscores(group, args.y)
        for row in group:
            x = row.get(args.x)
            if id(row) in z and isinstance(x, float):
                points.append((x, z[id(row)]))
    if len(points) < 50:
        print(f"  only {len(points)} designs have both {args.x} and {args.y} -- nothing to draw")
        return 1

    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    # Clip the y axis to the bulk so a handful of outliers do not flatten everything else.
    lo_y, hi_y = st.quantiles(ys, n=100)[0], st.quantiles(ys, n=100)[-1]
    lo_x, hi_x = min(xs), max(xs)
    span_x = hi_x - lo_x or 1.0
    span_y = (hi_y - lo_y) or 1.0

    def px(x: float) -> float:
        return PAD_L + (x - lo_x) / span_x * (W - PAD_L - PAD_R)

    def py(y: float) -> float:
        return PAD_T + (hi_y - y) / span_y * (H - PAD_T - PAD_B)

    # The median line is computed on EVERY point, not on the sample that gets drawn.
    edges = [lo_x + i * span_x / args.bins for i in range(args.bins + 1)]
    buckets: list[list[float]] = [[] for _ in range(args.bins)]
    for x, y in points:
        buckets[min(int((x - lo_x) / span_x * args.bins), args.bins - 1)].append(y)
    median_path = [
        (px((edges[i] + edges[i + 1]) / 2), py(st.median(b)))
        for i, b in enumerate(buckets)
        if len(b) >= 20
    ]

    rng = random.Random(args.seed)
    drawn = points if len(points) <= args.points else rng.sample(points, args.points)
    # Small, translucent dots: with thousands of marks the ink density IS the information.
    radius = 1.7 if len(drawn) > 3000 else 2.4
    opacity = 0.16 if len(drawn) > 3000 else 0.3

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" '
        f'height="{H}" role="img" aria-label="{args.y} against {args.x}, one dot per design">',
        f"<style>{STYLE}</style>",
        f'<rect class="bg" x="0" y="0" width="{W}" height="{H}"/>',
        f'<text class="ti" x="{PAD_L}" y="22">{args.y} against {args.x}</text>',
        f'<text class="tk" x="{PAD_L}" y="38">{len(points):,} designs, {len(drawn):,} drawn. '
        f"y is the within-cell z-score, always oriented so LOWER IS BETTER.</text>",
        f'<text class="tk" x="{PAD_L}" y="52">The orange line is the median of ALL designs per '
        f"bin. Each stem gives one x value to all its designs, hence the columns.</text>",
    ]
    zero = py(0.0)
    if PAD_T <= zero <= H - PAD_B:
        parts.append(
            f'<line class="gr" x1="{PAD_L}" y1="{zero:.1f}" x2="{W - PAD_R}" y2="{zero:.1f}"/>'
        )
    for value in nice_ticks(lo_y, hi_y):
        y = py(value)
        if not (PAD_T - 1 <= y <= H - PAD_B + 1):
            continue
        parts.append(
            f'<text class="tk" x="{PAD_L - 8}" y="{y + 4:.1f}" text-anchor="end">{value:g}</text>'
        )
    for value in nice_ticks(lo_x, hi_x):
        x = px(value)
        if not (PAD_L - 1 <= x <= W - PAD_R + 1):
            continue
        tick_y = H - PAD_B + 18
        parts.append(
            f'<text class="tk" x="{x:.1f}" y="{tick_y}" text-anchor="middle">{value:g}</text>'
        )
    parts.append(
        f'<line class="ax" x1="{PAD_L}" y1="{H - PAD_B}" x2="{W - PAD_R}" y2="{H - PAD_B}"/>'
    )
    parts.append(f'<line class="ax" x1="{PAD_L}" y1="{PAD_T}" x2="{PAD_L}" y2="{H - PAD_B}"/>')
    parts.append(
        f'<text class="lb" x="{(PAD_L + W - PAD_R) / 2:.0f}" y="{H - 18}" '
        f'text-anchor="middle">{args.x} (kcal/mol, raw)</text>'
    )
    parts.append(
        f'<text class="lb" x="22" y="{(PAD_T + H - PAD_B) / 2:.0f}" text-anchor="middle" '
        f'transform="rotate(-90 22 {(PAD_T + H - PAD_B) / 2:.0f})">within-cell z of {args.y}</text>'
    )
    parts.append(f'<g class="dot" opacity="{opacity}">')
    for x, y in drawn:
        cy = py(y)
        if PAD_T - 20 <= cy <= H - PAD_B + 20:
            parts.append(f'<circle cx="{px(x):.1f}" cy="{cy:.1f}" r="{radius}"/>')
    parts.append("</g>")
    if len(median_path) > 1:
        pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in median_path)
        parts.append(f'<polyline class="med" points="{pts}"/>')
    parts.append("</svg>")

    into = Path(args.into) if args.into else ROOT / "docs/assets" / args.out
    into.mkdir(parents=True, exist_ok=True)
    path = into / f"shape_{args.x}_{args.y}.svg"
    path.write_text("\n".join(parts), encoding="utf-8")
    print(f"  {len(points):,} designs plotted ({len(drawn):,} dots drawn)")
    print(f"  wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
