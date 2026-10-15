"""Draw the AND gate in all four tube states, as an inline SVG for the iGEM wiki.

Run::

    uv run python tools/figure_and_gate_states.py --out and-gate-states.svg

Generated rather than drawn by hand for two reasons. The four panels have to be
geometrically consistent -- the same stem lengths, the same loop sizes, the same domain
boundaries -- and a reader who counts base pairs in one panel and not the other has found
a figure that argues against itself. And the architecture is still being characterised, so
the figure has to be cheap to regenerate when a length changes. Domain lengths are read
from the gate family rather than restated here.

**What this corrects against the sketch it is based on**, the first of which is the
architecture's whole claim:

1. **There is nothing between the two hairpins.** The sketch drew the second toehold as a
   free single-stranded stretch between them. Here trigger A's landing site ``x*`` is
   *inside the inhibitory hairpin's own stem*, paired with ``x`` on the ascending arm. That
   is what makes this an AND and not an OR: with no trigger present, trigger A has no
   exposed nucleotide anywhere to nucleate on.
2. **The start codon sits in a 3x3 internal loop, not a one-sided bulge.** ``AUG`` faces a
   3-nt opposing bulge across the main stem, so the main stem is 9 bp, then the loop, then
   6 bp.
3. **The naming runs the other way round.** The sketch's "trigger 1" is our trigger **B**,
   which binds the permanently free 5' toehold and acts first; its "trigger 2" is our
   trigger **A**, which acts second. Our state labels put trigger A in the left digit, so
   state ``10`` is the *second* trigger of the cascade arriving alone.

**Labelling rule.** SVG text does not wrap, and a long label silently overflows its panel
or lands on top of something else. So nothing inside the drawing is longer than a symbol
or two words, and every sentence lives in the figure's caption on the page, where it wraps
and can be edited without touching geometry. The first version of this figure ignored that
and its labels collided with the panel headings, with the pills and with each other.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from engine.gates.toehold import ProkaryoticToeholdAndGate as Gate

# --- Panel geometry ------------------------------------------------------------------
#
# A panel is WIDTH x PANEL_H in SVG user units, shown at roughly 1 unit = 1 px inside a
# horizontally scrolling box, so it scrolls rather than shrinks on a narrow screen.
#
# The vertical bands. This is what the first version got wrong: it let the drawing start
# where the heading was still being written.
#
#      26   state label and panel title
#      46   one-line panel caption
#      82   the hairpin names
#      92   top of a loop        <- the drawing proper starts here
#     258   the backbone's baseline
#     284   one row of short symbols under the baseline
#     314   a trigger strand, where the state has one
#     336   that trigger's name

WIDTH = 900
PANEL_H = 362
BASE_Y = 258
APEX_Y = 118  # a loop's lowest point; its interior runs up to APEX_Y - LOOP_R
LOOP_R = 26
STEM_TOP = APEX_Y + 10

#: One base pair is PITCH units of stem, in BOTH hairpins. Drawing them at different
#: pitches makes one stem look denser than the other when the only real difference is how
#: many pairs it has, so the pitch is a constant and the stem's length follows from it.
#: 18 bp at 6 units is 108, and the main hairpin's 6 + 9 bp plus a 3-nt internal loop is
#: 36 + 18 + 54 = 108 as well, so the two hairpins are the same height by arithmetic
#: rather than by adjustment.
PITCH = 6
MAIN_STEM_BP = 18
STEM_BOTTOM = STEM_TOP + PITCH * MAIN_STEM_BP

#: The internal loop that holds the start codon: 3 unpaired positions on each side, so it
#: occupies 3 pitches of the main hairpin's stem.
LOOP_FROM = STEM_TOP + PITCH * 6
LOOP_TO = LOOP_FROM + PITCH * 3
NAME_Y = 82
SYMBOL_Y = 284
TRIG_Y = 314
GENE_X = 706
GENE_W = 170
PILL_W = 34
PILL_H = 18

# Where each folded hairpin stands. The first one's descending arm and the second one's
# ascending arm are adjacent, which is the drawing's way of saying that no nucleotide
# separates them.
H1_X = 232
H2_X = 318


def _rungs(left: float, right: float, y_from: float, y_to: float, count: int) -> str:
    """`count` base-pair rungs, evenly spaced, between a hairpin's two arms."""
    if count <= 0:
        return ""
    step = (y_to - y_from) / count
    return "\n    ".join(
        f'<line class="st-rung" x1="{left:.1f}" y1="{y_from + step * (i + 0.5):.1f}" '
        f'x2="{right:.1f}" y2="{y_from + step * (i + 0.5):.1f}" />'
        for i in range(count)
    )


