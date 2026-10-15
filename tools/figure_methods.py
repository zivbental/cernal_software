"""The four Methods figures for the iGEM model page, as inline SVG.

Run::

    uv run python tools/figure_methods.py --out-dir <somewhere>

Writes four files:

``methods-triggers.svg``   (3.3) which trigger domain pairs with which switch domain
``methods-overlaps.svg``   (4.2) the measured distribution of overlap lengths
``methods-conflicts.svg``  (4.3) the per-position conflict, and the front it produces
``methods-levers.svg``     (4.4) what each of the three levers changes, on one design

Two rules carried over from ``figure_and_gate_states.py``, both learned the hard way:
SVG text does not wrap, so nothing inside a drawing is longer than a symbol or two words
and every sentence lives in the page's caption; and the panels are laid out in declared
bands rather than by eye, because judging a 1,500-unit figure in a browser is how the
first version shipped with labels on top of each other.

**The numbers are measured, not illustrative.** The overlap histogram is every candidate
the pair finder returns on the three gene pairs (53,530 of them). The conflict figure and
the lever figure are one real ``ggt`` x ``fadB`` pair carried through the production path,
and its ``len_x`` is 4 -- the modal overlap, not a convenient one. The one thing chosen
for legibility is which pair: it has 4 disagreeing positions where the median is 10 to 11,
and the caption says so, because a figure that quietly shows the easy case is worse than
no figure.
"""

from __future__ import annotations

import argparse
import math
import pathlib

WIDTH = 900

# --- measured inputs -----------------------------------------------------------------
#
# From tools/audit_grid_coverage.py's sibling measurement over every candidate pair:
#   uv run python -I <scratch>/overlap_distribution.py
OVERLAPS: tuple[tuple[str, int, float], ...] = (
    ("4", 39349, 0.735),
    ("5", 10348, 0.193),
    ("6", 2827, 0.053),
    ("7", 696, 0.013),
    ("8", 243, 0.005),
    ("9+", 67, 0.001),
)
OVERLAP_TOTAL = 53530

#: One real ggt x fadB pair, x_start 63, xstar_start 983, len_x 4.
ARM_EXT = "CCGCCGCCGCGCCU"  # what trigger A's extension would put on the ascending arm
ARM_WANTED = "AUGCCGCCGCCCAU"  # what trigger B needs there
CONFLICTS = (0, 1, 10, 12)

#: (lock, A site, B site, on the front) for every assignment that survives the rules.
POINTS: tuple[tuple[float, float, float, bool], ...] = (
    (-29.50, -23.90, -29.50, True),
    (-29.20, -28.30, -29.50, True),
    (-29.10, -27.30, -29.50, False),
    (-28.30, -34.50, -29.50, True),
    (-28.10, -41.10, -28.30, True),
    (-26.60, -34.90, -29.20, True),
    (-25.90, -41.10, -29.20, True),
    (-25.40, -38.10, -28.30, False),
    (-25.10, -30.50, -29.50, False),
    (-24.80, -34.90, -29.50, True),
    (-24.70, -33.90, -29.50, False),
    (-24.60, -34.10, -25.10, False),
    (-24.30, -38.50, -25.10, False),
    (-24.30, -34.10, -25.10, False),
    (-24.20, -37.50, -25.10, False),
    (-24.00, -38.50, -25.10, False),
    (-23.90, -41.10, -29.50, True),
    (-23.90, -31.90, -29.20, False),
    (-23.90, -37.50, -25.10, False),
    (-23.80, -30.90, -25.10, False),
    (-23.70, -38.10, -25.10, False),
    (-23.40, -44.70, -25.10, True),
    (-23.20, -38.10, -29.20, False),
    (-23.10, -44.70, -25.10, False),
    (-22.40, -27.50, -29.50, False),
    (-22.10, -31.90, -29.50, False),
    (-22.00, -30.90, -29.50, False),
    (-21.20, -38.10, -29.50, False),
    (-21.00, -44.70, -28.30, True),
    (-19.50, -38.50, -29.20, False),
    (-19.40, -37.50, -25.10, False),
    (-19.30, -44.70, -25.10, False),
    (-18.80, -44.70, -29.20, True),
    (-18.00, -34.10, -29.50, False),
    (-17.70, -38.50, -29.50, False),
    (-17.60, -37.50, -29.50, False),
    (-16.80, -44.70, -29.50, True),
)
ENUMERATED = 81
SURVIVED = 37
ON_FRONT = 12
MIXED_ON_FRONT = 10

