"""Read-only screening inventory verification; never grants sequence release."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def main():
    from engine.common_mechanism import load_adapter

    try:
        load_adapter(os.environ["CERNAL_COMMEC_MANIFEST"])._verify_installation()
    except (KeyError, OSError, ValueError, TypeError):
        print("Screening unavailable or invalid; sequence release remains fail-closed.")
        return 1
    print("Screening inventory verified; this is not a sequence verdict or release authorization.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