def _hairpin(
    ascend_x: float,
    *,
    enter_x: float,
    exit_x: float,
    blocks: tuple[tuple[int, float, float], ...],
) -> tuple[str, str]:
    """One folded hairpin: its path fragment and its rungs.

    ``blocks`` is the stem read downward from the loop as ``(base pairs, y_from, y_to)``.
    Gaps between blocks are left unpaired, which is how the internal loop that holds the
    start codon is drawn.
    """
    descend_x = ascend_x + LOOP_R * 2
    path = (
        f"L {enter_x:.1f} {BASE_Y} "
        f"Q {ascend_x:.1f} {BASE_Y} {ascend_x:.1f} {BASE_Y - 22:.1f} "
        f"L {ascend_x:.1f} {APEX_Y} "
        f"A {LOOP_R} {LOOP_R} 0 1 1 {descend_x:.1f} {APEX_Y} "
        f"L {descend_x:.1f} {BASE_Y - 22:.1f} "
        f"Q {descend_x:.1f} {BASE_Y} {exit_x:.1f} {BASE_Y} "
    )
    rungs = "\n    ".join(_rungs(ascend_x, descend_x, a, b, n) for n, a, b in blocks)
    return path, rungs


def _along(x: float, y_from: float, y_to: float, label: str, side: str) -> str:
    """A domain name written along a vertical arm, reading bottom-to-top.

    The two hairpins stand 34 units apart, which is the architecture's a = 0 and not a
    drawing choice, so a horizontal label on an inner arm has nowhere to go. Rotated text
    runs along the arm instead, where a 108-unit stem gives room for any domain name.
    `side` is "left" or "right" of the arm.
    """
    cy = (y_from + y_to) / 2
    cx = x - 7 if side == "left" else x + 11
    return (
        f'<text class="st-domain" x="{cx:.1f}" y="{cy:.1f}" text-anchor="middle" '
        f'transform="rotate(-90 {cx:.1f} {cy:.1f})">{label}</text>'
    )


def _domain_labels() -> str:
    """Every domain of the shut molecule, named where it sits.

    Read 5' to 3': the leader and the free toehold on the baseline, then the inhibitory
    hairpin's ascending arm (x then k2*), its loop, its descending arm (z then x*), then
    the main hairpin's ascending arm (main_pre* then k1*) across the start-codon loop, its
    own loop, its descending arm (main_z then main_pre), and the linker out to the gene.
    """
    h1_descend = H1_X + LOOP_R * 2
    h2_descend = H2_X + LOOP_R * 2
    mid_loop = (LOOP_FROM + LOOP_TO) / 2
    return "\n    ".join(
        (
            # the baseline, 5' to 3'
            f'<text class="st-domain" x="34" y="{BASE_Y + 16}">cap</text>',
            f'<text class="st-domain" x="112" y="{BASE_Y + 16}" text-anchor="middle">r2*</text>',
            f'<text class="st-domain" x="{GENE_X - 86}" y="{BASE_Y + 16}">linker</text>',
            # the inhibitory hairpin
            _along(H1_X, STEM_TOP, STEM_TOP + PITCH * 9, "k2*", "left"),
            _along(H1_X, STEM_TOP + PITCH * 9, STEM_BOTTOM, "x", "left"),
            _along(h1_descend, STEM_TOP, STEM_TOP + PITCH * 9, "z", "right"),
            _along(h1_descend, STEM_TOP + PITCH * 9, STEM_BOTTOM, "x*", "right"),
            # the main hairpin. Its ascending arm faces the inhibitory one across a gap of
            # 34 units, so both of its labels sit on the far side of that arm.
            _along(H2_X, STEM_TOP, LOOP_FROM, "k1*", "left"),
            _along(H2_X, LOOP_TO, STEM_BOTTOM, "main_pre*", "left"),
            _along(h2_descend, STEM_TOP, LOOP_FROM, "main_z", "right"),
            _along(h2_descend, LOOP_TO, STEM_BOTTOM, "main_pre", "right"),
            f'<text class="st-domain" x="{H2_X - 16:.1f}" y="{mid_loop + 4:.1f}" '
            f'text-anchor="end">bulge*</text>',
        )
    )


