"""Render an HTML report to PDF via headless Chromium (Playwright).

Manual browser "print to PDF" depends on dialog settings a person has to pick
every time (orientation, margins, scale) and on Chrome's imperfect handling of
CSS Grid/Flexbox fragmentation across pages. This script fixes those choices in
code instead, so the PDF a person gets is the PDF this notebook actually tested
against `@media print` (see the report's own `_CSS` cell) — reproducible, not
"whatever the last dialog said."

A separate process, not a notebook cell: Playwright's sync API cannot run
inside a kernel's already-running asyncio event loop, and shelling out to a
plain script sidesteps that instead of juggling the async API inside Jupyter.

Usage:
    python render_pdf.py <input.html> <output.pdf> [--portrait]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright


def render_pdf(html_path: Path, pdf_path: Path, *, landscape: bool = True) -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            page.goto(html_path.resolve().as_uri())
            # Chromium's PDF export always uses print styles: no separate
            # emulate_media() call needed for @media print to apply.
            page.pdf(
                path=str(pdf_path),
                format="A4",
                landscape=landscape,
                print_background=True,
                margin={"top": "14mm", "bottom": "14mm", "left": "14mm", "right": "14mm"},
            )
        finally:
            browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("html_path", type=Path)
    parser.add_argument("pdf_path", type=Path)
    parser.add_argument(
        "--portrait", action="store_true", help="Portrait instead of the landscape default."
    )
    args = parser.parse_args()

    render_pdf(args.html_path, args.pdf_path, landscape=not args.portrait)
    print(f"wrote {args.pdf_path.stat().st_size:,} bytes to {args.pdf_path}")


if __name__ == "__main__":
    main()
