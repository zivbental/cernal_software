"""Check the tracked barrier rows against the digests their README records.

The barrier run is tracked rather than regenerated, so the thing that can go wrong is
quiet: a local re-run overwrites a shard, the file still parses, every figure still
draws, and the numbers on the page no longer come from the rows in the repository. A
digest is what separates "these are the rows" from "these are some rows".

Digests are taken over the stored bytes with newlines normalised to LF, which is what
``.gitattributes`` pins these files to. Without that normalisation a Windows checkout
rewrites every newline and an undamaged file hashes wrong -- the failure the expression
catalog hit, where 3,001 CRLF made an intact file fail its own recorded digest.

Run::

    uv run python tools/barrier_checksums.py
    uv run python tools/barrier_checksums.py --write   # after a deliberate re-run

Exit status is 1 when a file has moved, is missing, or is present but unrecorded, so it
can gate a publish.
"""

from __future__ import annotations

import argparse
import hashlib
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
BARRIER = ROOT / "docs/assets/barrier"
README = BARRIER / "README.md"

#: The README's checksum table: | `name` | rows | bytes | `digest…` |
ROW = re.compile(r"^\|\s*`([^`]+)`\s*\|\s*([\d,]+)\s*\|\s*([\d,]+)\s*\|\s*`([0-9a-f]+)…?`\s*\|\s*$")


def measure(path: pathlib.Path) -> tuple[int, int, str]:
    """Rows, bytes and digest over the LF form, which is what the repository stores."""
    data = path.read_bytes().replace(b"\r\n", b"\n")
    return data.count(b"\n") - 1, len(data), hashlib.sha256(data).hexdigest()


def recorded() -> dict[str, tuple[int, int, str]]:
    out: dict[str, tuple[int, int, str]] = {}
    for line in README.read_text(encoding="utf-8").splitlines():
        match = ROW.match(line)
        if match:
            name, rows, size, digest = match.groups()
            out[name] = (int(rows.replace(",", "")), int(size.replace(",", "")), digest)
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Verify the tracked barrier rows.")
    parser.add_argument(
        "--write", action="store_true", help="rewrite the README table from what is on disk"
    )
    args = parser.parse_args(argv)

    on_disk = {p.name: measure(p) for p in sorted(BARRIER.glob("*.csv"))}

    if args.write:
        table = [
            f"| `{name}` | {rows:,} | {size:,} | `{digest[:16]}…` |"
            for name, (rows, size, digest) in on_disk.items()
        ]
        text = README.read_text(encoding="utf-8")
        start = text.index("| File | Rows | Bytes | SHA-256 |")
        head = text.index("\n", text.index("\n", start) + 1) + 1  # past header and rule
        end = text.index("\n\n", head)
        README.write_text(text[:head] + "\n".join(table) + text[end:], encoding="utf-8")
        print(f"  rewrote {len(table)} row(s) in {README.name}")
        return 0

    claimed = recorded()
    if not claimed:
        print(f"  no checksum table found in {README.name}")
        return 1

    problems = 0
    for name, (rows, size, digest) in on_disk.items():
        if name not in claimed:
            problems += 1
            print(f"  [UNRECORDED] {name}: present on disk, absent from the README")
            continue
        want_rows, want_size, want_digest = claimed[name]
        if not digest.startswith(want_digest):
            problems += 1
            print(
                f"  [MOVED] {name}: README says {want_digest}… "
                f"({want_rows:,} rows, {want_size:,} B), disk has {digest[:16]}… "
                f"({rows:,} rows, {size:,} B)"
            )
    for name in claimed.keys() - on_disk.keys():
        problems += 1
        print(f"  [MISSING] {name}: recorded in the README, not on disk")

    print()
    if problems:
        print(f"  {problems} file(s) disagree with the README. Re-run with --write only")
        print("  if the rows were deliberately regenerated, and say so in the commit.")
        return 1
    print(f"  {len(on_disk)} file(s) match the digests the README records.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
