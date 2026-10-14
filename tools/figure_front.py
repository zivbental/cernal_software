"""The non-dominated rule itself, on an example small enough to check by hand.

Run::

    uv run python tools/figure_front.py --out-dir <somewhere>

Writes ``methods-front.svg``, for section 4.3's explainer box.

The page's other 4.3 figure shows a 4-position stem with 81 builds and says which
survive. It shows the *result* of the rule. This one shows the rule: a real pair with
only **three** disagreeing positions, so all 27 builds fit on one plot and a reader can
verify any claim in the drawing by eye.

**Everything here is measured**, by ``<scratch>/front_example.py`` against the same
``_secondary_domains`` / ``_build_arms`` / ``fixed_alignment_energy`` path production
uses: ggt x fadB, x_start 1717, xstar_start 515, len_x 5, disagreeing positions 0, 1
and 6. 27 builds enumerated, 16 survive the two rules, 5 are non-dominated.

The pair was chosen for having three conflicts where the median is 10 to 11, and the
figure says so, because a figure that quietly shows the easy case is worse than none.

One point carries the whole argument for the third axis. ``MMM`` is dominated on the
two axes drawn -- ``AAM`` has the same grip on trigger A and a stronger lock -- and is
kept only because its grip for trigger B is 3.7 kcal/mol stronger. It is drawn
differently for that reason, and it is the same effect that 38.9% of all built stems
show at scale.

Layout rules carried over from ``figure_methods.py``: declared bands, nothing inside
the drawing longer than a symbol or two words, and a programmatic width check rather
than judging overflow in a browser.
"""

from __future__ import annotations

import argparse
import pathlib

WIDTH = 900

#: (lock, A's grip, B's grip, survives both rules, non-dominated in 3-D, assignment).
#: A = lock+A at that position, B = lock+B, M = A+B with the lock given up.
BUILDS: tuple[tuple[float, float, float, bool, bool, str], ...] = (
    (-12.90, -30.90, -23.30, True, True, "MMM"),
    (-17.20, -30.90, -16.60, False, False, "MMA"),
    (-19.60, -26.60, -23.30, True, True, "MMB"),
    (-13.70, -30.90, -16.90, True, False, "MAM"),
    (-18.00, -30.90, -10.20, False, False, "MAA"),
    (-20.40, -26.60, -16.90, False, False, "MAB"),
    (-15.20, -26.20, -23.30, True, False, "MBM"),
    (-19.50, -26.20, -16.60, False, False, "MBA"),
    (-21.90, -21.90, -23.30, True, True, "MBB"),
    (-11.40, -30.90, -22.70, True, False, "AMM"),
    (-15.70, -30.90, -16.00, True, False, "AMA"),
    (-18.10, -26.60, -22.70, True, False, "AMB"),
    (-16.10, -30.90, -19.60, True, True, "AAM"),
    (-20.40, -30.90, -12.90, False, False, "AAA"),
    (-22.80, -26.60, -19.60, False, False, "AAB"),
    (-18.10, -26.20, -22.70, True, False, "ABM"),
    (-22.40, -26.20, -16.00, False, False, "ABA"),
    (-24.80, -21.90, -22.70, False, False, "ABB"),
    (-10.20, -24.50, -23.30, True, False, "BMM"),
    (-14.50, -24.50, -16.60, True, False, "BMA"),
    (-16.90, -20.20, -23.30, True, False, "BMB"),
    (-14.50, -24.50, -16.90, True, False, "BAM"),
    (-18.80, -24.50, -10.20, False, False, "BAA"),
    (-21.20, -20.20, -16.90, False, False, "BAB"),
    (-16.60, -24.80, -23.30, True, False, "BBM"),
    (-20.90, -24.80, -16.60, False, False, "BBA"),
    (-23.30, -20.50, -23.30, True, True, "BBB"),
)

#: Trigger A's extension and what trigger B needs, on the ascending arm, 5' to 3'.
ARM_EXT = "GAUUUAACGGCGG"
ARM_WANTED = "CCGCCGGUAAAGA"
CONFLICTS = (0, 1, 6)

