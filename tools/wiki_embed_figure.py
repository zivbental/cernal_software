"""Put a regenerated figure back into the wiki page it is inlined in.

Run either way::

    uv run python tools/wiki_embed_figure.py --generator figure_and_gate_states \\
        --select ag-fig--states --page /path/to/wiki/wiki/pages/and-gate-model.html
    uv run python tools/figure_methods.py --out-dir build
    uv run python tools/wiki_embed_figure.py --svg build/methods-triggers.svg \\
        --select "which domain of each trigger" --page /path/to/page.html

Publication helper for the separate Wiki checkout, not a CERNAL runtime module.
The target page must be provided explicitly; no personal filesystem path is assumed.

Figures are inlined in the page rather than linked, so every regeneration has to be
carried across by hand, and doing that by hand is how a page ends up showing a figure
whose generator has moved on. This swaps the one ``<svg>`` block inside the chosen
``<figure>`` and leaves the figcaption and everything around it alone.

``--select`` is any text that appears in exactly one figure block -- a class modifier
where that is unique, a phrase from the figcaption where it is not. The swap is refused
unless exactly one figure matches, so a renamed, moved or duplicated figure stops the
run rather than silently rewriting the wrong one.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent


def _generate(generator: str) -> str:
    with tempfile.TemporaryDirectory() as hold:
        out = pathlib.Path(hold) / "figure.svg"
        subprocess.run(
            [sys.executable, str(REPO / "tools" / f"{generator}.py"), "--out", str(out)],
            cwd=REPO,
            check=True,
        )
        return out.read_text(encoding="utf-8").strip()


def embed(svg: str, select: str, page: pathlib.Path) -> str:
    """Replace one uniquely selected inline SVG while retaining its caption and page."""
    text = page.read_text(encoding="utf-8")
    blocks = [
        (m.start(), text.index("</figure>", m.start())) for m in re.finditer(r"<figure\b", text)
    ]
    hits = [(a, b) for a, b in blocks if select in text[a:b]]
    if len(hits) != 1:
        raise SystemExit(f"  expected one figure containing {select!r}, found {len(hits)}")

    start, stop = hits[0]
    block = text[start:stop]
    opened = block.index("<svg")
    closed = block.index("</svg>") + len("</svg>")
    rebuilt = block[:opened] + svg + block[closed:]
    page.write_text(text[:start] + rebuilt + text[stop:], encoding="utf-8")
    return f"  {select!r}: {len(svg):,} characters of SVG, page {len(text):,} characters"


def main(argv=None) -> int:
    """Generate or read an SVG and embed it in the explicitly selected page."""
    parser = argparse.ArgumentParser(description="Re-embed a generated figure.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--generator", help="module under tools/, without the .py")
    source.add_argument("--svg", type=pathlib.Path, help="an already-generated SVG")
    parser.add_argument("--select", required=True, help="text unique to the target figure")
    parser.add_argument("--page", required=True, type=pathlib.Path)
    args = parser.parse_args(argv)

    svg = (
        _generate(args.generator)
        if args.generator
        else args.svg.read_text(encoding="utf-8").strip()
    )
    print(embed(svg, args.select, args.page))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
