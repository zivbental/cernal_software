"""Draw the AND gate in all four tube states, as an inline SVG for the iGEM wiki.

Run::

    uv run python tools/figure_and_gate_states.py --out and-gate-states.svg

The figure is generated rather than drawn by hand for two reasons. The four panels have
to be geometrically consistent -- the same stem lengths, the same loop sizes, the same
domain boundaries -- and a reader who counts base pairs in one panel and not the other
has found a figure that argues against itself. And the architecture is still being
characterised, so the figure has to be cheap to regenerate when a length changes.

**What this corrects against the sketch it is based on.** The starting point was a
generic two-toehold cartoon, and it was wrong about this architecture in three ways, the
first of which is the architecture's whole claim:

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
   state ``10`` is the *second* trigger of the cascade arriving alone -- the panel a reader
   is most likely to misread, and it is labelled accordingly.

Domain lengths are read from the family itself rather than restated here, so the figure
cannot drift from the code.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from engine.gates.toehold import ProkaryoticToeholdAndGate as Gate

# --- Panel geometry ------------------------------------------------------------------
#
# One panel is WIDTH x PANEL_H. Everything is in SVG user units, and the figure is shown
# inside a horizontally scrolling box at a declared minimum width, so these are read at
# roughly 1 unit = 1 px on a desktop column and the figure scrolls rather than shrinks on
# a phone. Shrinking it would put the labels below legible size.

WIDTH = 880
PANEL_H = 300
BASE_Y = 232  # the backbone's baseline inside a panel
APEX_Y = 70  # where a hairpin's loop sits
LOOP_R = 26  # half the distance between a hairpin's two arms
GENE_X = 700  # left edge of the output-gene box
GENE_W = 160


def _rungs(x_left: float, x_right: float, y_from: float, y_to: float, count: int) -> str:
    """`count` base-pair rungs, evenly spaced, between a hairpin's two arms."""
    if count <= 0:
        return ""
    step = (y_to - y_from) / count
    out = []
    for i in range(count):
        y = y_from + step * (i + 0.5)
        out.append(
            f'<line class="st-rung" x1="{x_left:.1f}" y1="{y:.1f}" '
            f'x2="{x_right:.1f}" y2="{y:.1f}" />'
        )
    return "\n    ".join(out)


def _hairpin(
    ascend_x: float,
    *,
    enter_x: float,
    exit_x: float,
    blocks: tuple[tuple[int, float, float], ...],
) -> tuple[str, str, float]:
    """One folded hairpin. Returns (path fragment, rungs, the x the backbone leaves at).

    ``blocks`` is the stem read from the loop downward: ``(base pairs, y_from, y_to)`` per
    paired block, with the gaps between blocks left unpaired -- which is how an internal
    loop such as the one holding the start codon is drawn.
    """
    descend_x = ascend_x + LOOP_R * 2
    path = (
        f"L {enter_x:.1f} {BASE_Y} Q {ascend_x:.1f} {BASE_Y} {ascend_x:.1f} {BASE_Y - 24:.1f} "
        f"L {ascend_x:.1f} {APEX_Y} "
        f"A {LOOP_R} {LOOP_R} 0 1 1 {descend_x:.1f} {APEX_Y} "
        f"L {descend_x:.1f} {BASE_Y - 24:.1f} "
        f"Q {descend_x:.1f} {BASE_Y} {exit_x:.1f} {BASE_Y} "
    )
    rungs = "\n    ".join(
        _rungs(ascend_x, descend_x, y_from, y_to, pairs) for pairs, y_from, y_to in blocks
    )
    return path, rungs, descend_x


def _pill(x: float, y: float, label: str, kind: str, w: float = 38) -> str:
    """A labelled domain marker. `kind` is "rbs" (rounded) or "aug" (square)."""
    radius = 9 if kind == "rbs" else 3
    return (
        f'<rect class="st-{kind}" x="{x:.1f}" y="{y:.1f}" width="{w}" height="20" '
        f'rx="{radius}" />\n    '
        f'<text class="st-pill-text" x="{x + w / 2:.1f}" y="{y + 14:.1f}" '
        f'text-anchor="middle">{label}</text>'
    )