def _pill(cx: float, cy: float, label: str, kind: str) -> str:
    """A labelled element centred on (cx, cy). `kind` is "rbs", "aug" or "loop"."""
    return (
        f'<rect class="st-{kind}" x="{cx - PILL_W / 2:.1f}" y="{cy - PILL_H / 2:.1f}" '
        f'width="{PILL_W}" height="{PILL_H}" rx="{9 if kind != "aug" else 3}" />\n    '
        f'<text class="st-pill-text st-pill-text--{kind}" x="{cx:.1f}" '
        f'y="{cy + 4.5:.1f}" text-anchor="middle">{label}</text>'
    )


def _bulge(cx: float, cy: float) -> str:
    """The three unpaired bases facing the start codon across the main stem.

    Drawn as three open circles on the ascending arm rather than labelled, because the
    thing worth seeing is that they are UNPAIRED and that there are exactly as many of
    them as there are bases in the codon opposite. A word here would not fit and would
    not say more.
    """
    return "\n    ".join(
        f'<circle class="st-bulge" cx="{cx:.1f}" cy="{cy + offset:.1f}" r="3.2" />'
        for offset in (-PITCH, 0, PITCH)
    )


def _symbol(cx: float, label: str) -> str:
    """A short symbol under the baseline, with a tick up to whatever it names."""
    return (
        f'<line class="st-lead" x1="{cx:.1f}" y1="{BASE_Y + 5:.1f}" '
        f'x2="{cx:.1f}" y2="{SYMBOL_Y - 11:.1f}" />\n    '
        f'<text class="st-symbol" x="{cx:.1f}" y="{SYMBOL_Y:.1f}" '
        f'text-anchor="middle">{label}</text>'
    )


def _gene(active: bool) -> str:
    """The output-gene box at the 3' end."""
    top = BASE_Y - 16
    if active:
        mark = (
            f'<path class="st-tick" d="M {GENE_X + 14:.0f} {top + 16:.0f} '
            f'L {GENE_X + 23:.0f} {top + 25:.0f} L {GENE_X + 38:.0f} {top + 6:.0f}" />'
        )
    else:
        mark = (
            f'<path class="st-cross" d="M {GENE_X + 14:.0f} {top + 7:.0f} '
            f"L {GENE_X + 33:.0f} {top + 26:.0f} M {GENE_X + 14:.0f} {top + 26:.0f} "
            f'L {GENE_X + 33:.0f} {top + 7:.0f}" />'
        )
    label = "Output translated" if active else "No output"
    return (
        f'<rect class="st-gene st-gene--{"on" if active else "off"}" x="{GENE_X}" '
        f'y="{top}" width="{GENE_W}" height="32" rx="4" />\n    {mark}\n    '
        f'<text class="st-gene-text" x="{GENE_X + GENE_W / 2 + 22:.0f}" '
        f'y="{top + 21:.0f}" text-anchor="middle">{label}</text>'
    )


