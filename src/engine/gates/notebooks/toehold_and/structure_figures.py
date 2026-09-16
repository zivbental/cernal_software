"""Draw each design's folded OFF state, annotated with its own four-tube results.

    uv run python src/engine/gates/notebooks/toehold_and/structure_figures.py \\
        --fasta "path/to/mCherry original.txt" --out figures --designs 3

**The layout comes from ViennaRNA, the drawing does not.** ``naview_xy_coordinates``
places every nucleotide of the predicted OFF structure; everything after that — backbone
weight, base-pair rungs, translucent domain highlights, leader lines — is drawn here, in
the same visual language as the project's hand-drawn schematic. A raw ``RNAplot`` output
would be legible but anonymous, and it could not carry the per-domain measurements, which
are the reason the figure exists.

One SVG per design. Each carries **that design's** numbers, not a representative set: the
four ``dG_open`` values, ``A_M`` and ``A_S`` per state, the toehold's availability, and the
decomposition of what trigger A's nucleation site is paired *to* — locked inside the
hairpin, or engaged by trigger A. That last one is the measurement ``A_S`` cannot make,
since an unpaired probability cannot tell a site held shut by the switch from one held by
the trigger.
"""

import argparse
import statistics
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[4]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import RNA  # noqa: E402  — this file draws, it does not fold for the pipeline

from engine import sequences as sq  # noqa: E402
from engine.domain import Host  # noqa: E402
from engine.gates.toehold import ProkaryoticToeholdAndGate  # noqa: E402
from engine.gates.tools.codons import CodonOptimizer  # noqa: E402
from engine.gates.tools.folding import FoldEngine  # noqa: E402
from engine.gates.tools.translation import TranslationScorer  # noqa: E402

#: Palette lifted from the project's own schematic so the generated figures sit beside it.
INK = "#141413"
GREY = "#3D3D3A"
MUTED = "#5F5E5A"
PAPER = "#F1EFE8"
INDIGO, INDIGO_DK = "#534AB7", "#3C3489"
GREEN, GREEN_DK = "#639922", "#3B6D11"
RED, RED_DK = "#A32D2D", "#791F1F"
ORANGE, ORANGE_DK = "#E07A2C", "#A0521E"
TEAL, TEAL_DK = "#5DCAA5", "#0F6E56"
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif"

#: Which domains get a highlight, in what colour, and how they are named to a reader.
HIGHLIGHTS = [
    ("r2_star", INDIGO, INDIGO_DK, "r2* — free toehold, trigger B lands here"),
    ("sw_x", TEAL, TEAL_DK, "sw_x"),
    ("k2_star", TEAL, TEAL_DK, "k2*"),
    ("secondary_z", ORANGE, ORANGE_DK, "secondaryZ"),
    ("sw_xs", RED, RED_DK, "x* — trigger A's only nucleation site"),
    ("rbs_loop", GREEN, GREEN_DK, "RBS loop"),
    ("aug", RED, RED_DK, "AUG"),
]


def esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def layout(structure: str) -> list[tuple[float, float]]:
    """Nucleotide positions for a dot-bracket structure, from ViennaRNA's naview layout.

    The vector comes back one longer than the sequence — the trailing entry is padding, not
    a base — so it is trimmed here rather than by every caller.
    """
    coords = RNA.naview_xy_coordinates(structure)
    return [(coords[i].X, coords[i].Y) for i in range(len(structure))]


def pair_table(structure: str) -> dict[int, int]:
    stack, pairs = [], {}
    for index, char in enumerate(structure):
        if char == "(":
            stack.append(index)
        elif char == ")":
            opened = stack.pop()
            pairs[opened] = index
            pairs[index] = opened
    return pairs


def fit(points, width, height, pad):
    """Scale a layout into a box, preserving aspect so no helix is sheared."""
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    span_x, span_y = max(xs) - min(xs) or 1, max(ys) - min(ys) or 1
    scale = min((width - 2 * pad) / span_x, (height - 2 * pad) / span_y)
    off_x = pad + (width - 2 * pad - span_x * scale) / 2 - min(xs) * scale
    off_y = pad + (height - 2 * pad - span_y * scale) / 2 - min(ys) * scale
    # SVG y grows downward; the layout's does not, so it is flipped about the box.
    return [(x * scale + off_x, height - (y * scale + off_y)) for x, y in points]