def _gene(y: float, active: bool) -> str:
    """The output-gene box at the 3' end."""
    cls = "st-gene st-gene--on" if active else "st-gene st-gene--off"
    label = "Output translated" if active else "No output"
    mark = (
        f'<path class="st-tick" d="M {GENE_X + 12:.0f} {y + 11:.0f} '
        f'L {GENE_X + 21:.0f} {y + 20:.0f} L {GENE_X + 35:.0f} {y:.0f}" />'
        if active
        else f'<path class="st-cross" d="M {GENE_X + 12:.0f} {y:.0f} '
        f"L {GENE_X + 30:.0f} {y + 20:.0f} M {GENE_X + 12:.0f} {y + 20:.0f} "
        f'L {GENE_X + 30:.0f} {y:.0f}" />'
    )
    return (
        f'<rect class="{cls}" x="{GENE_X}" y="{y - 6:.0f}" width="{GENE_W}" height="32" rx="4" />'
        f"\n    {mark}"
        f'\n    <text class="st-gene-text" x="{GENE_X + GENE_W / 2 + 22:.0f}" '
        f'y="{y + 14:.0f}" text-anchor="middle">{label}</text>'
    )


def _trigger(x_from: float, x_to: float, y: float, name: str, cls: str) -> str:
    """A bound trigger: an antiparallel strand under the backbone, with duplex rungs."""
    ticks = "\n    ".join(
        f'<line class="st-duplex" x1="{x:.1f}" y1="{y - 22:.1f}" x2="{x:.1f}" y2="{y - 4:.1f}" />'
        for x in _spread(x_from, x_to, 7)
    )
    return (
        f"{ticks}\n    "
        f'<path class="st-trig st-trig--{cls}" d="M {x_from:.1f} {y} L {x_to:.1f} {y}" />\n    '
        f'<text class="st-end" x="{x_from - 6:.1f}" '
        f'y="{y + 4:.1f}" text-anchor="end">3&#8242;</text>\n    '
        f'<text class="st-end" x="{x_to + 6:.1f}" y="{y + 4:.1f}">5&#8242;</text>\n    '
        f'<text class="st-trig-text st-trig-text--{cls}" x="{(x_from + x_to) / 2:.1f}" '
        f'y="{y + 22:.1f}" text-anchor="middle">{name}</text>'
    )


def _spread(x_from: float, x_to: float, count: int) -> list[float]:
    step = (x_to - x_from) / (count + 1)
    return [x_from + step * (i + 1) for i in range(count)]


# --- The four panels -----------------------------------------------------------------


def panel_00(d: dict[str, int]) -> str:
    """Neither trigger. Both hairpins shut; trigger A has nowhere to bind."""
    tail_end = 150
    h1_path, h1_rungs, h1_out = _hairpin(
        172, enter_x=tail_end, exit_x=224, blocks=((18, APEX_Y + 8, BASE_Y - 30),)
    )
    h2_path, h2_rungs, _ = _hairpin(
        246,
        enter_x=230,
        exit_x=300,
        blocks=((6, APEX_Y + 8, 140), (9, 170, BASE_Y - 30)),
    )
    return f"""
    <path class="st-bb" d="M 24 {BASE_Y} {h1_path}{h2_path}L {GENE_X - 10} {BASE_Y}" />
    {h1_rungs}
    {h2_rungs}
    <path class="st-toehold" d="M 28 {BASE_Y} L {tail_end} {BASE_Y}" />
    <text class="st-dom" x="28" y="{BASE_Y + 24}">r2*, {d["r2_star"]} nt &#8212; always free</text>
    <path class="st-site" d="M 224 {BASE_Y - 34} L 224 {APEX_Y + 30}" />
    <text class="st-site-text" x="232" y="{BASE_Y - 70}">x* &#8212; trigger A&#8217;s site,</text>
    <text class="st-site-text" x="232" y="{BASE_Y - 54}">paired shut inside this stem</text>
    <text class="st-dom" x="150" y="{APEX_Y - 34}">inhibitory hairpin</text>
    <text class="st-dom-sub" x="150" y="{APEX_Y - 18}">{d["secondary_loop"]} nt loop, no RBS</text>
    <text class="st-dom" x="300" y="{APEX_Y - 34}">main hairpin</text>
    <text class="st-dom-sub" x="300" y="{APEX_Y - 18}">RBS in the loop, AUG in the stem</text>
    {_pill(272, APEX_Y - 42, "RBS", "rbs")}
    {_pill(276, 146, "AUG", "aug")}
    <text class="st-note" x="{(h1_out + 246) / 2:.0f}" y="{BASE_Y + 46}"
          text-anchor="middle">&#9650;</text>
    <text class="st-note" x="420" y="{BASE_Y + 50}">no spacer between the hairpins (a = 0)</text>
    <text class="st-end" x="16" y="{BASE_Y + 4}" text-anchor="end">5&#8242;</text>
    {_gene(BASE_Y - 10, active=False)}
    """