def _trigger(x_from: float, x_to: float, name: str, cls: str) -> str:
    """A bound trigger: an antiparallel strand under the backbone, with duplex rungs."""
    step = (x_to - x_from) / 8
    ticks = "\n    ".join(
        f'<line class="st-duplex" x1="{x_from + step * (i + 1):.1f}" y1="{BASE_Y + 5:.1f}" '
        f'x2="{x_from + step * (i + 1):.1f}" y2="{TRIG_Y - 5:.1f}" />'
        for i in range(7)
    )
    return (
        f"{ticks}\n    "
        f'<path class="st-trig st-trig--{cls}" '
        f'd="M {x_from:.1f} {TRIG_Y} L {x_to:.1f} {TRIG_Y}" />\n    '
        f'<text class="st-end" x="{x_from - 7:.1f}" y="{TRIG_Y + 4:.1f}" '
        f'text-anchor="end">3&#8242;</text>\n    '
        f'<text class="st-end" x="{x_to + 7:.1f}" y="{TRIG_Y + 4:.1f}">5&#8242;</text>\n    '
        f'<text class="st-trig-text st-trig-text--{cls}" x="{(x_from + x_to) / 2:.1f}" '
        f'y="{TRIG_Y + 22:.1f}" text-anchor="middle">{name}</text>'
    )


def _five_prime() -> str:
    return f'<text class="st-end" x="16" y="{BASE_Y + 4:.0f}" text-anchor="end">5&#8242;</text>'


def _closed_pair() -> tuple[str, str]:
    """Both hairpins folded: the drawing shared by panels 00 and 10."""
    h1_path, h1_rungs = _hairpin(
        H1_X,
        enter_x=210,
        exit_x=H1_X + LOOP_R * 2 + 12,
        blocks=((18, STEM_TOP, STEM_BOTTOM),),
    )
    h2_path, h2_rungs = _hairpin(
        H2_X,
        enter_x=H2_X - 12,
        exit_x=H2_X + LOOP_R * 2 + 22,
        blocks=((6, STEM_TOP, LOOP_FROM), (9, LOOP_TO, STEM_BOTTOM)),
    )
    backbone = (
        f'<path class="st-bb" d="M 24 {BASE_Y} {h1_path}{h2_path}L {GENE_X - 10} {BASE_Y}" />'
    )
    return backbone, f"{h1_rungs}\n    {h2_rungs}"


def _shut_decorations() -> str:
    """The pills, the two highlights and the symbols shared by panels 00 and 10."""
    descend = H1_X + LOOP_R * 2
    return f"""<path class="st-toehold" d="M 28 {BASE_Y} L 196 {BASE_Y}" />
    <path class="st-site" d="M {descend} {STEM_TOP} L {descend} {STEM_BOTTOM}" />
    {_pill(H1_X + LOOP_R, APEX_Y - LOOP_R + 2, "15 nt", "loop")}
    {_pill(H2_X + LOOP_R + 9, APEX_Y - LOOP_R + 2, "RBS", "rbs")}
    {_pill(H2_X + LOOP_R + 9, (LOOP_FROM + LOOP_TO) / 2, "AUG", "aug")}
    {_bulge(H2_X, (LOOP_FROM + LOOP_TO) / 2)}
    {_symbol(H2_X - 6, "a = 0")}
    {_domain_labels()}"""


# --- The four panels -----------------------------------------------------------------


def panel_00() -> str:
    """Neither trigger. Both hairpins shut; trigger A has nowhere to bind."""
    backbone, rungs = _closed_pair()
    return f"""
    {backbone}
    {rungs}
    <text class="st-name" x="300" y="{NAME_Y}" text-anchor="end">inhibitory hairpin</text>
    <text class="st-name" x="322" y="{NAME_Y}">main hairpin</text>
    {_shut_decorations()}
    {_five_prime()}
    {_gene(active=False)}
    """


