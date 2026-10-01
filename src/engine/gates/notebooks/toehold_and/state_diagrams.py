"""Schematics of the four logic states — what the gate is *meant* to do, and what it does.

    uv run python src/engine/gates/notebooks/toehold_and/state_diagrams.py --out figures

These are explanatory drawings, not structure predictions: idealised hairpins in the
project's own schematic language, one panel per logic state, so the mechanism can be
followed without reading a 161-nt fold. The nucleotide-level plots of specific candidates
are a different job and live in ``structure_figures.py``.

Every panel is laid out on a fixed grid — a title band, a drawing band and a reserved
annotation band — and every label is anchored to a slot inside its own band. Nothing is
placed relative to a curve, so no annotation can drift onto another as the geometry
changes.

Where the measured behaviour departs from the intent, the panel says so rather than drawing
the intent alone. State 10 is the case that matters: the drawing shows trigger A with
nowhere to land, which is what ``a = 0`` is for, and the note records that at equilibrium it
opens the main hairpin regardless.
"""

import argparse
from pathlib import Path

INK = "#141413"
GREY = "#3D3D3A"
MUTED = "#5F5E5A"
PAPER = "#F1EFE8"
INDIGO, INDIGO_DK = "#534AB7", "#3C3489"
GREEN_DK = "#3B6D11"
RED, RED_DK = "#A32D2D", "#791F1F"
ORANGE_DK = "#A0521E"
TEAL, TEAL_DK = "#5DCAA5", "#0F6E56"
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif"

W = 920
PANEL_H = 268
BASE = 178  # backbone baseline inside a panel
STEM_TOP = 62  # top of a hairpin stem inside a panel
LOOP_R = 26

LEFT = 56  # 5' end
# SVG canvas x-coordinates in PIXELS, not nucleotide indices -- this is a hand-drawn
# schematic on a ~1000 px canvas, so the numbers are unrelated to the 161-nt switch.
# The two hairpins used to share x = 320 (SEC_R == MAIN_L) to express "a = 0, no gap".
# Drawing them on the same vertical made the path double back and the two hairpin
# outlines overlap. They are now adjacent-but-distinct, and the a = 0 junction is drawn
# as a shared knee instead of a shared line.
SEC_L, SEC_R = 244, 312  # secondary hairpin verticals
MAIN_L, MAIN_R = 326, 394  # main hairpin verticals — 14 px apart, a = 0 marked at the knee
RIGHT = 864  # 3' end