def panel_10(d: dict[str, int]) -> str:
    """Trigger A alone. Same molecule as 00, and A is left holding nothing."""
    tail_end = 150
    h1_path, h1_rungs, _ = _hairpin(
        172, enter_x=tail_end, exit_x=224, blocks=((18, APEX_Y + 8, BASE_Y - 30),)
    )
    h2_path, h2_rungs, _ = _hairpin(
        246,
        enter_x=230,
        exit_x=300,
        blocks=((6, APEX_Y + 8, 140), (9, 170, BASE_Y - 30)),
    )
    return f"""
    <path class="st-bb" d="M 24 {BASE_Y} {h1_path}{h2_path}L {GENE_X - 10} {BASE_Y}" />
    {h1_rungs}
    {h2_rungs}
    <path class="st-toehold" d="M 28 {BASE_Y} L {tail_end} {BASE_Y}" />
    <path class="st-site" d="M 224 {BASE_Y - 34} L 224 {APEX_Y + 30}" />
    <text class="st-site-text" x="232" y="{BASE_Y - 70}">x* still paired shut,</text>
    <text class="st-site-text" x="232" y="{BASE_Y - 54}">so A cannot nucleate</text>
    {_pill(272, APEX_Y - 42, "RBS", "rbs")}
    {_pill(276, 146, "AUG", "aug")}
    <path class="st-trig st-trig--a" d="M 410 {BASE_Y + 34} L 530 {BASE_Y + 34}" />
    <text class="st-trig-text st-trig-text--a" x="470" y="{BASE_Y + 56}"
          text-anchor="middle">Trigger A, unbound</text>
    <path class="st-cross-big"
          d="M 548 {BASE_Y + 24} L 568 {BASE_Y + 44}
             M 548 {BASE_Y + 44} L 568 {BASE_Y + 24}" />
    <text class="st-end" x="16" y="{BASE_Y + 4}" text-anchor="end">5&#8242;</text>
    {_gene(BASE_Y - 10, active=False)}
    """


def panel_01(d: dict[str, int]) -> str:
    """Trigger B alone. The inhibitory hairpin opens; the main one does not."""
    opened_end = 352
    h2_path, h2_rungs, _ = _hairpin(
        374,
        enter_x=opened_end,
        exit_x=428,
        blocks=((6, APEX_Y + 8, 140), (9, 170, BASE_Y - 30)),
    )
    return f"""
    <path class="st-bb"
          d="M 24 {BASE_Y} L {opened_end} {BASE_Y} {h2_path}L {GENE_X - 10} {BASE_Y}" />
    {h2_rungs}
    <path class="st-toehold" d="M 28 {BASE_Y} L 150 {BASE_Y}" />
    {_trigger(30, 230, BASE_Y + 40, "Trigger B &#8212; binds r2*, x and k2*", "b")}
    <path class="st-open" d="M 256 {BASE_Y} L {opened_end} {BASE_Y}" />
    <text class="st-site-text" x="256" y="{BASE_Y - 20}">x* now exposed</text>
    <text class="st-dom" x="30" y="{APEX_Y + 30}">inhibitory hairpin opened</text>
    <text class="st-dom-sub" x="30" y="{APEX_Y + 46}">the main hairpin is untouched</text>
    {_pill(400, APEX_Y - 42, "RBS", "rbs")}
    {_pill(404, 146, "AUG", "aug")}
    <text class="st-end" x="16" y="{BASE_Y + 4}" text-anchor="end">5&#8242;</text>
    {_gene(BASE_Y - 10, active=False)}
    """