def panel_10() -> str:
    """Trigger A alone. The same molecule as 00, and A is left holding nothing."""
    backbone, rungs = _closed_pair()
    return f"""
    {backbone}
    {rungs}
    <text class="st-name" x="300" y="{NAME_Y}" text-anchor="end">inhibitory hairpin</text>
    <text class="st-name" x="322" y="{NAME_Y}">main hairpin</text>
    {_shut_decorations()}
    <path class="st-trig st-trig--a" d="M 470 {TRIG_Y} L 600 {TRIG_Y}" />
    <text class="st-trig-text st-trig-text--a" x="535" y="{TRIG_Y + 22}"
      text-anchor="middle">Trigger A</text>
    <path class="st-cross-big" d="M 622 {TRIG_Y - 10} L 642 {TRIG_Y + 10}
      M 622 {TRIG_Y + 10} L 642 {TRIG_Y - 10}" />
    {_five_prime()}
    {_gene(active=False)}
    """


def panel_01() -> str:
    """Trigger B alone. The inhibitory hairpin opens; the main one does not."""
    open_to = 396
    h2_x = 418
    h2_path, h2_rungs = _hairpin(
        h2_x,
        enter_x=open_to,
        exit_x=h2_x + LOOP_R * 2 + 22,
        blocks=((6, STEM_TOP, LOOP_FROM), (9, LOOP_TO, STEM_BOTTOM)),
    )
    return f"""
    <path class="st-bb" d="M 24 {BASE_Y} L {open_to} {BASE_Y} {h2_path}L {GENE_X - 10} {BASE_Y}" />
    {h2_rungs}
    <text class="st-name" x="200" y="{NAME_Y}" text-anchor="middle">inhibitory hairpin opened</text>
    <text class="st-name" x="444" y="{NAME_Y}" text-anchor="middle">main hairpin</text>
    <path class="st-toehold" d="M 28 {BASE_Y} L 196 {BASE_Y}" />
    <path class="st-open" d="M 296 {BASE_Y} L {open_to} {BASE_Y}" />
    {_pill(h2_x + LOOP_R + 9, APEX_Y - LOOP_R + 2, "RBS", "rbs")}
    {_pill(h2_x + LOOP_R + 9, (LOOP_FROM + LOOP_TO) / 2, "AUG", "aug")}
    {_bulge(h2_x, (LOOP_FROM + LOOP_TO) / 2)}
    {_symbol(346, "x* free")}
    <text class="st-domain" x="34" y="{BASE_Y + 16}">cap</text>
    <text class="st-domain" x="112" y="{BASE_Y + 16}" text-anchor="middle">r2*</text>
    <text class="st-domain" x="228" y="{BASE_Y + 16}" text-anchor="middle">x &#183; k2*</text>
    <text class="st-domain" x="330" y="{BASE_Y + 16}" text-anchor="middle">z &#183; x*</text>
    <text class="st-domain" x="{GENE_X - 86}" y="{BASE_Y + 16}">linker</text>
    {_along(h2_x, STEM_TOP, LOOP_FROM, "k1*", "left")}
    {_along(h2_x, LOOP_TO, STEM_BOTTOM, "main_pre*", "left")}
    {_along(h2_x + LOOP_R * 2, STEM_TOP, LOOP_FROM, "main_z", "right")}
    {_along(h2_x + LOOP_R * 2, LOOP_TO, STEM_BOTTOM, "main_pre", "right")}
    <text class="st-domain" x="{h2_x - 16}" y="{(LOOP_FROM + LOOP_TO) / 2 + 4}"
      text-anchor="end">bulge*</text>
    {_trigger(30, 266, "Trigger B", "b")}
    {_five_prime()}
    {_gene(active=False)}
    """