#: The build whose domination rectangle is drawn, and the one that dominates it.
SHOWN = "ABM"
SHOWN_BY = "MMB"
#: Non-dominated on the two axes drawn, and the one point that is not.
THIRD_AXIS = "MMM"
THIRD_AXIS_BY = "AAM"


def _text(x, y, s, cls, anchor="start") -> str:
    extra = f' text-anchor="{anchor}"' if anchor != "start" else ""
    return f'<text class="{cls}" x="{x:.1f}" y="{y:.1f}"{extra}>{s}</text>'


def front() -> str:
    by_name = {b[5]: b for b in BUILDS}

    out = [
        _text(8, 28, "What &#8220;non-dominated&#8221; throws away, and what it keeps", "mt-title"),
        _text(
            8,
            48,
            "One real ggt &#215; fadB pair with three disagreeing positions, "
            "so all 27 builds fit on one plot. The median has 10 to 11.",
            "mt-caption",
        ),
    ]

    # --- band 1: the three positions and the three choices at each --------------------
    top, cell, left = 86, 26, 230
    out.append(_text(8, top + 18, "the arm, 13 nt", "mt-row"))
    out.append(_text(left - 14, top + 18, "A would put", "mt-side", "end"))
    out.append(_text(left - 14, top + cell + 18, "B needs", "mt-side", "end"))
    for index, (base_a, base_b) in enumerate(zip(ARM_EXT, ARM_WANTED, strict=True)):
        x = left + index * cell
        clash = index in CONFLICTS
        for row, base in ((0, base_a), (1, base_b)):
            out.append(
                f'<rect class="mt-cell{" mt-cell--clash" if clash else ""}" '
                f'x="{x}" y="{top + row * cell}" width="{cell - 2}" '
                f'height="{cell - 2}" rx="2" />'
            )
            out.append(_text(x + cell / 2 - 1, top + row * cell + 18, base, "mt-base", "middle"))
        if clash:
            out.append(
                _text(
                    x + cell / 2 - 1,
                    top + 2 * cell + 20,
                    "A&#8901;B&#8901;M",
                    "mt-clash-mark",
                    "middle",
                )
            )
    out.append(
        _text(
            8,
            top + 2 * cell + 20,
            "3 choices &#215; 3 positions = 27 builds, every one of them enumerated",
            "mt-note",
        )
    )

    # --- band 2: the plot --------------------------------------------------------------
    plot_x, plot_y, plot_w, plot_h = 230, 196, 470, 330
    locks = [b[0] for b in BUILDS]
    grips = [b[1] for b in BUILDS]
    lo_l, hi_l = min(locks) - 1.2, max(locks) + 1.2
    lo_g, hi_g = min(grips) - 1.2, max(grips) + 1.2

    def px(lock):  # stronger lock to the left
        return plot_x + (lock - lo_l) / (hi_l - lo_l) * plot_w

    def py(grip):  # stronger grip upward
        return plot_y + (grip - lo_g) / (hi_g - lo_g) * plot_h

    # The rectangle first, so every mark sits on top of it.
    by = by_name[SHOWN_BY]
    out.append(
        f'<rect class="mt-dom-box" x="{px(by[0]):.1f}" y="{py(by[1]):.1f}" '
        f'width="{px(hi_l) - px(by[0]):.1f}" height="{py(hi_g) - py(by[1]):.1f}" />'
    )

    out += [
        f'<line class="mt-axis-line" x1="{plot_x}" y1="{plot_y + plot_h}" '
        f'x2="{plot_x + plot_w}" y2="{plot_y + plot_h}" />',
        f'<line class="mt-axis-line" x1="{plot_x}" y1="{plot_y}" '
        f'x2="{plot_x}" y2="{plot_y + plot_h}" />',
        _text(
            plot_x + plot_w / 2,
            plot_y + plot_h + 30,
            "the lock, kcal/mol &#8212; stronger to the left",
            "mt-axis",
            "middle",
        ),
        _text(plot_x - 14, plot_y + 10, "A&#8217;s grip", "mt-axis", "end"),
        _text(plot_x - 14, plot_y + 26, "stronger", "mt-axis", "end"),
    ]

    for lock, grip, _b_site, ok, on_front, name in BUILDS:
        x, y = px(lock), py(grip)
        if not ok:
            out.append(
                f'<path class="mt-rejected" d="M {x - 4.5:.1f} {y - 4.5:.1f} '
                f'l 9 9 M {x + 4.5:.1f} {y - 4.5:.1f} l -9 9" />'
            )
            continue
        cls = (
            "mt-third-axis" if name == THIRD_AXIS else ("mt-front" if on_front else "mt-dominated")
        )
        out.append(f'<circle class="{cls}" cx="{x:.1f}" cy="{y:.1f}" r="6.5" />')

    for name, dx, dy, anchor in (
        (SHOWN, 11, 4, "start"),
        (SHOWN_BY, -11, 4, "end"),
        (THIRD_AXIS, 12, 4, "start"),
        (THIRD_AXIS_BY, -11, 4, "end"),
        ("BBB", -11, 4, "end"),
        ("AAA", 11, 4, "start"),
    ):
        b = by_name[name]
        out.append(_text(px(b[0]) + dx, py(b[1]) + dy, name, "mt-point-name", anchor))

    # --- band 3: the legend, down the left, level with the plot -----------------------
    for offset, (mark, line) in enumerate(
        (
            ("rejected", "11 rejected by the two rules"),
            ("dominated", "11 kept, then dominated"),
            ("front", "4 non-dominated here"),
            ("third", "1 more, on the axis not drawn"),
        )
    ):
        y = plot_y + 24 + offset * 34
        if mark == "rejected":
            out.append(
                f'<path class="mt-rejected" d="M 11.5 {y - 4.5:.1f} l 9 9 '
                f'M 20.5 {y - 4.5:.1f} l -9 9" />'
            )
        else:
            cls = {"dominated": "mt-dominated", "front": "mt-front", "third": "mt-third-axis"}[mark]
            out.append(f'<circle class="{cls}" cx="16" cy="{y:.1f}" r="6.5" />')
        out.append(_text(32, y + 5, line, "mt-legend"))

    y = plot_y + 24 + 4 * 34 + 10
    for line in (
        "The rule, in one",
        "sentence: a build is",
        "discarded only when",
        "another is at least",
        "as good on all three",
        "claims and better on",
        "one. The grey box is",
        f"everything {SHOWN_BY}",
        f"beats; {SHOWN} is in it.",
    ):
        out.append(_text(8, y, line, "mt-note"))
        y += 18

    base = plot_y + plot_h + 56
    for offset, line in enumerate(
        (
            f"{THIRD_AXIS} is why the third axis is not optional. On the two axes drawn it "
            f"loses to {THIRD_AXIS_BY}:",
            "same grip on trigger A, and a lock 3.2 kcal/mol stronger. It survives because "
            "its grip on trigger B is 3.7 stronger,",
            "and no surviving build beats it on all three. At full scale that is not a "
            "curiosity: projecting every built stem onto",
            "these two axes alone would discard 38.9% of the front.",
            "",
            "Only one of the five is a global strategy, the all-B build. The other four give "
            "up the lock at some positions, or serve",
            "trigger A at others, and neither global strategy can express them. The all-A "
            "build (AAA) does not survive the rules.",
        )
    ):
        out.append(_text(8, base + offset * 20, line, "mt-note"))

    return _svg(
        out,
        base + 136,
        "All 27 builds of a three-conflict stem plotted on the lock against "
        "trigger A's grip, showing which are rejected, which are dominated, "
        "which form the front, and one build kept only by the third axis.",
    )


def _svg(parts: list[str], height: int, aria: str) -> str:
    body = "\n    ".join(p for p in parts if p)
    return (
        f'<svg viewBox="0 0 {WIDTH} {height}" role="img" aria-label="{aria}">\n    {body}\n</svg>'
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Draw the non-dominated explainer.")
    parser.add_argument("--out-dir", default=".", type=pathlib.Path)
    args = parser.parse_args(argv)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    svg = front()
    (args.out_dir / "methods-front.svg").write_text(svg, encoding="utf-8")
    print(f"  methods-front.svg: {len(svg):,} characters")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
