"""Install byte-pinned runtime data without changing its historical interpretation.

Only the reviewed manifest is an authority for URLs and hashes. No provider discovery,
regeneration, executable installation, or screening approval takes place here.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path, PurePosixPath
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "manifest.json"


class DataInstallError(Exception):
    """A required asset cannot be installed or verified."""


def destination(root: Path, relative: str) -> Path:
    """Reject traversal and symlink escapes before any file is written."""
    part = PurePosixPath(relative)
    if not relative or "\\" in relative or part.is_absolute() or ".." in part.parts:
        raise DataInstallError(f"Unsafe asset path: {relative!r}")
    target = root.joinpath(*part.parts)
    if any(part.is_symlink() for part in (target, *target.parents)):
        raise DataInstallError(f"Symlink in asset path: {relative!r}")
    if not target.resolve().is_relative_to(root.resolve()):
        raise DataInstallError(f"Asset path escapes installation directory: {relative!r}")
    return target


def verified(path: Path, asset: dict) -> bool:
    if not path.is_file() or path.stat().st_size != asset["size"]:
        return False
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest() == asset["sha256"]


def load_manifest(path: Path, profile: str) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or profile not in data.get("profiles", {}):
        raise DataInstallError("Unsupported data manifest version or profile")
    commit = data.get("source_commit", "")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise DataInstallError("Manifest requires an immutable source commit")
    prefix = f"https://raw.githubusercontent.com/zivbental/cernal_software/{commit}/"
    assets = []
    paths = set()
    for asset in data["files"]:
        relative = asset["path"]
        destination(ROOT, relative)
        if relative in paths:
            raise DataInstallError(f"Duplicate asset path: {relative}")
        paths.add(relative)
        if (
            not re.fullmatch(r"[0-9a-f]{64}", asset.get("sha256", ""))
            or type(asset.get("size")) is not int
            or asset["size"] < 1
            or asset.get("url") != prefix + relative
        ):
            raise DataInstallError(f"Invalid asset identity: {relative}")
        if asset["group"] in data["profiles"][profile]:
            assets.append(asset)
    if not assets:
        raise DataInstallError("Empty data profile")
    return assets


def _atomic_copy(source: Path, target: Path, asset: dict) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as output:
            temporary = Path(output.name)
            with source.open("rb") as input_file:
                shutil.copyfileobj(input_file, output)
        if not verified(temporary, asset):
            raise DataInstallError(f"Cache changed while installing {asset['path']}")
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def install_asset(asset: dict, root: Path, cache: Path, *, offline: bool = False) -> str:
    target = destination(root, asset["path"])
    cached = destination(cache, asset["sha256"])
    if verified(target, asset):
        # Populate a portable, content-addressed cache even on an existing checkout.
        if not verified(cached, asset):
            _atomic_copy(target, cached, asset)
        return "verified"
    if not verified(cached, asset):
        if offline:
            raise DataInstallError(f"Missing or corrupt data/cache for {asset['path']} (offline)")
        cache.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=cache, delete=False) as output:
                temporary = Path(output.name)
                with urlopen(asset["url"], timeout=120) as response:
                    if not response.geturl().startswith("https://"):
                        raise DataInstallError("Refusing an insecure data redirect")
                    total = 0
                    while chunk := response.read(1024 * 1024):
                        total += len(chunk)
                        if total > asset["size"]:
                            raise DataInstallError(f"Oversized download: {asset['path']}")
                        output.write(chunk)
            if not verified(temporary, asset):
                raise DataInstallError(f"SHA-256/size mismatch downloading {asset['path']}")
            os.replace(temporary, cached)
        except (OSError, URLError) as exc:
            raise DataInstallError(f"Cannot download {asset['path']}: {exc}") from exc
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    _atomic_copy(cached, target, asset)
    return "installed"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="Never request the network")
    parser.add_argument(
        "--check", action="store_true", help="Verify installed files; change nothing"
    )
    parser.add_argument("--profile", choices=("runtime", "test"), default="runtime")
    parser.add_argument("--cache-dir", type=Path, default=ROOT / "var" / "data-cache")
    parser.add_argument(
        "--root", type=Path, default=ROOT, help="Install into an isolated source tree"
    )
    args = parser.parse_args(argv)
    try:
        assets = load_manifest(MANIFEST, args.profile)
        for asset in assets:
            if args.check:
                if not verified(destination(args.root, asset["path"]), asset):
                    raise DataInstallError(f"Missing or corrupt installed data: {asset['path']}")
            else:
                status = install_asset(asset, args.root, args.cache_dir, offline=args.offline)
                print(f"{status}: {asset['path']}", flush=True)
        print(f"Verified {len(assets)} assets ({sum(a['size'] for a in assets):,} bytes).")
        return 0
    except (DataInstallError, OSError, ValueError, KeyError) as exc:
        print(
            f"Data setup failed: {exc}\n"
            "See docs/data-installation.md. No replacement dataset used.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