def draw(design, out_path: Path) -> None:
    switch = design["switch"]
    structure = design["off_mfe"]
    domains = design["domains"]
    o = design["observables"]

    W, H = 1000, 640
    plot_w = 600
    points = fit(layout(structure), plot_w, H - 120, 46)
    points = [(x + 8, y + 74) for x, y in points]
    pairs = pair_table(structure)

    svg = [
        f'<svg width="100%" viewBox="0 0 {W} {H}" role="img" xmlns="http://www.w3.org/2000/svg">',
        f"<title>{esc(design['label'])} — predicted OFF state with four-tube results</title>",
        f"<desc>{esc(design['label'])}: the switch folded with no trigger present, "
        "annotated with the accessibility and opening-cost measurements from all four "
        "logic states.</desc>",
        f'<rect width="{W}" height="{H}" fill="{PAPER}"/>',
        f'<text x="24" y="30" font-family="{FONT}" font-size="14" font-weight="500" '
        f'fill="{INK}">{esc(design["label"])} — predicted OFF state, '
        f"{len(switch)} nt</text>",
        f'<text x="24" y="50" font-family="{FONT}" font-size="12" fill="{GREY}">'
        f"MFE {design['mfe']:.1f} kcal/mol · layout by ViennaRNA naview · "
        f"stem {esc(design['scheme'])}, lock {design['lock']:.1f} kcal/mol</text>",
    ]

    # base-pair rungs first, so the backbone sits over them
    drawn = set()
    for i, j in pairs.items():
        if (j, i) in drawn or i > j:
            continue
        drawn.add((i, j))
        x1, y1 = points[i]
        x2, y2 = points[j]
        svg.append(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{INK}" stroke-width="1" opacity="0.55"/>'
        )

    # domain highlights, under the backbone so the backbone reads continuous
    for name, colour, _dark, _label in HIGHLIGHTS:
        start, end = domains[name]
        segment = " ".join(
            f"{'M' if k == start else 'L'} {points[k][0]:.1f} {points[k][1]:.1f}"
            for k in range(start, end)
        )
        svg.append(
            f'<path d="{segment}" fill="none" stroke="{colour}" stroke-width="7" '
            f'stroke-linecap="round" stroke-linejoin="round" opacity="0.42"/>'
        )

    backbone = " ".join(
        f"{'M' if k == 0 else 'L'} {x:.1f} {y:.1f}" for k, (x, y) in enumerate(points)
    )
    svg.append(
        f'<path d="{backbone}" fill="none" stroke="{INK}" stroke-width="2.2" '
        f'stroke-linecap="round" stroke-linejoin="round"/>'
    )

    # 5' and 3' ends
    for index, text, anchor in ((0, "5&#8242;", "end"), (len(points) - 1, "3&#8242;", "start")):
        x, y = points[index]
        svg.append(
            f'<text x="{x + (-8 if anchor == "end" else 8):.1f}" y="{y + 4:.1f}" '
            f'text-anchor="{anchor}" font-family="{FONT}" font-size="12" '
            f'fill="{GREY}">{text}</text>'
        )

    # domain labels, placed at each highlight's midpoint
    for name, _colour, dark, label in HIGHLIGHTS:
        start, end = domains[name]
        mid = (start + end) // 2
        x, y = points[mid]
        short = label.split(" — ")[0]
        svg.append(
            f'<text x="{x:.1f}" y="{y - 9:.1f}" text-anchor="middle" font-family="{FONT}" '
            f'font-size="10.5" font-weight="500" fill="{dark}">{esc(short)}</text>'
        )

    # ---- measurement panel -------------------------------------------------------
    px = plot_w + 40
    svg.append(
        f'<line x1="{px - 18}" y1="70" x2="{px - 18}" y2="{H - 30}" stroke="{GREY}" '
        f'stroke-width="1" opacity="0.35"/>'
    )

    def head(y, text):
        svg.append(
            f'<text x="{px}" y="{y}" font-family="{FONT}" font-size="11" '
            f'font-weight="600" fill="{INK}" letter-spacing="0.06em">{esc(text)}</text>'
        )

    def row(y, label, values, flags=()):
        svg.append(
            f'<text x="{px}" y="{y}" font-family="{FONT}" font-size="11.5" '
            f'fill="{GREY}">{esc(label)}</text>'
        )
        for k, value in enumerate(values):
            colour = RED_DK if k < len(flags) and flags[k] else INK
            weight = "600" if k < len(flags) and flags[k] else "400"
            svg.append(
                f'<text x="{px + 150 + k * 62}" y="{y}" text-anchor="end" '
                f'font-family="{FONT}" font-size="11.5" font-weight="{weight}" '
                f'fill="{colour}">{esc(value)}</text>'
            )

    y = 96
    head(y, "FOUR TUBES")
    y += 20
    row(y, "state", ["00", "01", "10", "11"])
    svg.append(
        f'<line x1="{px}" y1="{y + 6}" x2="{px + 336}" y2="{y + 6}" stroke="{GREY}" '
        f'stroke-width="1" opacity="0.4"/>'
    )
    y += 24
    row(y, "dG_open (kcal/mol)", [f"{o[f'dG_open_{s}']:.2f}" for s in ("00", "01", "10", "11")])
    y += 20
    am = [o[f"A_M_{s}"] for s in ("00", "01", "10", "11")]
    row(
        y,
        "A_M  main arm",
        [f"{v:.3f}" for v in am],
        flags=[False, False, am[2] >= 0.2, am[3] <= 0.5],
    )
    y += 20
    a_s = [o[f"A_S_{s}"] for s in ("00", "01", "10", "11")]
    row(y, "A_S  x* unpaired", [f"{v:.3f}" for v in a_s])
    y += 20
    row(y, "x* locked", [f"{v:.3f}" for v in design["locked"]])
    y += 20
    row(y, "x* engaged by A", [f"{v:.3f}" for v in design["engaged"]])

    y += 34
    head(y, "SINGLE NUMBERS")
    y += 22
    for label, value, failed in design["singles"]:
        svg.append(
            f'<text x="{px}" y="{y}" font-family="{FONT}" font-size="11.5" '
            f'fill="{GREY}">{esc(label)}</text>'
        )
        svg.append(
            f'<text x="{px + 336}" y="{y}" text-anchor="end" font-family="{FONT}" '
            f'font-size="11.5" font-weight="{"600" if failed else "400"}" '
            f'fill="{RED_DK if failed else INK}">{esc(value)}</text>'
        )
        y += 20

    y += 14
    note = design["note"]
    svg.append(
        f'<rect x="{px - 6}" y="{y - 14}" width="348" height="{18 * len(note) + 14}" '
        f'fill="#FFFFFF" opacity="0.55" rx="2"/>'
    )
    for line in note:
        svg.append(
            f'<text x="{px}" y="{y}" font-family="{FONT}" font-size="11" '
            f'fill="{MUTED}">{esc(line)}</text>'
        )
        y += 16

    svg.append("</svg>")
    out_path.write_text("\n".join(svg), encoding="utf-8")