#: What each lever changes on that same design, holding the stem fixed.
LEVERS: tuple[tuple[str, str, str, str, str], ...] = (
    ("closure", "the bulge facing the start codon", "bulge_star", "UCC", "AGU"),
    ("upper3", "the top of the main stem", "k1_star + k1", "GAGCUC", "AUAUAU"),
    ("lower3", "the foot of the main stem", "Main_pre* + Main_pre", "AAUU", "GGCC"),
)

#: The main hairpin of that design, 5' to 3'.
MAIN_DOMAINS: tuple[tuple[str, str, str], ...] = (
    ("Main_pre*", "AAAACAACU", "lower"),
    ("bulge", "UCC", "closure"),
    ("k1*", "UGAGAG", "upper"),
    ("RBS loop", "AGACAAGAACAGAGGAGA", "plain"),
    ("k1", "CUCUCA", "upper"),
    ("AUG", "AUG", "start"),
    ("Main_pre", "AGUUGUUUU", "lower"),
)


def _text(x, y, s, cls, anchor="start") -> str:
    extra = f' text-anchor="{anchor}"' if anchor != "start" else ""
    return f'<text class="{cls}" x="{x:.1f}" y="{y:.1f}"{extra}>{s}</text>'


# --- 3.3  the two triggers against the switch ----------------------------------------