def panel_11() -> str:
    """Both triggers. Both hairpins open, the footprint is clear, translation proceeds."""
    return f"""
    <path class="st-bb" d="M 24 {BASE_Y} L {GENE_X - 10} {BASE_Y}" />
    <text class="st-name" x="300" y="{NAME_Y}" text-anchor="middle">both hairpins opened</text>
    <path class="st-toehold" d="M 28 {BASE_Y} L 196 {BASE_Y}" />
    <path class="st-open" d="M 470 {BASE_Y} L 664 {BASE_Y}" />
    {_pill(494, BASE_Y, "RBS", "rbs")}
    {_pill(548, BASE_Y, "AUG", "aug")}
    <text class="st-domain" x="34" y="{BASE_Y + 16}">cap</text>
    <text class="st-domain" x="112" y="{BASE_Y + 16}" text-anchor="middle">r2*</text>
    <text class="st-domain" x="228" y="{BASE_Y + 16}" text-anchor="middle">x &#183; k2*</text>
    <text class="st-domain" x="330" y="{BASE_Y + 16}" text-anchor="middle">z &#183; x*</text>
    <text class="st-domain" x="414" y="{BASE_Y + 16}"
      text-anchor="middle">main_pre* &#183; k1*</text>
    <text class="st-domain" x="574" y="{BASE_Y + 16}" text-anchor="middle">main_z</text>
    <text class="st-domain" x="{GENE_X - 86}" y="{BASE_Y + 16}">linker</text>
    <ellipse class="st-ribo" cx="612" cy="{BASE_Y}" rx="44" ry="22" />
    <text class="st-name" x="612" y="{BASE_Y - 36}" text-anchor="middle">30S ribosome</text>
    {_trigger(30, 266, "Trigger B", "b")}
    {_trigger(318, 456, "Trigger A", "a")}
    {_five_prime()}
    {_gene(active=True)}
    """


PANELS = (
    (
        "00",
        "Neither trigger",
        "Both hairpins shut. Trigger A&#8217;s site is paired inside the inhibitory stem.",
        panel_00,
    ),
    (
        "10",
        "Trigger A alone &#8212; the second of the cascade",
        "The molecule is unchanged: A arrives at a shut gate and finds no site.",
        panel_10,
    ),
    (
        "01",
        "Trigger B alone &#8212; the first of the cascade",
        "B opens the inhibitory hairpin and exposes x*. Primed, and still off.",
        panel_01,
    ),
    (
        "11",
        "Both triggers",
        "B primes, A invades the main stem, and the footprint comes free.",
        panel_11,
    ),
)

ARIA = (
    "The two-input toehold AND gate in all four tube states. With neither trigger both "
    "hairpins are shut and trigger A's binding site is paired inside the inhibitory stem, "
    "so it has nothing to bind. Trigger A alone changes nothing. Trigger B alone opens the "
    "inhibitory hairpin and exposes A's site, but leaves the ribosome binding site and "
    "start codon buried. Only with both triggers is the start codon free and the output "
    "translated."
)


def build() -> str:
    # Read off the family so the figure cannot drift from the code it describes.
    secondary_loop = len(Gate.SECONDARY_LOOP)
    rbs_loop = len(Gate.RBS_FLANK) + len(Gate.RBS_PROKARYOTIC)
    assert secondary_loop == 15, f"the inhibitory loop is {secondary_loop} nt, not 15"
    assert rbs_loop == 18, f"the RBS loop is {rbs_loop} nt, not 18"

    total = PANEL_H * len(PANELS) + 16
    out = [f'<svg viewBox="0 0 {WIDTH} {total}" role="img" aria-label="{ARIA}">']
    for index, (state, title, caption, draw) in enumerate(PANELS):
        out.append(f'  <g transform="translate(0,{index * PANEL_H})">')
        out.append(f'    <text class="st-state" x="8" y="26">{state}</text>')
        out.append(f'    <text class="st-title" x="56" y="26">{title}</text>')
        out.append(f'    <text class="st-caption" x="56" y="46">{caption}</text>')
        out.append(draw())
        if index < len(PANELS) - 1:
            out.append(
                f'    <line class="st-divider" x1="8" y1="{PANEL_H - 12}" '
                f'x2="{WIDTH - 8}" y2="{PANEL_H - 12}" />'
            )
        out.append("  </g>")
    out.append("</svg>")
    return "\n".join(out)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Draw the AND gate in all four states.")
    parser.add_argument("--out", default="and-gate-states.svg", help="where to write the SVG")
    args = parser.parse_args(argv)
    svg = build()
    pathlib.Path(args.out).write_text(svg, encoding="utf-8")
    print(f"{args.out}: {len(svg):,} characters, {len(PANELS)} panels")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
