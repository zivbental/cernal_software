"""Put a regenerated figure back into the wiki page it is inlined in.

Run::

    uv run python tools/wiki_embed_figure.py figure_and_gate_states states

Figures are inlined in the page rather than linked, so every regeneration has to be
carried across by hand, and doing that by hand is how a page ends up showing a figure
whose generator moved on. This runs the generator and swaps the one ``<svg>`` block
inside the named ``<figure>``, leaving the figcaption and everything around it alone.

The figure is found by the modifier on its ``<figure>`` class -- ``ag-fig--states``
for ``states`` -- and the swap is refused unless exactly one matches, so a renamed or
duplicated figure stops the run instead of silently rewriting the wrong one.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys
import tempfile

PAGE = pathlib.Path(r"C:\dev\tau-israel\wiki\pages\and-gate-model.html")
REPO = pathlib.Path(__file__).resolve().parent.parent


def embed(generator: str, modifier: str, page: pathlib.Path) -> str:
    with tempfile.TemporaryDirectory() as hold:
        out = pathlib.Path(hold) / f"{modifier}.svg"
        subprocess.run(
            [sys.executable, str(REPO / "tools" / f"{generator}.py"), "--out", str(out)],
            cwd=REPO,
            check=True,
        )
        svg = out.read_text(encoding="utf-8").strip()

    text = page.read_text(encoding="utf-8")
    opens = [m.start() for m in re.finditer(rf'<figure class="[^"]*ag-fig--{modifier}\b', text)]
    if len(opens) != 1:
        raise SystemExit(f"  expected one ag-fig--{modifier} figure, found {len(opens)}")
    start, stop = opens[0], text.index("</figure>", opens[0])
    block = text[start:stop]

    svg_at = block.index("<svg")
    svg_end = block.index("</svg>") + len("</svg>")
    rebuilt = block[:svg_at] + svg + block[svg_end:]
    page.write_text(text[:start] + rebuilt + text[stop:], encoding="utf-8")
    return f"  {modifier}: {len(svg):,} characters of SVG, page {len(text):,} characters"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Re-embed a generated figure.")
    parser.add_argument("generator", help="module under tools/, without the .py")
    parser.add_argument("modifier", help="the ag-fig-- modifier on the target figure")
    parser.add_argument("--page", default=PAGE, type=pathlib.Path)
    args = parser.parse_args(argv)
    print(embed(args.generator, args.modifier, args.page))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
