"""Nucleotide-level plots of each design's folded OFF state, with its own four-tube results.

    uv run python src/engine/gates/notebooks/toehold_and/structure_figures.py \\
        --fasta "path/to/mCherry original.txt" --out figures

**A real structure plot, not a schematic.** Every base is drawn at the position
``FoldEngine.layout_coordinates`` gives it — ViennaRNA's naview layout, the algorithm
behind ``RNAplot`` and the familiar forna pictures — as a lettered circle, with the
backbone threading through them and a rung on every base pair. Bases are coloured by the
domain they belong to, which forna's own output cannot do and which is the reason these are
worth generating: it makes the hairpins, the toehold and the start codon findable in a
161-nt fold without counting round the loop.

The schematics that explain the *mechanism* are a different job and live in
``state_diagrams.py``. This file draws what a specific candidate actually folds into.

One SVG per design, each carrying **that design's** numbers: the four ``dG_open`` values,
``A_M`` and ``A_S`` per state, the toehold's availability, and what trigger A's nucleation
site is paired *to* — locked inside the hairpin, or engaged by trigger A. That last pair is
the measurement ``A_S`` cannot make, since an unpaired probability cannot tell a site held
shut by the switch from one held by the trigger.
"""

import argparse
import statistics
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[4]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from engine import sequences as sq  # noqa: E402
from engine.domain import Host  # noqa: E402
from engine.gates.toehold import ProkaryoticToeholdAndGate  # noqa: E402
from engine.gates.tools.codons import CodonOptimizer  # noqa: E402
from engine.gates.tools.folding import FoldEngine  # noqa: E402
from engine.gates.tools.translation import TranslationScorer  # noqa: E402

INK = "#141413"
GREY = "#3D3D3A"
MUTED = "#5F5E5A"
PAPER = "#F1EFE8"
RED_DK = "#791F1F"
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif"

#: Fill, outline and key label per domain. Unlisted positions — the loops and the linker —
#: fall through to the neutral pair below.
DOMAIN_STYLE = {
    "r2_star": ("#DCD8F2", "#4A42A8", "r2* toehold (trigger B's site)"),
    "sw_x": ("#CBDFF5", "#1B5FA8", "sw_x"),
    "k2_star": ("#C6E8E4", "#0E6A66", "k2*"),
    "secondary_z": ("#E9E6B8", "#6E6410", "secondaryZ"),
    "sw_xs": ("#F3CDCD", "#A32D2D", "x* nucleation site"),
    "main_pre_star": ("#E3E1DB", "#5F5E5A", "main arm  pre*/bulge*  and main_pre"),
    "bulge_star": ("#E3E1DB", "#5F5E5A", None),
    "k1_star": ("#E7D9C6", "#7A5230", "k1* : mainZ  upper stem (6 bp)"),
    "rbs_loop": ("#D9E8C6", "#3B6D11", "RBS loop"),
    "main_z": ("#E7D9C6", "#7A5230", None),
    "aug": ("#F8CCE2", "#9B1B6A", "AUG"),
    "main_pre": ("#E3E1DB", "#5F5E5A", None),
}
NEUTRAL = ("#EDEBE4", "#9A9890", None)


def esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


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


def place(points, spacing=23.0, pad=32.0):
    """Scale the layout so neighbouring bases sit ``spacing`` apart, and flip y for SVG.

    Scaled by the *median* neighbour distance rather than by the bounding box: naview keeps
    bases roughly equidistant, so this puts every lettered circle at a legible size however
    long the molecule is, and lets the canvas grow instead of the letters shrinking.
    """
    gaps = [
        ((points[i + 1][0] - points[i][0]) ** 2 + (points[i + 1][1] - points[i][1]) ** 2) ** 0.5
        for i in range(len(points) - 1)
    ]
    unit = statistics.median([g for g in gaps if g > 0]) or 1.0
    scale = spacing / unit
    xs = [p[0] * scale for p in points]
    ys = [p[1] * scale for p in points]
    min_x, max_y = min(xs), max(ys)
    placed = [(x - min_x + pad, (max_y - y) + pad) for x, y in zip(xs, ys, strict=True)]
    return placed, max(x for x, _ in placed) + pad, max(y for _, y in placed) + pad


def domain_of(index, domains):
    for name, (start, end) in domains.items():
        if start <= index < end:
            return name
    return None