def triggers() -> str:
    """Which domain of each trigger pairs with which domain of the switch."""
    row_b, row_switch, row_a = 70, 170, 270
    # Widths are schematic, not to scale: a 161-nt switch at any honest scale is wider
    # than the figure, and what this figure is for is which domain meets which.
    scale = 0.84

    def w(n: int) -> float:
        return round(n * scale, 1)

    blocks = [("k2", w(70), "b"), ("x*", w(46), "shared"), ("r2", w(150), "b")]
    switch = [
        ("r2*", w(150), "b"),
        ("x", w(46), "shared"),
        ("k2*", w(70), "stem"),
        ("loop", w(62), "const"),
        ("Sec_z", w(70), "stem"),
        ("x*", w(46), "shared"),
        ("Main_pre*", w(74), "a"),
        ("bulge", w(36), "a"),
        ("k1*", w(54), "a"),
        ("RBS", w(86), "const"),
        ("k1", w(54), "a"),
        ("AUG", w(36), "start"),
        ("Main_pre", w(74), "a"),
        ("linker", w(70), "const"),
    ]
    trigger_a = [
        ("k1", w(54), "a"),
        ("bulge", w(36), "a"),
        ("Main_pre", w(74), "a"),
        ("x", w(46), "shared"),
    ]

    out = [
        _text(8, 28, "How the two triggers meet the switch", "mt-title"),
        _text(
            8,
            48,
            "Each trigger binds antiparallel: its 5&#8242; end pairs with the "
            "3&#8242;-most domain of its footprint.",
            "mt-caption",
        ),
    ]

    def strip(items, y, x0, tag):
        x = x0
        parts = [_text(x0 - 10, y + 23, "5&#8242;", "mt-end", "end")]
        for label, width, kind in items:
            parts.append(
                f'<rect class="mt-box mt-fill-{kind}" x="{x:.1f}" y="{y}" '
                f'width="{width}" height="34" />'
            )
            parts.append(_text(x + width / 2, y + 23, label, "mt-dom", "middle"))
            x += width
        parts.append(_text(x + 10, y + 23, "3&#8242;", "mt-end"))
        parts.append(_text(x0, y - 10, tag, "mt-row"))
        return "\n    ".join(parts), x

    # trigger B sits over the 5' half of the switch; trigger A over the 3' half.
    switch_x0 = 48
    b_svg, _ = strip(blocks, row_b, switch_x0, "Trigger B &#8212; 50 nt, from gene B")
    s_svg, _switch_end = strip(switch, row_switch, switch_x0, "The switch, 5&#8242; to 3&#8242;")

    # trigger A binds the contiguous run x* .. k1*, so centre it under that run
    def span(items, x0, first, last):
        x, start, end = x0, None, None
        for label, width, _ in items:
            if label == first and start is None:
                start = x
            x += width
            if label == last:
                end = x
        return start, end

    a_from, a_to = span(switch, switch_x0, "x*", "k1*")
    a_width = sum(width for _, width, _ in trigger_a)
    a_x0 = (a_from + a_to) / 2 - a_width / 2
    a_svg, _ = strip(trigger_a, row_a, a_x0, "Trigger A &#8212; 36 nt, from gene A")
    out += [b_svg, s_svg, a_svg]

    # tie lines: each trigger domain to the switch domain it pairs with.
    def centre(items, x0, name, nth=0):
        x, seen = x0, 0
        for label, width, _ in items:
            if label == name:
                if seen == nth:
                    return x + width / 2
                seen += 1
            x += width
        raise KeyError(name)

    ties = [
        (centre(blocks, switch_x0, "k2"), centre(switch, switch_x0, "k2*"), "b"),
        (centre(blocks, switch_x0, "x*"), centre(switch, switch_x0, "x"), "shared"),
        (centre(blocks, switch_x0, "r2"), centre(switch, switch_x0, "r2*"), "b"),
        (centre(trigger_a, a_x0, "k1"), centre(switch, switch_x0, "k1*"), "a"),
        (centre(trigger_a, a_x0, "bulge"), centre(switch, switch_x0, "bulge"), "a"),
        (centre(trigger_a, a_x0, "Main_pre"), centre(switch, switch_x0, "Main_pre*"), "a"),
        (centre(trigger_a, a_x0, "x"), centre(switch, switch_x0, "x*"), "shared"),
    ]
    for x_from, x_to, kind in ties[:3]:
        out.append(
            f'<path class="mt-tie mt-tie--{kind}" d="M {x_from:.1f} {row_b + 34} '
            f"C {x_from:.1f} {row_b + 66} {x_to:.1f} {row_switch - 32} "
            f'{x_to:.1f} {row_switch}" />'
        )
    for x_from, x_to, kind in ties[3:]:
        out.append(
            f'<path class="mt-tie mt-tie--{kind}" d="M {x_from:.1f} {row_a} '
            f"C {x_from:.1f} {row_a - 32} {x_to:.1f} {row_switch + 66} "
            f'{x_to:.1f} {row_switch + 34}" />'
        )

    out.append(
        _text(
            8,
            338,
            "A star is the reverse complement. The shared domain "
            "x appears twice on the switch and once in each trigger.",
            "mt-note",
        )
    )
    return _svg(
        out,
        360,
        "Which domain of each trigger pairs with which domain of the "
        "switch. Trigger B binds the 5 prime half, trigger A the 3 prime "
        "half, and the shared overlap x couples them.",
    )


# --- 4.2  the overlap histogram ------------------------------------------------------


