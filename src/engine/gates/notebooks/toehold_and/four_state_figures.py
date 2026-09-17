"""One candidate, four separate nucleotide plots — the switch alone and with each trigger.

    uv run python src/engine/gates/notebooks/toehold_and/four_state_figures.py \\
        --fasta "path/to/mCherry original.txt" --out fourstate

**What this is for.** The four-tube numbers say *that* state 10 behaves like state 11; they
do not show *what the molecule is doing*. These do. Each state gets its own SVG showing the
real minimum-free-energy structure of that tube — every base lettered, placed by ViennaRNA's
naview layout (the algorithm behind ``RNAplot`` and forna), the switch coloured by domain
and each trigger in its own colour. Put the four side by side and the mechanism is visible
without reading a single number: which hairpin is open, what each trigger is holding, and
what the ribosome window looks like in each case.

**Honesty rules, because these are pictures and pictures persuade.**

* The structure drawn is ``FoldEngine.mfe`` of that tube. Nothing is forced, nothing is
  idealised, and no intended structure is drawn anywhere. Where the molecule disagrees with
  the design's intent, the picture shows the molecule.
* The MFE is one structure out of an ensemble, and the ensemble is what every number in this
  project is computed from. Each figure therefore states its own ensemble-vs-MFE gap, so a
  reader knows how representative the drawing is.
* Multi-strand tubes are laid out over the concatenation, because naview works in one
  coordinate space. The junctions between molecules are **not** drawn as backbone — a gap is
  left and the strand is labelled — so nothing suggests the three molecules are one chain.

**What to look at.** In the OFF state (00) both hairpins are shut. Adding trigger B (01)
should open the inhibitory hairpin only. Adding trigger A (10) should, if the gate worked,
do almost nothing — and on our designs it does not; that difference between what 10 *should*
look like and what it does look like is the whole investigation, in one picture.
"""

import argparse
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[4]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from structure_figures import (  # noqa: E402  (sibling module, same directory)
    DOMAIN_STYLE,
    FONT,
    GREY,
    INK,
    MUTED,
    NEUTRAL,
    PAPER,
    esc,
    pair_table,
    place,
)

from engine import sequences as sq  # noqa: E402
from engine.domain import Host  # noqa: E402
from engine.gates.toehold import ProkaryoticToeholdAndGate, _mean_unpaired  # noqa: E402
from engine.gates.tools.codons import CodonOptimizer  # noqa: E402
from engine.gates.tools.folding import FoldEngine  # noqa: E402
from engine.gates.tools.translation import TranslationScorer  # noqa: E402

# The switch's domains are all PALE fills. The two triggers get SATURATED fills with
# white letters, so a trigger can never be mistaken for a switch domain whatever the
# domain palette does -- which is what went wrong the first time.
TRIGGER_A_STYLE = ("#C2620F", "#7A3D08", "trigger A")
TRIGGER_B_STYLE = ("#0E6B54", "#084637", "trigger B")


def letter_colour(fill: str) -> str:
    """Black on a pale fill, white on a dark one, by relative luminance."""
    r, g, b = (int(fill[i : i + 2], 16) / 255 for i in (1, 3, 5))
    return "#FFFFFF" if (0.2126 * r + 0.7152 * g + 0.0722 * b) < 0.5 else None


STATES = {
    "00": ("switch alone", "neither trigger — both hairpins should be shut"),
    "01": ("switch + trigger B", "B alone — the inhibitory hairpin should open, nothing else"),
    "10": ("switch + trigger A", "A alone — this is the state that must stay OFF"),
    "11": ("switch + A + B", "both — the only state that should translate"),
}


def read_fasta(path: str) -> str:
    lines = Path(path).read_text().splitlines()
    return sq.to_rna("".join(line.strip() for line in lines if not line.startswith(">")))


def style_for(index: int, switch_len: int, breaks: list[int], domains: dict, order: list[str]):
    """Fill, stroke and legend key for one position of the concatenation.

    ``breaks`` are the cut points **including** the end of the switch, so the trigger a
    position belongs to is ``(how many cuts it is past) - 1``. Getting that off by one put
    trigger A in trigger B's colour on every figure, and in a two-strand tube it ran off
    the end of ``order`` entirely and fell through to B's colour by default.
    """
    if index < switch_len:
        for name, (start, end) in domains.items():
            if start <= index < end:
                return DOMAIN_STYLE.get(name, NEUTRAL)
        return NEUTRAL
    which = sum(1 for cut in breaks if index >= cut) - 1
    if not 0 <= which < len(order):
        raise ValueError(f"position {index} is past every strand in {order}")
    return TRIGGER_A_STYLE if order[which] == "A" else TRIGGER_B_STYLE