def draw(design, out_path: Path) -> None:
    structure = design["off_mfe"]
    domains = design["domains"]
    sequence = design["switch"]
    o = design["observables"]

    points, plot_w, plot_h = place(design["layout"])
    top = 74
    column = max(plot_w, 470)
    W = column + 400
    H = max(plot_h + top + 30, 660)
    pairs = pair_table(structure)

    svg = [
        f'<svg width="100%" viewBox="0 0 {W:.0f} {H:.0f}" role="img" '
        f'xmlns="http://www.w3.org/2000/svg">',
        f"<title>{esc(design['label'])} — folded OFF state with four-tube results</title>",
        "<desc>Nucleotide-level plot of the switch folded with no trigger present, every "
        "base lettered and coloured by domain, annotated with measurements from all four "
        "logic states.</desc>",
        f'<rect width="{W:.0f}" height="{H:.0f}" fill="{PAPER}"/>',
        f'<text x="24" y="32" font-family="{FONT}" font-size="14" font-weight="500" '
        f'fill="{INK}">{esc(design["label"])} — folded OFF state, {len(sequence)} nt</text>',
        f'<text x="24" y="52" font-family="{FONT}" font-size="12" fill="{GREY}">'
        f"MFE {design['mfe']:.1f} kcal/mol · ViennaRNA naview layout · "
        f"{esc(design['scheme'])} stem, lock {design['lock']:.1f} kcal/mol</text>",
    ]

    pts = [(x + 10, y + top) for x, y in points]

    seen = set()
    for i, j in pairs.items():
        if i > j or (i, j) in seen:
            continue
        seen.add((i, j))
        x1, y1 = pts[i]
        x2, y2 = pts[j]
        svg.append(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{INK}" stroke-width="1.1" opacity="0.45"/>'
        )

    backbone = " ".join(f"{'M' if k == 0 else 'L'} {x:.1f} {y:.1f}" for k, (x, y) in enumerate(pts))
    svg.append(
        f'<path d="{backbone}" fill="none" stroke="{INK}" stroke-width="1.6" '
        f'opacity="0.75" stroke-linecap="round" stroke-linejoin="round"/>'
    )

    for index, (x, y) in enumerate(pts):
        fill, edge, _ = DOMAIN_STYLE.get(domain_of(index, domains), NEUTRAL)
        svg.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6.6" fill="{fill}" stroke="{edge}" '
            f'stroke-width="1.1"/>'
        )
        svg.append(
            f'<text x="{x:.1f}" y="{y + 3.2:.1f}" text-anchor="middle" font-family="{FONT}" '
            f'font-size="8.5" font-weight="500" fill="{INK}">{sequence[index]}</text>'
        )

    for index, text, dx in ((0, "5&#8242;", -15), (len(pts) - 1, "3&#8242;", 15)):
        x, y = pts[index]
        svg.append(
            f'<text x="{x + dx:.1f}" y="{y + 4:.1f}" text-anchor="middle" font-family="{FONT}" '
            f'font-size="11" font-weight="600" fill="{GREY}">{text}</text>'
        )

    # ---- key and measurements, in a reserved column so nothing can collide -----------
    px = column + 26
    cols = [px + 190, px + 244, px + 298, px + 352]
    svg.append(
        f'<line x1="{px - 14}" y1="70" x2="{px - 14}" y2="{H - 26:.0f}" stroke="{GREY}" '
        f'stroke-width="1" opacity="0.3"/>'
    )

    def head(y, text):
        svg.append(
            f'<text x="{px}" y="{y}" font-family="{FONT}" font-size="11" font-weight="600" '
            f'fill="{INK}" letter-spacing="0.06em">{text}</text>'
        )

    y = 92
    head(y, "DOMAINS")
    y += 19
    for name, (fill, edge, label) in DOMAIN_STYLE.items():
        if label is None or name not in domains:
            continue
        svg.append(
            f'<circle cx="{px + 6}" cy="{y - 4}" r="6" fill="{fill}" stroke="{edge}" '
            f'stroke-width="1.1"/>'
        )
        svg.append(
            f'<text x="{px + 20}" y="{y}" font-family="{FONT}" font-size="11" '
            f'fill="{GREY}">{esc(label)}</text>'
        )
        y += 17

    y += 18
    head(y, "FOUR TUBES")
    y += 20

    def row(label, values, flags=(), bold=False):
        nonlocal y
        svg.append(
            f'<text x="{px}" y="{y}" font-family="{FONT}" font-size="11" '
            f'fill="{GREY}">{esc(label)}</text>'
        )
        for k, value in enumerate(values):
            failed = k < len(flags) and flags[k]
            svg.append(
                f'<text x="{cols[k]}" y="{y}" text-anchor="end" font-family="{FONT}" '
                f'font-size="11" font-weight="{"600" if failed or bold else "400"}" '
                f'fill="{RED_DK if failed else INK}">{esc(value)}</text>'
            )
        y += 17

    states = ("00", "01", "10", "11")
    row("state", list(states), bold=True)
    svg.append(
        f'<line x1="{px}" y1="{y - 12}" x2="{cols[3]}" y2="{y - 12}" stroke="{GREY}" '
        f'stroke-width="1" opacity="0.35"/>'
    )
    row("dG_open  kcal/mol", [f"{o[f'dG_open_{s}']:.2f}" for s in states])
    am = [o[f"A_M_{s}"] for s in states]
    row("A_M  main arm", [f"{v:.3f}" for v in am], flags=[0, 0, am[2] >= 0.2, am[3] <= 0.5])
    row("A_S  x* unpaired", [f"{o[f'A_S_{s}']:.3f}" for s in states])
    row("x* locked", [f"{v:.3f}" for v in design["locked"]])
    row("x* engaged by A", [f"{v:.3f}" for v in design["engaged"]])

    y += 18
    head(y, "SINGLE NUMBERS")
    y += 20
    for label, value, failed in design["singles"]:
        svg.append(
            f'<text x="{px}" y="{y}" font-family="{FONT}" font-size="11" '
            f'fill="{GREY}">{esc(label)}</text>'
        )
        svg.append(
            f'<text x="{cols[3]}" y="{y}" text-anchor="end" font-family="{FONT}" '
            f'font-size="11" font-weight="{"600" if failed else "400"}" '
            f'fill="{RED_DK if failed else INK}">{esc(value)}</text>'
        )
        y += 17

    y += 13
    for line in design["note"]:
        svg.append(
            f'<text x="{px}" y="{y}" font-family="{FONT}" font-size="10.5" '
            f'fill="{MUTED}">{esc(line)}</text>'
        )
        y += 15

    svg.append("</svg>")
    out_path.write_text("\n".join(svg), encoding="utf-8")