def overlaps() -> str:
    left, base_y, bar_w, gap = 110, 300, 78, 26
    peak = max(count for _, count, _ in OVERLAPS)
    height = 210
    out = [
        _text(8, 28, "Overlap length, over every candidate pair", "mt-title"),
        _text(
            8,
            48,
            f"Three gene pairs, {OVERLAP_TOTAL:,} candidates. Not the subset a run takes.",
            "mt-caption",
        ),
    ]
    for index, (label, count, share) in enumerate(OVERLAPS):
        x = left + index * (bar_w + gap)
        bar = max(2.0, height * count / peak)
        out.append(
            f'<rect class="mt-bar" x="{x}" y="{base_y - bar:.1f}" '
            f'width="{bar_w}" height="{bar:.1f}" />'
        )
        out.append(_text(x + bar_w / 2, base_y - bar - 24, f"{count:,}", "mt-value", "middle"))
        out.append(_text(x + bar_w / 2, base_y - bar - 8, f"{share:.1%}", "mt-share", "middle"))
        out.append(_text(x + bar_w / 2, base_y + 22, f"{label} nt", "mt-axis", "middle"))
    out.append(
        f'<line class="mt-axis-line" x1="{left - 16}" y1="{base_y}" '
        f'x2="{left + len(OVERLAPS) * (bar_w + gap)}" y2="{base_y}" />'
    )
    out.append(_text(8, base_y + 22, "overlap", "mt-axis"))

    # Green's shortest first-generation toehold, for scale.
    marker = left + 5 * (bar_w + gap) + bar_w + 10
    out.append(
        f'<line class="mt-marker" x1="{marker}" y1="{base_y - height - 40}" '
        f'x2="{marker}" y2="{base_y}" />'
    )
    out.append(
        _text(
            marker - 10,
            base_y - height - 26,
            "12 nt &#8212; Green&#8217;s shortest first-generation",
            "mt-marker-text",
            "end",
        )
    )
    out.append(
        _text(
            marker - 10,
            base_y - height - 8,
            "toehold. 4 candidates of 53,530 reach it.",
            "mt-marker-text",
            "end",
        )
    )
    out.append(
        _text(
            8,
            base_y + 62,
            "median 4 nt &#183; mean 4.36 &#183; 73.5% exactly at the floor "
            "&#183; 98.1% at 6 nt or shorter",
            "mt-note",
        )
    )
    return _svg(
        out,
        380,
        "Bar chart of overlap length across 53,530 candidate trigger "
        "pairs. 73.5 percent are exactly 4 nucleotides, the minimum, and "
        "98.1 percent are 6 or shorter.",
    )


# --- 4.3  the conflict, and the front it produces ------------------------------------


def conflicts() -> str:
    cell, left, top = 38, 190, 108
    out = [
        _text(8, 28, "One stem, four disagreements, twelve surviving builds", "mt-title"),
        _text(
            8,
            48,
            "A real ggt &#215; fadB pair. Its overlap is 4 nt, the modal length.",
            "mt-caption",
        ),
        _text(8, top - 18, "the inhibitory stem&#8217;s ascending arm, 14 nt", "mt-row"),
        _text(left - 14, top + 25, "trigger A would put", "mt-side", "end"),
        _text(left - 14, top + cell + 25, "trigger B needs", "mt-side", "end"),
    ]
    for index, (a_base, b_base) in enumerate(zip(ARM_EXT, ARM_WANTED, strict=True)):
        x = left + index * cell
        clash = index in CONFLICTS
        for row, base in ((0, a_base), (1, b_base)):
            out.append(
                f'<rect class="mt-cell{" mt-cell--clash" if clash else ""}" '
                f'x="{x}" y="{top + row * cell}" width="{cell - 3}" height="{cell - 3}" />'
            )
            out.append(_text(x + (cell - 3) / 2, top + row * cell + 25, base, "mt-base", "middle"))
        if clash:
            out.append(
                _text(x + (cell - 3) / 2, top + 2 * cell + 20, "&#8597;", "mt-clash-mark", "middle")
            )
    out.append(
        _text(
            left,
            top + 2 * cell + 44,
            f"{len(CONFLICTS)} of {len(ARM_EXT)} positions disagree. Each one can "
            "serve A, serve B, or keep the stem shut.",
            "mt-note",
        )
    )

    # the front
    plot_x, plot_y, plot_w, plot_h = 190, 268, 520, 220
    locks = [p[0] for p in POINTS]
    sites = [p[1] for p in POINTS]
    lo_l, hi_l = min(locks), max(locks)
    lo_s, hi_s = min(sites), max(sites)
    out += [
        _text(8, plot_y - 14, "every surviving build, and the front", "mt-row"),
        f'<line class="mt-axis-line" x1="{plot_x}" y1="{plot_y + plot_h}" '
        f'x2="{plot_x + plot_w}" y2="{plot_y + plot_h}" />',
        f'<line class="mt-axis-line" x1="{plot_x}" y1="{plot_y}" '
        f'x2="{plot_x}" y2="{plot_y + plot_h}" />',
        _text(
            plot_x + plot_w / 2,
            plot_y + plot_h + 34,
            "the lock, kcal/mol &#8212; stronger to the left",
            "mt-axis",
            "middle",
        ),
        _text(plot_x - 14, plot_y + 10, "A&#8217;s grip", "mt-axis", "end"),
        _text(plot_x - 14, plot_y + 26, "stronger", "mt-axis", "end"),
    ]
    for lock, site, _b, on_front in POINTS:
        px = plot_x + plot_w * (lock - lo_l) / (hi_l - lo_l)
        py = plot_y + plot_h * (site - lo_s) / (hi_s - lo_s)
        cls = "mt-front" if on_front else "mt-dominated"
        out.append(f'<circle class="{cls}" cx="{px:.1f}" cy="{py:.1f}" r="6" />')
    out.append(_text(plot_x + plot_w + 16, plot_y + 40, f"{ENUMERATED} assignments", "mt-legend"))
    out.append(_text(plot_x + plot_w + 16, plot_y + 60, f"{SURVIVED} pass the rules", "mt-legend"))
    out.append(_text(plot_x + plot_w + 16, plot_y + 80, f"{ON_FRONT} non-dominated", "mt-legend"))
    out.append(
        _text(
            plot_x + plot_w + 16, plot_y + 100, f"{MIXED_ON_FRONT} of those are mixed", "mt-legend"
        )
    )
    out.append(
        _text(
            8,
            plot_y + plot_h + 72,
            "Nothing is ranked here. A build is dropped only when another is at "
            "least as good on all three claims and better on one.",
            "mt-note",
        )
    )
    return _svg(
        out,
        590,
        "The inhibitory stem's ascending arm with four disagreeing "
        "positions marked, and a scatter of every surviving build "
        "showing which are non-dominated.",
    )