def esc(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def text(x, y, s, *, size=12, fill=GREY, anchor="middle", weight="400"):
    return (
        f'<text x="{x:.0f}" y="{y:.0f}" text-anchor="{anchor}" font-family="{FONT}" '
        f'font-size="{size}" font-weight="{weight}" fill="{fill}">{esc(s)}</text>'
    )


def closed_hairpin(x_l, x_r, y0, *, bulge=False):
    """A shut hairpin: up the left arm, round the loop, down the right arm.

    ``bulge`` puts the 3x3 internal loop opposite the start codon into the descending arm,
    which is where the main hairpin keeps its AUG.
    """
    mid = y0 - 10
    d = [f"L {x_l - 30:.0f} {y0:.0f} Q {x_l:.0f} {y0:.0f} {x_l:.0f} {mid:.0f}"]
    d.append(f"L {x_l:.0f} {STEM_TOP + LOOP_R:.0f}")
    d.append(f"A {LOOP_R} {LOOP_R} 0 1 1 {x_r:.0f} {STEM_TOP + LOOP_R:.0f}")
    if bulge:
        knee = STEM_TOP + LOOP_R + 52
        d.append(f"L {x_r:.0f} {knee:.0f}")
        d.append(f"Q {x_r + 24:.0f} {knee + 17:.0f} {x_r:.0f} {knee + 34:.0f}")
        d.append(f"L {x_r:.0f} {mid:.0f}")
    else:
        d.append(f"L {x_r:.0f} {mid:.0f}")
    d.append(f"Q {x_r:.0f} {y0:.0f} {x_r + 30:.0f} {y0:.0f}")
    return " ".join(d)


def rungs(x_l, x_r, y0, *, skip=()):
    out = []
    y = STEM_TOP + LOOP_R + 14
    while y < y0 - 18:
        if not any(lo <= y <= hi for lo, hi in skip):
            out.append(
                f'<line x1="{x_l:.0f}" y1="{y:.0f}" x2="{x_r:.0f}" y2="{y:.0f}" '
                f'stroke="{INK}" stroke-width="1" opacity="0.6"/>'
            )
        y += 16
    return out


def duplex(x1, x2, y0, offset, colour, *, label=None, label_dy=-26):
    """A trigger lying alongside the backbone, with pairing rungs between the two."""
    out = [
        f'<path d="M {x1:.0f} {y0 - offset:.0f} L {x2:.0f} {y0 - offset:.0f}" fill="none" '
        f'stroke="{colour}" stroke-width="3" stroke-linecap="round"/>'
    ]
    x = x1 + 10
    while x < x2 - 6:
        out.append(
            f'<line x1="{x:.0f}" y1="{y0 - offset + 3:.0f}" x2="{x:.0f}" y2="{y0 - 3:.0f}" '
            f'stroke="{colour}" stroke-width="1" opacity="0.65"/>'
        )
        x += 15
    if label:
        out.append(
            text((x1 + x2) / 2, y0 - offset + label_dy, label, size=11.5, fill=colour, weight="500")
        )
    return out


def highlight(d, colour, width=7):
    return (
        f'<path d="{d}" fill="none" stroke="{colour}" stroke-width="{width}" '
        f'stroke-linecap="round" opacity="0.38"/>'
    )


def panel(state, top):
    """One logic state. Returns the SVG fragments for the panel at vertical offset ``top``."""
    y0 = top + BASE
    o = []

    def T(x, y, s, **kw):
        return text(x, y + top, s, **kw)

    titles = {
        "00": ("State 00 — neither trigger", "both hairpins shut, the toehold free and waiting"),
        "01": (
            "State 01 — trigger B only",
            "B opens the inhibitory hairpin and exposes x*; the main hairpin stays shut",
        ),
        "10": (
            "State 10 — trigger A only",
            "a = 0, so A has no exposed nucleotide to land on — the intent",
        ),
        "11": (
            "State 11 — both triggers",
            "x* is free, A nucleates there and opens the main hairpin: output",
        ),
    }
    head, sub = titles[state]
    o.append(T(LEFT - 16, 26, head, size=13.5, fill=INK, anchor="start", weight="600"))
    o.append(T(LEFT - 16, 44, sub, size=11.5, fill=MUTED, anchor="start"))

    sec_open = state in ("01", "11")
    main_open = state == "11"

    # ---- backbone -----------------------------------------------------------------
    path = [f"M {LEFT:.0f} {y0:.0f}"]
    if sec_open:
        path.append(f"L {SEC_R + 30:.0f} {y0:.0f}")
    else:
        path.append(closed_hairpin(SEC_L, SEC_R, y0))
    if main_open:
        path.append(f"L {RIGHT:.0f} {y0:.0f}")
    else:
        path.append(closed_hairpin(MAIN_L, MAIN_R, y0, bulge=True))
        path.append(f"L {RIGHT:.0f} {y0:.0f}")
    d = " ".join(path)

    # domain highlights sit under the backbone
    o.append(highlight(f"M {LEFT + 4:.0f} {y0:.0f} L {SEC_L - 34:.0f} {y0:.0f}", INDIGO))
    if not sec_open:
        o.append(
            highlight(
                f"M {SEC_R:.0f} {STEM_TOP + LOOP_R + 30:.0f} L {SEC_R:.0f} {y0 - 14:.0f}", RED
            )
        )
    else:
        o.append(highlight(f"M {SEC_L - 10:.0f} {y0:.0f} L {SEC_R + 24:.0f} {y0:.0f}", RED))

    o.append(
        f'<path d="{d}" fill="none" stroke="{INK}" stroke-width="2.5" stroke-linecap="round"/>'
    )

    if not sec_open:
        o.extend(rungs(SEC_L, SEC_R, y0))
    if not main_open:
        knee = STEM_TOP + LOOP_R + 52
        o.extend(rungs(MAIN_L, MAIN_R, y0, skip=((knee - 6, knee + 40),)))

    # ---- triggers ------------------------------------------------------------------
    if state in ("01", "11"):
        o.extend(duplex(LEFT + 8, SEC_R + 20, y0, 22, TEAL_DK, label="trigger B"))
    if state == "11":
        o.extend(duplex(SEC_R + 34, RIGHT - 300, y0, 22, ORANGE_DK, label="trigger A"))
    if state == "10":
        o.append(
            f'<path d="M {LEFT + 150:.0f} {top + 78:.0f} L {LEFT + 330:.0f} {top + 78:.0f}" '
            f'fill="none" stroke="{ORANGE_DK}" stroke-width="3" stroke-linecap="round" '
            f'stroke-dasharray="7 5"/>'
        )
        o.append(
            T(
                LEFT + 240,
                68,
                "trigger A — nowhere to bind",
                size=11.5,
                fill=ORANGE_DK,
                weight="500",
            )
        )

    # ---- fixed annotation slots ----------------------------------------------------
    o.append(T(LEFT - 16, BASE + 6, "5'", size=12, anchor="end"))
    o.append(T(RIGHT + 16, BASE + 6, "3'", size=12, anchor="start"))
    o.append(
        T((LEFT + SEC_L - 34) / 2, BASE + 26, "r2* toehold (32 nt)", size=11.5, fill=INDIGO_DK)
    )
    if not sec_open:
        o.append(T((SEC_L + SEC_R) / 2, BASE + 26, "inhibitory hairpin", size=11.5, fill=TEAL_DK))
        o.append(
            T(
                SEC_R + 6,
                STEM_TOP + LOOP_R + 92 - BASE + BASE,
                "x*",
                size=11,
                fill=RED_DK,
                anchor="start",
            )
        )
    else:
        o.append(T((SEC_L + SEC_R) / 2 + 10, BASE + 26, "x* exposed", size=11.5, fill=RED_DK))
    if not main_open:
        o.append(
            T(
                (MAIN_L + MAIN_R) / 2 + 40,
                BASE + 26,
                "main hairpin — RBS and AUG shut",
                size=11.5,
                fill=GREEN_DK,
                anchor="start",
            )
        )
        o.append(
            T(MAIN_R + 30, STEM_TOP + 16, "RBS in loop", size=11, fill=GREEN_DK, anchor="start")
        )
        o.append(
            T(
                MAIN_R + 30,
                STEM_TOP + LOOP_R + 74,
                "AUG in 3x3 bulge",
                size=11,
                fill=RED_DK,
                anchor="start",
            )
        )
    else:
        o.append(
            T(
                RIGHT - 190,
                BASE + 26,
                "RBS and AUG released — translation",
                size=11.5,
                fill=GREEN_DK,
                anchor="middle",
            )
        )
    if state == "00":
        o.append(T(SEC_R + 6, BASE - 96, "a = 0", size=11, fill=MUTED, anchor="start"))

    notes = {
        "00": "Measured: x* locked 0.999, A_M 0.009, dG_open 17.0 kcal/mol. "
        "The OFF state is the structure drawn.",
        "01": "Measured: x* free 1.000, main hairpin still shut at A_M 0.009. "
        "Trigger B does exactly its job.",
        "10": "Measured: A_M 0.518 and dG_open 4.37 — identical to state 11. At equilibrium "
        "A opens the main hairpin anyway; the protection a = 0 gives is kinetic.",
        "11": "Measured: x* engaged by A 0.991, A_M 0.518, dG_open 4.37. Correct behaviour, "
        "but indistinguishable from state 10.",
    }
    colour = RED_DK if state == "10" else MUTED
    o.append(T(LEFT - 16, PANEL_H - 24, notes[state], size=11, fill=colour, anchor="start"))
    return o


def build_svg() -> str:
    states = ("00", "01", "11", "10")
    height = 74 + PANEL_H * len(states)
    out = [
        f'<svg width="100%" viewBox="0 0 {W} {height}" role="img" '
        f'xmlns="http://www.w3.org/2000/svg">',
        "<title>The four logic states of the A0 AND gate</title>",
        "<desc>Schematic of the prokaryotic two-input AND gate in each of its four logic "
        "states, with the measured behaviour noted under each panel.</desc>",
        f'<rect width="{W}" height="{height}" fill="{PAPER}"/>',
        text(40, 34, "The four logic states", size=15, fill=INK, anchor="start", weight="600"),
        text(
            40,
            54,
            "Trigger A is the left digit. Idealised geometry; measured values from the "
            "four-tube evaluation are noted under each panel.",
            size=11.5,
            fill=MUTED,
            anchor="start",
        ),
    ]
    for index, state in enumerate(states):
        top = 74 + PANEL_H * index
        if index:
            out.append(
                f'<line x1="40" y1="{top - 2}" x2="{W - 40}" y2="{top - 2}" stroke="{GREY}" '
                f'stroke-width="1" opacity="0.2"/>'
            )
        out.extend(panel(state, top))
    out.append("</svg>")
    return "\n".join(out)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default="figures")
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "four_states.svg"
    path.write_text(build_svg(), encoding="utf-8")
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