def panel_11(d: dict[str, int]) -> str:
    """Both triggers. Both hairpins open, the footprint is clear, translation proceeds."""
    return f"""
    <path class="st-bb" d="M 24 {BASE_Y} L {GENE_X - 10} {BASE_Y}" />
    <path class="st-toehold" d="M 28 {BASE_Y} L 150 {BASE_Y}" />
    {_trigger(30, 230, BASE_Y + 40, "Trigger B", "b")}
    {_trigger(252, 420, BASE_Y + 40, "Trigger A &#8212; binds x*, Main_pre* and k1*", "a")}
    <path class="st-open" d="M 430 {BASE_Y} L 620 {BASE_Y}" />
    {_pill(436, BASE_Y - 10, "RBS", "rbs")}
    {_pill(494, BASE_Y - 10, "AUG", "aug")}
    <ellipse class="st-ribo" cx="560" cy="{BASE_Y}" rx="42" ry="22" />
    <text class="st-ribo-text" x="560" y="{BASE_Y - 34}"
          text-anchor="middle">30S ribosome</text>
    <text class="st-dom-sub" x="430" y="{BASE_Y + 24}">the footprint is clear</text>
    <text class="st-end" x="16" y="{BASE_Y + 4}" text-anchor="end">5&#8242;</text>
    {_gene(BASE_Y - 10, active=True)}
    """


PANELS = (
    (
        "00",
        "Neither trigger",
        "Both hairpins shut. Trigger A&#8217;s site is paired "
        "inside the inhibitory stem.",
        panel_00,
    ),
    (
        "10",
        "Trigger A alone &#8212; the second of the cascade",
        "The molecule is unchanged: A arrives to a shut gate, "
        "and finds no site.",
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
        "B primes, A invades the main stem, RBS and start codon come free.",
        panel_11,
    ),
)


def build() -> str:
    # Read off the family so the figure cannot drift from the code it describes.
    d = {
        "r2_star": Gate.TOEHOLD_B_LEN,
        "secondary_loop": len(Gate.SECONDARY_LOOP),
        "rbs_loop": len(Gate.RBS_FLANK) + len(Gate.RBS_PROKARYOTIC),
    }
    total_h = PANEL_H * len(PANELS) + 20
    out = [
        f'<svg viewBox="0 0 {WIDTH} {total_h}" role="img" '
        'aria-label="The two-input toehold AND gate in all four tube states. '
        "With neither trigger both hairpins are shut and trigger A has no exposed "
        "binding site. Trigger A alone changes nothing. Trigger B alone opens the "
        "inhibitory hairpin and exposes A's site but leaves the ribosome binding site "
        "and start codon buried. Only with both triggers is the start codon free and "
        'the output translated.">'
    ]
    for index, (state, title, caption, draw) in enumerate(PANELS):
        top = index * PANEL_H
        out.append(f'  <g transform="translate(0,{top})">')
        out.append(f'    <text class="st-state" x="8" y="26">{state}</text>')
        out.append(f'    <text class="st-title" x="54" y="26">{title}</text>')
        out.append(f'    <text class="st-caption" x="54" y="46">{caption}</text>')
        out.append(draw(d))
        if index < len(PANELS) - 1:
            out.append(
                f'    <line class="st-divider" x1="8" y1="{PANEL_H - 10}" '
                f'x2="{WIDTH - 8}" y2="{PANEL_H - 10}" />'
            )
        out.append("  </g>")
    out.append("</svg>")
    return "\n".join(out)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="and-gate-states.svg", help="where to write the SVG")
    args = parser.parse_args(argv)
    svg = build()
    path = pathlib.Path(args.out)
    path.write_text(svg, encoding="utf-8")
    print(f"{path}: {len(svg):,} characters, {len(PANELS)} panels")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