# --- 4.4  the three levers -----------------------------------------------------------


def levers() -> str:
    out = [
        _text(8, 28, "What each lever changes", "mt-title"),
        _text(8, 48, "One trigger pair, one stem. Only the named lever moves.", "mt-caption"),
    ]
    x, y = 150, 92
    out.append(_text(8, y + 24, "the main hairpin", "mt-side"))
    for label, seq, kind in MAIN_DOMAINS:
        width = max(46, len(seq) * 13)
        out.append(
            f'<rect class="mt-box mt-lev-{kind}" x="{x}" y="{y}" width="{width}" height="36" />'
        )
        out.append(_text(x + width / 2, y + 23, label, "mt-dom", "middle"))
        out.append(_text(x + width / 2, y + 52, seq, "mt-seq", "middle"))
        x += width + 4
    out.append(_text(150, y - 12, "5&#8242;", "mt-end"))
    out.append(_text(x - 4, y - 12, "3&#8242;", "mt-end", "end"))

    row = 196
    out.append(_text(8, row - 12, "the three levers", "mt-row"))
    for index, (name, where, domain, before, after) in enumerate(LEVERS):
        top = row + index * 62
        out.append(
            f'<rect class="mt-lev-row mt-lev-{name}" x="150" y="{top}" width="700" height="50" />'
        )
        out.append(_text(166, top + 22, name, "mt-lever-name"))
        out.append(_text(166, top + 40, where, "mt-lever-where"))
        out.append(_text(400, top + 22, domain, "mt-lever-domain"))
        out.append(_text(640, top + 30, before, "mt-seq-before", "end"))
        out.append(_text(656, top + 30, "&#8594;", "mt-lever-where"))
        out.append(_text(676, top + 30, after, "mt-seq-after"))
    out.append(
        _text(
            8,
            row + 3 * 62 + 24,
            "Each lever is a patch to a named domain that changes no length, so "
            "the domain map stays valid.",
            "mt-note",
        )
    )
    return _svg(
        out,
        row + 3 * 62 + 48,
        "The main hairpin's domains with their sequences, and a row per lever "
        "giving the domain it patches and the exact substitution it makes.",
    )


# --- 4.5  how the space is cut down ---------------------------------------------------


