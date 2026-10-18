"""The Results figures for the iGEM model page, as inline SVG.

Run::

    uv run python tools/figure_results.py --out-dir <somewhere>

``results-survival.svg``   (7.2) per-pair survival, the U distribution
``results-terms.svg``      (7.3) the stem energy against each measured term, ON and OFF apart

Same two rules as the Methods figures: declared bands rather than judging by eye, and
nothing inside a drawing longer than a symbol or two words, because SVG text does not
wrap. Every number is read off ``docs/assets/axes_c8/`` and is quoted in the page beside
the figure, so the two cannot drift.
"""

from __future__ import annotations

import argparse
import pathlib

WIDTH = 900

#: Per-pair survival, from `probes.txt`: how many of 210 trigger pairs have that share of
#: their designs opening. The point of the figure is the SHAPE -- a smooth spread would
#: mean the levers decide how far a pair gets, and a U means the pair was already decided.
SURVIVAL: tuple[tuple[str, int], ...] = (
    ("0-10", 22),
    ("10-20", 3),
    ("20-30", 11),
    ("30-40", 5),
    ("40-50", 5),
    ("50-60", 7),
    ("60-70", 13),
    ("70-80", 19),
    ("80-90", 27),
    ("90-100", 98),
)
PAIRS = 210

#: Within-cell Spearman against the trigger-A grip on the inhibitory arm, from
#: `correlation.csv`. Grouped because the grouping is the finding: the leak terms and the
#: worst-OFF terms move with the grip, and the ON-state terms do not move at all.
TERMS: tuple[tuple[str, str, float], ...] = (
    ("leak", "trigger A on x*", -0.701),
    ("leak", "A on the main arm", -0.470),
    ("worst OFF", "arm openness", -0.381),
    ("worst OFF", "main-stem opening", -0.357),
    ("worst OFF", "window opening", -0.346),
    ("worst OFF", "ensemble defect", -0.329),
    ("ON state", "ensemble defect", 0.047),
    ("ON state", "arm openness", 0.043),
    ("ON state", "main-stem opening", 0.030),
    ("ON state", "window opening", 0.023),
)


def _text(x, y, s, cls, anchor="start") -> str:
    extra = f' text-anchor="{anchor}"' if anchor != "start" else ""
    return f'<text class="{cls}" x="{x:.1f}" y="{y:.1f}"{extra}>{s}</text>'


def survival() -> str:
    """The U: most pairs are almost wholly usable or almost wholly dead."""
    left, base, bar_w, gap = 86, 330, 68, 12
    tallest = max(n for _, n in SURVIVAL)
    height = 210
    out = [
        _text(8, 28, "ON-state screening success varies across trigger pairs", "mt-title"),
        _text(
            8,
            48,
            "Number of trigger pairs by percentage of designs passing the ON-state screen.",
            "mt-caption",
        ),
    ]
    for index, (label, count) in enumerate(SURVIVAL):
        x = left + index * (bar_w + gap)
        bar = count / tallest * height
        extreme = label in ("0-10", "90-100")
        out.append(
            f'<rect class="mt-bar{" mt-bar--hot" if extreme else ""}" x="{x}" '
            f'y="{base - bar:.1f}" width="{bar_w}" height="{bar:.1f}" />'
        )
        out.append(_text(x + bar_w / 2, base - bar - 10, str(count), "mt-value", "middle"))
        out.append(_text(x + bar_w / 2, base + 22, label, "mt-axis", "middle"))
    out.append(
        f'<line class="mt-axis-line" x1="{left - 16}" y1="{base}" '
        f'x2="{left + len(SURVIVAL) * (bar_w + gap)}" y2="{base}" />'
    )
    out.append(_text(8, base + 22, "% pass", "mt-axis"))
    out.append(
        _text(
            8,
            base + 58,
            "120/210 pairs fall in the two end bands; 15 have no designs passing the screen.",
            "mt-note",
        )
    )
    out.append(
        _text(
            8,
            base + 78,
            "Pass rates reflect the sampled designs and the chosen screening threshold.",
            "mt-note",
        )
    )
    return _svg(
        out,
        base + 100,
        "Histogram showing the percentage of sampled designs passing the "
        "ON-state opening-cost screen for each of 210 trigger-window pairs: "
        "98 pairs in the 90 to 100 percent band and 22 pairs in the 0 to 10 "
        "percent band.",
    )


def terms() -> str:
    """The grip moves the leak and does not move the ON state."""
    left, top, row_h, zero = 300, 96, 26, 560
    scale = 300  # units per 1.0 of rho
    out = [
        _text(8, 28, "Trigger A binding tracks A-only occupancy", "mt-title"),
        _text(
            8,
            48,
            "Spearman correlation within a fixed input pair and geometry; "
            "stronger binding means more-negative energy.",
            "mt-caption",
        ),
    ]
    group_seen: set[str] = set()
    for index, (group, label, rho) in enumerate(TERMS):
        y = top + index * row_h
        if group not in group_seen:
            group_seen.add(group)
            out.append(_text(8, y + 14, group, "mt-row"))
        out.append(_text(left - 14, y + 14, label, "mt-side", "end"))
        span = rho * scale
        x = zero + min(span, 0)
        out.append(
            f'<rect class="mt-bar{" mt-bar--hot" if group == "leak" else ""}" '
            f'x="{x:.1f}" y="{y + 3}" width="{abs(span):.1f}" height="16" />'
        )
        at = zero + span + (-8 if rho < 0 else 8)
        out.append(_text(at, y + 16, f"{rho:+.3f}", "mt-value", "end" if rho < 0 else "start"))
    base = top + len(TERMS) * row_h
    out.append(
        f'<line class="mt-axis-line" x1="{zero}" y1="{top - 8}" x2="{zero}" y2="{base + 4}" />'
    )
    out.append(_text(zero, base + 24, "0", "mt-axis", "middle"))
    out.append(_text(zero - scale * 0.7, base + 24, "&minus;0.7", "mt-axis", "middle"))
    out.append(
        _text(
            8,
            base + 56,
            "Negative correlation: stronger A binding is associated with higher A-only occupancy.",
            "mt-note",
        )
    )
    out.append(
        _text(
            8, base + 76, "All four ON-state correlations are small: +0.023 to +0.047.", "mt-note"
        )
    )
    return _svg(
        out,
        base + 96,
        "Within-cell Spearman rank correlations between the predicted "
        "trigger-A inhibitory-arm binding energy and A-only binding, "
        "worst-OFF structural quantities, and ON-state quantities. A-only "
        "binding shows stronger negative correlations, while ON-state "
        "correlations are near zero.",
    )


def _svg(parts: list[str], height: int, aria: str) -> str:
    body = "\n    ".join(p for p in parts if p)
    return (
        f'<svg viewBox="0 0 {WIDTH} {height}" role="img" aria-label="{aria}">\n    {body}\n</svg>'
    )


FIGURES = {"results-survival.svg": survival, "results-terms.svg": terms}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Draw the Results figures.")
    parser.add_argument("--out-dir", default=".", type=pathlib.Path)
    args = parser.parse_args(argv)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for name, build in FIGURES.items():
        svg = build()
        (args.out_dir / name).write_text(svg, encoding="utf-8")
        print(f"  {name}: {len(svg):,} characters")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
