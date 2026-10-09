"""Figures for ``eu_and_v3.ipynb``: a lettered 2D structure as inline SVG and a base-pair
probability heatmap as a PNG.

Folding stays in ``FoldEngine`` (``mfe``, ``layout_coordinates``, ``base_pair_probabilities``); this
module only draws what it is handed. ``structure_svg`` is the drawing used by
``and_eu_report.ipynb``
(lettered circles scaled by the median neighbour gap, flipped y; the idea follows Offer's
``structure_figures.py``).
"""

from __future__ import annotations

import base64
import html
import io
import statistics

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

_DEFAULT_FILL = "#C7D0CA"  # a base outside every known domain span
_PAYLOAD_RING_COLOR = "#B5760E"  # ring on a base paired to the construct's own hidden tail
_TRIGGER_COLOR = "#D1495B"  # ring on a base paired to the hidden trigger strand

DOMAIN_COLORS = {
    "prefix": "#C9A227",
    "toehold": "#1F6FEB",
    "stem_up": "#7E97AC",
    "loop": "#8E6AA8",
    "stem_down": "#B6C8D8",
    "kozak": "#2E9E56",
    "exp_gene": "#B5760E",
}


# Second hairpin of an AND construct: same roles, other hues, so the two hairpins tell apart.
DOMAIN_COLORS_B = {
    "toehold": "#17A2B8",
    "stem_up": "#9CB5A0",
    "loop": "#C27BA0",
    "stem_down": "#C9D9CB",
    "kozak": "#2E9E56",
    "exp_gene": "#B5760E",
}
SPACER_COLOR = "#B0B0B0"


def domain_fill(
    domains: dict, palette: dict | None = None, suffix: str = ""
) -> list[tuple[int, int, str, str]]:
    """``(start, end, colour, label)`` per non-empty domain of a ``{name: (start, end)}`` dict.

    ``palette`` defaults to :data:`DOMAIN_COLORS`; ``suffix`` (" (A)", " (B)") disambiguates two
    hairpins sharing domain names in an AND construct's legend.
    """
    colors = DOMAIN_COLORS if palette is None else palette
    return [
        (s, e, colors.get(name, _DEFAULT_FILL), f"{name}{suffix}")
        for name, (s, e) in domains.items()
        if e > s
    ]


