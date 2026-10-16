"""Audit the accepted withholding snapshot, not unsupported historical quantities.

The missing source rows prevent numerical validation. An exact snapshot digest
ensures added claims, figures or scripts cannot bypass this gate. Restoring results
requires replacing this audit with checks derived from versioned scientific inputs.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

PAGE = Path(__file__).resolve().parents[1] / "docs/wiki/and-gate-model.html"
WITHHELD_SNAPSHOT_SHA256 = "eadea6486c75fea01d632cff110db7ff6e2af41c253d12a6f3fc74af7bb2c4e9"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--page", default=PAGE, type=Path)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    try:
        digest = hashlib.sha256(args.page.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    except OSError as error:
        print(f"Evidence snapshot unavailable: {error}")
        return 1
    if digest != WITHHELD_SNAPSHOT_SHA256:
        print("Snapshot changed: source-backed scientific review and audit update required")
        return 1
    print("Withholding snapshot verified; no scientific results validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
