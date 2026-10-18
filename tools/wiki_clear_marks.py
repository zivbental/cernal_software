"""Clear the yellow review marks from the iGEM model page.

Run at the START of a writing pass, so that the marks left at the end of it show that
pass's work and nothing else::

    uv run python tools/wiki_clear_marks.py
    uv run python tools/wiki_clear_marks.py --count      # how many are set, change nothing

The page marks everything added or changed in the most recent pass with the CSS class
``ag-new`` (defined in ``static/and-gate-model.css`` as review scaffolding, to be removed
with it before publication). A mark that survives into the next pass is worse than no mark
at all, because it says "new" about text the reviewer has already read and approved.

The page lives in the wiki repository, which is a separate clone:
``C:\\dev\\tau-israel``. Pass ``--page`` if it is somewhere else.

The class is removed in all three forms it can take, and nothing else is touched:

    class="ag-new"          -> the attribute is dropped entirely
    class="ag-fig ag-new"   -> the token is dropped, the rest kept
    class="ag-new ag-fig"   -> the token is dropped, the rest kept
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

DEFAULT_PAGE = pathlib.Path(r"C:\dev\tau-israel\wiki\pages\and-gate-model.html")

#: Matches one class attribute and captures its token list.
CLASS_ATTR = re.compile(r'\sclass="([^"]*)"')
MARK = "ag-new"


def strip(html: str) -> tuple[str, int]:
    """Remove every ``ag-new`` token. Returns the new html and how many were removed."""
    removed = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal removed
        tokens = match.group(1).split()
        kept = [token for token in tokens if token != MARK]
        removed += len(tokens) - len(kept)
        if not kept:
            # The element had no other class; drop the attribute rather than leaving
            # `class=""` behind, which is valid but reads as an oversight.
            return ""
        return f' class="{" ".join(kept)}"'

    return CLASS_ATTR.sub(replace, html), removed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Clear the page's yellow review marks.")
    parser.add_argument("--page", type=pathlib.Path, default=DEFAULT_PAGE)
    parser.add_argument(
        "--count",
        action="store_true",
        help="report how many marks are set and change nothing",
    )
    args = parser.parse_args(argv)

    if not args.page.exists():
        print(f"no page at {args.page}", file=sys.stderr)
        return 1

    html = args.page.read_text(encoding="utf-8")
    cleared, removed = strip(html)

    if args.count:
        print(f"{args.page.name}: {removed} marks set")
        return 0

    if removed == 0:
        print(f"{args.page.name}: already clear")
        return 0

    args.page.write_text(cleared, encoding="utf-8")
    print(f"{args.page.name}: cleared {removed} marks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
