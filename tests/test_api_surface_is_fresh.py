"""Keeps ``docs/api-surface.md`` honest.

The API surface document is the answer to "does this already exist?" — the question a
contributor must ask before writing a function, and the one their Claude Code session
asks on their behalf. A stale index is worse than no index: it says `gc_content` does not
exist, the member writes their own on a 0-1 scale, and every downstream metric shifts
without a single error being raised.

So the document is generated from the source, and this test regenerates it and compares.
It is the same idea as a lockfile: the artefact is committed for the humans and the tools
that cannot run the generator, and CI proves it still matches what generated it.

The generator itself imports nothing but the standard library, so this test passes in an
environment with no Django, no ViennaRNA and no compiled extensions.
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GENERATOR = REPO_ROOT / "tools" / "gen_api_surface.py"
SURFACE = REPO_ROOT / "docs" / "api-surface.md"

#: Printed on failure. Whoever sees this test go red must be able to copy one line.
FIX = "uv run python tools/gen_api_surface.py"


def test_generator_exists():
    assert GENERATOR.is_file(), (
        f"{GENERATOR.relative_to(REPO_ROOT).as_posix()} is missing — "
        "docs/api-surface.md has no source of truth."
    )


def test_api_surface_document_exists():
    assert SURFACE.is_file(), (
        f"docs/api-surface.md is missing. Generate it with:\n\n    {FIX}\n\n"
        "It is the index every contributor searches before writing a function."
    )


def test_api_surface_matches_the_engine():
    """``docs/api-surface.md`` must equal a fresh generation from ``src/engine/``.

    Run through a subprocess rather than by importing the generator: it is a standalone
    script under ``tools/``, which is not an installed package and is not on the test
    path. ``cwd`` is pinned to the repository root so the test behaves identically
    however pytest was invoked — the generator resolves its own paths from ``__file__``,
    but a relative ``cwd`` would still change what the traceback shows.
    """
    result = subprocess.run(
        [sys.executable, str(GENERATOR), "--check"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )

    assert result.returncode == 0, (
        "docs/api-surface.md no longer matches src/engine/.\n\n"
        "Either a public function, class, constant or signature changed without the\n"
        "index being regenerated, or the index was edited by hand. It is a generated\n"
        "file — edit the code, then regenerate. One command:\n\n"
        f"    {FIX}\n\n"
        "then commit docs/api-surface.md along with your code change.\n\n"
        "--- generator output ---\n" + (result.stdout + result.stderr).strip()
    )
