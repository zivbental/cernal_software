"""Bootstraps the main Django project so this client's tests can run a real
MockEngine server (docs/public-api.md §11.4) without a separate install.

Not shipped — dev-only. The published ``cernal`` package has no Django dependency.
"""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PACKAGE_ROOT = Path(__file__).resolve().parents[1]

for path in (_REPO_ROOT / "src", _PACKAGE_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