def funnel() -> str:
    """Each cut, with what it leaves.

    Bar length is logarithmic. The first cut is four orders of magnitude, and on a linear
    scale every stage after it would be invisible -- which would hide the part of the
    figure that is actually about design decisions.
    """
    stages = (
        ("every candidate pair", 53530, "all three gene pairs", "pairs"),
        ("carried into the sweep", 210, "a declared budget, spread across the ranking", "pairs"),
        ("in both geometries", 420, "neither stem layout has been retired", "cells"),
        ("with its own stems", 3555, "about 9 per cell; the data sizes this", "stems"),
        ("over the lever grid", 341280, "16 closures, 3 upper3, 2 lower3", "designs"),
        ("folded in four tubes", 147129, "the rest stop at the ON-state ceiling", "designs"),
    )
    left, top, row_h, bar_max = 290, 96, 46, 440
    peak = math.log10(max(n for _, n, _, _ in stages))
    out = [
        _text(8, 28, "How the space is cut, and by what", "mt-title"),
        _text(
            8,
            48,
            "Bar length is logarithmic: the first cut alone is four orders of magnitude.",
            "mt-caption",
        ),
    ]
    for index, (label, count, why, unit) in enumerate(stages):
        y = top + index * row_h
        width = bar_max * math.log10(count) / peak
        folded = index >= 4
        out.append(
            f'<rect class="mt-funnel{" mt-funnel--fold" if folded else ""}" '
            f'x="{left}" y="{y}" width="{width:.1f}" height="30" />'
        )
        out.append(_text(left - 12, y + 21, label, "mt-dom", "end"))
        out.append(_text(left + width + 10, y + 21, f"{count:,} {unit}", "mt-value"))
        out.append(_text(8, y + 21, why, "mt-note"))
    base = top + len(stages) * row_h
    out.append(
        _text(
            8,
            base + 22,
            "Only the last two rows involve folding. Everything "
            "above them is counting, and is what makes the folding "
            "affordable.",
            "mt-note",
        )
    )
    return _svg(
        out,
        base + 44,
        "A logarithmic funnel from 53,530 candidate trigger pairs down to the "
        "147,129 designs folded in all four tubes, with the reason for each cut.",
    )


# --- 4.6  the four tubes --------------------------------------------------------------