def build(gate, transcript, pair, stem, label):
    trigger_a = transcript[slice(*pair.window_a())]
    trigger_b = transcript[slice(*pair.window_b())]
    switch = gate.assemble(trigger_a, trigger_b, pair.len_x, stem)
    o = gate.four_tube_observables(switch, trigger_a, trigger_b)

    sequence = switch.sequence
    fold = gate.folder.mfe(sequence)
    n = len(sequence)
    xs, swx = switch.domains["sw_xs"], switch.domains["sw_x"]
    locked, engaged = [], []
    for strands, has_a in (
        (sequence, False),
        (f"{sequence}&{trigger_b}", False),
        (f"{sequence}&{trigger_a}", True),
        (f"{sequence}&{trigger_a}&{trigger_b}", True),
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

    sep_no_ten = min(o["dG_open_00"], o["dG_open_01"]) - o["dG_open_11"]
    singles = [
        ("separation (all OFF)", f"{o['separation']:.2f}", o["separation"] <= 1.5),
        ("separation (excl. 10)", f"{sep_no_ten:.2f}", sep_no_ten <= 1.5),
        ("ddG_AND", f"{o['ddG_AND']:.2f}", o["ddG_AND"] >= -1.0),
        ("A(r2*|00)   tau8 > 0.5", f"{o['A_r2_star_00']:.3f}", o["A_r2_star_00"] <= 0.5),
        ("d(Omega00)  tau9 < 0.1", f"{o['d_off']:.3f}", o["d_off"] >= 0.1),
        ("dG_bind_B", f"{o['dG_bind_B']:.1f}", False),
        ("dG_bind_A given B", f"{o['dG_bind_A_given_B']:.1f}", False),
        ("ddG_pref (stem)", f"{stem.ddg_pref:.2f}", stem.ddg_pref < 0),
    ]
    note = [
        "dG_open(10) = dG_open(11): trigger A opens the main hairpin",
        "with or without B. x* still behaves as designed, locked in 00",
        "and free in 01, so the inhibitory hairpin works and what is",
        "missing is kinetic discrimination, not structure.",
    ]
    return {
        "label": label,
        "scheme": stem.scheme,
        "lock": stem.lock_energy,
        "switch": sequence,
        "off_mfe": fold.structure,
        "mfe": fold.energy,
        "layout": gate.folder.layout_coordinates(fold.structure),
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
    parser.add_argument("--lab-filter", action="store_true", help="require buildable controls")
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
        if args.lab_filter and not all(gate.controls_constructible(transcript, pair)):
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

    for family in ("A-anchored", "B-anchored", "mixed"):
        members = sorted((s for s in stems if s.scheme == family), key=lambda s: s.lock_energy)
        if not members:
            print(f"  {family:<11} no build on the frontier")
            continue
        stem = members[0]
        design = build(gate, transcript, pair, stem, f"x@{pair.x_start} · {family}")
        path = out / f"design_x{pair.x_start}_{family.replace('-', '_')}.svg"
        draw(design, path)
        print(f"  {family:<11} lock {stem.lock_energy:>7.1f}  ->  {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
