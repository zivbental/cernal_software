"""Figure 7.4 -- the equilibrium leak against the path barrier, per design.

Drawn from the rows themselves, never from the summary numbers: one mark per design,
306 of them, read out of ``docs/assets/barrier/best_*.csv``.

Two panels of the same 306 points, differing only in the y scale, because the finding
needs both.

**Left, y over its full range 0 to 1.** Every point is pinned against the ceiling. The
measure the feasible set rejects designs with has nothing left to say about them, and a
flat line of marks says that faster than a range does.

**Right, y zoomed to the 0.002 the data actually occupies.** There *is* an ordering in
there, and it correlates with the path barrier at +0.528. Showing only the left panel
would hide that; showing only the right would imply the ordering means something a bench
could see. The caption says which reading is safe.

The x axis is the path barrier, an upper bound from a heuristic path search, so the
figure is careful never to call a high value protection.

Run::

    uv run python tools/figure_kinetic.py --out kinetic-vs-equilibrium.svg
"""

from __future__ import annotations

import argparse
import csv
import math
import pathlib

WIDTH = 900
PLOT_Y = 76
PLOT_H = 250
PANEL_W = 384
LEFT_X = 60
RIGHT_X = 500

REPO = pathlib.Path(__file__).resolve().parent.parent
ROWS = REPO / "docs/assets/barrier"

X_MIN, X_MAX = 0.0, 27.0
X_TICKS = (0, 5, 10, 15, 20, 25)


def load() -> list[tuple[float, float]]:
    """Every design that carries both readings, as (path barrier, equilibrium leak)."""
    out: list[tuple[float, float]] = []
    for path in sorted(ROWS.glob("best_*.csv")):
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if row.get("b_10") in (None, "", "None"):
                    continue
                if row.get("leak") in (None, "", "None"):
                    continue
                out.append((float(row["b_10"]), float(row["leak"])))
    return out


def spearman(xs: list[float], ys: list[float]) -> float:
    def ranks(values: list[float]) -> list[float]:
        order = sorted(range(len(values)), key=lambda i: values[i])
        out = [0.0] * len(values)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
                j += 1
            shared = (i + j) / 2 + 1
            for k in range(i, j + 1):
                out[order[k]] = shared
            i = j + 1
        return out

    rx, ry = ranks(xs), ranks(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry, strict=True))
    dx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    dy = math.sqrt(sum((b - my) ** 2 for b in ry))
    return num / (dx * dy) if dx and dy else 0.0


def _text(x: float, y: float, body: str, cls: str, anchor: str = "start") -> str:
    extra = f' text-anchor="{anchor}"' if anchor != "start" else ""
    return f'<text class="{cls}" x="{x:.1f}" y="{y:.1f}"{extra}>{body}</text>'


def panel(
    origin: float,
    points: list[tuple[float, float]],
    low: float,
    high: float,
    title: str,
    note: str,
    y_labels: tuple[str, ...],
) -> list[str]:
    out = [
        _text(origin, PLOT_Y - 30, title, "kx-panel"),
        _text(origin, PLOT_Y - 13, note, "kx-note"),
        f'<rect class="kx-frame" x="{origin}" y="{PLOT_Y}" '
        f'width="{PANEL_W}" height="{PLOT_H}" rx="3" />',
    ]
    for index, label in enumerate(y_labels):
        fraction = index / (len(y_labels) - 1)
        y = PLOT_Y + PLOT_H - fraction * PLOT_H
        out.append(f'<path class="kx-grid" d="M {origin} {y:.1f} L {origin + PANEL_W} {y:.1f}" />')
        out.append(_text(origin - 7, y + 4, label, "kx-tick", "end"))
    for tick in X_TICKS:
        x = origin + (tick - X_MIN) / (X_MAX - X_MIN) * PANEL_W
        out.append(_text(x, PLOT_Y + PLOT_H + 16, str(tick), "kx-tick", "middle"))

    for barrier, leak in points:
        x = origin + (barrier - X_MIN) / (X_MAX - X_MIN) * PANEL_W
        clipped = min(max(leak, low), high)
        y = PLOT_Y + PLOT_H - (clipped - low) / (high - low) * PLOT_H
        out.append(f'<circle class="kx-dot" cx="{x:.1f}" cy="{y:.1f}" r="3" />')
    return out


def figure() -> str:
    points = load()
    if not points:
        raise SystemExit(f"  no rows with both readings under {ROWS}")
    barriers = [b for b, _leak in points]
    leaks = [leak for _b, leak in points]
    rho = spearman(barriers, leaks)

    out = [
        _text(10, 26, "Preferred-stem occupancy is concentrated near 1.0", "kx-title"),
        _text(
            10,
            46,
            f"{len(points)} preferred-stem designs, one mark each. Both panels show the "
            f"same points; only the vertical scale differs.",
            "kx-caption",
        ),
    ]
    out += panel(
        LEFT_X,
        points,
        0.0,
        1.0,
        "on the scale the measure is defined on",
        "equilibrium occupancy, 0 to 1",
        ("0", "0.25", "0.5", "0.75", "1.0"),
    )
    out += panel(
        RIGHT_X,
        points,
        0.998,
        1.0,
        "on the 0.002 the data occupies",
        f"the ordering is real, and correlates at &rho;&nbsp;+{rho:.3f}",
        ("0.998", "0.9985", "0.999", "0.9995", "1.000"),
    )

    axis_y = PLOT_Y + PLOT_H + 36
    out.append(
        _text(
            LEFT_X + PANEL_W / 2,
            axis_y,
            "path barrier (kcal/mol) &mdash; an upper bound, so a high value is not protection",
            "kx-axis",
            "middle",
        )
    )
    out.append(
        _text(
            RIGHT_X + PANEL_W / 2,
            axis_y,
            "path barrier (kcal/mol)",
            "kx-axis",
            "middle",
        )
    )
    out.append(
        _text(
            10,
            axis_y + 22,
            f"barrier {min(barriers):.1f} to {max(barriers):.1f} kcal/mol, a span of "
            f"{max(barriers) - min(barriers):.1f}. Occupancy {min(leaks):.4f} to "
            f"{max(leaks):.4f}, a span of {max(leaks) - min(leaks):.4f}.",
            "kx-foot",
        )
    )

    height = axis_y + 36
    body = "\n    ".join(out)
    return (
        f'<svg viewBox="0 0 {WIDTH} {height:.0f}" role="img" aria-label="Scatter plots '
        f"of {len(points)} preferred-stem designs, showing heuristic path-energy "
        f"estimate against state-10 equilibrium occupancy. The left panel uses the "
        f"complete zero-to-one occupancy scale; the right magnifies the narrow "
        f'0.998-to-1.000 range.">'
        f"\n    {body}\n</svg>"
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Draw the two readings of state 10.")
    parser.add_argument("--out", default="kinetic-vs-equilibrium.svg", type=pathlib.Path)
    args = parser.parse_args(argv)
    svg = figure()
    args.out.write_text(svg, encoding="utf-8")
    print(f"  {args.out.name}: {len(svg):,} characters")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
