"""List, verify or recover archived prokaryotic AND research outputs.

Reads the A0 or corrected-path research manifest and immutable local Git objects.
No network, folding, scoring or application configuration is involved. Recovery
preserves binary bytes and verifies the recorded size and SHA-256 before writing.
The default destination is var/and-research-archive; existing files are never replaced.
See docs/prokaryotic-and-reproducibility.md for the runtime/research source map.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data/research-archive.json"
PATH_MANIFEST = ROOT / "data/prokaryotic-and-path-archive.json"
PREFIX = "src/engine/gates/notebooks/toehold_and/results/"
PREFIXES = (PREFIX, "docs/assets/barrier/")


def load_archive(manifest: Path = MANIFEST) -> tuple[str, list[dict]]:
    """Validate the pinned revision and AND-only paths before using the archive."""
    data = json.loads(manifest.read_text(encoding="utf-8"))
    revision = data["source_commit"]
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Archive source_commit must be a full Git commit hash")
    records = data["files"]
    seen = set()
    for record in records:
        name = record["path"]
        parts = PurePosixPath(name).parts
        if (
            not name.startswith(PREFIXES)
            or "\\" in name
            or ".." in parts
            or PurePosixPath(name).as_posix() != name
            or name in seen
        ):
            raise ValueError(f"Invalid or duplicate AND archive path: {name}")
        if not isinstance(record["size"], int) or record["size"] < 0:
            raise ValueError(f"Invalid byte count: {name}")
        if not re.fullmatch(r"[0-9a-f]{64}", record["sha256"]):
            raise ValueError(f"Invalid SHA-256: {name}")
        seen.add(name)
    return revision, records


def checked_destination(output_dir: Path, name: str) -> Path:
    """Keep the original relative path inside the requested output directory."""
    root = output_dir.resolve()
    target = (root / name).resolve()
    if not target.is_relative_to(root):
        raise ValueError(f"Destination escapes output directory: {name}")
    return target


def matches(content: bytes, record: dict) -> bool:
    """Compare binary content with both independent manifest checks."""
    return (
        len(content) == record["size"] and hashlib.sha256(content).hexdigest() == record["sha256"]
    )


def recover(record: dict, revision: str, output_dir: Path, *, repo: Path = ROOT) -> str:
    """Recover one verified Git blob, refusing to replace a different local file."""
    target = checked_destination(output_dir, record["path"])
    if target.exists():
        if matches(target.read_bytes(), record):
            return "verified existing"
        raise ValueError(f"Existing file differs; left unchanged: {target}")
    result = subprocess.run(
        ["git", "-C", str(repo), "show", f"{revision}:{record['path']}"],
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise ValueError(
            f"Git source unavailable: {revision}:{record['path']}. "
            "Use a clone containing the pinned historical commit."
        )
    if not matches(result.stdout, record):
        raise ValueError(f"Archived blob fails byte count/SHA-256: {record['path']}")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as output:
        output.write(result.stdout)
    return "recovered"


def main(argv: list[str] | None = None) -> int:
    """Run the selected archive action; report missing evidence without substitution."""
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--list", action="store_true", help="List paths and hashes (default)")
    action.add_argument("--restore", action="store_true", help="Recover exact historical bytes")
    action.add_argument(
        "--check", action="store_true", help="Verify recovered files; write nothing"
    )
    parser.add_argument(
        "--path", action="append", help="Exact manifest path; repeat to select files"
    )
    parser.add_argument("--output-dir", type=Path, default=ROOT / "var/and-research-archive")
    parser.add_argument(
        "--dataset",
        choices=("a0", "corrected-paths"),
        default="a0",
        help="Historical A0 outputs or corrected heuristic path-energy outputs",
    )
    args = parser.parse_args(argv)
    try:
        revision, records = load_archive(MANIFEST if args.dataset == "a0" else PATH_MANIFEST)
        if args.path:
            requested = set(args.path)
            unknown = requested - {r["path"] for r in records}
            if unknown:
                raise ValueError(f"Not in the AND archive: {', '.join(sorted(unknown))}")
            records = [r for r in records if r["path"] in requested]
        print(
            f"Source: {revision}; {len(records)} files; {sum(r['size'] for r in records):,} bytes"
        )
        for record in records:
            if args.restore:
                status = recover(record, revision, args.output_dir)
            elif args.check:
                target = checked_destination(args.output_dir, record["path"])
                if not target.is_file() or not matches(target.read_bytes(), record):
                    raise ValueError(f"Missing or different recovered file: {target}")
                status = "verified"
            else:
                status = f"{record['size']} bytes {record['sha256']}"
            print(f"{status}: {record['path']}")
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"AND archive: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
