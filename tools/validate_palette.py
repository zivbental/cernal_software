"""The dataviz palette checks, in Python, because this machine has no node.

A faithful port of the six checks in the bundled ``validate_palette.js``: the OKLCH
lightness band and chroma floor, OKLab Delta E (x100) between slots under the
Machado-Oliveira-Fernandes (2009) severity-1.0 protan/deutan simulation with tritan
reported, the unsimulated normal-vision floor, and WCAG contrast against the chart
surface. The constants and the colour maths are copied from that file rather than
re-derived, because the CVD thresholds are calibrated to that specific simulation.

The point of porting it rather than judging by eye is that this is the one part of
choosing a palette that is computable.

Run::

    uv run python tools/validate_palette.py "#1F7A82,#C41E3A" --mode light
    uv run python tools/validate_palette.py "#1F7A82,#C41E3A" --surface "#FAFAFA"
"""

from __future__ import annotations

import argparse
import math
import re

BAND = {"light": (0.43, 0.77), "dark": (0.48, 0.67)}
CHROMA_FLOOR = 0.10
CVD_TARGET, CVD_FLOOR = 8.0, 6.0
NORMAL_FLOOR = 15.0
CONTRAST_MIN = 3.0
DEFAULT_SURFACE = {"light": "#fcfcfb", "dark": "#1a1a19"}

MACHADO = {
    "protan": (
        (0.152286, 1.052583, -0.204868),
        (0.114503, 0.786281, 0.099216),
        (-0.003882, -0.048116, 1.051998),
    ),
    "deutan": (
        (0.367322, 0.860646, -0.227968),
        (0.280085, 0.672501, 0.047413),
        (-0.011820, 0.042940, 0.968881),
    ),
    "tritan": (
        (1.255528, -0.076749, -0.178779),
        (-0.078411, 0.930809, 0.147602),
        (0.004733, 0.691367, 0.303900),
    ),
}

#: The whitespace both engines strip, built from code points so that no ambiguous
#: space character appears in this source. Kept in lockstep with the JavaScript
#: twin: the shared set is the intersection of what JS trim() and Python str.strip()
#: remove, which also covers the non-breaking spaces that come along when a hex list is
#: copied out of a rendered page.
WS_CHARS = "".join(
    chr(c)
    for c in (
        0x20,
        0x09,
        0x0A,
        0x0B,
        0x0C,
        0x0D,
        0xA0,
        0x1680,
        *range(0x2000, 0x200B),
        0x2028,
        0x2029,
        0x202F,
        0x205F,
        0x3000,
    )
)


def _clean(value: str) -> str:
    return value.strip(WS_CHARS)


def _srgb(hex_colour: str) -> list[float]:
    text = _clean(hex_colour).lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}", text):
        raise SystemExit(f"  not a six-digit hex colour: {hex_colour!r}")
    return [int(text[i : i + 2], 16) / 255 for i in (0, 2, 4)]


def _linear(hex_colour: str) -> list[float]:
    return [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in _srgb(hex_colour)]


def _oklab(rgb: list[float]) -> tuple[float, float, float]:
    r, g, b = rgb
    long = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    med = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    short = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    return (
        0.2104542553 * long + 0.7936177850 * med - 0.0040720468 * short,
        1.9779984951 * long - 2.4285922050 * med + 0.4505937099 * short,
        0.0259040371 * long + 0.7827717662 * med - 0.8086757660 * short,
    )


def _oklch(hex_colour: str) -> tuple[float, float]:
    light, a, b = _oklab(_linear(hex_colour))
    return light, math.hypot(a, b)


def _simulate(hex_colour: str, kind: str) -> list[float]:
    r, g, b = _linear(hex_colour)
    return [min(1.0, max(0.0, row[0] * r + row[1] * g + row[2] * b)) for row in MACHADO[kind]]


def delta_e(first: str, second: str, kind: str | None = None) -> float:
    """Euclidean distance in OKLab, x100. No kind means unsimulated vision."""
    a = _oklab(_simulate(first, kind) if kind else _linear(first))
    b = _oklab(_simulate(second, kind) if kind else _linear(second))
    return 100 * math.dist(a, b)


def contrast(first: str, second: str) -> float:
    def luminance(colour: str) -> float:
        r, g, b = _linear(colour)
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    high, low = sorted((luminance(first), luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def validate(palette: list[str], mode: str, surface: str, every_pair: bool) -> bool:
    low, high = BAND[mode]
    rows: list[tuple[str, bool, str]] = []

    stray = [(c, round(_oklch(c)[0], 3)) for c in palette if not low <= _oklch(c)[0] <= high]
    rows.append(
        (
            f"lightness band {low}-{high}",
            not stray,
            f"outside: {stray}" if stray else f"all {len(palette)} inside",
        )
    )

    thin = [(c, round(_oklch(c)[1], 3)) for c in palette if _oklch(c)[1] < CHROMA_FLOOR]
    rows.append(
        (
            f"chroma floor {CHROMA_FLOOR}",
            not thin,
            f"reads gray: {thin}" if thin else f"all {len(palette)} at or above",
        )
    )

    pairs = (
        [(i, j) for i in range(len(palette)) for j in range(i + 1, len(palette))]
        if every_pair
        else [(i, i + 1) for i in range(len(palette) - 1)]
    )
    worst, worst_at, worst_kind = 99.0, None, ""
    for kind in ("protan", "deutan"):
        for i, j in pairs:
            found = delta_e(palette[i], palette[j], kind)
            if found < worst:
                worst, worst_at, worst_kind = found, (palette[i], palette[j]), kind
    tritan = min((delta_e(palette[i], palette[j], "tritan") for i, j in pairs), default=99.0)
    detail = "n/a"
    if worst_at:
        detail = (
            f"worst {worst_at[0]} vs {worst_at[1]} dE {worst:.1f} "
            f"({worst_kind}), tritan {tritan:.1f}"
        )
    rows.append(
        (f"CVD separation (target {CVD_TARGET}, floor {CVD_FLOOR})", worst >= CVD_FLOOR, detail)
    )

    plain = min((delta_e(palette[i], palette[j]) for i, j in pairs), default=99.0)
    rows.append(
        (f"normal-vision floor {NORMAL_FLOOR}", plain >= NORMAL_FLOOR, f"worst pair dE {plain:.1f}")
    )

    faint = [
        (c, round(contrast(c, surface), 2)) for c in palette if contrast(c, surface) < CONTRAST_MIN
    ]
    rows.append(
        (
            f"contrast vs {surface} (min {CONTRAST_MIN}:1)",
            not faint,
            f"below, so visible labels or a table view are required: {faint}"
            if faint
            else f"all {len(palette)} at or above",
        )
    )

    print(f"  palette {palette}, mode {mode}, surface {surface}")
    for name, passed, note in rows:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name:<44} {note}")
    if CVD_FLOOR <= worst < CVD_TARGET:
        print("  note: between floor and target, so secondary encoding is required")
    return all(passed for _name, passed, _note in rows)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="The dataviz palette checks, in Python.")
    parser.add_argument("palette", help="comma-separated hex colours")
    parser.add_argument("--mode", choices=("light", "dark"), default="light")
    parser.add_argument("--surface")
    parser.add_argument("--pairs", choices=("adjacent", "all"), default="adjacent")
    args = parser.parse_args(argv)

    palette = [c for c in (_clean(p) for p in args.palette.split(",")) if c]
    surface = args.surface or DEFAULT_SURFACE[args.mode]
    return 0 if validate(palette, args.mode, surface, args.pairs == "all") else 1


if __name__ == "__main__":
    raise SystemExit(main())