def build(gate, transcript, pair, stem, label):
    switch = gate.assemble(
        transcript[slice(*pair.window_a())], transcript[slice(*pair.window_b())], pair.len_x, stem
    )
    trigger_a = transcript[slice(*pair.window_a())]
    trigger_b = transcript[slice(*pair.window_b())]
    o = gate.four_tube_observables(switch, trigger_a, trigger_b)

    sequence = switch.sequence
    fold = gate.folder.mfe(sequence)
    n = len(sequence)
    xs, swx = switch.domains["sw_xs"], switch.domains["sw_x"]
    locked, engaged = [], []
    for _state, strands, has_a in (
        ("00", sequence, False),
        ("01", f"{sequence}&{trigger_b}", False),
        ("10", f"{sequence}&{trigger_a}", True),
        ("11", f"{sequence}&{trigger_a}&{trigger_b}", True),
    ):
        matrix = gate.folder.base_pair_probabilities(strands)
        locked.append(statistics.mean(sum(matrix[i][j] for j in range(*swx)) for i in range(*xs)))
        engaged.append(
            statistics.mean(
                sum(matrix[i][j] for j in range(n, n + len(trigger_a))) for i in range(*xs)
            )
            if has_a
            else 0.0
        )

    off = [o["dG_open_00"], o["dG_open_01"]]
    sep_no_ten = min(v - o["dG_open_11"] for v in off)
    singles = [
        ("separation (all OFF states)", f"{o['separation']:.2f}", o["separation"] <= 1.5),
        ("separation (excluding 10)", f"{sep_no_ten:.2f}", sep_no_ten <= 1.5),
        ("ddG_AND", f"{o['ddG_AND']:.2f}", o["ddG_AND"] >= -1.0),
        ("A(r2*|00)   τ8 > 0.5", f"{o['A_r2_star_00']:.3f}", o["A_r2_star_00"] <= 0.5),
        ("d(Ω00)   τ9 < 0.1", f"{o['d_off']:.3f}", o["d_off"] >= 0.1),
        ("dG_bind_B", f"{o['dG_bind_B']:.1f}", False),
        ("dG_bind_A | B", f"{o['dG_bind_A_given_B']:.1f}", False),
        ("ddG_pref (stem)", f"{stem.ddg_pref:.2f}", stem.ddg_pref < 0),
    ]
    note = [
        "dG_open(10) = dG_open(11): trigger A opens the main",
        "hairpin whether or not B has acted. x* still shows the",
        "designed behaviour — locked in 00, free in 01 — so the",
        "inhibitory hairpin works; the discrimination is kinetic.",
    ]
    return {
        "label": label,
        "scheme": stem.scheme,
        "lock": stem.lock_energy,
        "switch": sequence,
        "off_mfe": fold.structure,
        "mfe": fold.energy,
        "domains": switch.domains,
        "observables": o,
        "locked": locked,
        "engaged": engaged,
        "singles": singles,
        "note": note,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fasta", required=True)
    parser.add_argument("--out", default="figures")
    parser.add_argument("--designs", type=int, default=3, help="one per stem family")
    args = parser.parse_args(argv)

    gate = ProkaryoticToeholdAndGate(
        Host.ECOLI, FoldEngine(37.0), TranslationScorer(Host.ECOLI), CodonOptimizer(Host.ECOLI)
    )
    lines = Path(args.fasta).read_text().splitlines()
    transcript = sq.to_rna("".join(x.strip() for x in lines if not x.startswith(">")))

    candidates = []
    for pair in gate.find_trigger_pairs(transcript):
        start, end = pair.window_a()
        if gate.screen_trigger_window(transcript[start:end], transcript[pair.x_start - 9 :][:9]):
            continue
        candidates.append(pair)
    candidates.sort(key=lambda p: (-p.len_x, -p.gap()))
    pair = candidates[0]

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stems = gate.secondary_stems(
        transcript[slice(*pair.window_a())], transcript[slice(*pair.window_b())], pair.len_x
    )
    print(f"pair x@{pair.x_start} len_x={pair.len_x}: {len(stems)} builds on the frontier")

    made = 0
    for family in ("A-anchored", "B-anchored", "mixed"):
        members = sorted((s for s in stems if s.scheme == family), key=lambda s: s.lock_energy)
        if not members or made >= args.designs:
            continue
        stem = members[0]
        label = f"x@{pair.x_start} · {family}"
        design = build(gate, transcript, pair, stem, label)
        path = out / f"design_x{pair.x_start}_{family.replace('-', '_')}.svg"
        draw(design, path)
        print(f"  {family:<11} lock {stem.lock_energy:>7.1f}  ->  {path}")
        made += 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