def draw_state(design: dict, state: str, out_path: Path) -> None:
    flat = design["structure"].replace("&", "")
    sequence = design["sequence"].replace("&", "")
    points, plot_w, plot_h = place(design["layout"])
    pairs = pair_table(flat)
    breaks = design["breaks"]
    switch_len = design["switch_len"]

    top = 96
    width = max(plot_w, 520) + 360
    height = max(plot_h + top + 40, 620)
    title, subtitle = STATES[state]

    svg = [
        f'<svg width="100%" viewBox="0 0 {width:.0f} {height:.0f}" role="img" '
        f'xmlns="http://www.w3.org/2000/svg">',
        f"<title>State {state} — {esc(title)}</title>",
        f"<desc>Minimum free energy structure of the {esc(title)} tube, every base lettered "
        f"and placed by ViennaRNA's naview layout. {esc(subtitle)}</desc>",
        f'<rect width="{width:.0f}" height="{height:.0f}" fill="{PAPER}"/>',
        f'<text x="24" y="34" font-family="{FONT}" font-size="17" font-weight="600" '
        f'fill="{INK}">State {state} — {esc(title)}</text>',
        f'<text x="24" y="55" font-family="{FONT}" font-size="12.5" fill="{GREY}">'
        f"{esc(subtitle)}</text>",
        f'<text x="24" y="76" font-family="{FONT}" font-size="12" fill="{MUTED}">'
        f"MFE {design['mfe']:.1f} kcal/mol · ensemble {design['ensemble']:.1f} · "
        f"gap {design['mfe'] - design['ensemble']:.1f} (how much the drawing represents) · "
        f"{len(flat)} nt</text>",
    ]

    # Backbone, broken at every strand junction so three molecules never read as one chain.
    for i in range(len(flat) - 1):
        if (i + 1) in breaks:
            continue
        x1, y1 = points[i]
        x2, y2 = points[i + 1]
        svg.append(
            f'<line x1="{x1:.1f}" y1="{y1 + top:.1f}" x2="{x2:.1f}" y2="{y2 + top:.1f}" '
            f'stroke="{MUTED}" stroke-width="1.6"/>'
        )
    # Base pairs.
    for i, j in pairs.items():
        if i >= j:
            continue
        x1, y1 = points[i]
        x2, y2 = points[j]
        svg.append(
            f'<line x1="{x1:.1f}" y1="{y1 + top:.1f}" x2="{x2:.1f}" y2="{y2 + top:.1f}" '
            f'stroke="#B9B6AC" stroke-width="1.1" stroke-dasharray="2.5 2.5"/>'
        )
    # Lettered circles.
    for i, (x, y) in enumerate(points):
        fill, stroke, _ = style_for(i, switch_len, breaks, design["domains"], design["order"])
        svg.append(
            f'<circle cx="{x:.1f}" cy="{y + top:.1f}" r="9.2" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="1.3"/>'
        )
        ink = letter_colour(fill) or stroke
        svg.append(
            f'<text x="{x:.1f}" y="{y + top + 3.4:.1f}" font-family="{FONT}" font-size="9.5" '
            f'font-weight="600" text-anchor="middle" fill="{ink}">{sequence[i]}</text>'
        )

    # Legend and this state's own numbers, in a column clear of the plot.
    legend_x = max(plot_w, 520) + 20
    y = top + 6
    svg.append(
        f'<text x="{legend_x}" y="{y}" font-family="{FONT}" font-size="12.5" '
        f'font-weight="600" fill="{INK}">What is in this tube</text>'
    )
    y += 22
    for label, (fill, stroke, name) in (
        ("switch", (NEUTRAL[0], NEUTRAL[1], "switch")),
        ("A", TRIGGER_A_STYLE),
        ("B", TRIGGER_B_STYLE),
    ):
        present = label == "switch" or label in design["order"]
        svg.append(
            f'<circle cx="{legend_x + 8}" cy="{y - 4}" r="7" fill="{fill}" stroke="{stroke}" '
            f'stroke-width="1.3" opacity="{1.0 if present else 0.25}"/>'
        )
        svg.append(
            f'<text x="{legend_x + 24}" y="{y}" font-family="{FONT}" font-size="11.5" '
            f'fill="{GREY if present else "#AAA8A0"}">'
            f"{esc(name)}{'' if present else ' — not present'}</text>"
        )
        y += 20

    y += 10
    svg.append(
        f'<text x="{legend_x}" y="{y}" font-family="{FONT}" font-size="12.5" '
        f'font-weight="600" fill="{INK}">Domains of the switch</text>'
    )
    y += 20
    for _name, (fill, stroke, key) in DOMAIN_STYLE.items():
        if key is None:
            continue
        svg.append(
            f'<circle cx="{legend_x + 8}" cy="{y - 4}" r="7" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="1.3"/>'
        )
        svg.append(
            f'<text x="{legend_x + 24}" y="{y}" font-family="{FONT}" font-size="11.5" '
            f'fill="{GREY}">{esc(key)}</text>'
        )
        y += 19

    y += 14
    svg.append(
        f'<text x="{legend_x}" y="{y}" font-family="{FONT}" font-size="12.5" '
        f'font-weight="600" fill="{INK}">This state, measured</text>'
    )
    y += 20
    for label, value in design["readouts"]:
        svg.append(
            f'<text x="{legend_x}" y="{y}" font-family="{FONT}" font-size="11.5" '
            f'fill="{GREY}">{esc(label)}</text>'
        )
        svg.append(
            f'<text x="{width - 24:.0f}" y="{y}" font-family="{FONT}" font-size="11.5" '
            f'text-anchor="end" font-weight="600" fill="{INK}">{esc(value)}</text>'
        )
        y += 18

    svg.append("</svg>")
    out_path.write_text("\n".join(svg), encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fasta", required=True)
    parser.add_argument("--pair", type=int, default=0, help="index into the surviving pairs")
    parser.add_argument("--x-start", type=int, help="select the pair by x_start instead of index")
    parser.add_argument(
        "--variant",
        default="baseline",
        help="an architecture variant from modification_panel (baseline, upper3, upper6, "
        "aug_paired, stop_before_bulge, stabiliser)",
    )
    parser.add_argument(
        "--stem",
        default="0",
        help="build on the Pareto front: an index, or 'strongest' for the most negative "
        "lock energy. Index 0 is the all-'both' unlocked build, which has no inhibitory "
        "lock anywhere and is therefore the leakiest available -- a poor default for a "
        "figure meant to show the mechanism working.",
    )
    parser.add_argument("--out", default="fourstate", help="filename prefix")
    args = parser.parse_args(argv)

    output_dir = Path(__file__).resolve().parent / "results"
    output_dir.mkdir(parents=True, exist_ok=True)

    gate = ProkaryoticToeholdAndGate(
        Host.ECOLI, FoldEngine(37.0), TranslationScorer(Host.ECOLI), CodonOptimizer(Host.ECOLI)
    )
    transcript = read_fasta(args.fasta)
    pairs = []
    for pair in gate.find_trigger_pairs(transcript):
        start, end = pair.window_a()
        if gate.screen_trigger_window(transcript[start:end], transcript[pair.x_start - 9 :][:9]):
            continue
        pairs.append(pair)
    pairs.sort(key=lambda p: (-p.len_x, -p.gap(), p.x_start, p.xstar_start))
    if args.x_start is not None:
        matching = [p for p in pairs if p.x_start == args.x_start]
        if not matching:
            raise SystemExit(f"no surviving pair with x_start {args.x_start}")
        pair = matching[0]
    else:
        pair = pairs[args.pair]

    trigger_a = transcript[slice(*pair.window_a())]
    trigger_b = transcript[slice(*pair.window_b())]
    stems = gate.secondary_stems(trigger_a, trigger_b, pair.len_x)
    if args.stem == "strongest":
        stem = min(stems, key=lambda s: s.lock_energy)
    else:
        stem = stems[int(args.stem)]
    switch = gate.assemble(trigger_a, trigger_b, pair.len_x, stem)
    if args.variant != "baseline":
        from modification_panel import variants as _variants

        built = _variants(gate, switch, trigger_a)
        if args.variant not in built:
            raise SystemExit(f"unknown variant {args.variant!r}; have {sorted(built)}")
        switch = built[args.variant]
    observables = gate.four_tube_observables(switch, trigger_a, trigger_b)

    tubes = {
        "00": (switch.sequence, []),
        "01": (f"{switch.sequence}&{trigger_b}", ["B"]),
        "10": (f"{switch.sequence}&{trigger_a}", ["A"]),
        "11": (f"{switch.sequence}&{trigger_a}&{trigger_b}", ["A", "B"]),
    }
    print(
        f"pair x@{pair.x_start} len_x={pair.len_x}, {stem.scheme} stem, "
        f"lock {stem.lock_energy:.1f} kcal/mol (of {len(stems)} on the front), "
        f"switch {len(switch.sequence)} nt"
    )

    for state, (strands, order) in tubes.items():
        folded = gate.folder.mfe(strands)
        flat = folded.structure.replace("&", "")
        lengths = [len(part) for part in strands.split("&")]
        breaks, cursor = [], 0
        for length in lengths[:-1]:
            cursor += length
            breaks.append(cursor)
        matrix = gate.folder.pooled_pair_probabilities(strands)
        readouts = [
            ("dG_open (W_rank)", f"{observables[f'dG_open_{state}']:.2f} kcal/mol"),
            ("P_open (W_rank)", f"{gate.folder.p_open(strands, switch.span(-17, 13)):.3e}"),
            ("A_M  main stem", f"{observables[f'A_M_{state}']:.3f}"),
            ("A_S  x* site", f"{observables[f'A_S_{state}']:.3f}"),
            (
                "AUG alone",
                f"{_mean_unpaired(matrix, *switch.domains['aug']):.3f}",
            ),
        ]
        design = {
            "structure": folded.structure,
            "sequence": strands,
            "mfe": folded.energy,
            "ensemble": gate.folder.partition(strands),
            "layout": gate.folder.layout_coordinates(flat),
            "domains": switch.domains,
            "switch_len": len(switch.sequence),
            "breaks": breaks,
            "order": order,
            "readouts": readouts,
        }
        path = output_dir / f"{args.out}_x{pair.x_start}_{args.variant}_state{state}.svg"
        draw_state(design, state, path)
        print(f"  state {state}: {path}")

    print("\nOpen the four side by side. The mechanism is the difference between them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