def tubes() -> str:
    """What each tube contains, what it has to show, and which one holds the leak."""
    cells = (
        ("00", "the switch alone", "both hairpins shut", "", "plain"),
        (
            "10",
            "the switch + trigger A",
            "nothing should change: A has no exposed site",
            "where the leak lives",
            "leak",
        ),
        (
            "01",
            "the switch + trigger B",
            "the inhibitory hairpin opens, the main one does not",
            "the harder of the two to pass",
            "plain",
        ),
        ("11", "the switch + both triggers", "the footprint comes free", "the only ON state", "on"),
    )
    w, h, gap, left, top = 404, 126, 26, 36, 100
    out = [
        _text(8, 28, "The four tubes", "mt-title"),
        _text(
            8,
            48,
            "Folded at equilibrium with the triggers in excess. The left digit is trigger A.",
            "mt-caption",
        ),
    ]
    for index, (state, contents, must, note, kind) in enumerate(cells):
        x = left + (index % 2) * (w + gap)
        y = top + (index // 2) * (h + gap)
        out.append(
            f'<rect class="mt-tube mt-tube--{kind}" x="{x}" y="{y}" '
            f'width="{w}" height="{h}" rx="4" />'
        )
        out.append(_text(x + 18, y + 38, state, "mt-state-big"))
        out.append(_text(x + 86, y + 34, contents, "mt-dom"))
        out.append(_text(x + 18, y + 68, must, "mt-note"))
        if note:
            out.append(_text(x + 18, y + 98, note, "mt-leak-note" if kind == "leak" else "mt-note"))
    base = top + 2 * (h + gap)
    out.append(
        _text(
            8,
            base + 14,
            "10 and 01 are not the same test. In 10 the molecule "
            "is shut and the question is whether A gets a grip "
            "anyway;",
            "mt-note",
        )
    )
    out.append(
        _text(
            8,
            base + 34,
            "in 01 the main hairpin is already exposed and the "
            "question is whether it stays shut without A.",
            "mt-note",
        )
    )
    return _svg(
        out,
        base + 56,
        "The four tube states in a two by two grid: what each contains, what it "
        "has to show, and that state 10 is where the leak lives.",
    )


# --- 4.8  the two windows, and why one bounds the other -------------------------------


def windows() -> str:
    """The ribosome's window contains the stem's arms, which is the whole argument."""
    scale, left, mid = 16, 150, 176

    def at(pos):
        return left + (pos + 20) * scale

    out = [
        _text(8, 28, "Two windows, one inside the other", "mt-title"),
        _text(
            8,
            48,
            "Positions counted from the A of the start codon, which is +1. There is no zero.",
            "mt-caption",
        ),
        f'<line class="mt-axis-line" x1="{at(-20)}" y1="{mid}" x2="{at(16)}" y2="{mid}" />',
    ]
    for pos in (-17, -6, 1, 10, 13):
        out.append(
            f'<line class="mt-tick" x1="{at(pos)}" y1="{mid - 7}" x2="{at(pos)}" y2="{mid + 7}" />'
        )
        out.append(_text(at(pos), mid + 26, f"{pos:+d}", "mt-axis", "middle"))
    out.append(
        f'<rect class="mt-aug" x="{at(1)}" y="{mid - 14}" width="{3 * scale}" height="28" rx="3" />'
    )
    out.append(_text(at(1) + 1.5 * scale, mid + 5, "AUG", "mt-pill-text", "middle"))

    for y, lo, hi, label, why, kind in (
        (
            mid - 70,
            -17,
            13,
            "the ribosome&#8217;s window, 31 nt",
            "what Green&#8217;s 3.64 kcal/mol is measured over",
            "wide",
        ),
        (
            mid + 62,
            -6,
            9,
            "the main stem&#8217;s arms, 15 nt",
            "what the ON-state ceiling filters",
            "narrow",
        ),
    ):
        out.append(
            f'<rect class="mt-span mt-span--{kind}" x="{at(lo)}" y="{y - 14}" '
            f'width="{(hi - lo + 1) * scale}" height="28" rx="3" />'
        )
        out.append(_text(at(lo) + 10, y + 5, label, "mt-dom"))
        # Under the bar, not beside it: the wide span reaches x=678 and its note is
        # 43 characters, which ran 130 units past the figure's right edge.
        out.append(_text(at(lo) + 10, y + (26 if kind == "wide" else -22), why, "mt-note"))
        for edge in (lo, hi + 1):
            out.append(
                f'<line class="mt-lead" x1="{at(edge)}" y1="{y}" x2="{at(edge)}" y2="{mid}" />'
            )

    base = mid + 116
    for offset, line in enumerate(
        (
            "The ON-state ceiling is read over the WIDE span, which is the one an initiating "
            "30S subunit occupies and the one",
            "Green&#8217;s published ON costs are measured over. 7.2 kcal/mol is the highest "
            "cost among his switches above 20-fold ON/OFF.",
            "The narrow span is recorded for every design and decides nothing. The two are "
            "not interchangeable: measured on 147,244",
            "designs they differ by a median of 0.83 and by up to 7.45 kcal/mol, so every "
            "number says which span it belongs to.",
        )
    ):
        out.append(_text(8, base + offset * 20, line, "mt-note"))
    return _svg(
        out,
        base + 96,
        "The ribosome's 31-nucleotide window drawn above the main stem's "
        "15-nucleotide arms, showing the narrow span lying entirely inside "
        "the wide one.",
    )


def _svg(parts: list[str], height: int, aria: str) -> str:
    body = "\n    ".join(parts)
    return (
        f'<svg viewBox="0 0 {WIDTH} {height}" role="img" aria-label="{aria}">\n    {body}\n</svg>'
    )


FIGURES = {
    "methods-triggers.svg": triggers,
    "methods-funnel.svg": funnel,
    "methods-tubes.svg": tubes,
    "methods-windows.svg": windows,
    "methods-overlaps.svg": overlaps,
    "methods-conflicts.svg": conflicts,
    "methods-levers.svg": levers,
}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Draw the four Methods figures.")
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