def structure_svg(
    points,
    sequence,
    structure,
    title,
    spans=(),
    domain_fill=(),
    visible_len=None,
    construct_len=None,
    spacing=23.0,
    pad=34.0,
    radius=7.4,
    legend_ncol=3,
):
    """One folded structure as an inline SVG: every base a circle with its letter inside, the
    backbone through them and a rung on every base pair, filled by domain.

    Same semantics as :func:`structure_png` (same ``spans`` / ``domain_fill`` / ``visible_len`` /
    ``construct_len`` arguments, same ring rules), drawn as vector so the letters stay sharp at
    any zoom. ``points`` is ``FoldEngine.layout_coordinates(structure)``. Bases are drawn
    ``spacing`` apart (the median neighbour distance is scaled to it), so the canvas grows with
    the molecule instead of the letters shrinking. Layout idea (lettered circles, scaling by the
    median neighbour gap, flipped y) follows Offer's ``structure_figures.py``.
    """

    n_vis = len(sequence) if visible_len is None else visible_len
    n_construct = n_vis if construct_len is None else construct_len
    vis = points[:n_vis]
    gaps = [
        ((vis[i + 1][0] - vis[i][0]) ** 2 + (vis[i + 1][1] - vis[i][1]) ** 2) ** 0.5
        for i in range(n_vis - 1)
    ]
    unit = statistics.median([g for g in gaps if g > 0]) or 1.0
    k = spacing / unit
    raw = [(p[0] * k, p[1] * k) for p in vis]
    span_x = max(x for x, _ in raw) - min(x for x, _ in raw)
    span_y = max(y for _, y in raw) - min(y for _, y in raw)
    if span_y > 1.15 * span_x:
        # a tall layout is turned 90 degrees so it uses a landscape page's width and the
        # letters stay legible when the plot is fitted to the page
        raw = [(y, x) for x, y in raw]
    min_x = min(x for x, _ in raw)
    max_y = max(y for _, y in raw)
    top = 38.0  # title strip
    pts = [(x - min_x + pad, max_y - y + pad + top) for x, y in raw]
    width = max(x for x, _ in pts) + pad
    height = max(y for _, y in pts) + pad

    stack, partner = [], {}
    for i, ch in enumerate(structure):
        if ch == "(":
            stack.append(i)
        elif ch == ")":
            j = stack.pop()
            partner[i], partner[j] = j, i

    ink, muted = "#141413", "#5F5E5A"
    parts = []
    for i, j in partner.items():
        if i < j and j < n_vis:
            (x1, y1), (x2, y2) = pts[i], pts[j]
            parts.append(
                f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                f'stroke="#8899AA" stroke-width="1.3" opacity="0.8"/>'
            )
    backbone = " ".join(f"{'M' if q == 0 else 'L'} {x:.1f} {y:.1f}" for q, (x, y) in enumerate(pts))
    parts.append(
        f'<path d="{backbone}" fill="none" stroke="#B9C2BC" stroke-width="1.6" '
        f'stroke-linecap="round" stroke-linejoin="round"/>'
    )

    drew_payload = drew_trigger = False
    for i, (x, y) in enumerate(pts):
        fill = next((c for s, e, c, _l in domain_fill if s <= i < e), _DEFAULT_FILL)
        ring = next((c for s, e, c in spans if s <= i < e), None)
        j = partner.get(i)
        if ring is None and j is not None and j >= n_vis:
            # dangling stub: paired to a base that is deliberately not drawn
            if j < n_construct:
                ring, drew_payload = _PAYLOAD_RING_COLOR, True
            else:
                ring, drew_trigger = _TRIGGER_COLOR, True
        stroke, sw = (ring, 2.6) if ring else ("#666666", 0.8)
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius}" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="{sw}"/>'
        )
        parts.append(
            f'<text x="{x:.1f}" y="{y + 3.4:.1f}" text-anchor="middle" '
            f'font-family="Helvetica,Arial,sans-serif" font-size="9.5" font-weight="600" '
            f'fill="{ink}">{html.escape(sequence[i])}</text>'
        )
    for idx, text, dx in ((0, "5&#8242;", -17), (n_vis - 1, "3&#8242;", 17)):
        x, y = pts[idx]
        parts.append(
            f'<text x="{x + dx:.1f}" y="{y + 4:.1f}" text-anchor="middle" '
            f'font-family="Helvetica,Arial,sans-serif" font-size="12" font-weight="700" '
            f'fill="{muted}">{text}</text>'
        )

    # legend: unique (label, colour) domain entries, then one entry per ring colour drawn
    entries = []
    for _s, _e, c, label in domain_fill:
        if (label, c, "fill") not in entries:
            entries.append((label, c, "fill"))
    if drew_payload:
        entries.append(
            ("ring: paired into this construct's own hidden tail", _PAYLOAD_RING_COLOR, "ring")
        )
    if drew_trigger:
        entries.append(("ring: paired to a hidden trigger strand", _TRIGGER_COLOR, "ring"))
    col_w = width / legend_ncol
    rows = -(-len(entries) // legend_ncol) if entries else 0
    legend_top = height + 6
    for n, (label, c, kind) in enumerate(entries):
        lx = (n % legend_ncol) * col_w + 14
        ly = legend_top + (n // legend_ncol) * 20 + 10
        if kind == "fill":
            parts.append(
                f'<circle cx="{lx + 5:.1f}" cy="{ly - 4:.1f}" r="5.5" fill="{c}" '
                f'stroke="#666666" stroke-width="0.8"/>'
            )
        else:
            parts.append(
                f'<circle cx="{lx + 5:.1f}" cy="{ly - 4:.1f}" r="5.5" fill="none" '
                f'stroke="{c}" stroke-width="2.4"/>'
            )
        parts.append(
            f'<text x="{lx + 16:.1f}" y="{ly:.1f}" font-family="Helvetica,Arial,sans-serif" '
            f'font-size="11" fill="{ink}">{html.escape(label)}</text>'
        )
    total_h = height + (rows * 20 + 14 if rows else 0)
    title_svg = (
        f'<text x="{width / 2:.1f}" y="24" text-anchor="middle" '
        f'font-family="Helvetica,Arial,sans-serif" font-size="15" font-weight="700" '
        f'fill="{ink}">{html.escape(title)}</text>'
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.0f} {total_h:.0f}" '
        'style="width:100%;height:auto;max-height:640px;display:block;" role="img">'
        f"{title_svg}{''.join(parts)}</svg>"
    )


def bpp_heatmap_png(sequence: str, matrix, title: str, boundary=None) -> str:
    """Base-pair-probability heatmap as a base64 PNG; ``boundary``: a strand junction position
    (or several) marked with a dotted crosshair."""
    arr = np.array(matrix)
    fig, ax = plt.subplots(figsize=(3.6, 3.3), dpi=120)
    im = ax.imshow(arr, cmap="magma", vmin=0.0, vmax=1.0, origin="upper")
    if boundary is None:
        boundary = ()
    for position in (boundary,) if isinstance(boundary, int) else boundary:
        ax.axhline(position - 0.5, color="#D1495B", linewidth=1.1, linestyle=":")
        ax.axvline(position - 0.5, color="#D1495B", linewidth=1.1, linestyle=":")
    n = len(sequence)
    ticks = list(range(0, n, max(1, n // 12)))
    ax.set_xticks(ticks)
    ax.set_yticks(ticks)
    ax.set_xticklabels([str(t) for t in ticks], fontsize=6.5, rotation=90)
    ax.set_yticklabels([str(t) for t in ticks], fontsize=6.5)
    ax.set_xlim(-0.5, n - 0.5)
    ax.set_ylim(n - 0.5, -0.5)
    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("P(paired)", fontsize=7.5)
    cbar.ax.tick_params(labelsize=6.5)
    ax.set_title(title, fontsize=9, fontweight="bold")
    fig.tight_layout()
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", facecolor="white")
    plt.close(fig)
    return base64.b64encode(buffer.getvalue()).decode("ascii")
